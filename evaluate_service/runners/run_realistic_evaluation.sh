#!/bin/bash
# 运行真实模拟评估
set -e

cd "$(dirname "$0")/.."
echo "🎯 AI题材引擎 - 真实模拟评估"
echo "========================================"

# 检查测试数据
if [ ! -f "data/processed/validation_dataset.json" ]; then
    echo "❌ 测试数据不存在，请先运行完整评估流水线"
    exit 1
fi

# 运行真实模拟评估
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/results/reports/realistic_${TIMESTAMP}"

echo "📊 运行真实模拟评估器..."
python3 scripts/realistic_evaluator.py \
    --data_path "data/processed/validation_dataset.json" \
    --output_dir "$OUTPUT_DIR"

if [ $? -eq 0 ]; then
    # 生成增强报告
    echo ""
    echo "📈 生成增强版报告..."
    python3 scripts/report_generator_fixed.py \
        --result_file "$OUTPUT_DIR/realistic_metrics.json" \
        --output_file "$OUTPUT_DIR/report.html"
    
    echo ""
    echo "✅ 真实模拟评估完成!"
    echo ""
    echo "📊 评估结果摘要:"
    python3 -c "
import json
with open('$OUTPUT_DIR/realistic_metrics.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'   测试用例总数: {data[\"total_cases\"]}')
print(f'   成功识别数: {data[\"successful_cases\"]}')
print(f'   整体F1分数: {data[\"overall_f1\"]:.3f}')
print(f'   整体准确率: {data[\"overall_precision\"]:.3f}')
print(f'   整体召回率: {data[\"overall_recall\"]:.3f}')
print(f'   覆盖题材数: {len(data[\"theme_wise_metrics\"])}')

# 找出表现最好和最差的题材
themes = data['theme_wise_metrics']
if themes:
    sorted_themes = sorted(themes.items(), key=lambda x: x[1]['f1'], reverse=True)
    best = sorted_themes[0]
    worst = sorted_themes[-1]
    print(f'   最佳表现: {best[0]} (F1={best[1][\"f1\"]:.3f})')
    print(f'   最需改进: {worst[0]} (F1={worst[1][\"f1\"]:.3f})')
    
    # 计算不同表现水平的题材数量
    excellent = sum(1 for t in themes.values() if t['f1'] >= 0.8)
    good = sum(1 for t in themes.values() if 0.6 <= t['f1'] < 0.8)
    need_improve = sum(1 for t in themes.values() if t['f1'] < 0.6)
    print(f'   表现优秀(≥0.8): {excellent}个题材')
    print(f'   表现良好(0.6-0.8): {good}个题材')
    print(f'   需要改进(<0.6): {need_improve}个题材')
"
    
    echo ""
    echo "📁 生成的文件:"
    find "$OUTPUT_DIR" -type f -name "*.json" -o -name "*.html" | while read file; do
        size=$(wc -c < "$file" 2>/dev/null | awk '{print $1}')
        echo "   • $(basename "$file") ($((size/1024))KB)"
    done
    
    echo ""
    echo "🔍 查看详细结果:"
    echo "   cat $OUTPUT_DIR/detailed_results.json | head -50"
    echo "   或在浏览器打开: $OUTPUT_DIR/report.html"
    
    echo ""
    echo "🎯 下一步建议:"
    echo "   1. 分析表现较差的题材（F1<0.6）"
    echo "   2. 检查详细结果中的误识别和漏识别"
    echo "   3. 根据分析结果优化AI提示词和聚类参数"
else
    echo "❌ 评估失败"
    exit 1
fi
