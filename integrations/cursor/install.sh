#!/bin/bash
# Link integration for Cursor
# One command: rules + wiki scaffold + MCP registration
#
# Usage:
#   bash install.sh             → global: ~/.cursor/rules/link.mdc + ~/link/ + ~/.cursor/mcp.json
#   bash install.sh --project   → project: .cursor/rules/link.mdc + wiki here + .cursor/mcp.json only
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"
. "$SCRIPT_DIR/../_shared/instructions.sh"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/.cursor/rules/link.mdc"
    mkdir -p "$HOME/.cursor/rules"
    WIKI_PATH="$HOME/link/wiki"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET=".cursor/rules/link.mdc"
    mkdir -p .cursor/rules
    WIKI_PATH="$(pwd)/wiki"
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

# Cursor rule with alwaysApply
cat > "$TARGET" << 'FRONTMATTER'
---
description: Link knowledge wiki context
alwaysApply: true
---

FRONTMATTER
echo "$INSTRUCTIONS" >> "$TARGET"
echo "Link rule → $TARGET"

# Wiki scaffold + link-mcp install
if [ "$MODE" = "--global" ]; then
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
else
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
fi

MCP_PYTHON="python3"
WIKI_ROOT="${WIKI_PATH%/wiki}"
MCP_MARKER="$WIKI_ROOT/.link-mcp-python"
if [ -f "$MCP_MARKER" ]; then
    MCP_PYTHON="$(cat "$MCP_MARKER")"
fi

# Absolute wiki path for MCP (Cursor may start the server with a different cwd)
if [ -d "$WIKI_ROOT" ]; then
    WIKI_PATH="$(cd "$WIKI_ROOT" && pwd)/wiki"
else
    WIKI_PATH="$(pwd)/wiki"
fi

if [ "$MODE" = "--global" ]; then
    MCP_CONFIG="$HOME/.cursor/mcp.json"
    mkdir -p "$HOME/.cursor"
    REMOVE_GLOBAL_LINK="false"
    MCP_CONFIG_LABEL="~/.cursor/mcp.json"
else
    MCP_CONFIG="$(pwd)/.cursor/mcp.json"
    mkdir -p "$(dirname "$MCP_CONFIG")"
    REMOVE_GLOBAL_LINK="true"
    MCP_CONFIG_LABEL=".cursor/mcp.json"
fi

LINK_WIKI_PATH="$WIKI_PATH" \
LINK_MCP_PYTHON="$MCP_PYTHON" \
LINK_MCP_CONFIG="$MCP_CONFIG" \
LINK_REMOVE_GLOBAL_LINK="$REMOVE_GLOBAL_LINK" \
LINK_MCP_CONFIG_LABEL="$MCP_CONFIG_LABEL" \
python3 - << 'PYEOF'
import json
import os
from pathlib import Path

wiki_path = os.environ["LINK_WIKI_PATH"]
mcp_python = os.environ["LINK_MCP_PYTHON"]
config_path = Path(os.environ["LINK_MCP_CONFIG"]).expanduser()
remove_global = os.environ.get("LINK_REMOVE_GLOBAL_LINK", "false").lower() == "true"
label = os.environ.get("LINK_MCP_CONFIG_LABEL", str(config_path))

link_server = {
    "command": mcp_python,
    "args": ["-m", "link_mcp", "--wiki", wiki_path],
}

def load_config(path: Path) -> dict:
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    return {"mcpServers": {}}


def save_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


try:
    config = load_config(config_path)
    config.setdefault("mcpServers", {})["link"] = link_server
    save_config(config_path, config)
    print(f"  ✓ Link MCP registered in {label}")

    if remove_global:
        global_path = Path.home() / ".cursor" / "mcp.json"
        if global_path.is_file():
            global_config = load_config(global_path)
            servers = global_config.get("mcpServers", {})
            if "link" in servers:
                del servers["link"]
                save_config(global_path, global_config)
                print("  ✓ Removed Link MCP from ~/.cursor/mcp.json (project-local only)")
except Exception as exc:
    print(f"  · Could not auto-register MCP: {exc}")
PYEOF

if [ ! -f "$MCP_CONFIG" ]; then
    echo ""
    echo "  Add to $MCP_CONFIG_LABEL:"
    echo "  { \"mcpServers\": { \"link\": { \"command\": \"$MCP_PYTHON\", \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"] } } }"
fi

link_print_next_steps "$MODE"
