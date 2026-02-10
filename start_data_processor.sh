#!/bin/bash
# 启动实时数据处理服务
echo "🚀 启动 AI题材引擎 - 实时数据处理服务"
echo "="*70

# 检查Python环境
python --version || {
    echo "❌ Python未安装"
    exit 1
}

# 检查依赖
echo "🔧 检查依赖..."
python -c "import asyncpg" 2>/dev/null || {
    echo "❌ 缺少 asyncpg，正在安装..."
    pip install asyncpg
}

# 检查表结构
echo "🔍 检查表结构..."
python fix_table_structure_correct.py || {
    echo "⚠️  表结构检查失败，尝试修复..."
}

# 启动服务
echo ""
echo "🎯 启动实时数据处理服务..."
echo "📋 可选参数:"
echo "   --interval 30     # 处理间隔秒数"
echo "   --once           # 只运行一次"
echo "   --batch 10       # 每批处理数量"
echo ""
echo "🔍 查看日志: tail -f data_processor.log"
echo "📊 查看统计: 观察终端输出"
echo ""

# 启动服务
python theme_service/real_time_processor.py "$@"
