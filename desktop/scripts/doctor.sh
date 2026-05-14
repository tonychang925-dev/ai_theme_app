#!/bin/bash
# Standalone diagnostic script for AI题材引擎 Desktop
# Can be run independently to check if the environment is ready

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }

echo "=== AI投资助理 环境诊断 ==="
echo ""

# 1. Node.js
echo "[node]"
if command -v node >/dev/null 2>&1; then
  pass "node $(node --version)"
else
  fail "node not found — install: brew install node"
fi

# 2. npm
echo "[npm]"
if command -v npm >/dev/null 2>&1; then
  pass "npm $(npm --version)"
else
  fail "npm not found"
fi

# 3. Python venv
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
echo "[python venv]"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
  pass "$($VENV_PYTHON --version 2>&1)"
else
  fail ".venv/bin/python not found at $VENV_PYTHON"
  info "fix: cd $PROJECT_ROOT && python3 -m venv .venv"
fi

# 4. Python conda
echo "[python conda]"
CONDA_PYTHON="/opt/miniconda3/envs/theme_matcher_env/bin/python"
if [ -f "$CONDA_PYTHON" ]; then
  pass "$($CONDA_PYTHON --version 2>&1)"
else
  fail "conda env not found at $CONDA_PYTHON"
  info "fix: conda create -n theme_matcher_env python=3.12"
fi

# 5. PostgreSQL
echo "[postgresql]"
if pg_isready >/dev/null 2>&1; then
  pass "postgresql is ready"
elif brew services list 2>/dev/null | grep postgresql | grep started >/dev/null; then
  pass "postgresql (brew services)"
else
  warn "postgresql status unknown (may be running)"
fi

# 6. Redis
echo "[redis]"
if redis-cli ping >/dev/null 2>&1; then
  pass "redis is ready"
elif brew services list 2>/dev/null | grep redis | grep started >/dev/null; then
  pass "redis (brew services)"
else
  warn "redis may not be running"
  info "fix: brew services start redis"
fi

# 7. Frontend dist
echo "[frontend dist]"
if [ -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
  pass "frontend/dist exists"
else
  fail "frontend/dist/index.html not found"
  info "fix: cd $PROJECT_ROOT/frontend && npm run build"
fi

# 8. Python packages
echo "[python packages - venv]"
if [ -f "$VENV_PYTHON" ]; then
  for pkg in uvicorn fastapi httpx asyncpg passlib pydantic; do
    if "$VENV_PYTHON" -c "import $pkg" 2>/dev/null; then
      pass "$pkg"
    else
      fail "$pkg not installed"
    fi
  done
fi

echo ""
echo "=== 诊断完成 ==="
