#!/bin/bash

# 重启所有服务脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "=========================================="
echo "  重启AI主题分析应用所有服务"
echo "=========================================="
echo ""

# 首先停止所有服务
log_info "停止所有服务..."
./deployment/stop_services.sh

echo ""
echo "------------------------------------------"
echo ""

# 等待2秒确保服务完全停止
sleep 2

# 重新启动服务
log_info "重新启动服务..."
./deployment/deploy_production.sh --no-frontend

echo ""
echo "=========================================="
echo "  服务重启完成"
echo "=========================================="