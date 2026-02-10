#!/bin/bash
# 生成语义评估HTML报告
set -e

cd "$(dirname "$0")/.."
echo "🎨 生成语义评估HTML报告"
echo "========================================"

# 查找最新的语义评估结果
LATEST_RESULT=$(find data/results -name "semantic_fixed_*.json" -type f | sort -r | head -1)

if [ -z "$LATEST_RESULT" ]; then
    echo "❌ 未找到语义评估结果，先运行评估..."
    python3 scripts/semantic_evaluator_fixed.py \
        --data_path "data/processed/validation_dataset.json" \
        --output_dir "data/results" \
        --sample_size 10 \
        --eval_mode semantic \
        --threshold 0.7
    
    LATEST_RESULT=$(find data/results -name "semantic_fixed_*.json" -type f | sort -r | head -1)
fi

if [ -n "$LATEST_RESULT" ]; then
    echo "📁 使用评估结果: $LATEST_RESULT"
    
    # 生成HTML报告
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_HTML="data/results/semantic_report_${TIMESTAMP}.html"
    
    python3 scripts/semantic_report_generator.py \
        --result_file "$LATEST_RESULT" \
        --output_file "$OUTPUT_HTML"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ HTML报告生成成功!"
        echo "   报告文件: $OUTPUT_HTML"
        
        # 获取报告摘要
        echo ""
        echo "📋 报告摘要:"
        python3 -c "
import json
with open('$LATEST_RESULT', 'r', encoding='utf-8') as f:
    data = json.load(f)

stats = data.get('stats', {})
accuracy = data.get('accuracy', 0)
avg_similarity = data.get('avg_similarity', 0)

print('🎯 评估概览:')
print(f'   语义准确率: {accuracy:.1%}')
print(f'   平均相似度: {avg_similarity:.3f}')
print(f'   测试用例: {stats.get(\"total\", 0)}')
print(f'   成功处理: {stats.get(\"successful\", 0)}')
print(f'   匹配成功: {stats.get(\"matched\", 0)}')

# 业务价值评估
if accuracy >= 0.8 and avg_similarity >= 0.75:
    print('\\n💼 业务价值: ✅ 优秀 - 可直接用于投资分析')
elif accuracy >= 0.6 and avg_similarity >= 0.65:
    print('\\n💼 业务价值: ⚠️  良好 - 有较好参考价值')
else:
    print('\\n💼 业务价值: ❌ 需改进 - 需要优化')

print('\\n🚀 建议:')
print('   1. 在浏览器中打开HTML报告查看详细结果')
print('   2. 基于评估结果制定部署计划')
print('   3. 建立同义词映射表投入实际使用')
"
        
        # 生成PDF版本（可选）
        echo ""
        echo "📄 可选: 生成PDF版本"
        echo "   如果需要PDF版本，可以安装wkhtmltopdf后运行:"
        echo "   wkhtmltopdf $OUTPUT_HTML data/results/semantic_report_${TIMESTAMP}.pdf"
        
    else
        echo "❌ HTML报告生成失败"
        exit 1
    fi
else
    echo "❌ 未找到评估结果文件"
    exit 1
fi

echo ""
echo "🌐 在浏览器中打开报告:"
echo "   open $OUTPUT_HTML  # macOS"
echo "   xdg-open $OUTPUT_HTML  # Linux"
echo "   start $OUTPUT_HTML  # Windows"
