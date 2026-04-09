#!/bin/bash
# Check ~/link/raw/ for files not yet ingested.
# Called by session-start hooks to remind the agent about pending sources.

RAW_DIR="$HOME/link/raw"
PROCESSED="$HOME/link/.link_processed"

if [ ! -d "$RAW_DIR" ]; then
    exit 0
fi

touch "$PROCESSED"

PENDING=""
for file in "$RAW_DIR"/*; do
    [ -f "$file" ] || continue
    basename=$(basename "$file")
    case "$basename" in .gitkeep|.*) continue ;; esac
    if ! grep -qF "$basename" "$PROCESSED" 2>/dev/null; then
        PENDING="$PENDING $basename"
    fi
done

if [ -n "$PENDING" ]; then
    echo "Link: Unprocessed files in ~/link/raw/:$PENDING — consider ingesting them."
fi
