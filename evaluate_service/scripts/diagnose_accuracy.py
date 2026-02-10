#!/usr/bin/env python3
"""
诊断准确率问题
"""
import json
from pathlib import Path

project_root = Path(__file__).parent.parent.parent

print("🔍 诊断准确率问题")
print("=" * 60)

# 1. 加载测试数据
data_path = project_root / 'evaluate_service' / 'data' / 'processed' / 'validation_events_enhanced.json'
with open(data_path, 'r') as f:
    data = json.load(f)

events = data['events']
print(f"1. 测试数据: {len(events)} 个事件")

# 检查前5个事件的ID
print("\n2. 前5个事件ID:")
for i in range(min(5, len(events))):
    event = events[i]
    news_id = event.get('news_id', 'N/A')
    print(f"  事件 {i+1}: news_id = {news_id}")

# 2. 加载地面真值
gt_path = project_root / 'evaluate_service' / 'config' / 'ground_truth_correct.json'
with open(gt_path, 'r') as f:
    ground_truth = json.load(f)

print(f"\n3. 地面真值: {len(ground_truth)} 个映射")

# 检查是否有匹配的news_id
matching_count = 0
for event in events[:10]:
    news_id = event.get('news_id')
    if news_id and news_id in ground_truth:
        matching_count += 1

print(f"   前10个事件中匹配地面真值的数量: {matching_count}/10")

# 3. 检查主题分布
print("\n4. 测试数据中的主题分布:")
test_themes = {}
for event in events:
    original_data = event.get('original_data', {})
    theme = original_data.get('theme', '未知')
    test_themes[theme] = test_themes.get(theme, 0) + 1

print(f"   唯一主题数: {len(test_themes)}")
for theme, count in sorted(test_themes.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"   {theme}: {count}")

# 4. 地面真值主题分布
print("\n5. 地面真值主题分布:")
gt_themes = {}
for theme in ground_truth.values():
    gt_themes[theme] = gt_themes.get(theme, 0) + 1

print(f"   唯一主题数: {len(gt_themes)}")
for theme, count in sorted(gt_themes.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"   {theme}: {count}")

# 5. 对比
print("\n6. 主题对比:")
print("   测试数据主题:", sorted(test_themes.keys())[:10])
print("   地面真值主题:", sorted(gt_themes.keys())[:10])

print("\n" + "=" * 60)
print("🎯 诊断完成!")