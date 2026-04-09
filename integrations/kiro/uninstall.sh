#!/bin/bash
# Remove Link from Kiro
#
# Usage:
#   bash uninstall.sh             → removes global ~/.kiro/steering/link.md
#   bash uninstall.sh --project   → removes project .kiro/steering/link.md
set -e

MODE="${1:---global}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/.kiro/steering/link.md"
    HOOK="$HOME/.kiro/hooks/link-auto-ingest.json"
else
    TARGET=".kiro/steering/link.md"
    HOOK=".kiro/hooks/link-auto-ingest.json"
fi

if [ -f "$TARGET" ]; then
    rm "$TARGET"
    echo "Removed $TARGET"
else
    echo "No Link steering found at $TARGET"
fi

if [ -f "$HOOK" ]; then
    rm "$HOOK"
    echo "Removed auto-ingest hook"
fi
