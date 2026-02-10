#!/usr/bin/env python3
# test_fixed_decision_executor.py
"""
测试修复后的DecisionExecutor
"""

import sys
sys.path.append('/Users/admin/Desktop/ai_theme_app')
import asyncio

print("🧪 测试修复后的DecisionExecutor参数提取")
print("="*80)

async def test_fixed_params():
    # 模拟theme_rule_generator生成的完整数据
    from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed
    
    event_data = {
        'event_id': 'test_event_fix',
        'event_type': 'major',
        'title': '对日制裁相关新闻',
        'ai_analysis': {
            'core_concept': '日本首相参拜靖国神社引发地区紧张',
            'event_keywords': ['地缘政治', '国际关系', '东亚安全'],
            'summary': '日本首相参拜靖国神社引发地区紧张局势',
            'concept_confidence': 0.85,
            'impact_level': 'high'
        }
    }
    
    # 生成数据
    generator = ThemeRuleBasedGeneratorFixed([])
    dto = generator.generate_theme_data_only(event_data)
    theme_data = dto.theme_data
    
    print("📊 theme_rule_generator生成的原始数据:")
    print(f"   字段数: {len(theme_data)}")
    print(f"   关键字段:")
    for key in ['name', 'code', 'theme_type', 'level1_category', 'category1_code',
                'heat_score', 'confidence_score', 'source_system', 'source_id']:
        print(f"     {key}: {theme_data.get(key, '[未找到]')}")
    
    # 测试DecisionExecutor的参数提取
    print(f"\n🔧 测试DecisionExecutor参数提取:")
    
    # 创建DecisionExecutor实例（不实际运行）
    class MockRedis:
        pass
    
    class MockDBGateway:
        pass
    
    from database_service.streams.handlers.DecisionExecutor import DecisionExecutor
    executor = DecisionExecutor(MockRedis(), MockDBGateway(), "test")
    
    # 测试旧方法
    print("   1. 旧方法 (_prepare_theme_create_args_safe):")
    try:
        old_args = executor._prepare_theme_create_args_safe(theme_data)
        print(f"     提取字段数: {len(old_args)}")
        print(f"     字段: {list(old_args.keys())}")
        
        # 检查缺失的关键字段
        missing = []
        for field in ['level1_category', 'category1_code']:
            if field not in old_args:
                missing.append(field)
        
        if missing:
            print(f"     ❌ 缺失字段: {missing}")
        else:
            print(f"     ✅ 关键字段都存在")
    except Exception as e:
        print(f"     ❌ 旧方法失败: {e}")
    
    # 测试新方法（如果已添加）
    print(f"\n   2. 新方法 (_prepare_theme_create_args_complete):")
    try:
        # 添加新方法到executor（临时）
        def new_method(theme_data):
            """临时测试方法"""
            args = {
                'name': theme_data.get('name', ''),
                'code': theme_data.get('code', ''),
                'theme_type': theme_data.get('theme_type', 'concept'),
                'description': theme_data.get('description', ''),
                'status': theme_data.get('status', 'active'),
                'tags': theme_data.get('tags', {}),
                'heat_score': theme_data.get('heat_score', 50),
                'confidence_score': theme_data.get('confidence_score', 0.5),
                'lifecycle_stage': theme_data.get('lifecycle_stage', 'emerging'),
                'source_system': theme_data.get('source_system', 'ai_theme_discovery'),
                'source_id': theme_data.get('source_id', 'unknown'),
                'created_by': theme_data.get('created_by', 'theme_service'),
                'level1_category': theme_data.get('level1_category'),
                'level2_category': theme_data.get('level2_category'),
                'level3_category': theme_data.get('level3_category'),
                'category1_code': theme_data.get('category1_code'),
                'category2_code': theme_data.get('category2_code'),
                'category3_code': theme_data.get('category3_code'),
                'category_path': theme_data.get('category_path', []),
            }
            return args
        
        new_args = new_method(theme_data)
        print(f"     提取字段数: {len(new_args)}")
        print(f"     关键字段检查:")
        
        key_fields = ['level1_category', 'category1_code', 'heat_score', 'source_system']
        for field in key_fields:
            value = new_args.get(field)
            if value:
                print(f"       ✅ {field}: {value}")
            else:
                print(f"       ❌ {field}: 未找到或为空")
                
    except Exception as e:
        print(f"     ❌ 测试失败: {e}")

# 运行测试
asyncio.run(test_fixed_params())