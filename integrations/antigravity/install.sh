#!/bin/bash
# Link integration for Google Antigravity
#
# Usage:
#   bash install.sh             → global: ~/.gemini/GEMINI.md + central wiki at ~/link/
#   bash install.sh --project   → project-local: ./GEMINI.md + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MARKER="## Link — Personal Knowledge Wiki"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/.gemini/GEMINI.md"
    mkdir -p "$HOME/.gemini"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET="GEMINI.md"
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

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

if [ "$MODE" = "--global" ]; then
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
else
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
fi
echo "Done. Drop sources into raw/ and say 'ingest' to process them."
