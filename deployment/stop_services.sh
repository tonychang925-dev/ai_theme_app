#!/bin/bash

# 停止所有服务脚本

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

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

stop_service() {
    local service_name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            log_info "停止 $service_name (PID: $pid)..."
            kill $pid
            sleep 2

            if kill -0 $pid 2>/dev/null; then
                log_warning "$service_name 未正常停止，强制停止..."
                kill -9 $pid
            fi

            rm -f "$pid_file"
            log_success "$service_name 已停止"
        else
            log_warning "$service_name 进程不存在，清理PID文件"
            rm -f "$pid_file"
        fi
    else
        log_warning "$service_name PID文件不存在"
    fi
}

echo "=========================================="
echo "  停止AI主题分析应用所有服务"
echo "=========================================="
echo ""

# 停止后端服务
stop_service "后端服务" "logs/backend.pid"

# 停止前端BFF服务
stop_service "前端BFF服务" "logs/frontend_bff.pid"

# 停止模型服务
stop_service "模型服务" "logs/model_service.pid"

# 停止前端服务
stop_service "前端服务" "logs/frontend.pid"

echo ""
echo "=========================================="
echo "  所有服务已停止"
echo "=========================================="