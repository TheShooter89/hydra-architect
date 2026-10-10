#!/bin/bash
set -euo pipefail

HYDRA_NAME="Hydra Architect"

FORCE=0
MODE="project"
TARGET=""

usage() {
  cat <<EOF
Remove ${HYDRA_NAME} from an OpenCode config directory.

Usage:
  $0                          uninstall from ./.opencode/
  $0 .                        uninstall from ./.opencode/
  $0 --global                 uninstall from ~/.config/opencode/
  $0 --target /some/path      uninstall from /some/path/.opencode/
  $0 --force ...              skip confirmation

Examples:
  $0 .
  $0 --global
  $0 --target /home/user/work/project
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)
      MODE="global"
      shift
      ;;
    --target)
      if [[ -z "${2:-}" ]]; then usage; fi
      MODE="target"
      TARGET="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    .)
      MODE="project"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

case "$MODE" in
  global)
    BASE="$HOME/.config/opencode"
    ;;
  target)
    if [[ -z "$TARGET" ]]; then usage; fi
    BASE="$TARGET/.opencode"
    ;;
  project)
    BASE="$PWD/.opencode"
    ;;
esac

if [[ "$FORCE" -eq 0 ]]; then
  read -rp "Remove ${HYDRA_NAME} from ${BASE}? [y/N] " answer
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# Remove Hydra-specific files.
rm -f "$BASE/agents/hydra.md"
rm -f "$BASE/agents/hydra-profile.md"
rm -f "$BASE/agents/hydra-"*.md
rm -f "$BASE/commands/hydra.md"
rm -f "$BASE/commands/hydra-profile.md"
rm -f "$BASE/plugins/hydra.js"
rm -rf "$BASE/agents/workflows/hydra"
rm -rf "$BASE/skills/hydra"

# Unregister the plugin from opencode.json.
OPENCODE_JSON="$BASE/opencode.json"
if [[ -f "$OPENCODE_JSON" ]]; then
  node -e '
const fs = require("fs");
const path = process.argv[1];
const cfg = JSON.parse(fs.readFileSync(path, "utf8"));
cfg.plugin = (cfg.plugin || []).filter(p => p !== ".opencode/plugins/hydra.js");
fs.writeFileSync(path, JSON.stringify(cfg, null, 2) + "\n");
' "$OPENCODE_JSON"
fi

# Unregister the Hydra skill path from opencode.json.
if [[ -f "$OPENCODE_JSON" ]]; then
  node -e '
const fs = require("fs");
const path = process.argv[1];
const mode = process.argv[2];
const cfg = JSON.parse(fs.readFileSync(path, "utf8"));
if (cfg.skills && Array.isArray(cfg.skills.paths)) {
  const skillPath = mode === "global" ? "~/.config/opencode/skills" : ".opencode/skills";
  cfg.skills.paths = cfg.skills.paths.filter(p => p !== skillPath);
  if (cfg.skills.paths.length === 0 && Object.keys(cfg.skills).length === 1) {
    delete cfg.skills;
  }
}
fs.writeFileSync(path, JSON.stringify(cfg, null, 2) + "\n");
' "$OPENCODE_JSON" "$MODE"
fi

echo "${HYDRA_NAME} removed from ${BASE}"
echo "Restart OpenCode for the change to take effect."
