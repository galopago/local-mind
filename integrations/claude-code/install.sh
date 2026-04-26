#!/bin/bash
# Link integration for Claude Code
# One command: steering + wiki scaffold + MCP registration
#
# Usage:
#   bash install.sh             → global: ~/.claude/CLAUDE.md + central wiki at ~/link/
#   bash install.sh --project   → project-local: ./CLAUDE.md + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/.claude/CLAUDE.md"
    mkdir -p "$HOME/.claude"
    WIKI_PATH="$HOME/link/wiki"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET="CLAUDE.md"
    WIKI_PATH="$(pwd)/wiki"
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

# Steering
echo "$INSTRUCTIONS" > "$TARGET"
echo "Link steering → $TARGET"

# Wiki scaffold + link-mcp install
if [ "$MODE" = "--global" ]; then
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
else
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
fi

# Auto-register MCP server in Claude Code's config
# Claude Code uses ~/.claude.json for global MCP config
MCP_CONFIG="$HOME/.claude.json"
if [ -f "$MCP_CONFIG" ]; then
    if ! python3 -c "import json; d=json.load(open('$HOME/.claude.json')); exit(0 if 'link' in d.get('mcpServers',{}) else 1)" 2>/dev/null; then
        python3 - << 'PYEOF'
import json, os
config_path = os.path.expanduser("~/.claude.json")
wiki_path = os.path.expanduser("~/link/wiki")
try:
    with open(config_path) as f:
        config = json.load(f)
    config.setdefault("mcpServers", {})["link"] = {
        "command": "python3",
        "args": ["-m", "link_mcp", "--wiki", wiki_path]
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("  ✓ Link MCP registered in ~/.claude.json")
except Exception as e:
    print(f"  · Could not auto-register MCP: {e}")
PYEOF
    else
        echo "  · Link MCP already registered in ~/.claude.json"
    fi
else
    echo ""
    echo "  MCP config: add to ~/.claude.json or .mcp.json at project root:"
    echo "  { \"mcpServers\": { \"link\": { \"command\": \"python3\", \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"] } } }"
fi

echo ""
echo "Done."
echo "  Drop sources into ~/link/raw/ and say 'ingest' to process them."
echo "  View wiki: python ~/link/serve.py"
