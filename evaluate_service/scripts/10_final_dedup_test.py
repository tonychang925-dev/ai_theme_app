#!/usr/bin/env python3
"""
最终判重集成测试 - 使用修复版AI客户端
"""
import asyncio
import sys
from pathlib import Path
import logging

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def final_dedup_test():
    """最终判重测试"""
    print("=" * 70)
    print("🎯 最终判重集成测试")
    print("使用修复版AI客户端")
    print("=" * 70)
    
    try:
        # 导入模块
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        # 使用修复版AI客户端（需要先保存上面的代码）
        # 这里我们先创建一个临时修复版本
        class FinalTestAIClient:
            def __init__(self):
                self.event_configs = {
                    "test_exact_duplicate": {"decision": "MERGE_INTO", "confidence": 0.75},
                    "test_inclusion_duplicate": {"decision": "MERGE_INTO", "confidence": 0.72},
                    "test_semantic_duplicate": {"decision": "MERGE_INTO", "confidence": 0.74},
                    "test_unique": {"decision": "CREATE_NEW", "confidence": 0.90}
                }
            
            async def analyze_event_with_context(self, event_data, related_themes):
                event_id = event_data.get('id', '')
                config = self.event_configs.get(event_id, {"decision": "CREATE_NEW", "confidence": 0.80})
                
                # 智能生成目标题材名
                title = event_data.get('title', '')
                if config["decision"] == "MERGE_INTO" and related_themes:
                    target_name = related_themes[0].get('name', '默认题材')
                else:
                    target_name = f"{title[:8]}题材"
                
                return {
                    "decision": config["decision"],
                    "target_theme_name": target_name,
                    "confidence": config["confidence"],
                    "reason": "最终测试",
                    "source": "final_test"
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
        
        # 创建引擎
        ai_client = FinalTestAIClient()
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            dedup_engine=dedup_engine,
            config={
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3
            }
        )
        
        # 测试事件
        test_events = [
            {
                "id": "test_exact_duplicate",
                "title": "人工智能",
                "summary": "人工智能事件",
                "event_type": "技术",
                "impact_industries": ["人工智能"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.75, "reason": "测试"}
            },
            {
                "id": "test_inclusion_duplicate",
                "title": "人工智能芯片技术",
                "summary": "人工智能芯片技术",
                "event_type": "技术突破",
                "impact_industries": ["人工智能", "半导体"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.78, "reason": "测试"}
            },
            {
                "id": "test_unique",
                "title": "量子计算突破",
                "summary": "量子计算突破",
                "event_type": "技术突破",
                "impact_industries": ["量子计算"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.85, "reason": "测试"}
            }
        ]
        
        # 运行测试
        results = []
        duplicates_detected = 0
        
        print(f"\n🚀 运行 {len(test_events)} 个测试用例")
        print("=" * 70)
        
        for event in test_events:
            print(f"\n📝 事件: {event['title']}")
            print(f"  Directive: {event['theme_directive']['action']} (置信度: {event['theme_directive']['confidence']:.2f})")
            
            result = await engine.process_single_event(event)
            results.append(result)
            
            print(f"  执行路径: {result.get('execution_path')}")
            print(f"  状态: {result.get('status')}")
            
            dedup_info = result.get('deduplication_info', {})
            if dedup_info.get('should_merge', False):
                duplicates_detected += 1
                print(f"  🔥 检测到重复！合并到: {dedup_info.get('target_theme')}")
                print(f"     相似度: {dedup_info.get('similarity', 0):.2f}")
                print(f"     匹配类型: {dedup_info.get('match_type')}")
            else:
                print(f"  ✅ 未检测到重复")
        
        # 结果统计
        print(f"\n{'='*70}")
        print("📊 最终统计")
        print("=" * 70)
        
        stats = engine.get_stats()
        guided_create = stats.get('guided_create_path', 0) + stats.get('guided_merge_path', 0)
        dedup_checks = stats.get('component_usage', {}).get('dedup_engine_used', 0)
        
        print(f"总处理事件: {len(test_events)}")
        print(f"guided_create/merge路径: {guided_create}")
        print(f"判重检查次数: {dedup_checks}")
        print(f"检测到的重复数: {duplicates_detected}")
        
        if guided_create > 0:
            print(f"判重检查率: {dedup_checks/guided_create*100:.1f}%")
        
        print(f"\n{'='*70}")
        if duplicates_detected > 0:
            print("🎉 成功！判重功能检测到了重复！")
            return True
        else:
            print("❌ 仍然未检测到重复")
            print("需要进一步调试判重引擎的匹配逻辑")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    success = await final_dedup_test()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ 最终测试成功！判重功能正常工作")
    else:
        print("❌ 最终测试失败")
        print("建议：")
        print("1. 检查判重引擎的包含关系检测逻辑")
        print("2. 降低inclusion_match阈值")
        print("3. 扩展同义词词典")
    print("=" * 70)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))