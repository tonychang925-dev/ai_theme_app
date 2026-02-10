#!/usr/bin/env python3
"""
快速评估测试 - 验证核心功能
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def quick_validation():
    """快速验证测试"""
    print("=" * 60)
    print("🚀 快速验证测试")
    print("验证优化方案核心功能")
    print("=" * 60)
    
    try:
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        
        print("✅ 模块导入成功")
        
        # 创建测试数据
        test_events = [
            {
                "id": "quick_test_1",
                "title": "人工智能发展规划发布",
                "summary": "国家发布人工智能发展规划",
                "event_type": "政策发布",
                "impact_industries": ["人工智能", "信息技术"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.85,
                    "reason": "重大政策"
                }
            },
            {
                "id": "quick_test_2",
                "title": "AI智能眼镜新品",
                "summary": "公司发布AI智能眼镜",
                "event_type": "产品发布",
                "impact_industries": ["人工智能", "消费电子"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.78,
                    "reason": "新产品"
                }
            }
        ]
        
        # 创建AI客户端
        class QuickAIClient:
            async def analyze_event_with_context(self, event_data, related_themes):
                event_id = event_data.get('id', '')
                
                if '人工智能' in event_data.get('title', ''):
                    return {
                        "decision": "CREATE_NEW",
                        "target_theme_name": "人工智能",
                        "confidence": 0.75,
                        "reason": "AI相关事件",
                        "source": "quick_test"
                    }
                else:
                    return {
                        "decision": "CREATE_NEW",
                        "target_theme_name": "智能穿戴",
                        "confidence": 0.80,
                        "reason": "穿戴设备",
                        "source": "quick_test"
                    }
        
        # 创建判重引擎
        dedup_config = {
            "thresholds": {
                "exact_match": 1.0,
                "inclusion_match": 0.5,
                "semantic_similarity": 0.5,
                "auto_merge": 0.6
            },
            "strategies": {
                "enable_exact_match": True,
                "enable_inclusion_check": True,
                "enable_semantic_analysis": True,
                "use_jieba": True
            }
        }
        
        dedup_engine = ThemeDeduplicationEngine(config=dedup_config)
        ai_client = QuickAIClient()
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            dedup_engine=dedup_engine,
            config={
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3
            }
        )
        
        print(f"\n🔧 创建引擎成功")
        print(f"  判重引擎: {engine.dedup_engine is not None}")
        
        # 测试事件
        print(f"\n🧪 测试 {len(test_events)} 个事件")
        print("-" * 60)
        
        results = []
        for event in test_events:
            print(f"\n📝 事件: {event['title']}")
            result = await engine.process_single_event(event)
            results.append(result)
            
            print(f"  状态: {result.get('status')}")
            print(f"  路径: {result.get('execution_path')}")
            
            dedup_info = result.get('deduplication_info', {})
            if dedup_info:
                print(f"  判重: {'合并' if dedup_info.get('should_merge') else '独立'}")
        
        # 显示统计
        print(f"\n📊 统计信息")
        print("-" * 60)
        stats = engine.get_stats()
        
        for key in ['total_processed', 'created', 'merged', 'auto_merged', 'duplicate_prevented']:
            if key in stats:
                print(f"  {key}: {stats[key]}")
        
        print(f"\n🔧 组件使用:")
        for component, count in stats.get('component_usage', {}).items():
            print(f"  {component}: {count}")
        
        # 验证关键指标
        print(f"\n✅ 验证结果")
        print("-" * 60)
        
        dedup_checks = stats.get('component_usage', {}).get('dedup_engine_used', 0)
        duplicates_detected = stats.get('duplicate_prevented', 0)
        
        if dedup_checks > 0:
            print(f"✅ 判重引擎被调用: {dedup_checks} 次")
        else:
            print(f"❌ 判重引擎未被调用")
        
        if duplicates_detected > 0:
            print(f"✅ 检测到重复: {duplicates_detected} 个")
        else:
            print(f"⚠️  未检测到重复（可能需要调整阈值）")
        
        return True
        
    except Exception as e:
        print(f"❌ 快速验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    success = await quick_validation()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 快速验证通过！可以运行全面评估测试")
        print("\n下一步:")
        print("  运行: python evaluate_service/scripts/comprehensive_evaluation.py")
    else:
        print("❌ 快速验证失败，请检查系统配置")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))