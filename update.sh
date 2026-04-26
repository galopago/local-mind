#!/bin/bash
set -euo pipefail

# Safe update for ~/link/ — pulls latest code without touching your wiki data.
# Usage: bash ~/link/update.sh
#
# Updates: serve.py, LINK.md, .linkignore, integrations/
# Never touches: wiki/ (your personal data lives there)

LINK_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🔗 Updating Link..."
echo ""

# Fetch latest without merging
git -C "$LINK_ROOT" fetch origin main --quiet

# Checkout only safe files from origin/main
SAFE_FILES=(
  "serve.py"
  "LINK.md"
  ".linkignore"
  "README.md"
)

for f in "${SAFE_FILES[@]}"; do
  if git -C "$LINK_ROOT" show "origin/main:$f" &>/dev/null 2>&1; then
    git -C "$LINK_ROOT" checkout origin/main -- "$f"
    echo "   ✓ $f"
  fi
done

# Update integrations/ directory (agent instructions, install scripts)
git -C "$LINK_ROOT" checkout origin/main -- integrations/ 2>/dev/null && echo "   ✓ integrations/" || true

echo ""
echo "   Wiki data untouched. serve.py and LINK.md updated."
echo ""
