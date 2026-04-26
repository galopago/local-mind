#!/bin/bash
# Link integration for Codex / OpenCode
# One command: AGENTS.md + wiki scaffold + link-mcp install
#
# Usage:
#   bash install.sh             → global: ~/AGENTS.md + central wiki at ~/link/
#   bash install.sh --project   → project-local: ./AGENTS.md + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/AGENTS.md"
    WIKI_PATH="$HOME/link/wiki"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET="AGENTS.md"
    WIKI_PATH="$(pwd)/wiki"
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

# Instructions
echo "$INSTRUCTIONS" > "$TARGET"
echo "Link instructions → $TARGET"

# Wiki scaffold + link-mcp install
if [ "$MODE" = "--global" ]; then
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
else
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
fi

echo ""
echo "Done."
echo "  Drop sources into ~/link/raw/ and say 'ingest' to process them."
echo "  View wiki: python ~/link/serve.py"
echo ""
echo "  MCP (if your Codex client supports it):"
echo "  { \"mcpServers\": { \"link\": { \"command\": \"python3\", \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"] } } }"
