#!/bin/bash
# Link integration for Kiro
#
# Usage:
#   bash install.sh             → global: ~/.kiro/steering + central wiki at ~/link/
#   bash install.sh --project   → project-local: .kiro/steering + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/.kiro/steering/link.md"
    mkdir -p "$HOME/.kiro/steering"

    if [ -f "$TARGET" ]; then
        echo "Link already configured in $TARGET"
    else
        echo "$INSTRUCTIONS" > "$TARGET"
        echo "Link installed globally → $TARGET"
    fi

    # Install auto-ingest hook
    HOOK_DIR="$HOME/.kiro/hooks"
    HOOK_FILE="$HOOK_DIR/link-auto-ingest.json"
    mkdir -p "$HOOK_DIR"
    if [ ! -f "$HOOK_FILE" ]; then
        cp "$SCRIPT_DIR/hooks/auto-ingest.json" "$HOOK_FILE"
        echo "Auto-ingest hook installed → $HOOK_FILE"
    else
        echo "Auto-ingest hook already installed"
    fi

    echo "Scaffolding central wiki at ~/link/..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    echo ""
    echo "Done. Kiro will know about Link in every project."
    echo "Drop sources into ~/link/raw/ and tell Kiro to ingest them."
    echo ""
    echo "Auto-ingest hook: fires when new files appear in raw/"
    echo "  (works when ~/link/ is open as workspace or part of a multi-root workspace)"
    echo "View wiki: python ~/link/serve.py"

elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET=".kiro/steering/link.md"
    mkdir -p .kiro/steering

    if [ -f "$TARGET" ]; then
        echo "Link already configured in $TARGET"
    else
        echo "$INSTRUCTIONS" > "$TARGET"
        echo "Link installed → $TARGET"
    fi

    echo "Scaffolding project wiki..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
    echo ""
    echo "Done. Drop sources into raw/ and tell Kiro to ingest them."
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi
