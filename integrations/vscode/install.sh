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

# Write instructions to a temp file to avoid shell variable interpolation
# inside python3 -c strings (which breaks on quotes and special characters)
TMPFILE=$(mktemp /tmp/link-instructions.XXXXXX)
printf '%s' "$INSTRUCTIONS" > "$TMPFILE"

# Always update steering (idempotent)
    if false; then
    if grep -q "Link, an LLM-maintained knowledge wiki\|Link wiki" "$TARGET"; then
        echo "Link already configured in $TARGET"
    else
        python3 - "$TARGET" "$TMPFILE" << 'PYEOF'
import json, sys
target, tmpfile = sys.argv[1], sys.argv[2]
instructions_text = open(tmpfile).read()
settings = json.load(open(target))
instructions = settings.get('github.copilot.chat.codeGeneration.instructions', [])
instructions.append({'text': instructions_text})
settings['github.copilot.chat.codeGeneration.instructions'] = instructions
json.dump(settings, open(target, 'w'), indent=2)
print(f'Link instructions added to {target}')
PYEOF
    fi
else
    python3 - "$TARGET" "$TMPFILE" << 'PYEOF'
import json, sys
target, tmpfile = sys.argv[1], sys.argv[2]
instructions_text = open(tmpfile).read()
settings = {'github.copilot.chat.codeGeneration.instructions': [{'text': instructions_text}]}
json.dump(settings, open(target, 'w'), indent=2)
print(f'Link installed → {target}')
PYEOF
fi

rm -f "$TMPFILE"

if [ "$MODE" = "--project" ]; then
    echo "Scaffolding project wiki..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
else
    echo "Scaffolding central wiki at ~/link/..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
fi
echo ""
echo "Done. Drop sources and tell your agent to ingest them."
