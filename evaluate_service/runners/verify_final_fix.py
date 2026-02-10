# evaluate_service/runners/verify_final_fix.py
"""
验证最终修复效果
"""
#!/usr/bin/env python3
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print("🔍 验证最终修复效果")
print("="*80)

# 测试数据
test_event = {
    'news_id': 'test',
    'original_news': {'title': '测试', 'content': '内容'},
    'event_info': {'event_type': '测试', 'impact_industries': []}
}

test_themes = [{
    'name': '测试主题',
    'description': '测试',
    'keywords': ['测试'],
    'has_complete_content': True,
    'related_news_full_contents': [{
        'title': '测试新闻',
        'content': '内容',
        'content_length': 10,
        'event_id': 'test'
    }]
}]

try:
    from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
    
    analyzer = AIThemeSimilarityAnalyzer(None)
    prompt = analyzer._build_enhanced_prompt(test_event, test_themes)
    
    # 验证关键修复点
    enhancements = [
        ("包含'🔥 核心判断原则'强调", "🔥 核心判断原则"),
        ("包含'必须基于完整内容分析'要求", "必须基于完整内容分析"),
        ("输出格式包含'content_based_analysis'", '"content_based_analysis"'),
        ("输出格式包含'content_comparison'", '"content_comparison"'),
        ("包含'重要提醒'强调完整内容", "完整新闻内容"),
        ("保持原有任务1结构", "任务1：提取核心主题名称"),
        ("保持原有任务2结构", "任务2：相似性分析"),
        ("包含具体判断规则", "不应该匹配"),
        ("包含投资逻辑一致性原则", "投资逻辑一致性"),
    ]
    
    print("✅ 修复增强验证结果：")
    print("-"*40)
    
    all_ok = True
    for name, keyword in enhancements:
        if keyword in prompt:
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}")
            all_ok = False
    
    print("\n" + "="*80)
    
    if all_ok:
        print("🎉 修复完全成功！")
        print("  1. 保持了原有任务结构")
        print("  2. 增强了内容要求")
        print("  3. 提供了具体判断规则")
        print("  4. 强制AI基于完整内容分析")
    else:
        print("⚠️  修复不完整")
        
    # 显示关键改进片段
    print("\n🔍 关键改进片段：")
    print("-"*40)
    
    lines = prompt.split('\n')
    for i, line in enumerate(lines):
        if any(keyword in line for keyword in ['🔥', '必须基于', '完整内容', '投资逻辑', '不应该匹配']):
            print(f"{line[:80]}")
    
except Exception as e:
    print(f"❌ 验证失败: {e}")

print("\n" + "="*80)