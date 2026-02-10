#!/bin/bash
# 一键启动完整评估流程
set -e

echo "🚀 AI题材引擎评估 - 快速启动"
echo "========================================"

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

# 1. 检查环境
if [ ! -f "scripts/evaluator.py" ]; then
    echo "🛠️ 首次运行，正在设置环境..."
    ./runners/setup_evaluation.sh
fi

# 2. 检查数据
if [ ! -f "data/raw/test_cases.txt" ]; then
    echo "📝 创建示例测试数据..."
    ./runners/setup_data.sh
    echo ""
    echo "⚠️  请将您的10个题材完整数据添加到:"
    echo "   $BASE_DIR/data/raw/test_cases.txt"
    echo ""
    read -p "是否已添加数据? (按Enter继续，或Ctrl+C退出): " 
fi

# 3. 运行评估
echo "🔬 开始评估流程..."
./runners/run_baseline.sh

echo ""
echo "✅ 评估流程完成!"
echo "📁 查看结果:"
find "data/results/reports" -name "*.html" -type f | head -3 | while read report; do
    echo "   - $report"
done