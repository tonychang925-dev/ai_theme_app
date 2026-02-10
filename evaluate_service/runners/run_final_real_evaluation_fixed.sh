#!/bin/bash
# 最终真实AI引擎评估 - 修复版
set -e

cd "$(dirname "$0")/.."
echo "🎯 AI题材引擎 - 最终真实评估"
echo "========================================"

# 检查API密钥设置
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "⚠️  DEEPSEEK_API_KEY 未设置，使用测试模式"
    echo "   如果要使用真实AI API，请设置:"
    echo "   export DEEPSEEK_API_KEY=您的真实API密钥"
    export TEST_MODE=1
    USE_MOCK=true
    MODE_TEXT="测试模式（模拟API）"
else
    # 安全显示API密钥长度
    API_KEY_LENGTH=$(echo -n "$DEEPSEEK_API_KEY" | wc -c)
    echo "✅ DEEPSEEK_API_KEY 已设置 (长度: $API_KEY_LENGTH 字符)"
    USE_MOCK=false
    MODE_TEXT="真实AI模式"
fi

# 运行完整评估
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/results/final_real_evaluation_${TIMESTAMP}"

echo ""
echo "🔬 运行评估 ($MODE_TEXT)..."
echo "   测试数据集: data/processed/validation_dataset.json"
echo "   测试用例数: 76"
echo "   输出目录: $OUTPUT_DIR"

python3 scripts/real_ai_evaluator.py \
    --data_path "data/processed/validation_dataset.json" \
    --output_dir "$OUTPUT_DIR" \
    --sample_size 76

if [ $? -eq 0 ] && [ -f "$OUTPUT_DIR/real_ai_results.json" ]; then
    echo ""
    echo "✅ 评估完成!"
    echo ""
    
    # 显示详细结果
    python3 -c "
import json
import os
from datetime import datetime

with open('$OUTPUT_DIR/real_ai_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('📊 AI题材引擎评估报告')
print('=' * 60)
print(f'评估时间: {datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")}')
analysis_mode = data.get('analysis_mode', 'unknown')
print(f'评估模式: {\"真实AI API\" if analysis_mode == \"real\" else \"测试模式（模拟）\"}')
print('')

overall = data
print('🎯 整体表现')
print('-' * 40)
print(f'测试用例总数: {overall.get(\"total_cases\", 0)}')
print(f'成功处理数: {overall.get(\"successful_cases\", 0)}')
print(f'正确识别数: {overall.get(\"correct_cases\", 0)}')
print(f'整体准确率: {overall.get(\"overall_accuracy\", 0):.1%}')
print(f'平均置信度: {overall.get(\"summary\", {}).get(\"avg_confidence\", 0):.2f}')
print('')

theme_metrics = data.get('theme_metrics', {})
if theme_metrics:
    print('📈 各题材表现排名')
    print('-' * 40)
    sorted_themes = sorted(theme_metrics.items(), 
                          key=lambda x: x[1].get('accuracy', 0), 
                          reverse=True)
    
    # 优秀表现（准确率 >= 80%）
    excellent = [(t, m) for t, m in sorted_themes if m.get('accuracy', 0) >= 0.8]
    if excellent:
        print('🥇 优秀表现 (准确率 ≥ 80%):')
        for theme, metrics in excellent:
            acc = metrics.get('accuracy', 0)
            correct = metrics.get('correct_count', 0)
            total = metrics.get('test_count', 0)
            print(f'   ✅ {theme}: {acc:.1%} ({correct}/{total})')
    
    # 良好表现（准确率 60-79%）
    good = [(t, m) for t, m in sorted_themes if 0.6 <= m.get('accuracy', 0) < 0.8]
    if good:
        print('\\n🥈 良好表现 (60% ≤ 准确率 < 80%):')
        for theme, metrics in good:
            acc = metrics.get('accuracy', 0)
            correct = metrics.get('correct_count', 0)
            total = metrics.get('test_count', 0)
            print(f'   ⚠️  {theme}: {acc:.1%} ({correct}/{total})')
    
    # 需要改进（准确率 < 60%）
    poor = [(t, m) for t, m in sorted_themes if m.get('accuracy', 0) < 0.6]
    if poor:
        print('\\n🔧 需要改进 (准确率 < 60%):')
        for theme, metrics in poor:
            acc = metrics.get('accuracy', 0)
            correct = metrics.get('correct_count', 0)
            total = metrics.get('test_count', 0)
            print(f'   ❌ {theme}: {acc:.1%} ({correct}/{total})')
    
    # 统计信息
    print(f'\\n📊 统计信息:')
    print(f'   优秀题材数: {len(excellent)} / {len(sorted_themes)}')
    print(f'   良好题材数: {len(good)} / {len(sorted_themes)}')
    print(f'   需改进题材数: {len(poor)} / {len(sorted_themes)}')

# 显示失败案例
detailed_results = data.get('detailed_results', [])
failed = [r for r in detailed_results if not r.get('success', False)]
if failed:
    print(f'\\n❌ 失败案例 ({len(failed)} 个):')
    for result in failed[:3]:  # 只显示前3个
        theme = result.get('theme', 'unknown')
        error = result.get('error', 'unknown error')
        print(f'   • {theme}: {error[:50]}...')

# 显示成功案例样本
successful = [r for r in detailed_results if r.get('success', False)]
if successful:
    print(f'\\n🔍 成功案例样本:')
    for i, result in enumerate(successful[:2], 1):
        theme = result.get('theme', 'unknown')
        ground_truth = result.get('ground_truth', [])
        discovered = result.get('discovered', [])
        is_correct = result.get('is_correct', False)
        confidence = result.get('confidence', 'N/A')
        
        print(f'   示例{i}: {theme}')
        print(f'       真实题材: {ground_truth}')
        print(f'       发现题材: {discovered}')
        print(f'       是否正确: {\"✅\" if is_correct else \"❌\"}')
        print(f'       置信度: {confidence}')
        print()
"

    echo ""
    echo "📁 结果文件:"
    find "$OUTPUT_DIR" -type f -name "*.json" -o -name "*.html" | while read file; do
        size_kb=$(( ($(wc -c < "$file") + 1023) / 1024 ))
        echo "   • $(basename "$file") (${size_kb}KB)"
    done
    
    echo ""
    echo "🎯 优化建议:"
    
    if [ "$USE_MOCK" = true ]; then
        echo "   1. 📝 当前使用测试模式，要获得真实性能数据:"
        echo "      export DEEPSEEK_API_KEY=您的真实密钥"
        echo "      ./runners/run_final_real_evaluation_fixed.sh"
    else
        echo "   1. 🔍 分析低准确率题材，优化提示词:"
        echo "      python3 scripts/analyze_results.py $OUTPUT_DIR/real_ai_results.json"
    fi
    
    # 显示当前准确率
    CURRENT_ACC=$(python3 -c "import json;d=json.load(open('$OUTPUT_DIR/real_ai_results.json'));print(f'{d.get(\"overall_accuracy\", 0):.3f}')")
    
    echo "   2. 📈 与模拟评估对比:"
    echo "      模拟评估F1: 0.832"
    echo "      当前评估准确率: $CURRENT_ACC"
    
    if python3 -c "import sys; acc=float('$CURRENT_ACC'); sys.exit(0 if acc >= 0.832 else 1)"; then
        echo "      ✅ 当前准确率高于模拟评估"
    else
        echo "      ⚠️  当前准确率低于模拟评估"
    fi
    
else
    echo "❌ 评估失败，请检查错误信息"
    exit 1
fi
