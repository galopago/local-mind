#!/bin/bash
# Scaffold the Link wiki structure.
# Usage:
#   bash scaffold.sh              → scaffolds at ~/link/ (central wiki)
#   bash scaffold.sh --project    → scaffolds in current directory
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LINK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="${1:---global}"

if [ "$MODE" = "--project" ]; then
    TARGET_DIR="."
else
    TARGET_DIR="$HOME/link"
    mkdir -p "$TARGET_DIR"
fi

# Copy LINK.md if not present
if [ ! -f "$TARGET_DIR/LINK.md" ]; then
    cp "$LINK_ROOT/LINK.md" "$TARGET_DIR/LINK.md"
    echo "  Created $TARGET_DIR/LINK.md"
else
    echo "  $TARGET_DIR/LINK.md already exists"
fi

# Copy serve.py if not present
if [ ! -f "$TARGET_DIR/serve.py" ]; then
    cp "$LINK_ROOT/serve.py" "$TARGET_DIR/serve.py"
    echo "  Created $TARGET_DIR/serve.py"
else
    echo "  $TARGET_DIR/serve.py already exists"
fi

# Copy logo if not present
if [ ! -f "$TARGET_DIR/logo.png" ] && [ -f "$LINK_ROOT/logo.png" ]; then
    cp "$LINK_ROOT/logo.png" "$TARGET_DIR/logo.png"
    echo "  Created $TARGET_DIR/logo.png"
fi

# Copy .linkignore if not present
if [ ! -f "$TARGET_DIR/.linkignore" ]; then
    cp "$LINK_ROOT/.linkignore" "$TARGET_DIR/.linkignore"
    echo "  Created $TARGET_DIR/.linkignore"
fi

# Create directory structure
for dir in raw wiki/sources wiki/concepts wiki/entities wiki/comparisons wiki/explorations wiki/_categories; do
    mkdir -p "$TARGET_DIR/$dir"
    touch "$TARGET_DIR/$dir/.gitkeep"
done

# Create index.md if not present
if [ ! -f "$TARGET_DIR/wiki/index.md" ]; then
    cp "$LINK_ROOT/wiki/index.md" "$TARGET_DIR/wiki/index.md"
    echo "  Created $TARGET_DIR/wiki/index.md"
fi

# Create log.md if not present
if [ ! -f "$TARGET_DIR/wiki/log.md" ]; then
    cp "$LINK_ROOT/wiki/log.md" "$TARGET_DIR/wiki/log.md"
    echo "  Created $TARGET_DIR/wiki/log.md"
fi

echo "  Wiki structure ready at $TARGET_DIR"
