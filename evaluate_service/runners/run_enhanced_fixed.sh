#!/bin/bash

echo "🚀 开始增强系统评估测试（修复版）..."

# 设置Python路径
export PYTHONPATH=.:$PYTHONPATH

# 创建结果目录
mkdir -p data/results/enhanced
mkdir -p logs

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/enhanced_eval_fixed_${TIMESTAMP}.log"

echo "📊 运行增强系统评估..."
python -m scripts.evaluators.enhanced_evaluator_fixed > "${LOG_FILE}" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 增强系统评估完成!"
    echo "📁 结果保存在: data/results/enhanced/"
    echo "📁 日志文件: ${LOG_FILE}"
    
    # 显示最新结果摘要
    LATEST_RESULT="data/results/enhanced/latest_results.json"
    if [ -f "$LATEST_RESULT" ]; then
        echo -e "\n📋 最新评估结果摘要:"
        python -c "
import json
try:
    with open('$LATEST_RESULT', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    summary = data.get('summary', {})
    print(f'综合得分: {summary.get(\"overall_score\", 0):.3f}/1.0')
    print(f'评估等级: {summary.get(\"evaluation_level\", \"N/A\")}')
    print(f'建议: {summary.get(\"recommendation\", \"N/A\")}')
    
    metrics = summary.get('key_metrics', {})
    print(f'决策准确率: {metrics.get(\"decision_accuracy\", 0):.1%}')
    print(f'平均响应时间: {metrics.get(\"avg_response_time_ms\", 0):.0f}ms')
    print(f'题材重复率: {metrics.get(\"theme_duplication_rate\", 0):.1%}')
    
except Exception as e:
    print(f'读取结果失败: {e}')
"
    fi
else
    echo "❌ 增强系统评估失败!"
    echo "📁 查看错误日志: ${LOG_FILE}"
    
    # 显示日志尾部
    echo -e "\n🔍 错误日志尾部:"
    tail -20 "${LOG_FILE}"
    
    exit 1
fi
