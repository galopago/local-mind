#!/bin/bash
# Link integration for Kiro
#
# Fresh install: sets up steering + scaffolds wiki at ~/link/
# Update (re-run after git pull): updates steering + code files, never touches wiki data
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

    # Always update steering — it may have changed
    echo "$INSTRUCTIONS" > "$TARGET"
    echo "Link steering → $TARGET"

    bash "$SCRIPT_DIR/../_shared/scaffold.sh"
    echo ""
    echo "Done."
    echo "  Drop sources into ~/link/raw/ and say 'ingest' to process them."
    echo "  View wiki: python ~/link/serve.py"

elif [ "$MODE" = "--project" ]; then
    INSTRUCTIONS=$(cat "$SCRIPT_DIR/../_shared/link-instructions-project.md")
    TARGET=".kiro/steering/link.md"
    mkdir -p .kiro/steering

    echo "$INSTRUCTIONS" > "$TARGET"
    echo "Link steering → $TARGET"

    bash "$SCRIPT_DIR/../_shared/scaffold.sh" --project
    echo ""
    echo "Done. Drop sources into raw/ and say 'ingest' to process them."
else
    echo "Usage: bash install.sh [--project]"
    exit 1
fi
