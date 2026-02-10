"""
纯数据获取器 - 适配新数据结构版
职责：从数据库读取数据，不做任何业务逻辑
🔥 适配新的数据结构，正确处理完整原始内容
"""
import asyncio 
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from .interface import DatabaseManager, ThemeRecord
from .config import get_config

logger = logging.getLogger(__name__)

class PureDataFetcher:
    """纯数据获取器 - 适配新数据结构"""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        初始化数据获取器
        
        Args:
            db_manager: DatabaseManager实例
        """
        self.db_manager = db_manager
        logger.info("✅ PureDataFetcher 初始化完成（适配新数据结构）")
    
    # ========== 主题数据获取 ==========
    
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """
        获取所有活跃主题
        
        Returns:
            主题记录列表
        """
        try:
            themes = await self.db_manager.get_all_active_themes(limit)
            logger.debug(f"获取到 {len(themes)} 个活跃主题")
            return themes
        except Exception as e:
            logger.error(f"获取活跃主题失败: {e}")
            raise
    
    async def get_all_active_themes_with_context(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        修复版的 get_all_active_themes_with_context
        解决原方法在无缓存时的超时问题
        
        🔥 关键修复：
        1. 避免递归调用 get_event_with_full_context
        2. 简化上下文构建逻辑
        3. 保证性能稳定
        """
        try:
            logger.info(f"🛠️  使用修复版的 get_all_active_themes_with_context (limit={limit})")
            
            # 1. 尝试使用数据库的增强方法（可能缓存了）
            if hasattr(self.db_manager, 'get_all_active_themes_with_context'):
                try:
                    # 设置超时，防止长时间等待
                    themes = await asyncio.wait_for(
                        self.db_manager.get_all_active_themes_with_context(limit),
                        timeout=2.0  # 2秒超时
                    )
                    logger.info(f"✅ 数据库增强方法成功: {len(themes)} 个主题")
                    
                    # 确保有AI描述
                    for theme in themes:
                        if 'ai_description' not in theme or not theme['ai_description']:
                            theme['ai_description'] = self._generate_ai_description_new_structure(theme)
                    
                    return themes
                except asyncio.TimeoutError:
                    logger.warning("⚠️  数据库增强方法超时，使用简化修复版")
                except Exception as e:
                    logger.warning(f"⚠️  数据库增强方法失败: {e}")
            
            # 2. 修复版：简化处理逻辑
            themes = await self.get_all_active_themes(limit * 2)
            
            enriched_themes = []
            for theme in themes[:limit]:  # 只处理限定的数量
                # 转换为字典格式
                if hasattr(theme, 'to_dict'):
                    theme_dict = theme.to_dict()
                else:
                    theme_dict = {
                        'id': getattr(theme, 'id'),
                        'name': getattr(theme, 'name'),
                        'description': getattr(theme, 'description', ''),
                        'keywords': getattr(theme, 'keywords', []),
                        'heat_score': getattr(theme, 'heat_score', 0),
                        'discovery_confidence': getattr(theme, 'discovery_confidence', 0.5)
                    }
                
                # 获取事件ID（不获取完整事件内容，避免递归）
                try:
                    event_ids = await self.db_manager.get_theme_events(theme.id, limit=3)
                    event_count = len(event_ids)
                    
                    # 构建简化的事件摘要（避免完整内容获取）
                    event_summaries = []
                    for event_id in event_ids[:2]:  # 只取前2个
                        try:
                            # 仅获取基本信息，不调用 get_event_with_full_context
                            event = await self.db_manager.get_event(event_id)
                            if event and 'title' in event:
                                event_summaries.append({
                                    'id': event_id,
                                    'title': event.get('title', ''),
                                    'preview': event.get('full_content', '')[:80] + '...' if event.get('full_content') else '',
                                    'type': event.get('event_info', {}).get('event_type', '') if isinstance(event.get('event_info'), dict) else ''
                                })
                        except:
                            pass
                    
                except Exception as e:
                    logger.debug(f"获取主题 {theme.id} 事件信息失败: {e}")
                    event_count = 0
                    event_summaries = []
                
                # 构建简化上下文
                theme_dict['context'] = {
                    'event_count': event_count,
                    'event_summaries': event_summaries,
                    'has_events': event_count > 0
                }
                
                # 生成AI描述
                theme_dict['ai_description'] = self._generate_simple_ai_description(theme_dict, event_count)
                
                enriched_themes.append(theme_dict)
            
            logger.info(f"✅ 修复版生成 {len(enriched_themes)} 个增强主题")
            return enriched_themes
            
        except Exception as e:
            logger.error(f"修复版方法失败: {e}")
            # 降级：返回基础主题
            themes = await self.get_all_active_themes(limit)
            return [self._theme_to_dict_new_structure(theme) for theme in themes]

    def _generate_simple_ai_description(self, theme_dict: Dict, event_count: int) -> str:
        """生成简单的AI描述（修复版使用）"""
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
    
    def _theme_to_dict_new_structure(self, theme) -> Dict[str, Any]:
        """转换主题为字典（适配新结构）"""
        if hasattr(theme, 'to_dict'):
            result = theme.to_dict()
        else:
            # 兼容处理
            result = {}
            for attr in ['id', 'name', 'description', 'keywords', 'event_count', 'heat_score', 'discovery_confidence']:
                if hasattr(theme, attr):
                    result[attr] = getattr(theme, attr)
        
        # 🔥 确保有必要的字段
        if 'keywords' not in result:
            result['keywords'] = []
        if 'description' not in result or not result['description']:
            result['description'] = f"关于{result.get('name', '')}的主题"
        
        return result
    
    def _extract_event_summary_new_structure(self, event: Dict) -> str:
        """从事件中提取摘要（适配新结构）"""
        # 🔥 适配新结构：优先使用full_content
        full_content = event.get('full_content', '')
        if full_content and len(full_content) > 50:
            # 提取前100字符作为摘要
            summary = full_content[:100] + '...'
            return summary
        
        # 🔥 后备：从original_news.content提取
        if 'original_news' in event:
            content = event['original_news'].get('content', '')
            if content:
                return content[:80] + '...'
        
        # 🔥 最后：使用标题
        title = event.get('title', '')
        return title if title else "无摘要"
    
    def _extract_common_industries_new_structure(self, events: List[Dict]) -> List[str]:
        """提取共同影响的行业（适配新结构）"""
        if not events:
            return []
        
        industry_count = {}
        for event in events:
            # 🔥 适配新结构：从event_info获取行业
            event_info = event.get('event_info', {})
            industries = event_info.get('impact_industries', [])
            for industry in industries:
                industry_count[industry] = industry_count.get(industry, 0) + 1
        
        sorted_industries = sorted(industry_count.items(), key=lambda x: x[1], reverse=True)
        return [industry for industry, count in sorted_industries[:3]]
    
    def _get_events_time_range_new_structure(self, events: List[Dict]) -> str:
        """获取事件时间范围（适配新结构）"""
        dates = []
        for event in events:
            processed_at = event.get('processed_at')
            if processed_at:
                try:
                    if 'Z' in processed_at:
                        processed_at = processed_at.replace('Z', '+00:00')
                    dates.append(datetime.fromisoformat(processed_at))
                except:
                    pass
        
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            
            if min_date.date() == max_date.date():
                return min_date.strftime('%Y-%m-%d')
            elif min_date.year == max_date.year:
                return f"{min_date.strftime('%Y-%m')} 至 {max_date.strftime('%Y-%m')}"
            else:
                return f"{min_date.strftime('%Y')} 至 {max_date.strftime('%Y')}"
        
        return "未知"
    
    def _generate_ai_description_new_structure(self, theme_dict: Dict) -> str:
        """为主题生成AI描述（适配新结构）"""
        name = theme_dict.get('name', '')
        event_count = theme_dict.get('event_count', 0)
        
        if 'context' in theme_dict:
            context = theme_dict['context']
            common_industries = context.get('common_industries', [])
            event_summaries = context.get('event_summaries', [])
            
            if common_industries and event_summaries:
                industry_str = '、'.join(common_industries[:2])
                return f"{name}主题，涉及{industry_str}行业，包含{event_count}个事件。示例：{event_summaries[0]}"
            elif common_industries:
                industry_str = '、'.join(common_industries[:2])
                return f"{name}主题，涉及{industry_str}行业，包含{event_count}个相关事件。"
        
        return f"{name}主题，包含{event_count}个相关事件。"
    
    async def get_themes_by_ids(self, theme_ids: List[int]) -> List[ThemeRecord]:
        """
        根据ID批量获取主题
        """
        if not theme_ids:
            return []
        
        themes = []
        for theme_id in theme_ids:
            try:
                theme = await self.db_manager.get_theme(theme_id)
                if theme:
                    themes.append(theme)
            except Exception as e:
                logger.warning(f"获取主题 {theme_id} 失败: {e}")
                continue
        
        logger.debug(f"根据ID获取到 {len(themes)} 个主题")
        return themes
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """
        根据名称获取主题
        """
        try:
            theme = await self.db_manager.get_theme_by_name(name)
            return theme
        except Exception as e:
            logger.error(f"根据名称获取主题失败: {name}, 错误: {e}")
            return None
    
    async def search_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """
        根据关键词搜索主题
        """
        try:
            themes = await self.db_manager.get_themes_by_keywords(keywords, limit)
            logger.debug(f"关键词搜索 {keywords} -> 找到 {len(themes)} 个主题")
            return themes
        except Exception as e:
            logger.error(f"关键词搜索失败: {keywords}, 错误: {e}")
            raise
    
    # ========== 事件数据获取（适配新结构） ==========
    
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件详情"""
        try:
            event = await self.db_manager.get_event(event_id)
            return event
        except Exception as e:
            logger.error(f"获取事件失败: {event_id}, 错误: {e}")
            return None
    
    async def get_event_with_full_context(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        获取事件的完整上下文（适配新结构）
        
        🔥 专门为AI分析设计，返回完整信息
        """
        try:
            # 尝试使用数据库的增强方法
            if hasattr(self.db_manager, 'get_event_with_full_context'):
                event = await self.db_manager.get_event_with_full_context(event_id)
            else:
                event = await self.db_manager.get_event(event_id)
            
            if not event:
                logger.warning(f"事件 {event_id} 不存在")
                return None
            
            # 🔥 确保返回适配新结构的数据
            enriched_event = self._enrich_event_for_ai(event)
            
            logger.debug(f"获取到事件 {event_id} 的完整上下文")
            return enriched_event
            
        except Exception as e:
            logger.error(f"获取事件完整上下文失败: {event_id}, 错误: {e}")
            return None
    
    def _enrich_event_for_ai(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """为AI分析增强事件数据"""
        enriched = event.copy()
        
        # 🔥 确保有完整的内容供AI分析
        if 'full_content' not in enriched and 'original_news' in enriched:
            # 从original_news中提取内容
            original_news = enriched['original_news']
            if isinstance(original_news, dict):
                full_content = original_news.get('content', '')
                if full_content:
                    enriched['full_content'] = full_content
        
        # 🔥 添加数据质量标记
        enriched['data_quality'] = {
            'has_full_content': bool(enriched.get('full_content')) and len(enriched.get('full_content', '')) > 100,
            'content_length': len(enriched.get('full_content', '')),
            'has_event_info': 'event_info' in enriched,
            'has_theme_directive': 'theme_discovery_directive' in enriched
        }
        
        # 🔥 生成AI友好的描述
        if 'ai_description' not in enriched:
            enriched['ai_description'] = self._generate_event_ai_description(enriched)
        
        return enriched
    
    def _generate_event_ai_description(self, event: Dict[str, Any]) -> str:
        """为事件生成AI描述"""
        title = event.get('title', '未知事件')
        event_type = event.get('event_info', {}).get('event_type', '')
        
        # 提取关键信息
        if 'original_news' in event and isinstance(event['original_news'], dict):
            content = event['original_news'].get('content', '')
            if content:
                # 提取前50字符作为描述
                preview = content[:50] + '...' if len(content) > 50 else content
                return f"{title} - {event_type}：{preview}"
        
        return f"{title} - {event_type}"
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        try:
            events = await self.db_manager.get_unprocessed_events(limit)
            logger.debug(f"获取到 {len(events)} 个未处理事件")
            return events
        except Exception as e:
            logger.error(f"获取未处理事件失败: {e}")
            raise
    
    # ========== 关联数据获取 ==========
    
    async def get_event_themes(self, event_id: int) -> List[Dict[str, Any]]:
        """获取事件关联的主题"""
        try:
            relations = await self.db_manager.get_event_themes(event_id)
            
            # 转换为包含主题详情的字典
            result = []
            for relation in relations:
                theme = await self.db_manager.get_theme(relation.theme_id)
                if theme:
                    theme_dict = self._theme_to_dict_new_structure(theme)
                    result.append({
                        'relation': {
                            'id': relation.id,
                            'event_id': relation.event_id,
                            'theme_id': relation.theme_id,
                            'confidence': relation.confidence,
                            'confidence_level': relation.confidence_level,
                            'created_at': relation.created_at.isoformat() if hasattr(relation.created_at, 'isoformat') else str(relation.created_at)
                        },
                        'theme': theme_dict
                    })
            
            logger.debug(f"获取到事件 {event_id} 的 {len(result)} 个主题关联")
            return result
        except Exception as e:
            logger.error(f"获取事件主题关联失败: {event_id}, 错误: {e}")
            return []
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """获取主题关联的事件"""
        try:
            event_ids = await self.db_manager.get_theme_events(theme_id, limit)
            
            # 获取事件详情（适配新结构）
            events = []
            for event_id in event_ids[:limit]:
                event = await self.get_event_with_full_context(event_id)
                if event:
                    events.append(event)
            
            logger.debug(f"获取到主题 {theme_id} 的 {len(events)} 个关联事件")
            return events
        except Exception as e:
            logger.error(f"获取主题事件关联失败: {theme_id}, 错误: {e}")
            return []
    
    # ========== 统计信息 ==========
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            stats = await self.db_manager.get_stats()
            return stats
        except Exception as e:
            logger.error(f"获取数据库统计失败: {e}")
            return {}
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            return await self.db_manager.health_check()
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    # ========== 批量操作 ==========
    
    async def batch_get_themes(self, criteria: Dict[str, Any]) -> List[ThemeRecord]:
        """
        批量获取主题（根据条件）
        """
        keywords = criteria.get('keywords', [])
        if keywords:
            return await self.search_themes_by_keywords(keywords, criteria.get('limit', 20))
        
        return await self.get_all_active_themes(criteria.get('limit', 100))

# 工厂函数
async def create_pure_data_fetcher(db_config=None) -> PureDataFetcher:
    """创建纯数据获取器"""
    from .memory_manager import MemoryDatabaseManager
    
    try:
        if db_config is None:
            db_config = get_config()
        
        # 根据配置创建数据库管理器
        if db_config.db_type.value == "memory":
            db_manager = MemoryDatabaseManager(db_config)
        else:
            logger.warning("PostgreSQL未实现，使用内存数据库")
            db_manager = MemoryDatabaseManager(db_config)
        
        await db_manager.connect()
        
        fetcher = PureDataFetcher(db_manager)
        
        # 测试连接
        if await fetcher.health_check():
            logger.info("✅ PureDataFetcher 创建成功（适配新数据结构）")
            return fetcher
        else:
            raise ConnectionError("数据库连接失败")
            
    except Exception as e:
        logger.error(f"❌ 创建PureDataFetcher失败: {e}")
        raise

# 测试函数（适配新结构）
async def test_pure_data_fetcher():
    """测试纯数据获取器（适配新结构）"""
    print("🧪 测试PureDataFetcher（适配新结构）...")
    
    try:
        fetcher = await create_pure_data_fetcher()
        
        # 测试健康检查
        health = await fetcher.health_check()
        print(f"健康状态: {health}")
        
        # 测试获取活跃主题
        themes = await fetcher.get_all_active_themes(limit=5)
        print(f"获取到 {len(themes)} 个活跃主题")
        
        # 测试获取增强主题（适配新结构）
        enriched_themes = await fetcher.get_all_active_themes_with_context(limit=3)
        print(f"获取到 {len(enriched_themes)} 个增强主题（适配新结构）")
        
        if enriched_themes:
            print("\n📋 增强主题示例（新结构）：")
            for i, theme in enumerate(enriched_themes[:2], 1):
                print(f"  {i}. {theme.get('name')}")
                print(f"     描述: {theme.get('ai_description', '')[:50]}...")
                if 'context' in theme:
                    ctx = theme['context']
                    print(f"     事件数: {ctx.get('event_count', 0)}")
                    if 'common_industries' in ctx:
                        print(f"     行业: {', '.join(ctx['common_industries'][:2])}")
        
        # 测试获取事件
        if enriched_themes:
            first_theme = enriched_themes[0]
            if 'context' in first_theme and first_theme['context'].get('event_count', 0) > 0:
                events = await fetcher.get_theme_events(first_theme['id'], limit=2)
                print(f"\n📊 主题 '{first_theme['name']}' 的 {len(events)} 个事件")
                for event in events[:1]:
                    print(f"   事件ID: {event.get('id')}")
                    print(f"   标题: {event.get('title', '')[:40]}...")
                    print(f"   内容长度: {event.get('data_quality', {}).get('content_length', 0)}")
        
        # 获取统计信息
        stats = await fetcher.get_database_stats()
        print(f"\n📊 数据库统计: {stats}")
        
        print("\n✅ PureDataFetcher 测试完成（适配新数据结构）")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_pure_data_fetcher())