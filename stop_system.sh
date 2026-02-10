#!/bin/bash
echo "🛑 停止AI题材引擎系统"
echo "="*60

# 停止数据处理器
echo "停止数据处理器..."
pkill -f "final_processor.py" && echo "✅ 数据处理器已停止"

# 停止主题服务
echo "停止主题服务..."
pkill -f "start_service.py" && echo "✅ 主题服务已停止"

# 等待进程结束
sleep 2

echo ""
echo "📊 最终状态:"
if pgrep -f "python.*(final_processor|start_service)" > /dev/null; then
    echo "⚠️  仍有进程在运行，请检查"
else
    echo "✅ 所有服务已停止"
fi
