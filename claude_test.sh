#!/bin/bash
set -euo pipefail

# 设置变量
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "${PROJECT_DIR}"

export AI_THEME_APP_ROOT="$PROJECT_DIR"
export PROJECT_ROOT="$PROJECT_DIR"

echo "测试版本 - 环境变量: AI_THEME_APP_ROOT=$AI_THEME_APP_ROOT"

# 直接使用bun，不带env命令
bun -e "console.log('Bun环境中: AI_THEME_APP_ROOT:', Bun.env.AI_THEME_APP_ROOT)" 2>/dev/null || echo "bun命令失败"
