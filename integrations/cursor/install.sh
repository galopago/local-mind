#!/bin/bash
# Link integration for Cursor
#
# Usage:
#   bash install.sh --global    → ~/.cursor/rules/link.mdc (every project)
#   bash install.sh --project   → .cursor/rules/link.mdc + scaffold wiki here
#   bash install.sh             → defaults to --project
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
MODE="${1:---project}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/.cursor/rules/link.mdc"
    mkdir -p "$HOME/.cursor/rules"
elif [ "$MODE" = "--project" ]; then
    TARGET=".cursor/rules/link.mdc"
    mkdir -p .cursor/rules
else
    echo "Usage: bash install.sh [--global|--project]"
    exit 1
fi

if [ -f "$TARGET" ]; then
    echo "Link already configured in $TARGET"
    [ "$MODE" = "--project" ] && bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    exit 0
fi

cat > "$TARGET" << 'FRONTMATTER'
---
description: Link knowledge wiki context
alwaysApply: true
---

FRONTMATTER

echo "$INSTRUCTIONS" >> "$TARGET"
echo "Link installed → $TARGET"

if [ "$MODE" = "--global" ]; then
    echo "Cursor will include Link context in every project."
    echo ""
    echo "To scaffold a wiki in a project, cd into it and run:"
    echo "  bash $SCRIPT_DIR/install.sh --project"
elif [ "$MODE" = "--project" ]; then
    echo "Scaffolding wiki structure..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    echo ""
    echo "Done. Drop sources into raw/ and tell Cursor to ingest them."
fi
