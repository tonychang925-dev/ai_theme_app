#!/bin/bash
# Build the Electron desktop app (.app and .dmg)
# Usage: bash scripts/build-desktop.sh [--dir] [--dmg]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$DESKTOP_DIR/.." && pwd)"

echo "=== Building AI题材引擎 Desktop App ==="
echo "Desktop dir: $DESKTOP_DIR"
echo "Project root: $PROJECT_ROOT"

# Step 1: Build frontend
echo ""
echo "[1/4] Building frontend..."
bash "$SCRIPT_DIR/build-frontend.sh"

# Step 2: Install desktop deps
echo ""
echo "[2/4] Installing desktop dependencies..."
cd "$DESKTOP_DIR"
npm install --silent

# Step 3: Compile TypeScript
echo ""
echo "[3/4] Compiling TypeScript..."
npx tsc -p tsconfig.json

# Step 4: Package with electron-builder
echo ""
echo "[4/4] Packaging with electron-builder..."

TARGET="--dir"
if [[ "${1:-}" == "--dmg" ]]; then
  TARGET="--mac"
fi

npx electron-builder $TARGET \
  --config "$DESKTOP_DIR/package.json"

echo ""
echo "=== Build complete ==="
echo "Output: $DESKTOP_DIR/dist-electron/"
ls -la "$DESKTOP_DIR/dist-electron/" 2>/dev/null || echo "(check dist-electron/ for output)"
