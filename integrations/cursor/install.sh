#!/bin/bash
# Link integration for Cursor
#
# Usage:
#   bash install.sh             → global: ~/.cursor/rules/link.mdc + central wiki at ~/link/
#   bash install.sh --project   → project-local: .cursor/rules/link.mdc + wiki in current dir
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
    TARGET="$HOME/.cursor/rules/link.mdc"
    mkdir -p "$HOME/.cursor/rules"
elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET=".cursor/rules/link.mdc"
    mkdir -p .cursor/rules
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi

if [ -f "$TARGET" ]; then
    echo "Link already configured in $TARGET"
else
    cat > "$TARGET" << 'FRONTMATTER'
---
description: Link knowledge wiki context
alwaysApply: true
---

FRONTMATTER
    echo "$INSTRUCTIONS" >> "$TARGET"
    echo "Link installed → $TARGET"
fi

if [ "$MODE" = "--global" ]; then
    echo "Scaffolding central wiki at ~/link/..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"

    # Install check-raw hook
    HOOK_DIR="$HOME/.cursor/hooks"
    HOOK_FILE="$HOOK_DIR/link-check-raw.json"
    mkdir -p "$HOOK_DIR"
    if [ ! -f "$HOOK_FILE" ]; then
        cp "$SCRIPT_DIR/hooks/check-raw.json" "$HOOK_FILE"
        echo "Check-raw hook installed → $HOOK_FILE"
    fi

    echo ""
    echo "Done. Cursor will know about Link in every project."
    echo "Drop sources into ~/link/raw/ and tell Cursor to ingest them."
else
    echo "Scaffolding project wiki..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project

    # Install check-raw hook locally
    HOOK_DIR=".cursor/hooks"
    HOOK_FILE="$HOOK_DIR/link-check-raw.json"
    mkdir -p "$HOOK_DIR"
    if [ ! -f "$HOOK_FILE" ]; then
        cp "$SCRIPT_DIR/hooks/check-raw.json" "$HOOK_FILE"
        echo "Check-raw hook installed → $HOOK_FILE"
    fi

    echo ""
    echo "Done. Drop sources into raw/ and tell Cursor to ingest them."
fi
