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
. "$SCRIPT_DIR/../_shared/instructions.sh"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS_FILE="$SCRIPT_DIR/../_shared/link-instructions.md"
    TARGET="$HOME/AGENTS.md"
    WIKI_PATH="$HOME/link/wiki"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS_FILE="$SCRIPT_DIR/../_shared/link-instructions-project.md"
    TARGET="AGENTS.md"
    WIKI_PATH="$(pwd)/wiki"
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

# Instructions
link_upsert_instructions "$TARGET" "$INSTRUCTIONS_FILE" "Link instructions"

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

# Auto-register MCP in ~/.codex/config.toml
CODEX_CONFIG="$HOME/.codex/config.toml"
if [ -f "$CODEX_CONFIG" ] && ! grep -q '\[mcp_servers.link\]' "$CODEX_CONFIG"; then
    cat >> "$CODEX_CONFIG" << TOML

[mcp_servers.link]
command = "python3"
args = ["-m", "link_mcp", "--wiki", "$WIKI_PATH"]
TOML
    echo "  ✓ Link MCP registered in ~/.codex/config.toml"
elif [ ! -f "$CODEX_CONFIG" ]; then
    echo "  MCP config: add to ~/.codex/config.toml:"
    echo "  [mcp_servers.link]"
    echo "  command = \"python3\""
    echo "  args = [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"]"
fi
