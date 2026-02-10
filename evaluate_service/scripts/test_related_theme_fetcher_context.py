#!/usr/bin/env python3
"""
无缓存测试：模拟原始测试场景
"""
import asyncio
import sys
from pathlib import Path
import time

# 添加项目根目录
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_without_cache():
    """测试无缓存情况"""
    print("🧪 测试无缓存情况")
    
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.config import DatabaseConfig
    from database_service.pure_data_fetcher import PureDataFetcher
    
    # 创建数据库（禁用缓存）
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    
    # 禁用缓存
    db_manager.theme_context_cache.clear()
    db_manager.context_cache_ttl = 0  # 设置缓存TTL为0
    
    await db_manager.connect()
    
    # 创建测试数据
    theme = await db_manager.create_theme(
        name="无缓存测试主题",
        description="测试无缓存情况下的性能",
        keywords=["测试", "无缓存"],
        discovery_source="no_cache_test"
    )
    
    # 创建多个事件
    for i in range(3):
        event_data = {
            "news_id": f"nocache_event_{i+1}",
            "event_info": {
                "event_type": "技术发布",
                "impact_industries": ["人工智能", "测试"],
                "direction": "利好"
            },
            "original_news": {
                "title": f"无缓存测试事件{i+1}",
                "content": f"这是第{i+1}个无缓存测试事件的内容。详细描述事件的具体情况和影响。",
                "date": "2025-01-13"
            }
        }
        event_id = await db_manager.create_or_update_event(event_data)
        
        # 创建关联
        await db_manager.create_event_theme_relation(
            event_id=event_id,
            theme_id=theme.id,
            confidence=0.7
        )
    
    print(f"✅ 创建数据完成: 1个主题，3个事件")
    
    # 测试 PureDataFetcher
    fetcher = PureDataFetcher(db_manager)
    
    print("\n测试1: 第一次调用（无缓存）")
    start_time = time.time()
    try:
        result = await asyncio.wait_for(
            fetcher.get_all_active_themes_with_context(limit=5),
            timeout=10.0
        )
        elapsed = time.time() - start_time
        print(f"✅ 成功: {len(result)} 个主题，耗时 {elapsed:.2f} 秒")
        
        if result:
            print(f"  第一个主题: {result[0].get('name')}")
            print(f"  事件数量: {result[0].get('context', {}).get('event_count', 0)}")
        
    except asyncio.TimeoutError:
        print(f"❌ 超时！耗时超过10秒")
        return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n测试2: 第二次调用（应该有缓存）")
    start_time = time.time()
    try:
        result2 = await fetcher.get_all_active_themes_with_context(limit=5)
        elapsed = time.time() - start_time
        print(f"✅ 成功: {len(result2)} 个主题，耗时 {elapsed:.2f} 秒")
        
        # 检查缓存是否生效
        if elapsed < 0.1:
            print("  🚀 缓存生效，速度很快")
        else:
            print("  ⚠️  缓存可能未生效")
            
    except Exception as e:
        print(f"❌ 第二次调用异常: {e}")
    
    await db_manager.cleanup()
    return True

async def test_specific_scenario():
    """测试原始测试脚本的特定场景"""
    print("\n🔍 测试原始脚本场景")
    
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.config import DatabaseConfig
    from database_service.pure_data_fetcher import PureDataFetcher
    from theme_service.related_theme_fetcher import RelatedThemeFetcher
    
    # 完全模拟原始测试场景
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    await db_manager.connect()
    
    # 清除所有缓存
    db_manager.theme_context_cache.clear()
    
    # 创建和原始测试一样的数据
    theme = await db_manager.create_theme(
        name="人工智能",
        description="人工智能技术及应用",
        keywords=["AI", "人工智能", "机器学习"],
        discovery_source="test",
        discovery_confidence=0.9
    )
    
    event_data = {
        "news_id": "test_001",
        "event_info": {
            "event_type": "产品发布",
            "impact_industries": ["消费电子", "人工智能"],
            "direction": "利好",
            "event_confidence": 0.8
        },
        "original_news": {
            "title": "AI智能眼镜发布",
            "content": "某公司发布新款AI智能眼镜，具备语音助手和实时翻译功能。",
            "date": "2025-01-13"
        },
        "theme_discovery_directive": {
            "action": "CLUSTER",
            "decision_confidence": 0.7,
            "reason": "AI产品发布"
        }
    }
    
    event_id = await db_manager.create_or_update_event(event_data)
    await db_manager.create_event_theme_relation(
        event_id=event_id,
        theme_id=theme.id,
        confidence=0.8,
        confidence_level="high"
    )
    
    print("✅ 数据创建完成，开始测试...")
    
    # 测试步骤
    fetcher = PureDataFetcher(db_manager)
    theme_fetcher = RelatedThemeFetcher(fetcher)
    
    print("\n1. 测试 get_all_active_themes...")
    try:
        themes = await fetcher.get_all_active_themes(limit=10)
        print(f"  成功: {len(themes)} 个主题")
    except Exception as e:
        print(f"  失败: {e}")
        return False
    
    print("\n2. 测试 get_all_active_themes_with_context...")
    start_time = time.time()
    try:
        enriched = await asyncio.wait_for(
            fetcher.get_all_active_themes_with_context(limit=5),
            timeout=15.0  # 更长超时
        )
        elapsed = time.time() - start_time
        print(f"  成功: {len(enriched)} 个主题，耗时 {elapsed:.2f} 秒")
        
        if enriched:
            print(f"  主题字段: {list(enriched[0].keys())}")
            
    except asyncio.TimeoutError:
        print(f"  ❌ 超时！耗时超过15秒")
        print("  这可能是问题的根源...")
        
        # 打印当前状态
        print(f"  数据库状态:")
        print(f"    主题数量: {len(db_manager.themes)}")
        print(f"    事件数量: {len(db_manager.events)}")
        print(f"    关联数量: {len(db_manager.event_relations)}")
        
        return False
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n3. 测试 RelatedThemeFetcher.fetch_all_active_themes...")
    try:
        result = await theme_fetcher.fetch_all_active_themes(limit=10)
        print(f"  成功: {len(result)} 个主题")
    except Exception as e:
        print(f"  失败: {e}")
    
    await db_manager.cleanup()
    return True

async def main():
    """主测试"""
    print("=" * 60)
    print("🕵️ 无缓存性能测试")
    print("=" * 60)
    
    print("\n测试1: 无缓存场景")
    success1 = await test_without_cache()
    
    print("\n" + "=" * 40)
    print("\n测试2: 原始脚本场景")
    success2 = await test_specific_scenario()
    
    print("\n" + "=" * 40)
    print("\n📊 测试结果:")
    print(f"  测试1 (无缓存): {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"  测试2 (原始场景): {'✅ 通过' if success2 else '❌ 失败'}")
    
    if success1 and success2:
        print("\n🎉 所有测试通过！问题可能是原始测试脚本的配置问题")
    else:
        print("\n⚠️  发现性能问题，需要进一步优化")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试发生异常: {e}")
        import traceback
        traceback.print_exc()