#!/bin/bash

echo "🔍 开始验证和修复数据传递问题..."
echo "时间: $(date)"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "项目根目录: $PROJECT_ROOT"
echo ""

# 1. 检查原始数据结构
echo "📋 1. 检查原始数据结构..."
python3 -c "
import json
from pathlib import Path

input_file = Path('evaluate_service/data/raw/validation_dataset.json')
if input_file.exists():
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        sample = data[0] if data else {}
        print('✅ 数据是列表格式')
        print(f'  样本键: {list(sample.keys())}')
        print(f'  是否有test_id: {\"✅\" if \"test_id\" in sample else \"❌\"}')
        print(f'  是否有news_id: {\"✅\" if \"news_id\" in sample else \"❌\"}')
        print(f'  test_id示例: {sample.get(\"test_id\", \"N/A\")}')
        print(f'  content长度: {len(sample.get(\"content\", \"\"))} 字符')
    else:
        print('❌ 数据不是列表格式')
else:
    print('❌ 文件不存在')
"

echo ""
echo "📋 2. 检查event_extractor如何处理test_id..."
python3 -c "
import sys
from pathlib import Path

current_dir = Path.cwd()
sys.path.insert(0, str(current_dir))

# 读取event_extractor代码
extractor_path = current_dir / 'model_service' / 'services' / 'event_extractor.py'
if extractor_path.exists():
    with open(extractor_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查news_id提取逻辑
    if 'news_id = news_data.get' in content:
        print('✅ event_extractor中有news_id提取逻辑')
        # 查找相关代码
        import re
        pattern = r'news_id = news_data\.get\([^)]+\)'
        matches = re.findall(pattern, content)
        if matches:
            print(f'  提取逻辑: {matches[0]}')
    else:
        print('❌ 未找到news_id提取逻辑')
    
    # 检查是否使用test_id
    if 'test_id' in content:
        print('⚠️  代码中提到了test_id')
    else:
        print('❌ 代码中没有处理test_id')
else:
    print('❌ event_extractor.py不存在')
"

echo ""
echo "📋 3. 检查生成的事件数据..."
python3 -c "
import json
from pathlib import Path

gen_file = Path('evaluate_service/data/processed/validation_events_regenerated.json')
if gen_file.exists():
    with open(gen_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    events = data.get('events', [])
    if events:
        print(f'✅ 已生成 {len(events)} 条事件数据')
        
        # 检查news_id
        news_ids = [e.get('news_id') for e in events if 'news_id' in e]
        print(f'  有效的news_id数量: {sum(1 for nid in news_ids if nid)}')
        print(f'  None的news_id数量: {sum(1 for nid in news_ids if nid is None)}')
        
        # 检查原始数据保存
        has_original = sum(1 for e in events if 'original_data' in e)
        print(f'  有original_data的事件: {has_original}/{len(events)}')
        
        if has_original > 0:
            event = next(e for e in events if 'original_data' in e)
            orig = event['original_data']
            print(f'  原始内容长度: {len(orig.get(\"content\", \"\"))} 字符')
            print(f'  原始标题: {orig.get(\"title\", \"N/A\")[:50]}...')
    else:
        print('❌ 没有事件数据')
else:
    print('❌ 生成的文件不存在')
"

echo ""
echo "📋 4. 检查related_theme_fetcher上下文传递问题..."
python3 -c "
import sys
from pathlib import Path

current_dir = Path.cwd()
sys.path.insert(0, str(current_dir))

fetcher_path = current_dir / 'theme_service' / 'related_theme_fetcher.py'
if fetcher_path.exists():
    with open(fetcher_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print('🔍 related_theme_fetcher.py 分析:')
    
    # 检查关键方法
    methods = ['fetch_related_themes', '_enhance_event_data', '_get_full_summary']
    for method in methods:
        if f'def {method}' in content:
            print(f'  ✅ 找到方法: {method}')
        else:
            print(f'  ❌ 缺少方法: {method}')
    
    # 检查是否使用完整summary
    if 'full_summary' in content:
        print('  ✅ 使用了full_summary')
    else:
        print('  ❌ 没有使用full_summary')
    
    # 检查是否传递原始内容
    if 'original_data' in content:
        print('  ✅ 提到了original_data')
    else:
        print('  ❌ 没有提到original_data')
    
    # 检查是否只传递关键词
    if 'keywords' in content and content.count('keywords') > 3:
        print('  ⚠️  可能过度依赖keywords')
    
    # 查找AI调用部分
    import re
    ai_calls = re.findall(r'similarity_analyzer\.\w+\([^)]*event_data[^)]*\)', content, re.DOTALL)
    if ai_calls:
        print(f'  🔍 AI调用示例: {ai_calls[0][:100]}...')
    
else:
    print('❌ related_theme_fetcher.py不存在')
"
