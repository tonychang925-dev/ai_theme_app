#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "🔬 AI题材引擎 - 基线评估"
echo "================================"

# 检查数据
if [ ! -f "data/raw/test_cases.txt" ]; then
    echo "❌ 测试数据不存在: data/raw/test_cases.txt"
    echo "请先运行 ./runners/setup_data.sh 准备数据"
    exit 1
fi

# 1. 格式化数据
echo "1. 格式化测试数据..."
python3 scripts/data_formatter.py \
    --input "data/raw/test_cases.txt" \
    --output "data/processed/validation_dataset.json"

# 2. 运行评估
echo "2. 运行演示评估..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/results/reports/baseline_${TIMESTAMP}"
python3 scripts/evaluator.py \
    --data_path "data/processed/validation_dataset.json" \
    --output_dir "$OUTPUT_DIR"

# 3. 生成报告
echo "3. 生成评估报告..."
python3 scripts/report_generator.py \
    --result_file "$OUTPUT_DIR/metrics.json" \
    --output_file "$OUTPUT_DIR/report.html"

echo ""
echo "📊 评估完成!"
echo "   报告文件: $(pwd)/$OUTPUT_DIR/report.html"
echo "   数据文件: $(pwd)/$OUTPUT_DIR/metrics.json"
echo ""
echo "🚀 下一步: 连接真实AI引擎进行完整评估"
