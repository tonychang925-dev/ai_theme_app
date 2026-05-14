#!/bin/bash
# Build the frontend dist for desktop packaging
# Called before electron-builder to ensure frontend/dist exists

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=== Building frontend for desktop ==="
echo "Project root: $PROJECT_ROOT"

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "ERROR: frontend/ directory not found at $FRONTEND_DIR"
  exit 1
fi

cd "$FRONTEND_DIR"

# Check if dist already exists and is fresh
if [ -f "dist/index.html" ]; then
  echo "[ok] frontend/dist already exists"
else
  echo "[building] npm run build..."
  npm install --silent
  npm run build
fi

if [ ! -f "dist/index.html" ]; then
  echo "ERROR: frontend build failed - dist/index.html not found"
  exit 1
fi

echo "=== Frontend build complete ==="
echo "dist: $FRONTEND_DIR/dist"
