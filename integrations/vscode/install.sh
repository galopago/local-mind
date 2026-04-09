#!/bin/bash
# Link integration for VS Code (Copilot Chat)
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
else
    INSTRUCTIONS="This project uses Link, an LLM-maintained knowledge wiki at ~/link/. Read ~/link/LINK.md for the full schema. When the user says ingest/query/lint, follow the Link protocol. Wiki is at ~/link/wiki/, raw sources at ~/link/raw/."
fi

if [ -f "$TARGET" ]; then
    if grep -q "Link, an LLM-maintained knowledge wiki\|Link wiki" "$TARGET"; then
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

if [ "$MODE" = "--project" ]; then
    echo "Scaffolding project wiki..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
else
    echo "Scaffolding central wiki at ~/link/..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
fi
echo ""
echo "Done. Drop sources and tell your agent to ingest them."
