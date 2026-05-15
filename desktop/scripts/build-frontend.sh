#!/bin/bash
# Build the frontend dist for desktop packaging
# Called before electron-builder to ensure frontend/dist exists
# --force: always rebuild even if dist already exists

set -euo pipefail

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$DESKTOP_DIR/../frontend"

echo "=== Building frontend for desktop ==="
echo "Desktop dir: $DESKTOP_DIR"
echo "Frontend dir: $FRONTEND_DIR"

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "ERROR: frontend/ directory not found at $FRONTEND_DIR"
  exit 1
fi

cd "$FRONTEND_DIR"

echo "[building] npm run build (force=$FORCE)..."
npm install --silent 2>/dev/null || true
npm run build

if [ ! -f "dist/index.html" ]; then
  echo "ERROR: frontend build failed - dist/index.html not found"
  exit 1
fi

echo "=== Frontend build complete ==="
echo "dist: $FRONTEND_DIR/dist"

# Generate build-info.json for diagnostics
ENTRY_JS=$(grep -o 'src="/assets/[^"]*\.js"' "$FRONTEND_DIR/dist/index.html" | head -1 | sed 's/.*\/\([^"]*\)"/\1/')
cat > "$FRONTEND_DIR/dist/build-info.json" << BUILDFO
{
  "built_at": "$(date '+%F %T')",
  "entry_asset": "${ENTRY_JS:-unknown}",
  "git_sha": "$(git -C "$FRONTEND_DIR/.." rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
}
BUILDFO
echo "build-info.json: $(cat "$FRONTEND_DIR/dist/build-info.json")"
