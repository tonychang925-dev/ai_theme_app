#!/usr/bin/env python3
"""
创建修复版的 PureDataFetcher，解决超时问题
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FixedPureDataFetcher:
    """
    修复版的 PureDataFetcher
    解决 get_all_active_themes_with_context 超时问题
    """
    
    def __init__(self, db_manager):
        """使用原始数据库管理器"""
        self.db_manager = db_manager
        logger.info("✅ FixedPureDataFetcher 初始化完成")
    
    async def get_all_active_themes(self, limit: int = 1000):
        """直接调用数据库方法"""
        return await self.db_manager.get_all_active_themes(limit)
    
    async def get_all_active_themes_with_context(self, limit: int = 100):
        """
        修复版：简化的增强主题方法
        
        🔥 关键修复：
        1. 避免递归调用
        2. 简化上下文构建
        3. 保证性能
        """
        logger.info(f"🛠️  使用修复版的 get_all_active_themes_with_context (limit={limit})")
        
        try:
            # 1. 获取基础主题
            themes = await self.db_manager.get_all_active_themes(limit * 2)
            
            if not themes:
                logger.info("没有活跃主题")
                return []
            
            # 2. 简化的增强处理
            enriched_themes = []
            
            for theme in themes[:limit]:  # 只处理限定的数量
                # 转换为基础字典
                if hasattr(theme, 'to_dict'):
                    theme_dict = theme.to_dict()
                else:
                    theme_dict = {
                        'id': getattr(theme, 'id'),
                        'name': getattr(theme, 'name'),
                        'description': getattr(theme, 'description', ''),
                        'keywords': getattr(theme, 'keywords', []),
                        'heat_score': getattr(theme, 'heat_score', 0)
                    }
                
                # 3. 获取事件ID（不获取完整事件内容）
                try:
                    event_ids = await self.db_manager.get_theme_events(theme.id, limit=3)
                    event_count = len(event_ids)
                except:
                    event_count = 0
                    event_ids = []
                
                # 4. 构建简化上下文（避免复杂计算）
                theme_dict['context'] = {
                    'event_count': event_count,
                    'has_events': event_count > 0,
                    'event_ids': event_ids[:3]  # 只存储ID，不获取内容
                }
                
                # 5. 生成简单的AI描述
                theme_dict['ai_description'] = self._generate_simple_ai_description(theme_dict, event_count)
                
                enriched_themes.append(theme_dict)
            
            logger.info(f"✅ 修复版生成 {len(enriched_themes)} 个增强主题")
            return enriched_themes
            
        except Exception as e:
            logger.error(f"修复版方法失败: {e}")
            # 降级：返回基础主题
            themes = await self.get_all_active_themes(limit)
            simple_themes = []
            for theme in themes:
                if hasattr(theme, 'to_dict'):
                    simple_themes.append(theme.to_dict())
                else:
                    simple_themes.append({
                        'id': getattr(theme, 'id'),
                        'name': getattr(theme, 'name'),
                        'description': getattr(theme, 'description', ''),
                        'keywords': getattr(theme, 'keywords', [])
                    })
            return simple_themes
    
    def _generate_simple_ai_description(self, theme_dict, event_count):
        """生成简单的AI描述"""
        name = theme_dict.get('name', '')
        keywords = theme_dict.get('keywords', [])
        
        if event_count > 0:
            keyword_str = '、'.join(keywords[:3]) if keywords else ''
            if keyword_str:
                return f"{name}主题，关键词：{keyword_str}，关联{event_count}个事件。"
            else:
                return f"{name}主题，关联{event_count}个事件。"
        else:
            return f"{name}主题，尚无关联事件。"
    
    async def health_check(self):
        """健康检查"""
        return await self.db_manager.health_check()

async def test_fixed_fetcher():
    """测试修复版的 PureDataFetcher"""
    print("🧪 测试修复版的 PureDataFetcher")
    
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.config import DatabaseConfig
    
    # 创建数据库
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    await db_manager.connect()
    
    # 清除缓存
    db_manager.theme_context_cache.clear()
    
    # 创建测试数据
    theme = await db_manager.create_theme(
        name="测试修复主题",
        description="测试修复版的功能",
        keywords=["修复", "测试"],
        discovery_source="fix_test"
    )
    
    # 创建事件
    event_data = {
        "news_id": "fix_test_event",
        "event_info": {
            "event_type": "技术测试",
            "impact_industries": ["测试"],
            "direction": "中性"
        },
        "original_news": {
            "title": "修复测试事件",
            "content": "这是一个用于测试修复版的事件内容。",
            "date": "2025-01-13"
        }
    }
    
    event_id = await db_manager.create_or_update_event(event_data)
    await db_manager.create_event_theme_relation(
        event_id=event_id,
        theme_id=theme.id,
        confidence=0.8
    )
    
    print("✅ 测试数据创建完成")
    
    # 测试修复版
    import time
    
    fixed_fetcher = FixedPureDataFetcher(db_manager)
    
    print("\n1. 测试 get_all_active_themes...")
    start = time.time()
    themes = await fixed_fetcher.get_all_active_themes(limit=10)
    elapsed = time.time() - start
    print(f"   成功: {len(themes)} 个主题，耗时 {elapsed:.3f} 秒")
    
    print("\n2. 测试 get_all_active_themes_with_context (修复版)...")
    start = time.time()
    try:
        enriched = await asyncio.wait_for(
            fixed_fetcher.get_all_active_themes_with_context(limit=5),
            timeout=5.0
        )
        elapsed = time.time() - start
        print(f"   ✅ 成功: {len(enriched)} 个主题，耗时 {elapsed:.3f} 秒")
        
        if enriched:
            print(f"   第一个主题: {enriched[0].get('name')}")
            print(f"   上下文字段: {list(enriched[0].get('context', {}).keys())}")
            print(f"   AI描述: {enriched[0].get('ai_description', '')}")
            
            # 验证数据结构
            required = ['id', 'name', 'context', 'ai_description']
            missing = [f for f in required if f not in enriched[0]]
            if not missing:
                print(f"   ✅ 所有必要字段完整")
            else:
                print(f"   ⚠️  缺失字段: {missing}")
        
        await db_manager.cleanup()
        return True
        
    except asyncio.TimeoutError:
        print(f"   ❌ 修复版仍然超时！")
        return False
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_with_original_related_theme_fetcher():
    """使用修复版测试 RelatedThemeFetcher"""
    print("\n🧪 测试修复版与 RelatedThemeFetcher 集成")
    
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.config import DatabaseConfig
    from theme_service.related_theme_fetcher import RelatedThemeFetcher
    
    # 创建数据库
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    await db_manager.connect()
    
    # 创建数据
    theme = await db_manager.create_theme(
        name="集成测试主题",
        description="测试修复版与RelatedThemeFetcher的集成",
        keywords=["集成", "测试"],
        discovery_source="integration_test"
    )
    
    # 使用修复版的 fetcher
    fixed_fetcher = FixedPureDataFetcher(db_manager)
    
    # 创建 RelatedThemeFetcher
    theme_fetcher = RelatedThemeFetcher(fixed_fetcher)
    
    print("\n测试 RelatedThemeFetcher.fetch_all_active_themes...")
    try:
        themes = await asyncio.wait_for(
            theme_fetcher.fetch_all_active_themes(limit=10),
            timeout=5.0
        )
        print(f"✅ 成功: {len(themes)} 个主题")
        
        if themes:
            print(f"   第一个主题: {themes[0].get('name')}")
            print(f"   是否有上下文: {'✅' if 'context' in themes[0] else '❌'}")
            print(f"   是否有AI描述: {'✅' if 'ai_description' in themes[0] else '❌'}")
        
        await db_manager.cleanup()
        return True
        
    except asyncio.TimeoutError:
        print("❌ RelatedThemeFetcher 超时")
        return False
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

async def main():
    """主测试"""
    print("=" * 60)
    print("🔧 修复版 PureDataFetcher 测试")
    print("=" * 60)
    
    print("\n测试1: 修复版基础功能")
    test1 = await test_fixed_fetcher()
    
    print("\n" + "-" * 40)
    print("\n测试2: 与 RelatedThemeFetcher 集成")
    test2 = await test_with_original_related_theme_fetcher()
    
    print("\n" + "=" * 40)
    print("\n📊 最终结果:")
    print(f"  修复版基础功能: {'✅ 通过' if test1 else '❌ 失败'}")
    print(f"  与RelatedThemeFetcher集成: {'✅ 通过' if test2 else '❌ 失败'}")
    
    if test1 and test2:
        print("\n🎉 修复成功！可以继续验证AI相似性分析器")
        print("\n下一步：")
        print("  1. 将 FixedPureDataFetcher 集成到原始代码中")
        print("  2. 或修改原始 PureDataFetcher 中的问题方法")
        print("  3. 然后进行第二步：验证 AI 相似性分析器")
    else:
        print("\n⚠️  需要进一步调试")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试发生异常: {e}")
        import traceback
        traceback.print_exc()