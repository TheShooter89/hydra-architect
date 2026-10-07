// Hydra Architect plugin for OpenCode
// Resolves the active model profile, injects models and prompts into Hydra
// agents, and exposes tools for profile management and Jev decision support.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";
import { tool } from "@opencode-ai/plugin";

const ROLES = [
  "orchestrator",
  "explorer",
  "researcher",
  "test-scout",
  "architect",
  "implementer",
  "code-reviewer",
  "security-reviewer",
  "test-reviewer",
  "adjudicator",
  "final-verifier",
];

function findHydraRoot(directory) {
  const local = join(directory, ".opencode", "agents", "workflows", "hydra");
  if (existsSync(local)) return local;

  const global = join(homedir(), ".config", "opencode", "agents", "workflows", "hydra");
  if (existsSync(global)) return global;

  throw new Error(
    "Hydra workflow not found. Install it with ./install.sh . or ./install.sh --global"
  );
}

function hydraPath(directory, ...rest) {
  return join(findHydraRoot(directory), ...rest);
}

function loadPrompt(root, filename) {
  const path = join(root, "prompts", filename);
  if (!existsSync(path)) return undefined;
  try {
    return readFileSync(path, "utf8");
  } catch {
    return undefined;
  }
}

function runPython(directory, ...args) {
  const script = hydraPath(directory, "scripts", "resolve_profile.py");
  const result = spawnSync("python3", [script, ...args], {
    cwd: directory,
    encoding: "utf8",
    timeout: 15000,
  });
  if (result.status !== 0) {
    const err = (result.stderr || result.stdout || "resolve_profile.py failed").trim();
    throw new Error(err);
  }
  return JSON.parse(result.stdout);
}

function runJev(directory, questions) {
  const script = hydraPath(directory, "scripts", "jev.py");
  const result = spawnSync("python3", [script, "--questions", JSON.stringify(questions)], {
    cwd: directory,
    encoding: "utf8",
    timeout: 120000,
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "jev.py failed").trim());
  }
  return result.stdout;
}

function applyResolvedProfile(cfg, resolved) {
  if (!cfg.agent) cfg.agent = {};

  cfg.agent.hydra = cfg.agent.hydra || {};
  cfg.agent.hydra.model = resolved.models.orchestrator;

  for (const role of ROLES) {
    const agentName = `hydra-${role}`;
    if (cfg.agent[agentName]) {
      cfg.agent[agentName].model = resolved.models[role];
    }
  }
}

function applyPrompts(cfg, root) {
  if (!cfg.agent) cfg.agent = {};

  const main = loadPrompt(root, "orchestrator.md");
  if (main && cfg.agent.hydra) {
    cfg.agent.hydra.prompt = main;
  }

  const profileManager = loadPrompt(root, "profile-manager.md");
  if (profileManager && cfg.agent["hydra-profile"]) {
    cfg.agent["hydra-profile"].prompt = profileManager;
  }

  for (const role of ROLES) {
    const agentName = role === "orchestrator" ? "hydra" : `hydra-${role}`;
    const content = loadPrompt(root, `${role}.md`);
    if (content && cfg.agent[agentName]) {
      cfg.agent[agentName].prompt = content;
    }
  }
}

function getActiveName(directory) {
  const path = hydraPath(directory, "profiles", "active-profile.json");
  if (!existsSync(path)) return "default";
  try {
    return JSON.parse(readFileSync(path, "utf8")).profile || "default";
  } catch {
    return "default";
  }
}

function formatProfile(resolved) {
  const lines = ["Role → Model:"];
  for (const [role, model] of Object.entries(resolved.models)) {
    lines.push(`  ${role.padEnd(20)} ${model}`);
  }
  if (resolved.jev?.model) {
    lines.push(`  ${"jev".padEnd(20)} ${resolved.jev.model}`);
  }
  return lines.join("\n");
}

function formatDiff(diff) {
  const keys = Object.keys(diff.diffs || {});
  if (keys.length === 0) return "No model differences.";
  const lines = ["Changed roles:"];
  for (const role of keys) {
    const change = diff.diffs[role];
    lines.push(`  ${role}:`);
    lines.push(`    ${change.from}`);
    lines.push(`    → ${change.to}`);
  }
  return lines.join("\n");
}

export default async ({ directory }) => {
  let currentCfg = null;
  let hydraRoot = null;

  try {
    hydraRoot = findHydraRoot(directory);
  } catch {
    hydraRoot = null;
  }

  return {
    config: async (cfg) => {
      currentCfg = cfg;
      try {
        if (hydraRoot) applyPrompts(cfg, hydraRoot);
        const resolved = runPython(directory, "--active");
        applyResolvedProfile(cfg, resolved);
      } catch (e) {
        console.error("[hydra] failed to apply active profile:", e.message);
      }
    },

    tool: {
      hydra_profile: tool({
        description: "Set, show, or diff the active Hydra model profile.",
        args: {
          action: tool.schema.enum(["set", "show", "diff"]).describe("Action to perform"),
          profile: tool.schema.string().optional().describe("Profile name for set/show"),
          other: tool.schema.string().optional().describe("Second profile name for diff"),
        },
        async execute(args) {
          if (args.action === "set") {
            if (!args.profile) return "Error: profile is required for set";
            const resolved = runPython(directory, "--set", args.profile);
            if (currentCfg) applyResolvedProfile(currentCfg, resolved);
            return {
              title: "Hydra profile updated",
              output: `Active profile is now '${args.profile}'.\n\n${formatProfile(resolved)}`,
            };
          }

          if (args.action === "show") {
            const target = args.profile || getActiveName(directory);
            const resolved = runPython(directory, "--show", target);
            return {
              title: `Hydra profile: ${resolved.name}`,
              output: formatProfile(resolved),
            };
          }

          if (args.action === "diff") {
            if (!args.profile || !args.other) {
              return "Error: two profile names are required for diff";
            }
            const diff = runPython(directory, "--diff", args.profile, args.other);
            return {
              title: `Hydra profile diff: ${diff.from} → ${diff.to}`,
              output: formatDiff(diff),
            };
          }

          return `Error: unknown action '${args.action}'`;
        },
      }),

      hydra_resolve: tool({
        description: "Return the effective Hydra model profile as JSON.",
        args: {},
        async execute() {
          const resolved = runPython(directory, "--active");
          return {
            title: "Hydra active profile",
            output: JSON.stringify(resolved, null, 2),
          };
        },
      }),

      hydra_jev: tool({
        description: "Ask Jev a batch of typed questions and get structured answers.",
        args: {
          questions: tool.schema
            .record(tool.schema.string())
            .describe("JSON object mapping question names to question text"),
        },
        async execute(args) {
          const output = runJev(directory, args.questions);
          return {
            title: "Jev response",
            output,
          };
        },
      }),
    },
  };
};
