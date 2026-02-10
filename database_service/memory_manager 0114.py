"""
内存数据库管理器 - 适配新数据结构版
实现DatabaseManager接口，适配修复后的数据结构
"""
import logging
from typing import Dict, List, Any, Optional, AsyncContextManager
from datetime import datetime
from contextlib import asynccontextmanager

from collections import defaultdict
import asyncio
import re

from .interface import (
    DatabaseManager, ThemeRecord, EventThemeRelation,
    DatabaseError, DuplicateError
)
from .config import DatabaseConfig

logger = logging.getLogger(__name__)


class MemoryDatabaseManager(DatabaseManager):
    """
    内存数据库管理器 - 适配新数据结构版
    
    🔥 关键修复：适配新的数据结构，正确处理完整原始内容
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        初始化内存数据库
        """
        self.config = config
        
        # 内存存储
        self.themes: Dict[int, ThemeRecord] = {}  # id -> ThemeRecord
        self.name_index: Dict[str, int] = {}      # name -> id
        self.event_relations: Dict[int, EventThemeRelation] = {}  # id -> relation
        self.event_theme_index: Dict[int, List[int]] = {}  # event_id -> [relation_id]
        self.theme_event_index: Dict[int, List[int]] = {}  # theme_id -> [relation_id]
        
        # 🔥 修复：适配新数据结构的事件存储
        self.events: Dict[int, Dict[str, Any]] = {}  # event_id -> 新结构事件数据
        
        # 主题上下文缓存
        self.theme_context_cache: Dict[str, Dict[str, Any]] = {}
        self.context_cache_ttl: int = 60
        
        # 事件搜索索引
        self.event_search_index: Dict[str, List[int]] = defaultdict(list)
        
        # ID生成器
        self._next_theme_id = 1
        self._next_relation_id = 1
        self._next_event_id = 1000
        
        # 锁
        self._global_lock = asyncio.Lock()
        
        logger.info("✅ MemoryDatabaseManager 初始化完成（适配新数据结构）")
    
    # ========== 连接管理 ==========
    
    async def connect(self) -> bool:
        """建立连接"""
        logger.debug("MemoryDatabaseManager 连接就绪")
        return True
    
    async def disconnect(self) -> None:
        """关闭连接"""
        logger.debug("MemoryDatabaseManager 连接关闭")
    
    async def health_check(self) -> bool:
        """健康检查"""
        return True
    
    # ========== 事务管理 ==========
    
    @asynccontextmanager
    async def transaction(self):
        """内存数据库的事务模拟"""
        themes_backup = self.themes.copy()
        name_index_backup = self.name_index.copy()
        event_relations_backup = self.event_relations.copy()
        
        try:
            yield self
            logger.debug("事务提交成功")
        except Exception as e:
            self.themes = themes_backup
            self.name_index = name_index_backup
            self.event_relations = event_relations_backup
            logger.error(f"事务回滚: {e}")
            raise
    
    # ========== 主题操作 ==========
    
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """根据ID获取主题"""
        return self.themes.get(theme_id)
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        theme_id = self.name_index.get(name)
        return self.themes.get(theme_id) if theme_id else None
    
    async def find_related_themes(self, 
                                 event_data: Dict[str, Any],
                                 limit: int = 5) -> List[ThemeRecord]:
        """
        🔥 简化：不再进行关键词匹配
        匹配逻辑由AI相似性分析器完成
        """
        logger.warning("⚠️ find_related_themes方法已简化，请使用AI相似性分析器进行匹配")
        return await self.get_all_active_themes(limit)
    
    async def create_theme(self,
                          name: str,
                          keywords: Optional[List[str]] = None,
                          description: Optional[str] = None,
                          discovery_source: str = "enhanced_engine",
                          discovery_confidence: float = 0.0) -> ThemeRecord:
        """创建新主题"""
        async with self._global_lock:
            if name in self.name_index:
                existing_theme = self.themes[self.name_index[name]]
                logger.warning(f"主题 '{name}' 已存在，ID: {existing_theme.id}")
                raise DuplicateError(f"主题 '{name}' 已存在")
            
            if keywords is None:
                keywords = self._extract_keywords_from_name(name)
            
            theme = ThemeRecord(
                id=self._next_theme_id,
                name=name,
                keywords=keywords,
                description=description or f"{name}相关主题",
                discovery_source=discovery_source,
                discovery_confidence=discovery_confidence,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            self.themes[self._next_theme_id] = theme
            self.name_index[name] = self._next_theme_id
            
            logger.info(f"创建新主题: {name} (ID: {self._next_theme_id})")
            self._next_theme_id += 1
            return theme
    
    async def update_theme(self,
                          theme_id: int,
                          updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题信息"""
        async with self._global_lock:
            theme = self.themes.get(theme_id)
            if not theme:
                return None
            
            for key, value in updates.items():
                if hasattr(theme, key):
                    setattr(theme, key, value)
            
            theme.updated_at = datetime.now()
            
            if 'name' in updates and updates['name'] != theme.name:
                old_name = theme.name
                new_name = updates['name']
                
                if old_name in self.name_index:
                    del self.name_index[old_name]
                self.name_index[new_name] = theme_id
            
            logger.debug(f"更新主题: {theme.name} (ID: {theme_id})")
            return theme
    
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        async with self._global_lock:
            theme = self.themes.get(theme_id)
            if theme:
                theme.heat_score += increment
                theme.updated_at = datetime.now()
                logger.debug(f"主题热度增加: {theme.name} +{increment}")
    
    # ========== 事件-主题关联操作 ==========
    
    async def create_event_theme_relation(self,
                                         event_id: int,
                                         theme_id: int,
                                         confidence: float = 0.0,
                                         confidence_level: str = "medium",
                                         evidence: Optional[Dict] = None) -> EventThemeRelation:
        """创建事件-主题关联"""
        async with self._global_lock:
            existing_relation = self._find_existing_relation_no_lock(event_id, theme_id)
            
            if existing_relation:
                logger.info(f"事件-主题关联已存在: event={event_id}, theme={theme_id}")
                existing_relation.confidence = confidence
                existing_relation.confidence_level = confidence_level
                existing_relation.evidence = evidence or {}
                existing_relation.updated_at = datetime.now()
                return existing_relation
            
            relation = EventThemeRelation(
                id=self._next_relation_id,
                event_id=event_id,
                theme_id=theme_id,
                confidence=confidence,
                confidence_level=confidence_level,
                evidence=evidence or {},
                created_at=datetime.now()
            )
            
            self.event_relations[self._next_relation_id] = relation
            self.event_theme_index.setdefault(event_id, []).append(self._next_relation_id)
            self.theme_event_index.setdefault(theme_id, []).append(self._next_relation_id)
            
            if theme_id in self.themes:
                self.themes[theme_id].heat_score += 1
                self.themes[theme_id].updated_at = datetime.now()
            
            logger.info(f"✅ 创建事件-主题关联: event={event_id}, theme={theme_id}, confidence={confidence}")
            self._next_relation_id += 1
            return relation

    async def create_or_update_event_theme_relation(self,
                                                  event_id: int,
                                                  theme_id: int,
                                                  confidence: float = 0.0,
                                                  confidence_level: str = "medium",
                                                  evidence: Optional[Dict] = None) -> EventThemeRelation:
        """创建或更新事件-主题关联"""
        return await self.create_event_theme_relation(
            event_id=event_id,
            theme_id=theme_id,
            confidence=confidence,
            confidence_level=confidence_level,
            evidence=evidence
        )
    
    async def update_event_theme_relation(self,
                                         relation_id: int,
                                         updates: Dict[str, Any]) -> Optional[EventThemeRelation]:
        """更新事件-主题关联"""
        async with self._global_lock:
            relation = self.event_relations.get(relation_id)
            if not relation:
                logger.warning(f"关联不存在: {relation_id}")
                return None
            
            for key, value in updates.items():
                if hasattr(relation, key):
                    setattr(relation, key, value)
            
            relation.updated_at = datetime.now()
            logger.debug(f"更新事件-主题关联: {relation_id}")
            return relation
    
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        """获取事件关联的所有主题"""
        relation_ids = self.event_theme_index.get(event_id, [])
        relations = []
        
        for rel_id in relation_ids:
            if rel := self.event_relations.get(rel_id):
                relations.append(rel)
        
        return relations
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的所有事件ID"""
        relation_ids = self.theme_event_index.get(theme_id, [])
        event_ids = []
        
        for rel_id in relation_ids[:limit]:
            if rel := self.event_relations.get(rel_id):
                event_ids.append(rel.event_id)
        
        return list(set(event_ids))
    
    # ========== 事件操作 - 适配新数据结构 ==========
    
    async def create_or_update_event(self, event_data: Dict[str, Any]) -> int:
        """
        🔥 关键修复：适配新的事件数据结构
        
        新数据结构：
        {
            "news_id": "...",
            "event_info": {...},          # 事件基础信息
            "theme_discovery_directive": {...}, # 主题发现决策
            "original_news": {...}        # 完整原始数据
        }
        """
        async with self._global_lock:
            # 获取事件ID
            event_id = event_data.get('news_id', event_data.get('id', f'event_{self._next_event_id}'))
            
            # 处理事件ID
            if isinstance(event_id, str) and event_id.startswith('event_'):
                try:
                    event_id = self._next_event_id
                    self._next_event_id += 1
                except:
                    pass
            
            # 🔥 提取新结构中的完整内容
            full_content = ""
            title = ""
            
            if 'original_news' in event_data:
                original_news = event_data['original_news']
                full_content = original_news.get('content', '')
                title = original_news.get('title', '')
                logger.info(f"从original_news获取完整内容，长度: {len(full_content)} 字符")
            else:
                logger.warning(f"⚠️ 事件数据缺少original_news字段")
            
            # 🔥 构建适配新结构的完整事件数据
            complete_event = {
                'id': event_id,
                'news_id': event_data.get('news_id', event_id),
                'title': title,
                
                # 🔥 存储完整原始内容
                'full_content': full_content,
                'content_length': len(full_content),
                'has_full_content': len(full_content) > 100,
                
                # 🔥 适配新结构：event_info
                'event_info': event_data.get('event_info', {}),
                
                # 🔥 适配新结构：theme_discovery_directive
                'theme_discovery_directive': event_data.get('theme_discovery_directive', {}),
                
                # 🔥 适配新结构：original_news（完整存储）
                'original_news': event_data.get('original_news', {}),
                
                # 元数据
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'theme_directive_processed': False,
                
                # 🔥 移除冗余字段
                # ❌ 已移除：summary、raw_ai_response、ai_response、data_integrity、extraction_metadata
            }
            
            # 存储事件
            self.events[event_id] = complete_event
            
            # 更新搜索索引
            await self._update_event_search_index_new_structure(event_id, complete_event)
            
            logger.info(f"✅ 存储事件（新结构）: {event_id}, 内容长度: {len(full_content)}")
            
            return event_id
    
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件详情（适配新结构）"""
        async with self._global_lock:
            if event_id in self.events:
                return self.events[event_id]
            
            # 返回适配新结构的模拟数据
            logger.warning(f"事件 {event_id} 不存在，返回模拟数据（新结构）")
            return {
                'id': event_id,
                'news_id': f'test_{event_id}',
                'title': f'模拟事件 {event_id}',
                'full_content': f'这是事件 {event_id} 的完整内容，包含详细信息描述。这是一个模拟事件，用于测试系统功能。事件涉及多个行业领域，具有重要的市场影响。相关公司包括测试公司A和测试公司B。技术方面涉及创新突破和研发进展。该事件将在未来几个月内持续产生影响。',
                'content_length': 200,
                'has_full_content': True,
                'event_info': {
                    'event_type': '技术突破',
                    'impact_industries': ['人工智能', '大数据', '云计算'],
                    'direction': '利好',
                    'event_confidence': 0.8
                },
                'theme_discovery_directive': {
                    'action': 'CREATE_NEW',
                    'decision_confidence': 0.75,
                    'reason': '模拟重大技术突破事件'
                },
                'original_news': {
                    'title': f'模拟事件 {event_id}',
                    'content': f'这是事件 {event_id} 的完整原始内容...',
                    'content_length': 200,
                    'date': '2024-01-01'
                },
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'theme_directive_processed': False
            }
    
    async def get_event_with_full_context(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件的完整上下文"""
        event = await self.get_event(event_id)
        if not event:
            return None
        
        # 确保返回适配新结构的完整数据
        full_context = event.copy()
        
        # 🔥 添加数据完整性标记（适配新结构）
        full_content = event.get('full_content', '')
        full_context['data_quality'] = {
            'has_full_content': bool(full_content) and len(full_content) > 100,
            'content_length': len(full_content),
            'has_event_info': 'event_info' in event,
            'has_theme_directive': 'theme_discovery_directive' in event,
            'has_original_news': 'original_news' in event
        }
        
        return full_context
    
    async def _update_event_search_index_new_structure(self, event_id: int, event_data: Dict[str, Any]):
        """
        更新事件搜索索引（适配新结构）
        """
        # 从新结构的关键字段提取搜索词
        search_fields = []
        
        # 从original_news.title
        if 'original_news' in event_data:
            title = event_data['original_news'].get('title', '')
            if title:
                search_fields.append(title)
        
        # 从event_info.impact_industries
        if 'event_info' in event_data:
            industries = event_data['event_info'].get('impact_industries', [])
            search_fields.append(' '.join(industries))
        
        # 从full_content（提取前200字符）
        full_content = event_data.get('full_content', '')
        if full_content:
            search_fields.append(full_content[:200])
        
        for field in search_fields:
            if field:
                words = re.findall(r'[一-鿿]{2,4}', str(field))
                for word in words:
                    if word not in self.event_search_index or event_id not in self.event_search_index[word]:
                        self.event_search_index[word].append(event_id)
    
    async def mark_event_processed(self, event_id: int) -> None:
        """标记事件已处理"""
        async with self._global_lock:
            if event_id not in self.events:
                self.events[event_id] = {
                    'id': event_id,
                    'theme_directive_processed': True,
                    'processed_at': datetime.now().isoformat()
                }
            else:
                self.events[event_id]['theme_directive_processed'] = True
                self.events[event_id]['processed_at'] = datetime.now().isoformat()
            
            logger.debug(f"标记事件已处理: {event_id}")
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件（适配新结构）"""
        mock_events = []
        for i in range(min(limit, 5)):
            mock_events.append({
                'id': self._next_event_id + i,
                'news_id': f'test_{self._next_event_id + i}',
                'title': f'模拟事件 {i+1}',
                'full_content': f'模拟事件 {i+1} 的完整内容...',
                'event_info': {
                    'event_type': '技术突破',
                    'impact_industries': ['人工智能', '大数据'],
                    'direction': '利好',
                    'event_confidence': 0.8
                },
                'theme_discovery_directive': {
                    'action': 'CREATE_NEW',
                    'decision_confidence': 0.8,
                    'reason': '模拟重大事件'
                },
                'original_news': {
                    'title': f'模拟事件 {i+1}',
                    'content': f'模拟事件 {i+1} 的完整内容...'
                },
                'theme_directive_processed': False
            })
        
        return mock_events
    
    # ========== 主题增强功能 ==========
    
    async def get_enriched_theme(self, theme_id: int) -> Optional[Dict[str, Any]]:
        """
        获取增强的主题信息（适配新结构）
        """
        async with self._global_lock:
            cache_key = f"enriched_theme_{theme_id}"
            if cache_key in self.theme_context_cache:
                cached = self.theme_context_cache[cache_key]
                cache_time = datetime.fromisoformat(cached.get('cache_timestamp', '2000-01-01'))
                if (datetime.now() - cache_time).seconds < self.context_cache_ttl:
                    logger.debug(f"使用缓存的增强主题: {theme_id}")
                    return cached
            
            theme = self.themes.get(theme_id)
            if not theme:
                return None
            
            # 🔥 获取主题关联的完整事件数据（适配新结构）
            event_ids = await self.get_theme_events(theme_id, limit=5)
            events = []
            for event_id in event_ids:
                event = await self.get_event_with_full_context(event_id)
                if event:
                    events.append(event)
            
            # 🔥 构建增强主题信息（适配新结构）
            enriched = {
                'id': theme.id,
                'name': theme.name,
                'description': theme.description or f"关于{theme.name}的主题",
                'keywords': theme.keywords or [],
                'event_count': len(await self.get_theme_events(theme_id, limit=1000)),
                'heat_score': theme.heat_score,
                'confidence': theme.discovery_confidence,
                
                # 🔥 主题上下文（适配新结构）
                'context': {
                    'recent_events': events,
                    'event_count': len(events),
                    'event_summaries': [
                        {
                            'summary': e.get('full_content', '')[:150] + '...',
                            'industries': e.get('event_info', {}).get('impact_industries', []),
                            'type': e.get('event_info', {}).get('event_type', '')
                        }
                        for e in events[:3]
                    ],
                    'common_industries': self._extract_common_industries_new_structure(events),
                    'time_range': self._get_events_time_range_new_structure(events),
                    'key_entities': self._extract_key_entities_new_structure(events)
                },
                
                # 🔥 AI友好的描述
                'ai_description': self._generate_ai_description_new_structure(theme, events),
                
                'cache_timestamp': datetime.now().isoformat()
            }
            
            self.theme_context_cache[cache_key] = enriched
            logger.debug(f"生成增强主题: {theme.name}, 关联事件: {len(events)}")
            return enriched
    
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
    
    def _extract_key_entities_new_structure(self, events: List[Dict]) -> Dict[str, List]:
        """提取关键实体（适配新结构）"""
        entities = {
            'companies': set(),
            'technologies': set(),
            'keywords': set()
        }
        
        for event in events:
            # 🔥 适配新结构：从full_content提取
            content = event.get('full_content', '')
            if content:
                company_patterns = [r'([\u4e00-\u9fff]{2,6})公司', r'([\u4e00-\u9fff]{2,6})集团']
                for pattern in company_patterns:
                    matches = re.findall(pattern, content)
                    entities['companies'].update(matches)
                
                tech_keywords = ['技术', '研发', '创新', '突破', '专利', '成果', '系统', '平台']
                for keyword in tech_keywords:
                    if keyword in content:
                        matches = re.findall(f'[\u4e00-\u9fff]*{keyword}[\u4e00-\u9fff]*', content)
                        entities['technologies'].update(matches)
        
        return {k: list(v)[:5] for k, v in entities.items()}
    
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
    
    def _generate_ai_description_new_structure(self, theme: ThemeRecord, events: List[Dict]) -> str:
        """生成AI友好的主题描述（适配新结构）"""
        theme_name = theme.name
        event_count = len(events)
        
        if event_count == 0:
            return f"关于{theme_name}的主题，尚无关联事件"
        
        industries = set()
        event_types = set()
        
        for event in events[:3]:
            event_info = event.get('event_info', {})
            industries.update(event_info.get('impact_industries', []))
            event_types.add(event_info.get('event_type', ''))
        
        industry_str = '、'.join(list(industries)[:3]) if industries else "多个行业"
        event_type_str = '、'.join([t for t in event_types if t]) if event_types else "多种类型"
        
        if industry_str and event_type_str:
            return f"{theme_name}主题，涉及{industry_str}，事件类型包括{event_type_str}，共{event_count}个相关事件。"
        else:
            return f"{theme_name}主题，共{event_count}个相关事件。"
    
    # ========== 主题查询方法 ==========
    
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃题材"""
        async with self._global_lock:
            active_themes = []
            
            for theme in self.themes.values():
                if theme.lifecycle_stage != 'archived' and theme.heat_score >= 0:
                    active_themes.append(theme)
                
                if len(active_themes) >= limit * 2:
                    break
            
            active_themes.sort(key=lambda x: x.heat_score, reverse=True)
            result = active_themes[:limit]
            logger.debug(f"获取到 {len(result)} 个活跃主题")
            return result
    
    async def get_all_active_themes_with_context(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取所有活跃主题及其完整上下文（适配新结构）
        """
        themes = await self.get_all_active_themes(limit * 2)
        
        enriched_themes = []
        for theme in themes:
            enriched = await self.get_enriched_theme(theme.id)
            if enriched:
                enriched_themes.append(enriched)
        
        enriched_themes.sort(key=lambda x: x.get('event_count', 0), reverse=True)
        logger.info(f"获取到 {len(enriched_themes)} 个增强主题")
        return enriched_themes[:limit]
    
    async def get_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """根据关键词列表获取题材"""
        if not keywords:
            return []
        
        async with self._global_lock:
            matched_themes = []
            keyword_set = set(k.lower() for k in keywords)
            
            for theme in self.themes.values():
                theme_text = f"{theme.name} {' '.join(theme.keywords)} {theme.description or ''}"
                theme_text_lower = theme_text.lower()
                
                matched_keywords = sum(1 for kw in keyword_set if kw in theme_text_lower)
                
                if matched_keywords > 0:
                    theme_with_score = theme
                    theme_with_score.relevance_score = matched_keywords / len(keyword_set)
                    matched_themes.append(theme_with_score)
            
            matched_themes.sort(key=lambda x: getattr(x, 'relevance_score', 0), reverse=True)
            result = matched_themes[:limit]
            logger.debug(f"关键词查询: {keywords} -> 找到 {len(result)} 个匹配主题")
            return result
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        if not themes_data:
            return []
        
        created_themes = []
        async with self._global_lock:
            for theme_data in themes_data:
                try:
                    name = theme_data.get('name')
                    if name and name in self.name_index:
                        logger.warning(f"主题 '{name}' 已存在，跳过创建")
                        continue
                    
                    theme = await self.create_theme(**theme_data)
                    created_themes.append(theme)
                    
                except Exception as e:
                    logger.error(f"批量创建主题失败: {theme_data.get('name')}, 错误: {e}")
                    continue
        
        logger.info(f"批量创建了 {len(created_themes)} 个主题")
        return created_themes
    
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题"""
        if not query or not query.strip():
            return []
        
        query = query.strip().lower()
        
        async with self._global_lock:
            matched_themes = []
            
            for theme in self.themes.values():
                search_fields = [
                    theme.name.lower(),
                    ' '.join(theme.keywords).lower(),
                    (theme.description or '').lower()
                ]
                
                if any(query in field for field in search_fields if field):
                    matched_themes.append(theme)
            
            matched_themes.sort(key=lambda x: x.heat_score, reverse=True)
            result = matched_themes[:limit]
            logger.debug(f"搜索 '{query}' -> 找到 {len(result)} 个主题")
            return result
    
    # ========== 统计与监控 ==========
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        async with self._global_lock:
            return {
                'total_themes': len(self.themes),
                'total_relations': len(self.event_relations),
                'total_events': len(self.events),
                'theme_names': list(self.name_index.keys()),
                'avg_relations_per_theme': len(self.event_relations) / max(len(self.themes), 1),
                'memory_usage': 'N/A',
                'data_structure': '适配新结构',
                'event_avg_content_length': sum(len(e.get('full_content', '')) for e in self.events.values()) / max(len(self.events), 1)
            }
    
    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """执行原始SQL查询"""
        logger.warning("内存数据库不支持原始SQL查询")
        return []
    
    # ========== 辅助方法 ==========
    
    def _extract_keywords_from_name(self, name: str) -> List[str]:
        """从主题名称中提取关键词"""
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', name)
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', cleaned)
        english_words = re.findall(r'[A-Z]{2,}|[A-Z][a-z]+', cleaned)
        keywords = chinese_words + english_words
        
        if not keywords:
            keywords = [name[:20]]
        
        return list(set(keywords))[:5]
    
    def _find_existing_relation_no_lock(self, event_id: int, theme_id: int) -> Optional[EventThemeRelation]:
        """查找已存在的事件-主题关联"""
        relation_ids = self.event_theme_index.get(event_id, [])
        for rel_id in relation_ids:
            if rel := self.event_relations.get(rel_id):
                if rel.theme_id == theme_id:
                    return rel
        return None
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理MemoryDatabaseManager资源...")
        self.themes.clear()
        self.name_index.clear()
        self.event_relations.clear()
        self.event_theme_index.clear()
        self.theme_event_index.clear()
        self.events.clear()
        self.theme_context_cache.clear()
        self.event_search_index.clear()
        
        self._next_theme_id = 1
        self._next_relation_id = 1
        logger.info("✅ MemoryDatabaseManager资源清理完成")