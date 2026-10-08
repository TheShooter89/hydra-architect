# Hydra workflow

This folder contains the Hydra multi-agent coding swarm.

## Layout

- `profiles/` — model profiles (`default`, `cheap`, `free`, `max-quality`, `free-week`).
  - `active-profile.json` stores the currently selected profile name.
- `prompts/` — orchestration and subagent prompts.
- `scripts/` — Python helpers:
  - `resolve_profile.py` resolves profile inheritance, validates policy, and produces the effective role→model mapping.
  - `jev.py` calls OpenCode Zen System One, resolves the model from the active profile, and reuses the saved OpenCode Zen credential when no token override is set.
- `.env` (ignored, optional) — Jev endpoint/token/model overrides. Normally no Jev-specific setup is needed if OpenCode Zen is connected.

## Adding a new workflow

1. Create a new folder under `.opencode/agents/workflows/<name>/`.
2. Add a primary agent stub at `.opencode/agents/<name>.md`.
3. Add commands at `.opencode/commands/<name>.md` (optional).

## Restart requirement

Opencode loads agents, commands, plugins, and config once at startup. After changing any file under `.opencode/`, restart opencode for the changes to take effect.
