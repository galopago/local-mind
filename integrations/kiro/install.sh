#!/bin/bash
# Link integration for Kiro
#
# Usage:
#   bash install.sh --global    → ~/.kiro/steering/link.md (every project)
#   bash install.sh --project   → .kiro/steering/link.md + scaffold wiki here
#   bash install.sh             → defaults to --project
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
MODE="${1:---project}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/.kiro/steering/link.md"
    mkdir -p "$HOME/.kiro/steering"

    if [ -f "$TARGET" ]; then
        echo "Link already configured globally in $TARGET"
        exit 0
    fi

    echo "$INSTRUCTIONS" > "$TARGET"
    echo "Link installed globally → $TARGET"
    echo "Kiro will include Link context in every project."
    echo ""
    echo "To scaffold a wiki in a project, cd into it and run:"
    echo "  bash $SCRIPT_DIR/install.sh --project"

elif [ "$MODE" = "--project" ]; then
    TARGET=".kiro/steering/link.md"
    mkdir -p .kiro/steering

    if [ -f "$TARGET" ]; then
        echo "Link already configured in $TARGET"
    else
        echo "$INSTRUCTIONS" > "$TARGET"
        echo "Link installed → $TARGET"
    fi

    # Scaffold wiki structure
    echo "Scaffolding wiki structure..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    echo ""
    echo "Done. Drop sources into raw/ and tell Kiro to ingest them."
else
    echo "Usage: bash install.sh [--global|--project]"
    exit 1
fi
