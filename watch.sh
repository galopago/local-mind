#!/bin/bash
# Link file watcher — watches raw/ for new files and notifies you to ingest.
# Works on macOS (fswatch) and Linux (inotifywait).
#
# Usage:
#   bash watch.sh              # watches ~/link/raw/
#   bash watch.sh /path/to/raw # watches a specific raw/ directory
#
# This is a lightweight notifier — it tells you when new files arrive.
# The actual ingest still happens through your LLM agent.
# For full auto-ingest, use the Kiro fileCreated hook instead.

set -e

RAW_DIR="${1:-$HOME/link/raw}"

if [ ! -d "$RAW_DIR" ]; then
    echo "Directory not found: $RAW_DIR"
    echo "Run the install script first to scaffold the wiki."
    exit 1
fi

echo "  Link watcher → watching $RAW_DIR"
echo "  Drop files here and your agent will be notified to ingest them."
echo "  Ctrl+C to stop"
echo ""

# Track already-processed files
PROCESSED="$HOME/link/.link_processed"
touch "$PROCESSED"

notify() {
    local file="$1"
    local basename=$(basename "$file")

    # Skip hidden files and .gitkeep
    case "$basename" in
        .*) return ;;
    esac

    # Skip if already processed
    if grep -qF "$basename" "$PROCESSED" 2>/dev/null; then
        return
    fi

    echo "$basename" >> "$PROCESSED"
    echo "  [$(date '+%H:%M:%S')] New: $basename"
    echo "  → Tell your agent: ingest ~/link/raw/$basename"

    # macOS notification if available
    if command -v osascript &>/dev/null; then
        osascript -e "display notification \"New file: $basename\" with title \"Link\" subtitle \"Ready to ingest\"" 2>/dev/null || true
    fi
}

# Try fswatch (macOS), fall back to inotifywait (Linux), fall back to polling
if command -v fswatch &>/dev/null; then
    fswatch -0 --event Created "$RAW_DIR" | while IFS= read -r -d '' file; do
        notify "$file"
    done
elif command -v inotifywait &>/dev/null; then
    inotifywait -m -e create "$RAW_DIR" --format '%f' | while read -r file; do
        notify "$RAW_DIR/$file"
    done
else
    echo "  (no fswatch or inotifywait found — using polling every 5s)"
    while true; do
        for file in "$RAW_DIR"/*; do
            [ -f "$file" ] && notify "$file"
        done
        sleep 5
    done
fi
