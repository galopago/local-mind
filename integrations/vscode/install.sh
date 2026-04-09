#!/bin/bash
# Link integration for VS Code (Copilot Chat)
#
# Usage:
#   bash install.sh --project   → .vscode/settings.json + scaffold wiki
#   bash install.sh             → defaults to --project
#
# Note: VS Code settings are project-level only.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET=".vscode/settings.json"
mkdir -p .vscode

INSTRUCTIONS="This project uses Link, an LLM-maintained knowledge wiki. Read LINK.md for the full schema. When the user says ingest/query/lint, follow the Link protocol. Never modify raw/. The wiki is in wiki/."

if [ -f "$TARGET" ]; then
    if grep -q "Link, an LLM-maintained knowledge wiki" "$TARGET"; then
        echo "Link already configured in $TARGET"
    else
        python3 -c "
import json
settings = json.load(open('$TARGET'))
instructions = settings.get('github.copilot.chat.codeGeneration.instructions', [])
instructions.append({'text': '''$INSTRUCTIONS'''})
settings['github.copilot.chat.codeGeneration.instructions'] = instructions
json.dump(settings, open('$TARGET', 'w'), indent=2)
print('Link instructions added to $TARGET')
"
    fi
else
    python3 -c "
import json
settings = {'github.copilot.chat.codeGeneration.instructions': [{'text': '''$INSTRUCTIONS'''}]}
json.dump(settings, open('$TARGET', 'w'), indent=2)
print('Link installed → $TARGET')
"
fi

echo "Scaffolding wiki structure..."
bash "$SCRIPT_DIR/../_shared/scaffold.sh"
echo ""
echo "Done. Drop sources into raw/ and tell your agent to ingest them."
