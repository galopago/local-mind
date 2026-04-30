#!/bin/bash
# Link integration for Cursor
# One command: rules + wiki scaffold + MCP registration
#
# Usage:
#   bash install.sh             → global: ~/.cursor/rules/link.mdc + central wiki at ~/link/
#   bash install.sh --project   → project-local: .cursor/rules/link.mdc + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

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

# Auto-register MCP server in ~/.cursor/mcp.json
MCP_CONFIG="$HOME/.cursor/mcp.json"
if [ -f "$MCP_CONFIG" ]; then
    LINK_WIKI_PATH="$WIKI_PATH" python3 - << 'PYEOF'
import json, os
config_path = os.path.expanduser("~/.cursor/mcp.json")
wiki_path = os.environ["LINK_WIKI_PATH"]
try:
    with open(config_path) as f:
        config = json.load(f)
    config.setdefault("mcpServers", {})["link"] = {
        "command": "python3",
        "args": ["-m", "link_mcp", "--wiki", wiki_path]
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("  ✓ Link MCP registered in ~/.cursor/mcp.json")
except Exception as e:
    print(f"  · Could not auto-register MCP: {e}")
PYEOF
elif [ ! -f "$MCP_CONFIG" ]; then
    echo ""
    echo "  Add to ~/.cursor/mcp.json:"
    echo "  { \"mcpServers\": { \"link\": { \"command\": \"python3\", \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"] } } }"
fi

echo ""
echo "Done."
echo "  Drop sources into ~/link/raw/ and say 'ingest' to process them."
echo "  View wiki: python ~/link/serve.py"
