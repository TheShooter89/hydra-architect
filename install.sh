#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HYDRA_NAME="Hydra Architect"

# Local convention: this repo keeps a _RESOURCES symlink next to a sibling
# resources folder. That layout belongs to one machine, not to every clone, so
# the symlink is only maintained when the resources folder is already there or
# when this is the canonical checkout. Otherwise the installer stays out of the
# way instead of creating a foreign absolute path.
RESOURCES_DIR="/home/tanque/projects/stable/resources/hydra-architect"
CANONICAL_REPO="/home/tanque/projects/stable/code/hydra-architect"

FORCE=0
MODE="project"
TARGET=""

usage() {
  cat <<EOF
Install ${HYDRA_NAME} into an OpenCode config directory.

Usage:
  $0                          install into ./.opencode/
  $0 .                        install into ./.opencode/
  $0 --global                 install into ~/.config/opencode/
  $0 --target /some/path      install into /some/path/.opencode/
  $0 --force ...              overwrite existing files without asking

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

# Maintain the _RESOURCES symlink only when it belongs here.
if [[ ! -L "$SCRIPT_DIR/_RESOURCES" ]]; then
  if [[ -d "$RESOURCES_DIR" || "$SCRIPT_DIR" == "$CANONICAL_REPO" ]]; then
    mkdir -p "$RESOURCES_DIR"
    ln -s "$RESOURCES_DIR" "$SCRIPT_DIR/_RESOURCES"
    echo "Linked _RESOURCES -> ${RESOURCES_DIR}"
  fi
fi

hydra_files_exist() {
  [[ -d "$BASE/agents/workflows/hydra" ]] || [[ -f "$BASE/plugins/hydra.js" ]]
}

if hydra_files_exist && [[ "$FORCE" -eq 0 ]]; then
  read -rp "Hydra files already exist in ${BASE}. Overwrite? [y/N] " answer
  if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

mkdir -p "$BASE/agents" "$BASE/commands" "$BASE/plugins" "$BASE/agents/workflows"

# Copy Hydra workflow files.
cp -R "$SCRIPT_DIR/hydra/agents/"* "$BASE/agents/"
cp -R "$SCRIPT_DIR/hydra/commands/"* "$BASE/commands/"
cp "$SCRIPT_DIR/hydra/plugins/hydra.js" "$BASE/plugins/"
rm -rf "$BASE/agents/workflows/hydra"
cp -R "$SCRIPT_DIR/hydra/workflows/hydra" "$BASE/agents/workflows/"

# Install the plugin's npm dependency inside the OpenCode config directory,
# keeping it self-contained and away from the target project's package.json.
if [[ ! -f "$BASE/package.json" ]]; then
  printf '{"name":"hydra-architect-local","version":"1.0.0","private":true,"type":"module"}\n' > "$BASE/package.json"
fi
npm install @opencode-ai/plugin --prefix "$BASE"

# Make sure npm artifacts stay out of git if the OpenCode dir is tracked.
GITIGNORE="$BASE/.gitignore"
if [[ ! -f "$GITIGNORE" ]]; then
  touch "$GITIGNORE"
fi
for pattern in node_modules/ package.json package-lock.json npm-debug.log*; do
  if ! grep -qxF "$pattern" "$GITIGNORE" 2>/dev/null; then
    echo "$pattern" >> "$GITIGNORE"
  fi
done

# Register the plugin in opencode.json.
OPENCODE_JSON="$BASE/opencode.json"
if [[ ! -f "$OPENCODE_JSON" ]]; then
  cat > "$OPENCODE_JSON" <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": []
}
JSON
fi

node -e '
const fs = require("fs");
const path = process.argv[1];
const cfg = JSON.parse(fs.readFileSync(path, "utf8"));
cfg.plugin = cfg.plugin || [];
const entry = ".opencode/plugins/hydra.js";
if (!cfg.plugin.includes(entry)) cfg.plugin.push(entry);
fs.writeFileSync(path, JSON.stringify(cfg, null, 2) + "\n");
' "$OPENCODE_JSON"

cat <<EOF

${HYDRA_NAME} installed to ${BASE}

Next steps:
  1. Replace placeholder model IDs in ${BASE}/agents/workflows/hydra/profiles/
  2. Copy ${BASE}/agents/workflows/hydra/.env.example to .env and fill JEV_ENDPOINT / JEV_API_TOKEN
  3. Restart OpenCode for agents, commands, and the plugin to load

Useful commands:
  /hydra <task>
  /hydra-profile show
  /hydra-profile default | cheap | free | max-quality | free-week

EOF
