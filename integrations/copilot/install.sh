#!/bin/bash
# Link integration for GitHub Copilot
#
# Usage:
#   bash install.sh             → .github/copilot-instructions.md + central wiki at ~/link/
#   bash install.sh --project   → .github/copilot-instructions.md + wiki in current dir
#
# Note: Copilot instructions are always project-level. The wiki location differs.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MARKER="## Link — Personal Knowledge Wiki"
MODE="${1:---global}"

if [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
else
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
fi

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

if [ "$MODE" = "--project" ]; then
    echo "Scaffolding project wiki..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
else
    echo "Scaffolding central wiki at ~/link/..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
fi
echo ""
echo "Done. Drop sources and tell Copilot to ingest them."
