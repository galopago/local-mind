#!/bin/bash
# Remove Link from Cursor
set -e

MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/.cursor/rules/link.mdc"
else
    TARGET=".cursor/rules/link.mdc"
fi

if [ -f "$TARGET" ]; then
    rm "$TARGET"
    echo "Removed $TARGET"
else
    echo "No Link Cursor rule found at $TARGET"
fi
