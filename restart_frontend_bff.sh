#!/bin/bash

# 重启frontend_bff服务脚本

PROJECT_ROOT="/Users/admin/Desktop/ai_theme_app"
cd $PROJECT_ROOT/frontend_bff

echo "正在停止现有服务..."
pkill -f "uvicorn.*app:app" 2>/dev/null
sleep 2

echo "清理可能占用的端口..."
# 检查并释放8003端口
lsof -ti:8003 | xargs kill -9 2>/dev/null
lsof -ti:8005 | xargs kill -9 2>/dev/null
lsof -ti:5000 | xargs kill -9 2>/dev/null
sleep 1

echo "设置PYTHONPATH..."
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
echo "PYTHONPATH: $PYTHONPATH"

echo "启动新服务（端口8003）..."
nohup python -m uvicorn app:app --port 8003 --host 0.0.0.0 > frontend_bff.log 2>&1 &
PID=$!

echo "等待服务启动..."
sleep 3

# 检查服务是否启动
if ps -p $PID > /dev/null 2>&1; then
    echo "✅ 服务已启动！PID: $PID"
    echo "日志文件: /Users/admin/Desktop/ai_theme_app/frontend_bff/frontend_bff.log"
    echo ""
    echo "服务状态检查:"
    curl -s http://localhost:8003/health 2>/dev/null && echo "" || echo "❌ 服务未响应"
else
    echo "❌ 服务启动失败，请检查日志"
    tail -20 frontend_bff.log
fi

# 显示日志最后几行
echo ""
echo "最近日志:"
tail -5 frontend_bff.log