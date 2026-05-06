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
    TARGET_DIR="$(pwd)"
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

if [ -f "$LINK_ROOT/link.py" ]; then
    cp "$LINK_ROOT/link.py" "$TARGET_DIR/link.py"
    echo "  Updated link.py"
fi

if [ -d "$LINK_ROOT/mcp_package/link_core" ]; then
    mkdir -p "$TARGET_DIR/link_core"
    cp "$LINK_ROOT/mcp_package/link_core/"*.py "$TARGET_DIR/link_core/"
    echo "  Updated link_core"
fi

if [ -f "$LINK_ROOT/logo.png" ]; then
    cp "$LINK_ROOT/logo.png" "$TARGET_DIR/logo.png"
fi

if [ -f "$LINK_ROOT/logo.svg" ]; then
    cp "$LINK_ROOT/logo.svg" "$TARGET_DIR/logo.svg"
fi

cp "$LINK_ROOT/.linkignore" "$TARGET_DIR/.linkignore"

# ── Wiki structure: only on fresh install ────────────────────────────
# Never overwrite wiki data (index.md, log.md, _backlinks.json, page files).
if [ "$IS_UPDATE" = false ]; then
    for dir in raw wiki/sources wiki/concepts wiki/entities wiki/memories wiki/comparisons wiki/explorations; do
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
    for dir in raw wiki/sources wiki/concepts wiki/entities wiki/memories wiki/comparisons wiki/explorations; do
        mkdir -p "$TARGET_DIR/$dir"
    done
fi

echo "  Wiki ready at $TARGET_DIR"

# ── MCP server: install link-mcp package ─────────────────────────────
echo ""
echo "  Setting up MCP server..."

if [ -d "$LINK_ROOT/mcp_package" ]; then
    echo "  Installing/upgrading link-mcp from local checkout..."
    LINK_MCP_PACKAGE="$LINK_ROOT/mcp_package"
else
    echo "  Installing/upgrading link-mcp from PyPI..."
    LINK_MCP_PACKAGE="link-mcp"
fi

LINK_MCP_PYTHON="python3"
LINK_MCP_VENV="${LINK_MCP_VENV:-$HOME/.link-mcp-venv}"
LINK_MCP_VENV_PYTHON="$LINK_MCP_VENV/bin/python"
LINK_MCP_MARKER="$TARGET_DIR/.link-mcp-python"
LINK_MCP_INSTALLED=false
LINK_MCP_REUSED=false

if python3 -m pip install --upgrade "$LINK_MCP_PACKAGE" -q 2>/dev/null; then
    LINK_MCP_PYTHON="python3"
    LINK_MCP_INSTALLED=true
elif python3 -m venv "$LINK_MCP_VENV" 2>/dev/null \
    && "$LINK_MCP_VENV_PYTHON" -m pip install --upgrade pip -q 2>/dev/null \
    && "$LINK_MCP_VENV_PYTHON" -m pip install --upgrade "$LINK_MCP_PACKAGE" -q 2>/dev/null; then
    LINK_MCP_PYTHON="$LINK_MCP_VENV_PYTHON"
    LINK_MCP_INSTALLED=true
fi

if [ "$LINK_MCP_INSTALLED" = false ] && [ -f "$LINK_MCP_MARKER" ]; then
    LINK_MCP_MARKER_PYTHON="$(cat "$LINK_MCP_MARKER")"
    if [ -n "$LINK_MCP_MARKER_PYTHON" ] && "$LINK_MCP_MARKER_PYTHON" -c "import link_mcp" 2>/dev/null; then
        LINK_MCP_PYTHON="$LINK_MCP_MARKER_PYTHON"
        LINK_MCP_INSTALLED=true
        LINK_MCP_REUSED=true
    fi
elif [ "$LINK_MCP_INSTALLED" = false ] && [ -x "$LINK_MCP_VENV_PYTHON" ] && "$LINK_MCP_VENV_PYTHON" -c "import link_mcp" 2>/dev/null; then
    LINK_MCP_PYTHON="$LINK_MCP_VENV_PYTHON"
    LINK_MCP_INSTALLED=true
    LINK_MCP_REUSED=true
fi

if [ "$LINK_MCP_INSTALLED" = true ] && "$LINK_MCP_PYTHON" -c "import link_mcp" 2>/dev/null; then
    printf '%s\n' "$LINK_MCP_PYTHON" > "$LINK_MCP_MARKER"
    if [ "$LINK_MCP_REUSED" = true ]; then
        echo "  ✓ existing link-mcp available"
    else
        echo "  ✓ link-mcp installed"
    fi
    if [ "$LINK_MCP_PYTHON" != "python3" ]; then
        echo "  ✓ MCP Python: $LINK_MCP_PYTHON"
    fi
    if [ "$LINK_MCP_REUSED" = true ]; then
        echo "  · Automatic upgrade did not complete; run verify-mcp to confirm the installed version."
    fi
    echo ""
    echo "  Add to your MCP client config:"
    echo '  {'
    echo '    "mcpServers": {'
    echo '      "link": {'
    echo "        \"command\": \"$LINK_MCP_PYTHON\","
    echo "        \"args\": [\"-m\", \"link_mcp\", \"--wiki\", \"$TARGET_DIR/wiki\"]"
    echo '      }'
    echo '    }'
    echo '  }'
else
    echo "  · Could not install link-mcp automatically."
    echo "  Manual options:"
    echo "    python3 -m pip install --upgrade link-mcp"
    echo "    python3 -m venv ~/.link-mcp-venv"
    echo "    ~/.link-mcp-venv/bin/python -m pip install --upgrade pip link-mcp"
    echo "  If using the venv, set your MCP command to ~/.link-mcp-venv/bin/python."
fi

if [ -f "$TARGET_DIR/link.py" ]; then
    echo ""
    echo "  Check wiki health:"
    echo "    python3 \"$TARGET_DIR/link.py\" doctor \"$TARGET_DIR\""
    echo "  Verify MCP setup:"
    echo "    python3 \"$TARGET_DIR/link.py\" verify-mcp \"$TARGET_DIR\""
    echo "  Repair stale graph index:"
    echo "    python3 \"$TARGET_DIR/link.py\" rebuild-backlinks \"$TARGET_DIR\""
fi
