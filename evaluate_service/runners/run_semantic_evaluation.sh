#!/bin/bash
# 运行语义相似度评估
set -e

cd "$(dirname "$0")/.."
echo "🎯 语义相似度评估（评估真实业务价值）"
echo "========================================"

echo "📋 评估理念:"
echo "  我们不要求AI生成与'久赢恒丰'完全相同的题材名称"
echo "  我们关注AI是否能正确理解事件主题，进行语义一致的分类"
echo "  示例: '智能眼镜' ≈ 'AI/AR眼镜' (应该算正确)"
echo ""

# 运行参数
SAMPLE_SIZE=${1:-15}
EVAL_MODE=${2:-"semantic"}
THRESHOLD=${3:-0.7}
OUTPUT_DIR="data/results/semantic_${EVAL_MODE}_$(date +%Y%m%d_%H%M%S)"

echo "🔧 评估配置:"
echo "   样本大小: $SAMPLE_SIZE"
echo "   评估模式: $EVAL_MODE"
echo "   相似度阈值: $THRESHOLD"
echo "   输出目录: $OUTPUT_DIR"
echo ""

# 运行语义评估器
python3 scripts/semantic_evaluator.py \
    --data_path "data/processed/validation_dataset.json" \
    --output_dir "$OUTPUT_DIR" \
    --sample_size "$SAMPLE_SIZE" \
    --eval_mode "$EVAL_MODE" \
    --threshold "$THRESHOLD"

if [ $? -eq 0 ]; then
    echo ""
    echo "📊 语义评估完成!"
    
    # 查找最新结果
    LATEST_RESULT=$(find "$OUTPUT_DIR" -name "*.json" -type f | sort -r | head -1)
    
    if [ -n "$LATEST_RESULT" ] && [ -f "$LATEST_RESULT" ]; then
        echo ""
        echo "📈 业务价值分析:"
        python3 -c "
import json
with open('$LATEST_RESULT', 'r', encoding='utf-8') as f:
    data = json.load(f)

config = data.get('config', {})
metrics = data.get('metrics', {})

print(f'   评估模式: {config.get(\"eval_mode\", \"unknown\")}')
print(f'   相似度阈值: {config.get(\"semantic_threshold\", 0)}')
print(f'   平均语义相似度: {metrics.get(\"avg_similarity\", 0):.3f}')
print(f'   语义准确率: {metrics.get(\"accuracy_semantic\", 0):.1%}')

# 业务价值判断
semantic_acc = metrics.get('accuracy_semantic', 0)
avg_sim = metrics.get('avg_similarity', 0)

print(f'\\n💼 业务价值评估:')

if semantic_acc >= 0.8 and avg_sim >= 0.75:
    print('   ✅ 优秀 - AI能够准确理解事件主题，分类结果有很高业务价值')
    print('       可以直接应用于实际投资分析')
elif semantic_acc >= 0.6 and avg_sim >= 0.65:
    print('   ⚠️  良好 - AI基本理解事件主题，分类结果有较好业务价值')
    print('       可以应用，但建议继续优化')
elif semantic_acc >= 0.4 and avg_sim >= 0.55:
    print('   📝 一般 - AI对主题理解有限，分类结果需人工复核')
    print('       需要优化后再投入实际使用')
else:
    print('   ❌ 需改进 - AI难以理解事件主题，分类结果业务价值有限')
    print('       需要深入分析和优化')

# 显示具体案例
results = data.get('results', [])
if results:
    # 找出语义匹配良好但名称不同的案例
    semantic_matches = []
    for r in results:
        if r.get('success', False):
            match_result = r.get('match_result', {})
            similarity = match_result.get('similarity', 0)
            matched = match_result.get('matched', False)
            best_pair = match_result.get('best_pair', ('', ''))
            
            if matched and similarity >= 0.7 and best_pair[0] != best_pair[1]:
                semantic_matches.append(r)
    
    if semantic_matches:
        print(f'\\n🔍 语义匹配良好但名称不同的案例:')
        for r in semantic_matches[:2]:
            match_result = r.get('match_result', {})
            best_pair = match_result.get('best_pair', ('', ''))
            print(f'   主题: {r.get(\"theme\", \"unknown\")}')
            print(f'     久赢恒丰: {best_pair[0]}')
            print(f'     我们的AI: {best_pair[1]}')
            print(f'     语义相似度: {match_result.get(\"similarity\", 0):.3f}')
            print()
"
    fi
fi

echo ""
echo "🎯 优化建议:"
echo "   1. 如果语义准确率 > 80%，说明AI理解能力良好，可以投入实际使用"
echo "   2. 可以扩展同义词库，提高匹配灵活性"
echo "   3. 考虑增加行业关联性评估，进一步提高业务价值"
echo ""
echo "📊 其他评估模式尝试:"
echo "   ./runners/run_semantic_evaluation.sh 15 strict 0.9    # 严格模式"
echo "   ./runners/run_semantic_evaluation.sh 15 loose 0.5     # 宽松模式"
echo "   ./runners/run_semantic_evaluation.sh 15 semantic 0.7  # 语义模式（推荐）"
else
    echo "❌ 评估失败"
    exit 1
fi
