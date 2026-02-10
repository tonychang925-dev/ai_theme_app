#!/bin/bash
# 运行完整数据集评估
set -e

cd "$(dirname "$0")/.."
echo "🎯 AI题材引擎 - 完整数据集评估"
echo "========================================"

# 检查数据文件
DATA_FILE="data/processed/validation_dataset.json"
if [ ! -f "$DATA_FILE" ]; then
    echo "❌ 测试数据不存在: $DATA_FILE"
    exit 1
fi

# 统计数据
echo "📊 数据集统计:"
python3 -c "
import json
with open('$DATA_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'   测试用例总数: {len(data)}')

# 统计主题分布
theme_counts = {}
for case in data:
    theme = case.get('theme', 'unknown')
    theme_counts[theme] = theme_counts.get(theme, 0) + 1

print(f'   覆盖主题数: {len(theme_counts)}')
print('   主题分布:')
for theme, count in theme_counts.items():
    print(f'     • {theme}: {count}个案例')
"

echo ""
echo "⚠️  注意: 完整评估所有76个案例需要较长时间"
echo "   每个案例都需要调用DeepSeek API进行分析"
echo "   预计需要15-30分钟完成"
echo ""
read -p "是否继续? (y/N): " confirm

if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "评估取消"
    exit 0
fi

# 设置输出目录
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/results/full_dataset_${TIMESTAMP}"
THRESHOLD=${1:-0.7}

echo ""
echo "🔧 评估配置:"
echo "   数据集: $DATA_FILE"
echo "   相似度阈值: $THRESHOLD"
echo "   输出目录: $OUTPUT_DIR"
echo ""

# 运行完整评估
echo "🚀 开始完整数据集评估..."
echo "   请耐心等待，这需要一些时间..."
echo "   (可以查看日志了解进度)"
echo ""

python3 scripts/full_dataset_evaluator.py \
    --data_path "$DATA_FILE" \
    --output_dir "$OUTPUT_DIR" \
    --threshold "$THRESHOLD" 2>&1 | tee "$OUTPUT_DIR/evaluation.log"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ 完整评估完成!"
    
    # 查找结果文件
    RESULT_FILE=$(find "$OUTPUT_DIR" -name "full_evaluation_*.json" -type f | head -1)
    
    if [ -n "$RESULT_FILE" ] && [ -f "$RESULT_FILE" ]; then
        echo ""
        echo "📊 评估结果摘要:"
        python3 -c "
import json
with open('$RESULT_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)

summary = data.get('summary', {})
stats = data.get('stats', {})
problem_areas = data.get('problem_areas', {})

print('🎯 整体表现:')
print(f'   测试用例总数: {stats.get(\"total\", 0)}')
print(f'   成功处理数: {stats.get(\"successful\", 0)}')
print(f'   匹配成功数: {stats.get(\"matched\", 0)}')
print(f'   语义准确率: {stats.get(\"accuracy\", 0):.1%}')
print(f'   平均相似度: {stats.get(\"avg_similarity\", 0):.3f}')

print(f'\\n📈 主题表现统计:')
theme_stats = stats.get('theme_stats', {})
if theme_stats:
    # 计算表现分布
    excellent = sum(1 for t in theme_stats.values() if t.get('accuracy', 0) >= 0.8)
    good = sum(1 for t in theme_stats.values() if 0.6 <= t.get('accuracy', 0) < 0.8)
    fair = sum(1 for t in theme_stats.values() if 0.4 <= t.get('accuracy', 0) < 0.6)
    poor = sum(1 for t in theme_stats.values() if t.get('accuracy', 0) < 0.4)
    
    print(f'   优秀 (≥80%): {excellent}个主题')
    print(f'   良好 (60-79%): {good}个主题')
    print(f'   一般 (40-59%): {fair}个主题')
    print(f'   需改进 (<40%): {poor}个主题')

# 问题区域
if problem_areas.get('low_accuracy_themes'):
    print(f'\\n🔧 需要重点优化的主题:')
    for theme_info in problem_areas['low_accuracy_themes'][:5]:
        print(f'   • {theme_info[\"theme\"]}: {theme_info[\"accuracy\"]:.1%}')

# 业务价值
print(f'\\n💼 业务价值评估:')
if stats.get('accuracy', 0) >= 0.8:
    print('   ✅ 优秀 - 可以直接投入生产使用')
elif stats.get('accuracy', 0) >= 0.7:
    print('   ⚠️  良好 - 可以部署，建议继续优化')
elif stats.get('accuracy', 0) >= 0.6:
    print('   📝 一般 - 需要部分人工复核')
else:
    print('   ❌ 需改进 - 需要深入优化')
"
        
        # 生成HTML报告
        echo ""
        echo "🎨 生成HTML报告..."
        HTML_OUTPUT="$OUTPUT_DIR/full_report.html"
        python3 scripts/semantic_report_generator.py \
            --result_file "$RESULT_FILE" \
            --output_file "$HTML_OUTPUT"
        
        if [ $? -eq 0 ]; then
            echo "✅ HTML报告已生成: $HTML_OUTPUT"
            
            # 显示报告查看选项
            echo ""
            echo "🌐 查看报告选项:"
            echo "   1. 在浏览器中打开HTML报告"
            echo "   2. 查看详细数据"
            echo "   3. 生成优化建议"
            echo ""
            read -p "请选择 (1-3): " choice
            
            case $choice in
                1)
                    if [[ "$OSTYPE" == "darwin"* ]]; then
                        open "$HTML_OUTPUT"
                    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                        xdg-open "$HTML_OUTPUT" 2>/dev/null || echo "请手动打开: $HTML_OUTPUT"
                    else
                        echo "请手动打开: $HTML_OUTPUT"
                    fi
                    ;;
                2)
                    echo ""
                    echo "📊 详细数据位置:"
                    echo "   JSON数据: $RESULT_FILE"
                    echo "   评估日志: $OUTPUT_DIR/evaluation.log"
                    echo "   样本数量: 76个完整测试用例"
                    ;;
                3)
                    echo ""
                    echo "🚀 生成优化建议..."
                    python3 -c "
import json
with open('$RESULT_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)

problem_areas = data.get('problem_areas', {})
stats = data.get('stats', {})

print('🎯 优化建议:')
print('1. 立即实施:')
print('   • 建立完整的同义词映射表')
print('   • 部署到生产环境（如果准确率≥80%）')

print('\\n2. 短期优化 (1-2周):')
if problem_areas.get('low_accuracy_themes'):
    themes = [t['theme'] for t in problem_areas['low_accuracy_themes'][:3]]
    print(f'   • 重点优化主题: {', '.join(themes)}')
    print('   • 检查这些主题的同义词映射')
    print('   • 优化AI提示词')

print('\\n3. 长期优化 (1个月):')
print('   • 扩展主题知识库')
print('   • 增加更多评估维度')
print('   • 实现实时监控和反馈')
"
                    ;;
            esac
        fi
    fi
    
    echo ""
    echo "📁 生成的文件:"
    find "$OUTPUT_DIR" -type f -name "*.json" -o -name "*.html" -o -name "*.log" | while read file; do
        size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "?")
        echo "   • $(basename "$file") ($((size/1024))KB)"
    done
    
else
    echo "❌ 评估失败"
    exit 1
fi

echo ""
echo "🎯 下一步:"
echo "   1. 分析完整评估结果，识别需要优化的主题"
echo "   2. 根据结果制定具体的优化计划"
echo "   3. 定期运行完整评估监控改进效果"
