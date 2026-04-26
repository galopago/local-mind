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

# Always update steering (idempotent)
    if false; then
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
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
else
    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
fi
echo "Done. Drop sources into raw/ and say 'ingest' to process them."
