#!/usr/bin/env python3
# deep_debug_data_flow.py
"""
深度调试数据流：追踪字段丢失位置
"""

import sys
sys.path.append('/Users/admin/Desktop/ai_theme_app')
import asyncio
import json
from datetime import datetime

print("🔍 深度调试数据流")
print("="*80)

async def deep_debug():
    # 1. 生成完整数据
    print("1. 生成完整theme_data...")
    
    from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed
    
    event_data = {
        'event_id': 'deep_debug_001',
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
    
    generator = ThemeRuleBasedGeneratorFixed([])
    dto = generator.generate_theme_data_only(event_data)
    theme_data = dto.theme_data
    
    print(f"   ✅ 原始theme_data字段数: {len(theme_data)}")
    print(f"   📋 所有字段:")
    for key, value in theme_data.items():
        if value and key not in ['description', 'category_path', 'related_stocks']:
            print(f"     {key}: {value}")
    
    # 2. 模拟DecisionProcessor打包
    print(f"\n2. 模拟DecisionProcessor打包...")
    
    from theme_service.processors.decision_processor import DecisionProcessor
    
    class MockRedis:
        pass
    
    class MockDBGateway:
        pass
    
    processor = DecisionProcessor(MockRedis(), MockDBGateway(), [])
    
    # 生成决策
    decision = processor._generate_create_theme_decision(
        event_data=event_data,
        theme_generator_result=dto
    )
    
    print(f"   ✅ 决策字段: {list(decision.keys())}")
    
    # 检查complete_theme_data
    if 'complete_theme_data' in decision:
        complete = decision['complete_theme_data']
        print(f"   complete_theme_data类型: {type(complete)}")
        
        if isinstance(complete, dict):
            print(f"   complete_theme_data字段: {list(complete.keys())}")
            
            # 检查theme_data
            if 'theme_data' in complete:
                theme_in_decision = complete['theme_data']
                print(f"   theme_data类型: {type(theme_in_decision)}")
                print(f"   theme_data字段数: {len(theme_in_decision)}")
                
                # 检查关键字段
                key_fields = ['level1_category', 'category1_code', 'heat_score']
                for field in key_fields:
                    if field in theme_in_decision:
                        print(f"     ✅ {field}: {theme_in_decision[field]}")
                    else:
                        print(f"     ❌ {field}: 不在theme_data中")
                        
                # 对比原始和打包后的数据
                print(f"\n   🔄 对比原始和打包后的数据:")
                for field in key_fields:
                    original = theme_data.get(field)
                    packed = theme_in_decision.get(field)
                    if original != packed:
                        print(f"     ❌ {field}: 不一致 - 原始={original}, 打包={packed}")
                    else:
                        print(f"     ✅ {field}: 一致")
    
    # 3. 导入DecisionExecutor
    print(f"\n3. 导入DecisionExecutor...")
    
    try:
        from database_service.streams.handlers.DecisionExecutor import DecisionExecutor
        print("   ✅ 导入新版本DecisionExecutor")
        
        executor = DecisionExecutor(MockRedis(), MockDBGateway(), "deep_debug")
        
        # 4. 提取数据
        print(f"4. DecisionExecutor提取数据...")
        
        if hasattr(executor, '_extract_theme_data_safe'):
            extracted = executor._extract_theme_data_safe(decision)
            print(f"   使用_extract_theme_data_safe提取")
            
            if extracted:
                print(f"   ✅ 提取成功，字段数: {len(extracted)}")
                print(f"   关键字段检查:")
                
                key_fields = ['name', 'code', 'level1_category', 'category1_code', 'heat_score', 'source_system']
                for field in key_fields:
                    if field in extracted:
                        value = extracted[field]
                        print(f"     ✅ {field}: {value if value is not None else '[None]'}")
                    else:
                        print(f"     ❌ {field}: 未找到")
                
                # 检查数据丢失
                lost_fields = []
                for key in theme_data:
                    if key not in extracted:
                        lost_fields.append(key)
                
                if lost_fields:
                    print(f"\n   ⚠️  提取时丢失字段 ({len(lost_fields)}个):")
                    for field in lost_fields[:10]:  # 只显示前10个
                        print(f"     - {field}")
                
                # 5. 检查参数准备
                print(f"\n5. 检查参数准备...")
                
                if hasattr(executor, '_prepare_theme_create_args_safe'):
                    create_args = executor._prepare_theme_create_args_safe(extracted)
                    print(f"   准备参数数: {len(create_args)}")
                    
                    # 检查关键参数
                    key_params = ['level1_category', 'category1_code', 'heat_score', 'source_system']
                    missing_params = []
                    for param in key_params:
                        if param in create_args:
                            value = create_args[param]
                            print(f"     ✅ {param}: {value if value is not None else '[None]'}")
                        else:
                            missing_params.append(param)
                            print(f"     ❌ {param}: 不在参数中")
                    
                    if missing_params:
                        print(f"\n   🔥 问题发现: 参数准备时丢失字段: {missing_params}")
                        
                        # 查看_prepare_theme_create_args_safe方法
                        print(f"   🔍 查看_prepare_theme_create_args_safe方法实现...")
                        import inspect
                        try:
                            source = inspect.getsource(executor._prepare_theme_create_args_safe)
                            print(f"   方法源码 (前500字符):")
                            print(source[:500] + "...")
                            
                            # 检查方法中是否处理了这些字段
                            for param in missing_params:
                                if param in source:
                                    print(f"     ⚠️  {param}: 在方法代码中但未提取")
                                else:
                                    print(f"     ❌ {param}: 不在方法代码中")
                        except:
                            print(f"   无法获取方法源码")
                    else:
                        print(f"\n   ✅ 参数准备包含所有关键字段")
                        
                    # 6. 模拟数据库调用
                    print(f"\n6. 模拟数据库调用...")
                    
                    # 记录实际传递给create_theme的参数
                    actual_call_args = {}
                    
                    class TracedDBGateway:
                        async def create_theme(self, **kwargs):
                            nonlocal actual_call_args
                            actual_call_args = kwargs.copy()
                            print(f"   🗄️  create_theme被调用")
                            print(f"   实际传递参数数: {len(kwargs)}")
                            
                            # 检查关键参数
                            for param in key_params:
                                if param in kwargs:
                                    value = kwargs[param]
                                    print(f"     {'✅' if value else '❌'} {param}: {value if value is not None else '[None]'}")
                                else:
                                    print(f"     ❌ {param}: 未传递")
                            
                            # 模拟返回
                            return type('MockTheme', (), {'id': 9999, 'name': kwargs.get('name', 'mock')})()
                    
                    # 替换gateway
                    executor.db_gateway = TracedDBGateway()
                    
                    # 调用创建方法
                    print(f"\n   调用_execute_create_theme_safe...")
                    try:
                        if hasattr(executor, '_execute_create_theme_safe'):
                            result = await executor._execute_create_theme_safe(extracted)
                            print(f"   ✅ 方法执行成功")
                            
                            # 分析实际调用
                            print(f"\n   📊 实际调用分析:")
                            print(f"     实际传递参数: {list(actual_call_args.keys())}")
                            
                            # 检查丢失的参数
                            expected_from_prepare = set(create_args.keys())
                            actual_passed = set(actual_call_args.keys())
                            lost_in_call = expected_from_prepare - actual_passed
                            
                            if lost_in_call:
                                print(f"     ❌ 调用时丢失参数: {lost_in_call}")
                            else:
                                print(f"     ✅ 所有参数都传递了")
                            
                        else:
                            print(f"   ❌ 没有_execute_create_theme_safe方法")
                    except Exception as e:
                        print(f"   ❌ 执行失败: {e}")
                        
        else:
            print(f"   ❌ 没有_extract_theme_data_safe方法")
            
    except ImportError as e:
        print(f"   ❌ 导入DecisionExecutor失败: {e}")

# 运行调试
asyncio.run(deep_debug())