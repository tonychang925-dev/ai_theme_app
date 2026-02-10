#!/bin/bash
# evaluate_service/runners/run_data_integrity_validation.sh
#!/bin/bash

echo "🔍 开始数据完整性验证..."
echo "时间: $(date)"

# 进入项目根目录
cd "$(dirname "$0")/../.." || exit 1

# 检查文件是否存在
if [ ! -f "evaluate_service/data/processed/validation_events_regenerated.json" ]; then
    echo "❌ 重新生成的事件数据不存在，请先运行事件重新生成评估"
    echo "运行: ./evaluate_service/runners/run_event_regeneration.sh"
    exit 1
fi

# 运行完整性验证器
echo "运行数据完整性验证器..."
python evaluate_service/scripts/data_integrity_validator.py 2>&1 | tee evaluate_service/data/results/logs/data_integrity_$(date +%Y%m%d_%H%M%S).log

# 检查结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 数据完整性验证完成!"
    echo ""
    echo "📋 生成的文件:"
    echo "   📊 验证报告: evaluate_service/data/results/reports/data_integrity_report.json"
    echo ""
    # 显示摘要
    python -c "
import json
try:
    report = json.load(open('evaluate_service/data/results/reports/data_integrity_report.json'))
    summary = report['summary']
    print('📊 验证摘要:')
    print(f'   整体完整性: {summary[\"overall_integrity_score\"]:.2f}')
    print(f'   字段完整性: {summary[\"field_completeness_score\"]:.2f}')
    print(f'   内容保存率: {summary[\"content_preservation_score\"]:.2f}')
    print(f'   状态: {summary[\"status\"]}')
    if report.get('critical_issues'):
        print(f'   ⚠️  发现 {len(report[\"critical_issues\"])} 个关键问题')
except Exception as e:
    print(f'读取报告失败: {e}')
"
else
    echo "❌ 验证失败"
    exit 1
fi