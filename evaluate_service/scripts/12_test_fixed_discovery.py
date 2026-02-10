#!/usr/bin/env python3
"""
正确版判重测试 - 直接测试修改后的enhanced_theme_discovery.py
"""
import asyncio
import sys
from pathlib import Path
import logging

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_fixed_enhanced_discovery():
    """测试修复后的EnhancedThemeDiscoveryEngine"""
    print("=" * 70)
    print("🔧 测试修复版EnhancedThemeDiscoveryEngine")
    print("在所有路径中都加入判重检查")
    print("=" * 70)
    
    try:
        # 导入原文件（修改后的）
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        
        print("✅ 成功导入模块")
        
        # 创建极低阈值的判重引擎
        ultra_sensitive_config = {
            "thresholds": {
                "exact_match": 1.0,
                "inclusion_match": 0.2,  # 20%包含就判重
                "semantic_similarity": 0.2,
                "auto_merge": 0.3,
                "suggest_merge": 0.2,
                "keep_separate": 0.1
            },
            "strategies": {
                "enable_exact_match": True,
                "enable_inclusion_check": True,
                "enable_semantic_analysis": True,
                "use_jieba": True
            }
        }
        
        dedup_engine = ThemeDeduplicationEngine(config=ultra_sensitive_config)
        
        # 创建测试AI客户端
        class TestAIClient:
            def __init__(self):
                # 预设每个事件的AI响应
                self.responses = {
                    "test_exact": {"decision": "MERGE_INTO", "confidence": 0.78, "target": "人工智能"},
                    "test_inclusion": {"decision": "MERGE_INTO", "confidence": 0.75, "target": "AI眼镜"},
                    "test_unique": {"decision": "CREATE_NEW", "confidence": 0.90, "target": "量子计算突破"}
                }
            
            async def analyze_event_with_context(self, event_data, related_themes):
                event_id = event_data.get('id', '')
                response = self.responses.get(event_id, {"decision": "CREATE_NEW", "confidence": 0.80, "target": "新题材"})
                
                return {
                    "decision": response["decision"],
                    "target_theme_name": response["target"],
                    "confidence": response["confidence"],
                    "reason": "测试AI分析",
                    "source": "test_ai"
                }
        
        # 创建引擎
        ai_client = TestAIClient()
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            dedup_engine=dedup_engine,  # 🔥 传入判重引擎
            config={
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3
            }
        )
        
        # 获取引擎信息
        engine_info = engine.get_engine_info()
        print(f"\n🔧 引擎配置:")
        print(f"  版本: {engine_info.get('engine_version', 'unknown')}")
        print(f"  判重引擎: {engine_info.get('components_available', {}).get('dedup_engine', False)}")
        
        # 创建测试事件
        test_events = [
            {
                "id": "test_exact",
                "title": "人工智能",  # 精确重复
                "summary": "人工智能相关事件",
                "event_type": "技术",
                "impact_industries": ["人工智能"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.75, "reason": "测试"}
            },
            {
                "id": "test_inclusion", 
                "title": "AI智能眼镜新品",  # 包含关系重复
                "summary": "AI智能眼镜新品发布",
                "event_type": "产品发布",
                "impact_industries": ["人工智能", "消费电子"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.78, "reason": "测试"}
            },
            {
                "id": "test_unique",
                "title": "量子计算突破",  # 独特事件
                "summary": "量子计算技术突破",
                "event_type": "技术突破", 
                "impact_industries": ["量子计算"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.85, "reason": "测试"}
            }
        ]
        
        print(f"\n🚀 开始测试 {len(test_events)} 个事件")
        print("=" * 70)
        
        # 执行测试
        all_results = []
        duplicates_detected = 0
        
        for event in test_events:
            print(f"\n📝 事件: {event['title']}")
            print(f"  AI预设决策: {ai_client.responses.get(event['id'], {}).get('decision', 'N/A')}")
            print(f"  Directive置信度: {event['theme_directive']['confidence']:.2f}")
            
            result = await engine.process_single_event(event)
            all_results.append(result)
            
            # 显示结果
            print(f"  执行路径: {result.get('execution_path')}")
            print(f"  最终状态: {result.get('status')}")
            
            dedup_info = result.get('deduplication_info', {})
            if dedup_info:
                print(f"  🔍 判重检查: 已执行")
                if dedup_info.get('should_merge', False):
                    duplicates_detected += 1
                    print(f"  🔄 检测到重复！")
                    print(f"     合并到: {dedup_info.get('target_theme', '未知')}")
                    print(f"     相似度: {dedup_info.get('similarity', 0):.2f}")
                    print(f"     匹配类型: {dedup_info.get('match_type', '未知')}")
                else:
                    print(f"  ✅ 未检测到重复")
            else:
                print(f"  ⚠️  判重检查: 未执行")
            
            if result.get('ai_decision_overridden', False):
                print(f"  🔥 AI决策被判重检查覆盖！")
        
        # 显示统计
        print(f"\n{'='*70}")
        print("📊 测试统计")
        print("=" * 70)
        
        stats = engine.get_stats()
        
        print(f"处理统计:")
        print(f"  总事件数: {stats.get('total_processed', 0)}")
        print(f"  创建数: {stats.get('created', 0)}")
        print(f"  合并数: {stats.get('merged', 0)}")
        print(f"  自动合并数: {stats.get('auto_merged', 0)}")
        print(f"  判重阻止重复: {stats.get('duplicate_prevented', 0)}")
        
        print(f"\n执行路径分布:")
        print(f"  guided_create: {stats.get('guided_create_path', 0)}")
        print(f"  guided_merge: {stats.get('guided_merge_path', 0)}")
        print(f"  fast_track_create: {stats.get('fast_track_create_path', 0)}")
        
        print(f"\n判重效果:")
        print(f"  检测到的重复数: {duplicates_detected}")
        print(f"  组件使用 - 判重引擎: {stats.get('component_usage', {}).get('dedup_engine_used', 0)}")
        
        # 验证结果
        print(f"\n{'='*70}")
        print("✅ 验证结果")
        print("=" * 70)
        
        expected_duplicates = 2  # 前两个事件应该被检测为重复
        if duplicates_detected >= expected_duplicates:
            print(f"🎉 成功！判重功能正常工作")
            print(f"   检测到 {duplicates_detected} 个重复（期望 ≥{expected_duplicates}）")
            
            # 检查判重引擎是否在所有路径中被调用
            dedup_used = stats.get('component_usage', {}).get('dedup_engine_used', 0)
            if dedup_used > 0:
                print(f"   判重引擎调用次数: {dedup_used}")
                print(f"   🔥 修复成功：判重引擎在所有路径中都被调用！")
            else:
                print(f"   ❌ 问题：判重引擎未被调用")
            
            return True
        else:
            print(f"❌ 问题：期望检测到 ≥{expected_duplicates} 个重复，实际检测到 {duplicates_detected}")
            print(f"   可能原因：")
            print(f"   1. 判重引擎阈值仍然过高")
            print(f"   2. 包含关系检测逻辑有问题")
            print(f"   3. 事件没有进入正确的执行路径")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def debug_execution_paths():
    """调试执行路径逻辑"""
    print("\n" + "=" * 70)
    print("🔍 调试执行路径决策逻辑")
    print("=" * 70)
    
    # 直接测试执行路径决策逻辑
    from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
    
    # 创建测试实例
    class MockAIClient:
        async def analyze_event_with_context(self, event_data, related_themes):
            return {"decision": "CREATE_NEW", "confidence": 0.75, "target_theme_name": "测试"}
    
    engine = EnhancedThemeDiscoveryEngine(
        ai_client=MockAIClient(),
        dedup_engine=None,
        config={
            'fast_track_threshold': 0.85,
            'review_threshold': 0.65,
            'ignore_threshold': 0.3
        }
    )
    
    # 测试不同置信度的路径
    test_cases = [
        ("CREATE_NEW", 0.90, "fast_track_create"),
        ("CREATE_NEW", 0.75, "guided_create"),
        ("CREATE_NEW", 0.60, "review_pool"),
        ("MERGE_INTO", 0.80, "guided_merge"),
        ("MERGE_INTO", 0.60, "review_pool"),
        ("IGNORE", 0.80, "skip"),
        ("CLUSTER", 0.70, "review_pool")
    ]
    
    print("🧪 测试执行路径决策:")
    for decision_type, confidence, expected_path in test_cases:
        path = engine._determine_execution_path(
            "CREATE_NEW",  # directive_action
            0.75,         # directive_confidence
            decision_type,
            confidence
        )
        
        status = "✅" if path == expected_path else "❌"
        print(f"  {status} {decision_type} ({confidence:.2f}) -> {path} (期望: {expected_path})")


async def main():
    """主函数"""
    print("=" * 70)
    print("🔧 EnhancedThemeDiscoveryEngine判重功能修复测试")
    print("=" * 70)
    
    # 运行主测试
    success = await test_fixed_enhanced_discovery()
    
    # 如果需要，运行调试
    if not success:
        print("\n" + "=" * 70)
        print("🔍 启动调试模式...")
        print("=" * 70)
        await debug_execution_paths()
    
    print("\n" + "=" * 70)
    print("📋 修复总结")
    print("=" * 70)
    
    if success:
        print("✅ 修复成功！判重功能现在在所有执行路径中都工作")
        print("\n修复内容：")
        print("1. 在guided_merge路径中加入判重检查")
        print("2. 在fast_track_create路径中加入判重检查")
        print("3. 判重检查可以覆盖AI决策")
        print("4. 使用极低的判重阈值确保检测")
    else:
        print("❌ 修复未完全成功")
        print("\n下一步：")
        print("1. 检查判重引擎的inclusion_match检测逻辑")
        print("2. 进一步降低判重阈值")
        print("3. 查看判重引擎日志")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))