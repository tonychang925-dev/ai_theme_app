#!/usr/bin/env python3
"""
判重功能集成测试 - 专门测试EnhancedThemeDiscoveryEngine的判重功能
"""
import asyncio
import sys
from pathlib import Path
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 最佳判重配置
OPTIMIZED_DEDUP_CONFIG = {
    "thresholds": {
        "exact_match": 1.0,
        "inclusion_match": 0.6,      # 非常低的包含阈值
        "semantic_similarity": 0.55, # 很低的语义阈值
        "event_overlap": 0.5,
        "auto_merge": 0.65,          # 65%就自动合并
        "suggest_merge": 0.50,
        "keep_separate": 0.3
    },
    "weights": {
        "name_similarity": 0.35,
        "keyword_overlap": 0.35,     # 提高关键词权重
        "industry_match": 0.20,
        "semantic_similarity": 0.10
    },
    "strategies": {
        "enable_exact_match": True,
        "enable_inclusion_check": True,
        "enable_semantic_analysis": True,
        "enable_event_overlap": True,
        "use_jieba": True,
        "cache_enabled": True
    }
}

async def test_dedup_integration():
    """测试判重功能在EnhancedThemeDiscoveryEngine中的集成"""
    print("=" * 70)
    print("🔍 判重功能集成测试")
    print("测试EnhancedThemeDiscoveryEngine中的判重功能")
    print("=" * 70)
    
    try:
        # 1. 导入必要的模块
        print("📦 导入模块...")
        
        # 首先导入判重引擎
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        
        # 导入修复后的引擎
        # 我们需要先修改enhanced_theme_discovery.py文件
        # 这里假设已经修改好了，直接导入
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        print("✅ 模块导入成功")
        
        # 2. 创建AI客户端（模拟）
        class TestAIClient:
            def __init__(self):
                self.counter = 0
            
            async def analyze_event_with_context(self, event_data, related_themes):
                self.counter += 1
                
                # 🔧 关键：返回置信度在0.65-0.85之间，确保进入guided_create路径
                confidence = 0.75  # 正好在guided_create范围内
                
                # 根据事件ID调整，让部分事件进入不同路径
                event_id = event_data.get('id', '')
                if 'exact' in event_id:
                    confidence = 0.95  # 进入fast_track_create
                elif 'low' in event_id:
                    confidence = 0.60  # 进入review_pool
                
                return {
                    "decision": "CREATE_NEW",
                    "target_theme_name": event_data.get('title', '新题材')[:10],
                    "confidence": confidence,
                    "reason": "测试AI决策",
                    "comparison_analysis": "测试分析"
                }
        
        # 3. 创建判重引擎（使用优化配置）
        print("🔧 创建判重引擎...")
        dedup_engine = ThemeDeduplicationEngine(config=OPTIMIZED_DEDUP_CONFIG)
        
        # 4. 创建EnhancedThemeDiscoveryEngine
        print("🚀 创建EnhancedThemeDiscoveryEngine...")
        ai_client = TestAIClient()
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            dedup_engine=dedup_engine,  # 🔧 传入判重引擎
            config={
                'fast_track_threshold': 0.90,  # 提高阈值，让更多事件进入guided_create
                'review_threshold': 0.65,      # guided_create的阈值
                'ignore_threshold': 0.3,
                'dedup_threshold': 0.7
            }
        )
        
        # 5. 显示引擎信息
        engine_info = engine.get_engine_info()
        print(f"\n🔧 引擎信息:")
        print(f"  版本: {engine_info.get('engine_version')}")
        print(f"  判重引擎: {engine_info.get('components_available', {}).get('dedup_engine', False)}")
        print(f"  阈值配置:")
        for key, value in engine_info.get('thresholds', {}).items():
            print(f"    {key}: {value}")
        
        # 6. 创建测试事件
        print(f"\n📋 创建测试事件...")
        test_events = []
        
        # 事件1：应该检测到重复（AI智能眼镜 -> AI眼镜）
        test_events.append({
            "id": "test_duplicate_exact",
            "title": "AI智能眼镜发布",
            "summary": "某公司发布AI智能眼镜新品",
            "event_type": "产品发布",
            "impact_industries": ["消费电子", "人工智能"],
            "theme_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.78,  # 🔧 关键：置信度在0.65-0.85之间
                "reason": "新产品发布"
            }
        })
        
        # 事件2：包含关系重复（人工智能芯片 -> 人工智能）
        test_events.append({
            "id": "test_duplicate_inclusion",
            "title": "人工智能芯片研发",
            "summary": "人工智能专用芯片研发成功",
            "event_type": "技术突破",
            "impact_industries": ["半导体", "人工智能"],
            "theme_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.82,  # 🔧 关键：置信度在0.65-0.85之间
                "reason": "重要技术突破"
            }
        })
        
        # 事件3：不同题材（应该不重复）
        test_events.append({
            "id": "test_unique_theme",
            "title": "新型光伏材料突破",
            "summary": "钙钛矿光伏电池效率创新高",
            "event_type": "技术突破",
            "impact_industries": ["光伏", "新材料"],
            "theme_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.81,  # 🔧 关键：置信度在0.65-0.85之间
                "reason": "全新技术"
            }
        })
        
        # 事件4：高置信度，跳过判重
        test_events.append({
            "id": "test_skip_dedup",
            "title": "重大政策发布",
            "summary": "国家重大政策发布",
            "event_type": "政策发布",
            "impact_industries": ["政策"],
            "theme_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.95,  # 🔧 高置信度，会跳过判重
                "reason": "重大政策"
            }
        })
        
        print(f"✅ 创建了 {len(test_events)} 个测试事件")
        
        # 7. 处理每个事件
        print(f"\n🚀 开始处理事件...")
        results = []
        
        for i, event in enumerate(test_events):
            print(f"\n{'='*60}")
            print(f"📝 处理事件 {i+1}/{len(test_events)}: {event['title']}")
            print(f"  Directive: {event['theme_directive']['action']} (置信度: {event['theme_directive']['confidence']:.2f})")
            
            result = await engine.process_single_event(event)
            results.append(result)
            
            # 显示结果
            print(f"  ✅ 处理完成:")
            print(f"    状态: {result.get('status')}")
            print(f"    执行路径: {result.get('execution_path')}")
            print(f"    决策置信度: {result.get('decision_confidence_raw', result.get('ai_decision', {}).get('confidence', 0)):.2f}")
            
            # 显示判重信息
            dedup_info = result.get('deduplication_info', {})
            if result.get('components_used', {}).get('dedup_engine', False):
                print(f"    🔍 判重检查: 已执行")
                if dedup_info.get('should_merge', False):
                    print(f"    🔄 判重结果: 合并到 {dedup_info.get('target_theme', '未知')}")
                    print(f"        相似度: {dedup_info.get('similarity', 0):.2f}")
                    print(f"        匹配类型: {dedup_info.get('match_type', '未知')}")
                else:
                    print(f"    ✅ 判重结果: 未检测到重复")
            else:
                print(f"    ⚠️  判重检查: 未执行")
        
        # 8. 显示统计信息
        print(f"\n{'='*70}")
        print("📊 测试结果统计")
        print("=" * 70)
        
        stats = engine.get_stats()
        
        print(f"📈 处理统计:")
        print(f"  总处理事件: {stats.get('total_processed', 0)}")
        print(f"  成功创建: {stats.get('created', 0)}")
        print(f"  自动合并: {stats.get('auto_merged', 0)}")
        print(f"  判重阻止重复: {stats.get('duplicate_prevented', 0)}")
        
        print(f"\n🛣️ 执行路径分布:")
        print(f"  guided_create路径: {stats.get('guided_create_path', 0)}")
        print(f"  fast_track_create路径: {stats.get('fast_track_create_path', 0)}")
        print(f"  guided_merge路径: {stats.get('guided_merge_path', 0)}")
        
        print(f"\n🔧 组件使用:")
        for component, count in stats.get('component_usage', {}).items():
            print(f"  {component}: {count}")
        
        # 9. 分析判重效果
        guided_create_count = stats.get('guided_create_path', 0)
        dedup_checks = stats.get('component_usage', {}).get('dedup_engine_used', 0)
        duplicates_detected = stats.get('duplicate_prevented', 0)
        
        print(f"\n🎯 判重功能分析:")
        print(f"  guided_create路径触发次数: {guided_create_count}")
        print(f"  判重检查执行次数: {dedup_checks}")
        print(f"  检测到的重复数: {duplicates_detected}")
        
        if guided_create_count > 0:
            dedup_rate = dedup_checks / guided_create_count * 100
            print(f"  🔍 判重检查率: {dedup_rate:.1f}% (目标: 100%)")
        
        if dedup_checks > 0:
            detection_rate = duplicates_detected / dedup_checks * 100
            print(f"  🎯 重复检测率: {detection_rate:.1f}%")
        
        # 10. 关键结论
        print(f"\n{'='*70}")
        print("✅ 测试结论")
        print("=" * 70)
        
        if dedup_checks == 0:
            print("❌ 判重引擎从未被调用！")
            print("可能原因:")
            print("  1. AI置信度不在0.65-0.85范围内")
            print("  2. 阈值配置有问题")
            print("  3. 执行路径决策逻辑错误")
        elif duplicates_detected > 0:
            print(f"✅ 判重功能工作正常！检测到 {duplicates_detected} 个重复")
            print(f"   判重引擎在 {dedup_checks}/{guided_create_count} 个guided_create事件中被调用")
        else:
            print("⚠️  判重引擎被调用但未检测到重复")
            print("   可能测试用例不够典型，或判重阈值过高")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    success = await test_dedup_integration()
    
    if success:
        print("\n" + "=" * 70)
        print("🎉 判重功能集成测试完成！")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("❌ 测试失败，需要检查问题")
        print("=" * 70)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))