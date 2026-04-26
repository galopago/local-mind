#!/bin/bash
# Link integration for VS Code (Copilot Chat)
# One command: settings.json + wiki scaffold + link-mcp install
#
# Usage:
#   bash install.sh             → .vscode/settings.json + central wiki at ~/link/
#   bash install.sh --project   → .vscode/settings.json + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"
TARGET=".vscode/settings.json"
mkdir -p .vscode

if [ "$MODE" = "--project" ]; then
    INSTRUCTIONS="This project has its own Link wiki. Read LINK.md for the full schema. When the user says ingest/query/lint, follow the Link protocol. Never modify raw/. The wiki is in wiki/."
    WIKI_PATH="$(pwd)/wiki"
else
    INSTRUCTIONS="This project uses Link, an LLM-maintained knowledge wiki at ~/link/. Read ~/link/LINK.md for the full schema. When the user says ingest/query/lint, follow the Link protocol. Wiki is at ~/link/wiki/, raw sources at ~/link/raw/."
    WIKI_PATH="$HOME/link/wiki"
fi

# Write to .vscode/settings.json
python3 - << PYEOF
import json, os
target = "$TARGET"
instructions_text = """$INSTRUCTIONS"""
settings = {}
if os.path.exists(target):
    try:
        with open(target) as f:
            settings = json.load(f)
    except Exception:
        pass
settings['github.copilot.chat.codeGeneration.instructions'] = [{'text': instructions_text}]
with open(target, 'w') as f:
    json.dump(settings, f, indent=2)
print(f"Link instructions → {target}")
PYEOF

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
echo "  MCP: add to .vscode/mcp.json:"
echo "  { \"servers\": { \"link\": { \"type\": \"stdio\", \"command\": \"python3\", \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$WIKI_PATH\"] } } }"
