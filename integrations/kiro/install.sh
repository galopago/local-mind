#!/bin/bash
# Link integration for Kiro
#
# Fresh install: sets up steering + scaffolds wiki at ~/link/
# Update (re-run after git pull): updates steering + code files, never touches wiki data
#
# Usage:
#   bash install.sh             → global: ~/.kiro/steering + central wiki at ~/link/
#   bash install.sh --project   → project-local: .kiro/steering + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/.kiro/steering/link.md"
    mkdir -p "$HOME/.kiro/steering"

    # Always update steering — it may have changed
    echo "$INSTRUCTIONS" > "$TARGET"
    echo "Link steering → $TARGET"

    bash "$SCRIPT_DIR/../_shared/scaffold.sh"

    # Auto-register Link MCP server in Kiro's mcp.json
    MCP_CONFIG="$HOME/.kiro/settings/mcp.json"
    MCP_SERVER="$HOME/link/mcp_server.py"
    if [ -f "$MCP_CONFIG" ] && [ -f "$MCP_SERVER" ]; then
        if ! grep -q '"link"' "$MCP_CONFIG"; then
            python3 - << PYEOF
import json
config_path = "$MCP_CONFIG"
server_path = "$MCP_SERVER"
try:
    with open(config_path) as f:
        config = json.load(f)
    config.setdefault("mcpServers", {})["link"] = {
        "command": "python3",
        "args": [server_path],
        "disabled": False
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("  ✓ Link MCP server registered in ~/.kiro/settings/mcp.json")
except Exception as e:
    print(f"  · Could not auto-register MCP: {e}")
    print(f"    Add manually: python3 {server_path}")
PYEOF
        else
            echo "  · Link MCP already registered in ~/.kiro/settings/mcp.json"
        fi
    fi

    echo ""
    echo "Done."
    echo "  Drop sources into ~/link/raw/ and say 'ingest' to process them."
    echo "  View wiki: python ~/link/serve.py"

elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET=".kiro/steering/link.md"
    mkdir -p .kiro/steering

    echo "$INSTRUCTIONS" > "$TARGET"
    echo "Link steering → $TARGET"

    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
    echo ""
    echo "Done. Drop sources into raw/ and say 'ingest' to process them."
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi
