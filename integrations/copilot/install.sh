#!/bin/bash
# Link integration for GitHub Copilot
# One command: instructions + wiki scaffold + link-mcp install
#
# Usage:
#   bash install.sh             → .github/copilot-instructions.md + central wiki at ~/link/
#   bash install.sh --project   → .github/copilot-instructions.md + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

if [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    WIKI_PATH="$(pwd)/wiki"
else
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    WIKI_PATH="$HOME/link/wiki"
fi

TARGET=".github/copilot-instructions.md"
mkdir -p .github

echo "$INSTRUCTIONS" > "$TARGET"
echo "Link instructions → $TARGET"

if [ "$MODE" = "--project" ]; then
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
else
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
fi

echo ""
echo "Done."
echo "  Drop sources into raw/ and say 'ingest' to process them."
echo "  View wiki: python ~/link/serve.py"
echo ""
echo "  MCP: add to your Copilot MCP config:"
echo "  { \"mcpServers\": { \"link\": { \"command\": \"python3\", \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"] } } }"
