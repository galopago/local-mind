#!/bin/bash
# Remove Link from Kiro
#
# Usage:
#   bash uninstall.sh --global    → removes ~/.kiro/steering/link.md
#   bash uninstall.sh --project   → removes .kiro/steering/link.md
#   bash uninstall.sh             → defaults to --project
set -e

MODE="${1:---project}"

if [ "$MODE" = "--global" ]; then
    TARGET="$HOME/.kiro/steering/link.md"
else
    TARGET=".kiro/steering/link.md"
fi

if [ -f "$TARGET" ]; then
    rm "$TARGET"
    echo "Removed $TARGET"
else
    echo "No Link steering found at $TARGET"
fi
