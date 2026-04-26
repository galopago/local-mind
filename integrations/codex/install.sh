#!/bin/bash
# Link integration for Codex
#
# Usage:
#   bash install.sh             → global: ~/AGENTS.md + central wiki at ~/link/
#   bash install.sh --project   → project-local: ./AGENTS.md + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MARKER="## Link — Personal Knowledge Wiki"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/AGENTS.md"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET="AGENTS.md"
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

if [ -f "$TARGET" ] && grep -q "$MARKER" "$TARGET"; then
    echo "Link already configured in $TARGET"
else
    # Always update steering (idempotent)
    if false; then
        printf "\n\n%s" "$INSTRUCTIONS" >> "$TARGET"
        echo "Link section appended to $TARGET"
    else
        echo "$INSTRUCTIONS" > "$TARGET"
        echo "Link installed → $TARGET"
    fi
fi

if [ "$MODE" = "--global" ]; then
    echo "Scaffolding central wiki at ~/link/..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    echo ""
    echo "Done. Codex will know about Link in every project."
    echo "Drop sources into ~/link/raw/ and tell Codex to ingest them."
else
    echo "Scaffolding project wiki..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
    echo ""
    echo "Done. Drop sources into raw/ and tell Codex to ingest them."
fi
