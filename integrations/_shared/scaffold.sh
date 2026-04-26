#!/bin/bash
# Scaffold or update the Link wiki structure.
#
# Fresh install: creates everything from scratch.
# Update (wiki already exists): updates code/config files only, never touches wiki data.
#
# Usage:
#   bash scaffold.sh              → ~/link/ (central wiki)
#   bash scaffold.sh --project    → current directory

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

# ── Detect: fresh install or update? ─────────────────────────────────
# A wiki exists if wiki/index.md is present (created on first ingest or scaffold)
IS_UPDATE=false
if [ -f "$TARGET_DIR/wiki/index.md" ] || [ -f "$TARGET_DIR/wiki/log.md" ]; then
    IS_UPDATE=true
fi

if [ "$IS_UPDATE" = true ]; then
    echo "  Existing wiki detected at $TARGET_DIR — updating code only, wiki data untouched."
else
    echo "  Fresh install at $TARGET_DIR."
fi

# ── Code files: always update ─────────────────────────────────────────
# These are developer-maintained and should always reflect the latest version.
cp "$LINK_ROOT/serve.py" "$TARGET_DIR/serve.py"
echo "  Updated serve.py"

cp "$LINK_ROOT/LINK.md" "$TARGET_DIR/LINK.md"
echo "  Updated LINK.md"

if [ -f "$LINK_ROOT/logo.png" ]; then
    cp "$LINK_ROOT/logo.png" "$TARGET_DIR/logo.png"
fi

cp "$LINK_ROOT/.linkignore" "$TARGET_DIR/.linkignore"

# ── Wiki structure: only on fresh install ────────────────────────────
# Never overwrite wiki data (index.md, log.md, _backlinks.json, page files).
if [ "$IS_UPDATE" = false ]; then
    for dir in raw wiki/sources wiki/concepts wiki/entities wiki/comparisons wiki/explorations; do
        mkdir -p "$TARGET_DIR/$dir"
        touch "$TARGET_DIR/$dir/.gitkeep"
    done

    if [ ! -f "$TARGET_DIR/wiki/_backlinks.json" ]; then
        echo '{}' > "$TARGET_DIR/wiki/_backlinks.json"
        echo "  Created wiki/_backlinks.json"
    fi

    if [ ! -f "$TARGET_DIR/wiki/index.md" ]; then
        cp "$LINK_ROOT/wiki/index.md" "$TARGET_DIR/wiki/index.md"
        echo "  Created wiki/index.md"
    fi

    if [ ! -f "$TARGET_DIR/wiki/log.md" ]; then
        cp "$LINK_ROOT/wiki/log.md" "$TARGET_DIR/wiki/log.md"
        echo "  Created wiki/log.md"
    fi

    echo "  Wiki structure created at $TARGET_DIR"
else
    # On update: ensure directory structure exists (in case new dirs were added)
    for dir in raw wiki/sources wiki/concepts wiki/entities wiki/comparisons wiki/explorations; do
        mkdir -p "$TARGET_DIR/$dir"
    done
fi

echo "  Wiki ready at $TARGET_DIR"

# ── MCP server: install dependency + register in agent config ─────────
echo ""
echo "  Setting up MCP server..."

# Install mcp package if not present
if ! python3 -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
    echo "  Installing link-mcp package..."
    pip3 install link-mcp --break-system-packages -q 2>/dev/null || pip3 install link-mcp -q 2>/dev/null || true
fi

# ── MCP server: install link-mcp package ─────────────────────────────
echo ""
echo "  Setting up MCP server..."

# Install link-mcp if not present (includes the mcp SDK)
if ! python3 -c "import link_mcp" 2>/dev/null; then
    echo "  Installing link-mcp..."
    pip3 install link-mcp --break-system-packages -q 2>/dev/null || pip3 install link-mcp -q 2>/dev/null || true
fi

# Verify installation
if python3 -c "import link_mcp" 2>/dev/null; then
    echo "  ✓ link-mcp installed"
    echo ""
    echo "  Add to your MCP client config:"
    echo '  {'
    echo '    "mcpServers": {'
    echo '      "link": {'
    echo '        "command": "python3",'
    echo "        \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$TARGET_DIR/wiki\"]"
    echo '      }'
    echo '    }'
    echo '  }'
else
    echo "  · Could not install link-mcp. Install manually: pip install link-mcp"
fi
