#!/bin/bash

echo "🚀 开始事件重新生成评估..."
echo "时间: $(date)"
echo ""

# 进入项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "项目根目录: $PROJECT_ROOT"
echo ""

# 检查环境变量
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ 错误: DEEPSEEK_API_KEY 环境变量未设置"
    echo "请运行: export DEEPSEEK_API_KEY='your-api-key-here'"
    exit 1
fi

echo "🔑 API密钥: ${DEEPSEEK_API_KEY:0:10}..."
echo ""

# 检查原始数据文件
DATA_FILE="evaluate_service/data/raw/validation_dataset.json"
if [ ! -f "$DATA_FILE" ]; then
    echo "❌ 错误: 原始数据文件不存在"
    echo "请确保文件存在: $DATA_FILE"
    exit 1
fi

echo "📋 原始数据文件: $DATA_FILE"
echo ""

# 运行评估器
echo "⚡ 运行事件重新生成评估器..."
echo ""

# 检查是否测试模式
if [ "$1" = "--test" ]; then
    echo "🧪 测试模式：只处理前5条数据"
    python evaluate_service/scripts/event_regeneration_evaluator.py --test
else
    echo "⚡ 完整模式：处理全部76条数据"
    python evaluate_service/scripts/event_regeneration_evaluator.py
fi

# 检查退出代码
EXIT_CODE=$?
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 评估完成!"
    echo ""
    
    # 检查生成的文件
    GENERATED_FILE="evaluate_service/data/processed/validation_events_regenerated.json"
    REPORT_FILE="evaluate_service/data/results/reports/event_regeneration_report.json"
    
    if [ -f "$GENERATED_FILE" ]; then
        echo "📊 生成的文件:"
        echo "   📄 事件数据: $GENERATED_FILE"
        
        # 显示基本信息
        python3 -c "
import json
try:
    data = json.load(open('$GENERATED_FILE'))
    meta = data.get('metadata', {})
    print(f'   生成时间: {meta.get(\"generated_at\", \"N/A\")}')
    print(f'   事件数量: {len(data.get(\"events\", []))}')
    print(f'   成功率: {meta.get(\"success_rate\", 0):.1%}')
    print(f'   平均完整性: {meta.get(\"avg_integrity_score\", 0):.2f}')
except Exception as e:
    print(f'读取文件失败: {e}')
"
    fi
    
    if [ -f "$REPORT_FILE" ]; then
        echo "   📊 评估报告: $REPORT_FILE"
    fi
    
else
    echo "❌ 评估失败，退出代码: $EXIT_CODE"
    exit $EXIT_CODE
fi
