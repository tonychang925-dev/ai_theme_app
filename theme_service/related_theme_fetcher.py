"""
精简版相关题材检索器
🔥 职责单一：只负责查询数据，不做任何AI处理
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class RelatedThemeFetcher:
    """
    精简版相关题材检索器
    职责：从数据库查询主题数据，不做任何AI处理
    """
    
    def __init__(self, data_fetcher, use_cache: bool = True):
        if not data_fetcher:
            raise ValueError("必须提供PureDataFetcher实例")
            
        self.data_fetcher = data_fetcher
        self.use_cache = use_cache
        self.cache = {}
        self.cache_ttl = 300
        
        logger.info("✅ RelatedThemeFetcher初始化完成（精简版）")
    
    async def fetch_all_active_themes(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取所有活动主题 - 紧急修复版
        
        🔥 修复：确保返回所有主题，避免因为缓存或转换问题只返回部分主题
        """
        cache_key = f"active_themes_{limit}"
        
        # 🔥 修复1：每次调用都清除缓存，确保获取最新数据
        if cache_key in self.cache:
            logger.debug(f"🔥 清除主题缓存: {cache_key}")
            del self.cache[cache_key]
        
        try:
            themes = []
            
            # 🔥 修复2：直接调用数据库，跳过中间层
            if hasattr(self.data_fetcher, 'db_manager'):
                db_manager = self.data_fetcher.db_manager
                
                # 直接调用数据库
                raw_result = await db_manager.get_all_active_themes(limit=limit)
                logger.info(f"📊 数据库返回主题数: {len(raw_result) if raw_result else 0}")
                
                if raw_result:
                    # 转换为标准字典格式
                    for item in raw_result:
                        if isinstance(item, dict):
                            themes.append(item)
                        elif hasattr(item, '__dict__'):  # ThemeRecord 对象
                            themes.append({
                                'id': getattr(item, 'id', None),
                                'name': getattr(item, 'name', ''),
                                'description': getattr(item, 'description', ''),
                                'keywords': getattr(item, 'keywords', []),
                                'related_events': getattr(item, 'related_events', []),
                                'is_active': getattr(item, 'is_active', True),
                                'discovery_source': getattr(item, 'discovery_source', ''),
                                'discovery_confidence': getattr(item, 'discovery_confidence', 0.8)
                            })
                    
                    logger.info(f"✅ 成功获取 {len(themes)} 个主题")
                    
                    # 🔥 修复3：确保我们返回所有主题，显示所有主题名称
                    if themes:
                        theme_names = [t.get('name', '未知') for t in themes]
                        logger.info(f"📋 主题列表: {theme_names}")
            
            # 🔥 修复4：如果仍然有问题，使用更大的limit值重试
            if len(themes) < 3:  # 如果主题数太少
                logger.warning(f"⚠️  只获取到 {len(themes)} 个主题，尝试使用更大limit")
                
                # 重试使用更大limit
                raw_result = await db_manager.get_all_active_themes(limit=1000)
                if raw_result and len(raw_result) > len(themes):
                    logger.info(f"🔄 使用大limit后获取到 {len(raw_result)} 个主题")
                    # 重新转换...
            
            # 🔥 修复5：最终检查
            logger.info(f"🎯 最终返回 {len(themes)} 个主题给AI")
            
            # 缓存结果
            if self.use_cache and themes:
                self.cache[cache_key] = {
                    'themes': themes,
                    'timestamp': datetime.now().timestamp()
                }
            
            return themes
            
        except Exception as e:
            logger.error(f"❌ 获取活动主题失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def fetch_themes_by_industries(self, 
                                industries: List[str], 
                                limit: int = 20) -> List[Dict[str, Any]]:
        """
        🔥 修复：直接返回所有主题，让AI自己做相似性分析！
        
        Args:
            industries: 行业列表（只用于日志记录）
            limit: 返回主题数量限制
            
        Returns:
            所有主题列表
        """
        try:
            # 🔥 关键：直接返回所有主题，不做任何过滤
            all_themes = await self.fetch_all_active_themes(limit=limit)
            
            # 只记录日志，不进行过滤
            if industries:
                logger.info(f"📊 事件行业: {industries}")
            
            logger.info(f"✅ 返回 {len(all_themes)} 个主题给AI进行相似性分析")
            
            # 显示主题信息供调试
            for i, theme in enumerate(all_themes[:3]):
                logger.info(f"   主题 {i+1}: {theme.get('name', '')}")
            
            return all_themes
            
        except Exception as e:
            logger.error(f"❌ 获取主题失败: {e}")
            return []

    def _split_industry_words(self, industry: str) -> List[str]:
        """分割行业词"""
        # 移除括号内容
        industry = industry.split('（')[0].split('(')[0]
        
        # 分割成关键词
        words = []
        # 中文分割
        for char in industry:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符
                words.append(char)
        
        # 添加完整词
        words.append(industry)
        
        # 添加常见行业变体
        if '智能' in industry:
            words.extend(['AI', '人工智能', '智能'])
        if '消费' in industry:
            words.extend(['消费', '消费品'])
        if '电子' in industry:
            words.extend(['电子', '电子产品'])
        if '穿戴' in industry:
            words.extend(['穿戴', '可穿戴', '设备'])
        if 'AR' in industry or '增强现实' in industry:
            words.extend(['AR', '增强现实', '虚拟现实', 'VR'])
        
        return list(set(words))
    
    async def fetch_themes_with_full_context(self, event: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取主题及其完整上下文 - 供AI深度分析
        
        🔥 关键：提供主题关联的完整新闻内容，让AI进行深度对比
        """
        try:
            logger.info(f"🔍 开始深度主题检索，新事件: {event.get('news_id', 'unknown')}")
            
            # 1. 获取所有活跃主题
            all_themes = await self.fetch_all_active_themes(limit=100)
            
            if not all_themes:
                logger.info("数据库中没有现有主题")
                return []
            
            # 2. 获取新事件的完整内容
            new_event_content = ""
            if 'original_news' in event:
                original_news = event['original_news']
                new_event_content = original_news.get('content', '')
                logger.info(f"新事件内容长度: {len(new_event_content)}字符")
            
            # 3. 为每个主题构建完整上下文
            enriched_themes = []
            
            for theme in all_themes[:limit*2]:  # 获取更多主题用于过滤
                theme_id = theme.get('id')
                theme_name = theme.get('name', '')
                
                # 🔥 获取主题关联的事件ID
                event_ids = []
                try:
                    if hasattr(self.data_fetcher.db_manager, 'get_theme_events'):
                        event_ids = await self.data_fetcher.db_manager.get_theme_events(theme_id, limit=3)
                except:
                    logger.warning(f"无法获取主题 {theme_name} 的关联事件")
                
                # 🔥 获取关联事件的完整内容
                related_event_contents = []
                for event_id in event_ids[:2]:  # 取前2个事件的完整内容
                    try:
                        # 获取事件完整数据
                        if hasattr(self.data_fetcher, 'get_event_for_ai_analysis'):
                            event_data = await self.data_fetcher.get_event_for_ai_analysis(event_id)
                            if event_data and 'original_news' in event_data:
                                content = event_data['original_news'].get('content', '')
                                if content:
                                    related_event_contents.append({
                                        'event_id': event_id,
                                        'content_preview': content[:200] + '...' if len(content) > 200 else content,
                                        'full_content_length': len(content),
                                        'title': event_data['original_news'].get('title', '')
                                    })
                    except Exception as e:
                        logger.debug(f"获取事件 {event_id} 内容失败: {e}")
                
                # 🔥 构建增强主题信息
                enriched_theme = theme.copy()
                enriched_theme['related_event_contents'] = related_event_contents
                enriched_theme['event_content_count'] = len(related_event_contents)
                enriched_theme['total_content_length'] = sum(e['full_content_length'] for e in related_event_contents)
                
                # 计算简单的文本相似度（可选，AI会做深度分析）
                if new_event_content and related_event_contents:
                    # 简单计算：检查是否有共同关键词
                    new_content_words = set(new_event_content.split())
                    theme_content_words = set()
                    for event_content in related_event_contents:
                        preview = event_content.get('content_preview', '')
                        theme_content_words.update(preview.split())
                    
                    common_words = new_content_words & theme_content_words
                    enriched_theme['keyword_overlap'] = len(common_words)
                    enriched_theme['keyword_overlap_ratio'] = len(common_words) / max(len(new_content_words), 1)
                else:
                    enriched_theme['keyword_overlap'] = 0
                    enriched_theme['keyword_overlap_ratio'] = 0
                
                enriched_themes.append(enriched_theme)
            
            # 4. 按关键词重叠度排序
            enriched_themes.sort(key=lambda x: x.get('keyword_overlap_ratio', 0), reverse=True)
            
            result = enriched_themes[:limit]
            logger.info(f"🔍 找到 {len(result)} 个相关主题（带完整上下文）")
            
            # 记录上下文信息供调试
            for i, theme in enumerate(result[:3]):
                logger.info(f"  主题{i+1}: {theme.get('name')}, 关联事件数: {len(theme.get('related_event_contents', []))}, "
                        f"关键词重叠度: {theme.get('keyword_overlap_ratio', 0):.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取主题完整上下文失败: {e}")
            import traceback
            traceback.print_exc()
            return await self.fetch_all_active_themes(limit=limit)  # 降级到基本方法

    async def fetch_relevant_themes(self, event: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取相关主题 - 🔥智能处理：数据库为空时返回空列表，不为空时强制完整内容
        """
        try:
            logger.info(f"🔍 获取相关主题 - 事件: {event.get('news_id', 'unknown')}")
            
            # 1. 首先检查数据库状态
            all_themes = await self.fetch_all_active_themes(limit=10)
            
            if not all_themes:
                logger.info("✅ 数据库为空，将返回空列表给AI创建新主题")
                return []  # 🔥 关键：数据库为空时返回空列表，而不是抛出异常
            
            logger.info(f"📊 数据库中有 {len(all_themes)} 个主题，开始获取完整内容")
            
            # 2. 数据库不为空时，强制获取完整内容
            themes_with_content = await self.fetch_themes_with_complete_news_content(event, limit)
            
            if not themes_with_content:
                # 🔥 数据库有主题但无法获取完整内容，这是严重错误
                error_msg = "数据库有主题但无法获取完整新闻内容，请检查数据完整性"
                logger.error(f"❌🔥 {error_msg}")
                raise ValueError(error_msg)
            
            # 3. 验证主题是否包含完整内容
            incomplete_themes = [t for t in themes_with_content if not t.get('has_complete_content', False)]
            if incomplete_themes:
                incomplete_names = [t.get('name', '') for t in incomplete_themes]
                logger.warning(f"⚠️  部分主题缺少完整内容: {incomplete_names}")
            
            complete_count = sum(1 for t in themes_with_content if t.get('has_complete_content', False))
            logger.info(f"✅ 返回 {len(themes_with_content)} 个主题（{complete_count} 个有完整内容）")
            
            return themes_with_content
            
        except Exception as e:
            logger.error(f"❌ 获取相关主题失败: {e}")
            # 🔥 重要：只在数据库有主题但获取失败时才抛出异常
            all_themes = await self.fetch_all_active_themes(limit=10)
            if all_themes:
                raise  # 数据库有主题但获取失败，抛出异常
            else:
                logger.info("✅ 数据库为空，返回空列表")
                return []  # 数据库为空，返回空列表
        
    # theme_service/related_theme_fetcher.py 修改/添加以下方法
    async def fetch_themes_with_complete_news_content(self, event: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        """
        🔥 强制完整版：获取主题及其关联新闻的完整内容
        """
        try:
            logger.info("🔍 强制获取主题完整新闻内容...")
            
            # 1. 获取所有活跃主题
            all_themes = await self.fetch_all_active_themes(limit=100)
            
            if not all_themes:
                logger.info("数据库中没有现有主题")
                return []
            
            # 2. 为每个主题获取完整关联新闻
            enriched_themes = []
            
            for theme in all_themes[:limit*2]:
                theme_id = theme.get('id')
                theme_name = theme.get('name', '')
                
                # 获取主题关联的事件
                related_events = []
                try:
                    # 方法1: 从主题记录中获取
                    if 'related_events' in theme and theme['related_events']:
                        related_events = theme['related_events'][:3]  # 只取前3个
                    # 方法2: 从数据库获取
                    elif hasattr(self.data_fetcher.db_manager, 'get_theme_events'):
                        related_events = await self.data_fetcher.db_manager.get_theme_events(theme_id, limit=3)
                except Exception as e:
                    logger.debug(f"获取主题 {theme_name} 关联事件失败: {e}")
                
                # 获取每个关联事件的完整内容
                related_news_full_contents = []
                for event_id in related_events:
                    try:
                        # 获取事件完整数据
                        event_data = await self.data_fetcher.db_manager.get_event(event_id)
                        if event_data and 'original_news' in event_data:
                            original_news = event_data['original_news']
                            
                            # 构建完整内容
                            if 'content' in original_news and original_news['content']:
                                full_content = {
                                    'title': original_news.get('title', ''),
                                    'content': original_news.get('content', ''),
                                    'content_length': len(original_news.get('content', '')),
                                    'date': original_news.get('date', ''),
                                    'event_id': event_id
                                }
                                related_news_full_contents.append(full_content)
                    except Exception as e:
                        logger.debug(f"获取事件 {event_id} 内容失败: {e}")
                        continue
                
                # 构建增强主题
                enriched_theme = theme.copy()
                if related_news_full_contents:
                    enriched_theme['related_news_full_contents'] = related_news_full_contents
                    enriched_theme['has_complete_content'] = True
                    enriched_theme['related_event_count'] = len(related_news_full_contents)
                    enriched_theme['total_content_length'] = sum(n['content_length'] for n in related_news_full_contents)
                else:
                    enriched_theme['has_complete_content'] = False
                    enriched_theme['related_event_count'] = 0
                
                enriched_themes.append(enriched_theme)
            
            # 3. 排序并返回
            enriched_themes.sort(key=lambda x: x.get('has_complete_content', False), reverse=True)
            
            result = enriched_themes[:limit]
            logger.info(f"✅ 获取到 {len(result)} 个主题（{sum(1 for t in result if t.get('has_complete_content'))} 个有完整内容）")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取主题完整新闻内容失败: {e}")
            raise

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        logger.info("主题数据缓存已清除")