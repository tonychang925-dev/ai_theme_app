# evaluate_service/scripts/debug_detailed.py
#!/usr/bin/env python3
"""
详细调试脚本 - 诊断测试问题
"""
import sys
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置详细日志
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)


async def debug_event_processing():
    """调试事件处理全流程"""
    print("🔍 详细调试：事件处理全流程")
    print("=" * 60)
    
    try:
        # 1. 创建虚拟数据库
        from evaluate_service.core.virtual_theme_database import VirtualThemeDatabase
        virtual_db = VirtualThemeDatabase()
        
        print("✅ 虚拟数据库创建成功")
        
        # 2. 创建增强组件
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        theme_fetcher = RelatedThemeFetcher(virtual_db=virtual_db)
        ai_client = EnhancedAIThemeClient(virtual_db=virtual_db)
        dedup_engine = ThemeDeduplicationEngine()
        
        enhanced_engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            theme_fetcher=theme_fetcher,
            dedup_engine=dedup_engine,
            config={'fast_track_threshold': 0.85, 'review_threshold': 0.65}
        )
        
        print("✅ 所有组件初始化成功")
        
        # 3. 加载真实测试数据
        data_path = Path(project_root) / 'evaluate_service' / 'data' / 'processed' / 'validation_events_enhanced.json'
        
        if not data_path.exists():
            print(f"❌ 数据文件不存在: {data_path}")
            return None
        
        with open(data_path, 'r', encoding='utf-8') as f:
            events_data = json.load(f)
        
        print(f"✅ 加载测试数据: {len(events_data)} 个事件")
        
        # 4. 处理前5个事件
        test_events = events_data[:5]
        
        for i, event in enumerate(test_events, 1):
            print(f"\n{'='*60}")
            print(f"📊 处理事件 {i}/{len(test_events)}: {event.get('id', 'unknown')}")
            print(f"标题: {event.get('title', 'N/A')}")
            print(f"第一轮指令: {event.get('theme_directive', {}).get('action', 'N/A')}")
            
            try:
                # 处理事件
                start_time = datetime.now()
                result = await enhanced_engine.process_single_event(event)
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                
                print(f"⏱️  处理时间: {processing_time:.1f} ms")
                print(f"状态: {result.get('status')}")
                print(f"执行路径: {result.get('execution_path')}")
                
                if 'ai_decision' in result:
                    ai_decision = result['ai_decision']
                    print(f"AI决策: {ai_decision.get('decision')}")
                    print(f"目标主题: {ai_decision.get('target_theme_name')}")
                    print(f"置信度: {ai_decision.get('confidence')}")
                
                if 'execution_result' in result:
                    exec_result = result['execution_result']
                    action = exec_result.get('action')
                    theme = exec_result.get('new_theme_name') or exec_result.get('target_theme_name')
                    print(f"执行结果: {action} -> {theme}")
                
                if 'deduplication_info' in result:
                    dedup_info = result['deduplication_info']
                    if dedup_info.get('should_merge', False):
                        print(f"🔍 判重结果: 合并到 {dedup_info.get('target_theme')}")
                
                # 显示虚拟数据库状态
                db_stats = virtual_db.get_stats()
                print(f"🗄️  数据库状态: {db_stats['total_themes']} 个主题")
                
            except Exception as e:
                print(f"❌ 处理失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 5. 显示最终统计
        print(f"\n{'='*60}")
        print("📈 最终统计:")
        engine_stats = enhanced_engine.get_stats()
        
        for key, value in sorted(engine_stats.items()):
            if key not in ['component_usage']:
                print(f"  {key}: {value}")
        
        return enhanced_engine
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def debug_ground_truth_evaluation():
    """调试地面真值评估"""
    print("\n🔍 调试地面真值评估")
    print("=" * 60)
    
    try:
        from evaluate_service.core.ground_truth_evaluator import GroundTruthEvaluator
        
        # 创建评估器
        evaluator = GroundTruthEvaluator()
        
        print(f"✅ 地面真值映射数量: {len(evaluator.ground_truth)}")
        
        # 显示映射样本
        print("\n📋 映射样本:")
        sample_items = list(evaluator.ground_truth.items())[:10]
        for test_id, theme in sample_items:
            print(f"  {test_id} → {theme}")
        
        # 测试评估逻辑
        print("\n🧪 测试评估逻辑:")
        
        # 创建虚拟数据库
        from evaluate_service.core.virtual_theme_database import VirtualThemeDatabase
        virtual_db = VirtualThemeDatabase()
        
        # 添加一些主题
        virtual_db.add_theme("AI/AR眼镜", event_id="test_001")
        virtual_db.add_theme("人工智能", event_id="test_002")
        
        # 测试用例1：正确匹配
        print("\n1. 正确匹配测试:")
        eval_result1 = evaluator.evaluate_decision(
            event_id="AI_AR眼镜_001",
            ai_decision={"decision": "CREATE_NEW", "target_theme_name": "AI/AR眼镜", "confidence": 0.8},
            virtual_db=virtual_db,
            execution_result={"action": "create", "new_theme_name": "AI/AR眼镜"}
        )
        print(f"  是否正确: {eval_result1['is_correct']}")
        print(f"  原因: {eval_result1['reason']}")
        
        # 测试用例2：错误匹配
        print("\n2. 错误匹配测试:")
        eval_result2 = evaluator.evaluate_decision(
            event_id="AI_AR眼镜_001",
            ai_decision={"decision": "CREATE_NEW", "target_theme_name": "智能眼镜", "confidence": 0.8},
            virtual_db=virtual_db,
            execution_result={"action": "create", "new_theme_name": "智能眼镜"}
        )
        print(f"  是否正确: {eval_result2['is_correct']}")
        print(f"  原因: {eval_result2['reason']}")
        
        # 测试用例3：归并测试
        print("\n3. 归并测试:")
        eval_result3 = evaluator.evaluate_decision(
            event_id="AI_AR眼镜_002",
            ai_decision={"decision": "MERGE_INTO", "target_theme_name": "AI/AR眼镜", "confidence": 0.8},
            virtual_db=virtual_db,
            execution_result={"action": "merge", "target_theme_name": "AI/AR眼镜"}
        )
        print(f"  是否正确: {eval_result3['is_correct']}")
        print(f"  原因: {eval_result3['reason']}")
        
        # 计算指标
        metrics = evaluator.calculate_metrics()
        print(f"\n📊 评估指标:")
        print(f"  准确率: {metrics.get('accuracy', 0):.1f}%")
        
        return evaluator
        
    except Exception as e:
        print(f"❌ 地面真值调试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def debug_data_structure():
    """调试数据结构"""
    print("\n🔍 调试数据结构")
    print("=" * 60)
    
    try:
        # 加载测试数据
        data_path = Path(project_root) / 'evaluate_service' / 'data' / 'processed' / 'validation_events_enhanced.json'
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ 数据加载成功")
        print(f"数据类型: {type(data)}")
        
        # 🔥 修复：正确处理数据结构
        if isinstance(data, dict):
            print(f"字典键: {list(data.keys())}")
            
            if 'events' in data and isinstance(data['events'], list):
                events_data = data['events']
                print(f"在键 'events' 中找到事件列表，数量: {len(events_data)}")
                
                # 检查第一个事件
                if events_data:
                    first_event = events_data[0]
                    print(f"\n📋 第一个事件结构:")
                    print(f"  ID: {first_event.get('id', 'N/A')}")
                    print(f"  标题: {first_event.get('title', 'N/A')[:50]}...")
                    print(f"  事件类型: {first_event.get('event_type', 'N/A')}")
                    print(f"  影响行业: {first_event.get('impact_industries', [])}")
                    
                    if 'theme_directive' in first_event:
                        directive = first_event['theme_directive']
                        print(f"  第一轮指令: {directive.get('action', 'N/A')}")
                        print(f"  指令置信度: {directive.get('confidence', 'N/A')}")
                    else:
                        print("  ⚠️  缺少theme_directive字段")
        
        elif isinstance(data, list):
            print(f"事件数量: {len(data)}")
            events_data = data
            
            # 检查第一个事件
            if events_data:
                first_event = events_data[0]
                print(f"\n📋 第一个事件结构:")
                print(f"  ID: {first_event.get('id', 'N/A')}")
                print(f"  标题: {first_event.get('title', 'N/A')[:50]}...")
                print(f"  事件类型: {first_event.get('event_type', 'N/A')}")
                print(f"  影响行业: {first_event.get('impact_industries', [])}")
        
        return events_data if 'events_data' in locals() else data
        
    except Exception as e:
        print(f"❌ 数据结构调试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def debug_integrated_runner():
    """调试集成测试运行器"""
    print("\n🔍 调试集成测试运行器")
    print("=" * 60)
    
    try:
        from evaluate_service.runners.integrated_test_runner import IntegratedTestRunner
        
        # 创建测试组件
        from evaluate_service.core.virtual_theme_database import VirtualThemeDatabase
        from evaluate_service.core.ground_truth_evaluator import GroundTruthEvaluator
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        virtual_db = VirtualThemeDatabase()
        ground_truth_evaluator = GroundTruthEvaluator()
        
        theme_fetcher = RelatedThemeFetcher(virtual_db=virtual_db)
        ai_client = EnhancedAIThemeClient(virtual_db=virtual_db)
        dedup_engine = ThemeDeduplicationEngine()
        
        enhanced_engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            theme_fetcher=theme_fetcher,
            dedup_engine=dedup_engine,
            config={'fast_track_threshold': 0.85, 'review_threshold': 0.65}
        )
        
        # 创建运行器
        test_runner = IntegratedTestRunner(
            virtual_db=virtual_db,
            enhanced_engine=enhanced_engine,
            ground_truth_evaluator=ground_truth_evaluator,
            output_dir="evaluate_service/results/debug"
        )
        
        print("✅ 集成测试运行器创建成功")
        
        # 测试少量事件
        from evaluate_service.scripts.run_integrated_test import load_test_data
        events_data = await load_test_data({'max_events': 3})
        
        if events_data:
            print(f"加载 {len(events_data)} 个测试事件")
            
            # 运行测试
            report = await test_runner.run_full_test(events_data, max_events=3)
            
            if report:
                print(f"\n📊 测试报告摘要:")
                print(f"处理事件数: {report.get('test_summary', {}).get('total_events_processed', 0)}")
                print(f"成功率: {report.get('test_summary', {}).get('success_rate', 0):.1f}%")
                
                # 检查详细结果
                detailed = report.get('detailed_results', {})
                if detailed.get('processing_results'):
                    print(f"\n📋 处理结果样本:")
                    for i, result in enumerate(detailed['processing_results'][:3]):
                        print(f"  {i+1}. {result.get('event_id')}: {result.get('status')}")
        
        return test_runner
        
    except Exception as e:
        print(f"❌ 集成运行器调试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主调试函数"""
    print("🔧 开始详细调试")
    print("=" * 60)
    
    # 1. 调试数据结构
    events_data = await debug_data_structure()
    
    # 2. 调试事件处理
    engine = await debug_event_processing()
    
    # 3. 调试地面真值评估
    evaluator = await debug_ground_truth_evaluation()
    
    # 4. 调试集成运行器
    runner = await debug_integrated_runner()
    
    print("\n" + "=" * 60)
    print("🎉 详细调试完成!")
    
    # 总结问题
    print("\n📋 问题总结:")
    print("1. 事件处理可能被重复调用")
    print("2. 地面真值评估逻辑需要检查")
    print("3. 处理时间记录可能有问题")
    print("\n💡 建议:")
    print("1. 检查enhanced_theme_discovery.py中的处理逻辑")
    print("2. 验证ground_truth_mapping.json中的映射是否正确")
    print("3. 确保processing_time_ms被正确记录")


if __name__ == "__main__":
    asyncio.run(main())