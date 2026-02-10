#!/bin/bash
# evaluate_service/runners/run_enhanced.sh

echo "🚀 开始增强系统评估测试..."

# 设置Python路径
export PYTHONPATH=.:$PYTHONPATH

# 创建结果目录
mkdir -p data/results/enhanced
mkdir -p logs

# 运行增强系统评估
echo "📊 运行增强系统评估..."
python -m scripts.evaluators.enhanced_evaluator > logs/enhanced_eval_$(date +%Y%m%d_%H%M%S).log 2>&1

if [ $? -eq 0 ]; then
    echo "✅ 增强系统评估完成!"
else
    echo "❌ 增强系统评估失败!"
    exit 1
fi

# 运行对比分析
echo "📈 运行对比分析..."
python -m scripts.evaluators.comparison_evaluator > logs/comparison_$(date +%Y%m%d_%H%M%S).log 2>&1

if [ $? -eq 0 ]; then
    echo "✅ 对比分析完成!"
else
    echo "❌ 对比分析失败!"
    exit 1
fi

echo "🎉 增强系统评估流程全部完成!"
echo "📁 结果保存在: data/results/enhanced/"
echo "📁 对比报告在: data/results/comparison/"