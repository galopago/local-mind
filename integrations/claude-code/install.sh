#!/bin/bash
# Link integration for Claude Code
#
# Usage:
#   bash install.sh --global    → ~/.claude/CLAUDE.md (every project)
#   bash install.sh --project   → ./CLAUDE.md + scaffold wiki here
#   bash install.sh             → defaults to --project
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MARKER="## Link — Personal Knowledge Wiki"
INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions.md")
MODE="${1:---project}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/.claude/CLAUDE.md"
    mkdir -p "$HOME/.claude"
elif [ "$MODE" = "--project" ]; then
    TARGET="CLAUDE.md"
else
    echo "Usage: bash install.sh [--global|--project]"
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
    echo "Claude Code will include Link context in every project."
    echo ""
    echo "To scaffold a wiki in a project, cd into it and run:"
    echo "  bash $SCRIPT_DIR/install.sh --project"
elif [ "$MODE" = "--project" ]; then
    echo "Scaffolding wiki structure..."
    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    echo ""
    echo "Done. Drop sources into raw/ and tell Claude to ingest them."
fi
