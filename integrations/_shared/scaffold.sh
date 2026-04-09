#!/bin/bash
# Scaffold the Link wiki structure in the current directory.
# Called by integration install scripts. Safe to re-run.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LINK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Copy LINK.md if not present
if [ ! -f "LINK.md" ]; then
    cp "$LINK_ROOT/LINK.md" ./LINK.md
    echo "  Created LINK.md"
else
    echo "  LINK.md already exists"
fi

# Copy serve.py if not present
if [ ! -f "serve.py" ]; then
    cp "$LINK_ROOT/serve.py" ./serve.py
    echo "  Created serve.py"
else
    echo "  serve.py already exists"
fi

# Copy logo if not present
if [ ! -f "logo.png" ] && [ -f "$LINK_ROOT/logo.png" ]; then
    cp "$LINK_ROOT/logo.png" ./logo.png
    echo "  Created logo.png"
fi

# Copy .linkignore if not present
if [ ! -f ".linkignore" ]; then
    cp "$LINK_ROOT/.linkignore" ./.linkignore
    echo "  Created .linkignore"
fi

# Create directory structure
for dir in raw wiki/sources wiki/concepts wiki/entities wiki/comparisons wiki/explorations wiki/_categories; do
    mkdir -p "$dir"
    touch "$dir/.gitkeep"
done

# Create index.md if not present
if [ ! -f "wiki/index.md" ]; then
    cp "$LINK_ROOT/wiki/index.md" ./wiki/index.md
    echo "  Created wiki/index.md"
fi

# Create log.md if not present
if [ ! -f "wiki/log.md" ]; then
    cp "$LINK_ROOT/wiki/log.md" ./wiki/log.md
    echo "  Created wiki/log.md"
fi

echo "  Wiki structure ready"
