#!/bin/bash

echo "🚀 开始重新生成修复数据结构后的事件数据..."
echo "时间: $(date)"
echo ""

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

# 检查文件大小
FILE_SIZE=$(wc -c < "$DATA_FILE")
echo "📊 文件大小: $((FILE_SIZE/1024)) KB"
echo ""

# 检查数据条数
echo "🔍 检查数据条数..."
python3 -c "
import json
with open('$DATA_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)
if isinstance(data, list):
    print(f'✅ 数据是列表格式，共 {len(data)} 条新闻')
    # 显示前3条的信息
    for i in range(min(3, len(data))):
        news = data[i]
        print(f'  新闻 {i+1}: {news.get(\"test_id\", \"N/A\")} - {news.get(\"title\", \"无标题\")[:30]}...')
else:
    print('❌ 数据格式不是列表')
"

echo ""
echo "⚠️  注意：重新生成76条数据可能需要15-30分钟"
echo "    取决于API响应速度和网络状况"
echo ""

read -p "是否继续？(y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "操作取消"
    exit 0
fi

echo ""
echo "⚡ 开始重新生成..."
echo ""

# 创建日志目录
mkdir -p evaluate_service/data/results/logs

# 运行重新生成脚本
START_TIME=$(date +%s)
python evaluate_service/scripts/regenerate_fixed_events.py 2>&1 | tee evaluate_service/data/results/logs/fixed_regeneration_$(date +%Y%m%d_%H%M%S).log

EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "⏱️  总耗时: $((DURATION / 60))分$((DURATION % 60))秒"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 重新生成完成!"
    echo ""
    
    # 检查生成的文件
    GENERATED_FILE="evaluate_service/data/processed/validation_events_fixed.json"
    if [ -f "$GENERATED_FILE" ]; then
        echo "📊 生成的文件:"
        echo "   📄 事件数据: $GENERATED_FILE"
        
        # 显示基本信息（更新为新数据结构）
        python3 -c "
import json
try:
    data = json.load(open('$GENERATED_FILE'))
    meta = data.get('metadata', {})
    events = data.get('events', [])
    
    print(f'   生成时间: {meta.get(\"generated_at\", \"N/A\")}')
    print(f'   事件数量: {len(events)}')
    print(f'   成功率: {meta.get(\"success_rate\", 0):.1%}')
    print(f'   总耗时: {meta.get(\"processing_stats\", {}).get(\"total_time_minutes\", 0):.1f} 分钟')
    print(f'   平均处理时间: {meta.get(\"processing_stats\", {}).get(\"avg_time_per_event\", 0):.1f} 秒/条')
    
    # 显示新数据结构检查
    if events:
        first_event = events[0]
        print(f'\\n📋 新数据结构检查:')
        print(f'   新闻ID: {first_event.get(\"news_id\", \"N/A\")}')
        
        # 检查新字段
        if 'event_info' in first_event:
            print(f'   事件类型: {first_event[\"event_info\"].get(\"event_type\", \"N/A\")}')
            print(f'   事件置信度: {first_event[\"event_info\"].get(\"event_confidence\", \"N/A\")}')
        
        if 'theme_discovery_directive' in first_event:
            print(f'   决策动作: {first_event[\"theme_discovery_directive\"].get(\"action\", \"N/A\")}')
            print(f'   决策置信度: {first_event[\"theme_discovery_directive\"].get(\"decision_confidence\", \"N/A\")}')
        
        if 'original_news' in first_event:
            content_len = len(first_event[\"original_news\"].get(\"content\", \"\"))
            print(f'   原始内容长度: {content_len} 字符')
        
        # 检查是否有冗余字段
        redundant_fields = ['summary', 'raw_ai_response', 'ai_response', 'data_integrity', 'extraction_metadata']
        has_redundant = any(field in first_event for field in redundant_fields)
        print(f'   是否有冗余字段: {\"❌ 有\" if has_redundant else \"✅ 无\"}')
        
        # 显示核心字段
        print(f'\\n📝 核心字段检查:')
        expected_fields = ['news_id', 'event_info', 'theme_discovery_directive', 'original_news']
        for field in expected_fields:
            has_field = field in first_event
            print(f'   {field}: {\"✅\" if has_field else \"❌\"}')
        
except Exception as e:
    print(f'读取文件失败: {e}')
"
    else
        echo "❌ 生成的文件不存在"
    fi
    
    # 检查是否覆盖了原有的enhanced文件
    ENHANCED_FILE="evaluate_service/data/processed/validation_events_enhanced.json"
    if [ -f "$ENHANCED_FILE" ]; then
        echo ""
        echo "⚠️  注意: 已存在原有的enhanced文件"
        echo "    新修复文件: $GENERATED_FILE"
        echo "    旧文件: $ENHANCED_FILE"
        echo ""
        
        # 检查两个文件的大小
        NEW_SIZE=$(wc -c < "$GENERATED_FILE" 2>/dev/null || echo "0")
        OLD_SIZE=$(wc -c < "$ENHANCED_FILE" 2>/dev/null || echo "0")
        echo "📊 文件大小对比:"
        echo "  新文件: $((NEW_SIZE/1024)) KB"
        echo "  旧文件: $((OLD_SIZE/1024)) KB"
        echo ""
        
        echo "建议操作:"
        echo "1. 备份旧文件:"
        echo "   mv $ENHANCED_FILE ${ENHANCED_FILE}.backup"
        echo ""
        echo "2. 使用新文件:"
        echo "   mv $GENERATED_FILE $ENHANCED_FILE"
        echo ""
        echo "3. 或者直接覆盖:"
        echo "   cp $GENERATED_FILE $ENHANCED_FILE"
        echo ""
        echo "4. 要查看新文件结构:"
        echo "   python3 -c \"import json; data=json.load(open('$GENERATED_FILE')); print(json.dumps(data['events'][0], indent=2, ensure_ascii=False)[:500])\""
    else
        echo ""
        echo "📌 可以直接将新文件重命名为enhanced文件:"
        echo "   mv $GENERATED_FILE $ENHANCED_FILE"
    fi
    
    echo ""
    echo "🎯 下一步:"
    echo "  1. 确认数据结构正确"
    echo "  2. 运行: mv $GENERATED_FILE $ENHANCED_FILE"
    echo "  3. 继续修复related_theme_fetcher.py"
    
else
    echo "❌ 重新生成失败，退出代码: $EXIT_CODE"
    exit $EXIT_CODE
fi

echo ""
echo "✨ 脚本执行完成！"