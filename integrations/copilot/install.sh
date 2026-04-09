#!/bin/bash
# Link integration for GitHub Copilot
#
# Usage:
#   bash install.sh --project   → .github/copilot-instructions.md + scaffold wiki
#   bash install.sh             → defaults to --project
#
# Note: Copilot doesn't have a global instructions file — project-level only.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MARKER="## Link — Personal Knowledge Wiki"
INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
TARGET=".github/copilot-instructions.md"
mkdir -p .github

if [ -f "$TARGET" ] && grep -q "$MARKER" "$TARGET"; then
    echo "Link already configured in $TARGET"
else
    if [ -f "$TARGET" ]; then
        printf "\n\n%s" "$INSTRUCTIONS" >> "$TARGET"
        echo "Link section appended to $TARGET"
    else
        echo "$INSTRUCTIONS" > "$TARGET"
        echo "Link installed → $TARGET"
    fi
fi

echo "Scaffolding wiki structure..."
bash "$SCRIPT_DIR/../_shared/scaffold.sh"
echo ""
echo "Done. Drop sources into raw/ and tell Copilot to ingest them."
