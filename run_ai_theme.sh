#!/bin/bash
# AI题材引擎 - 一键启动

echo "🚀 AI题材引擎 - 启动所有服务"
echo "="*60

# 1. 启动主题服务
echo "1. 启动主题服务 (端口: 8002)..."
cd theme_service
if [ -f "fixed_start_service.py" ]; then
    nohup python3 fixed_start_service.py > ../theme_service.log 2>&1 &
else
    nohup python3 start_service.py > ../theme_service.log 2>&1 &
fi
THEME_PID=$!
cd ..

echo "   等待服务启动..."
sleep 8

# 检查服务是否启动
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "   ✅ 主题服务已启动 (PID: $THEME_PID)"
    echo "   🌐 访问: http://localhost:8002"
else
    echo "   ❌ 主题服务启动失败"
    echo "   查看日志: tail -f theme_service.log"
    exit 1
fi

# 2. 启动数据处理器
echo ""
echo "2. 启动数据处理器..."
cd theme_service
if [ -f "fixed_processor.py" ]; then
    nohup python3 fixed_processor.py > ../data_processor.log 2>&1 &
else
    nohup python3 final_processor.py > ../data_processor.log 2>&1 &
fi
PROCESSOR_PID=$!
cd ..

sleep 3

if ps -p $PROCESSOR_PID > /dev/null 2>&1; then
    echo "   ✅ 数据处理器已启动 (PID: $PROCESSOR_PID)"
    echo "   📝 日志: data_processor.log"
else
    echo "   ❌ 数据处理器启动失败"
    echo "   查看日志: tail -f data_processor.log"
    exit 1
fi

# 3. 启动监控
echo ""
echo "3. 启动系统监控..."
echo "   监控脚本: ./final_monitor.sh"
echo "   按 Ctrl+C 停止监控"
echo ""

# 显示状态
echo "="*60
echo "🎉 AI题材引擎系统已启动！"
echo ""
echo "📋 服务状态:"
echo "   ✅ 主题服务: http://localhost:8002 (PID: $THEME_PID)"
echo "   ✅ 数据处理器: 运行中 (PID: $PROCESSOR_PID)"
echo ""
echo "🔍 监控命令:"
echo "   ./final_monitor.sh          # 实时监控"
echo "   tail -f data_processor.log  # 查看处理日志"
echo "   tail -f theme_service.log   # 查看服务日志"
echo ""
echo "🛑 停止系统:"
echo "   pkill -f 'python.*(fixed_start_service|fixed_processor)'"
echo "   pkill -f 'python.*(start_service|final_processor)'"
echo ""
echo "📊 数据流集成已完成！"
echo "   model_service → 新闻事件 → 主题发现 → 主题映射 → API服务"
