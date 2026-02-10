#!/bin/bash
# 运行报告生成器
cd "$(dirname "$0")/.."

LATEST_REPORT=$(ls -dt data/results/reports/full_pipeline_* | head -1)

if [ -z "$LATEST_REPORT" ]; then
    echo "❌ 找不到最新的评估报告"
    exit 1
fi

METRICS_FILE="$LATEST_REPORT/metrics.json"
REPORT_FILE="$LATEST_REPORT/report_enhanced.html"

if [ ! -f "$METRICS_FILE" ]; then
    echo "❌ 找不到指标文件: $METRICS_FILE"
    exit 1
fi

echo "📊 生成增强版评估报告..."
echo "   输入文件: $METRICS_FILE"
echo "   输出文件: $REPORT_FILE"

python3 scripts/report_generator_fixed.py \
    --result_file "$METRICS_FILE" \
    --output_file "$REPORT_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 增强版报告生成完成!"
    echo "   报告文件: $REPORT_FILE"
    echo ""
    echo "📋 报告内容摘要:"
    python3 -c "
import json
with open('$METRICS_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'   总测试用例: {data.get(\"total_cases\", 0)}')
print(f'   整体F1分数: {data.get(\"overall_f1\", 0):.3f}')
print(f'   覆盖题材数: {len(data.get(\"theme_wise_metrics\", {}))}')

# 显示最佳和最差题材
themes = data.get('theme_wise_metrics', {})
if themes:
    sorted_themes = sorted(themes.items(), key=lambda x: x[1].get('f1', 0), reverse=True)
    if sorted_themes:
        best_theme, best_score = sorted_themes[0]
        worst_theme, worst_score = sorted_themes[-1]
        print(f'   最佳题材: {best_theme} (F1={best_score.get(\"f1\", 0):.3f})')
        print(f'   最差题材: {worst_theme} (F1={worst_score.get(\"f1\", 0):.3f})')
"
else
    echo "❌ 报告生成失败"
fi
