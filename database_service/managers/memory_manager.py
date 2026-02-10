# database_service/managers/memory_manager.py
"""
内存数据库管理器 - 适配实际表结构版本
基于实际的theme_master表结构（28个字段），包含申万行业分类
⚠️ 仅用于测试环境，生产环境请使用PostgresDatabaseManager
"""
import logging
from typing import Dict, List, Any, Optional, AsyncContextManager
from datetime import datetime
import asyncio

from managers.base_manager import BaseDatabaseManager
from ..interface import ThemeRecord, EventThemeRelation, ThemeTags, ThemeStatus, ThemeType, LifecycleStage, SourceSystem

logger = logging.getLogger(__name__)


class MemoryDatabaseManager(BaseDatabaseManager):
    """
    内存数据库管理器 - 实现标准接口
    基于实际28字段表结构，用于单元测试和开发环境
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.themes: Dict[int, ThemeRecord] = {}
        self.relations: List[EventThemeRelation] = []
        self.events: Dict[int, Dict[str, Any]] = {}
        self.next_id = 1000  # 从1000开始，避免与真实数据冲突
        
        # 从配置加载测试数据
        self._init_test_data()
        logger.info("✅ 内存数据库管理器初始化完成（28字段结构测试数据已加载）")
    
    def _init_test_data(self):
        """初始化测试数据（基于实际表结构）"""
        # 创建测试主题（基于实际表结构示例）
        test_themes = [
            self._create_test_theme(
                name="人工智能",
                code="TEST_AI_001",
                level1_category="计算机",
                level2_category="人工智能",
                level3_category="机器学习",
                heat_score=95,
                tags=ThemeTags(
                    keywords=["AI", "人工智能", "机器学习", "深度学习", "自然语言处理"],
                    aliases=["AI", "人工智能", "智能技术"],
                    concepts=["科技前沿", "数字经济", "产业升级"],
                    industries=["计算机", "软件服务"],
                    industry_code="AI",
                    heat_level="high"
                )
            ),
            self._create_test_theme(
                name="新能源汽车",
                code="TEST_NEV_002",
                level1_category="汽车",
                level2_category="新能源汽车",
                level3_category="电动车",
                heat_score=88,
                tags=ThemeTags(
                    keywords=["新能源汽车", "电动车", "锂电池", "充电桩", "特斯拉"],
                    aliases=["新能源汽车", "电动车", "新能源车"],
                    concepts=["绿色经济", "碳中和", "环保产业"],
                    industries=["汽车制造", "电力设备"],
                    industry_code="NEV",
                    heat_level="high"
                )
            ),
            self._create_test_theme(
                name="半导体芯片",
                code="TEST_CHIP_003",
                level1_category="电子",
                level2_category="半导体",
                level3_category="芯片设计",
                heat_score=92,
                tags=ThemeTags(
                    keywords=["半导体", "芯片", "集成电路", "处理器", "存储芯片"],
                    aliases=["芯片", "半导体", "集成电路"],
                    concepts=["自主可控", "科技强国", "高端制造"],
                    industries=["电子", "半导体"],
                    industry_code="CHIP",
                    heat_level="high"
                )
            ),
            self._create_test_theme(
                name="创新药",
                code="TEST_PHARMA_004",
                level1_category="医药生物",
                level2_category="生物制品",
                level3_category="创新药",
                heat_score=78,
                tags=ThemeTags(
                    keywords=["创新药", "生物医药", "医药研发", "临床试验", "药品"],
                    aliases=["创新药", "生物医药", "医药研发"],
                    concepts=["健康中国", "生命科学", "医疗创新"],
                    industries=["医药", "生物技术"],
                    industry_code="PHARMA",
                    heat_level="medium"
                )
            ),
            self._create_test_theme(
                name="光伏储能",
                code="TEST_PV_005",
                level1_category="电力设备",
                level2_category="光伏设备",
                level3_category="光伏辅材",
                heat_score=82,
                tags=ThemeTags(
                    keywords=["光伏", "储能", "太阳能", "清洁能源", "新能源"],
                    aliases=["光伏", "储能", "太阳能"],
                    concepts=["能源革命", "绿色发展", "碳中和"],
                    industries=["电力设备", "新能源"],
                    industry_code="PV",
                    heat_level="medium"
                )
            )
        ]
        
        for theme in test_themes:
            self.themes[theme.id] = theme
        
        # 创建测试事件
        test_events = [
            {
                'id': 2001,
                'title': 'OpenAI发布新一代AI模型，性能提升显著',
                'content': 'OpenAI在AI Day上发布了新一代AI模型，在多个基准测试中表现优异...',
                'summary': 'OpenAI发布新一代AI模型',
                'source': '科技新闻',
                'keywords': ['OpenAI', 'AI', '人工智能', '大模型', '机器学习'],
                'categories': ['科技', '人工智能'],
                'impact_industries': ['计算机', '软件服务'],
                'confidence': 0.9,
                'processed': False,
                'processing_status': 'pending'
            },
            {
                'id': 2002,
                'title': '特斯拉上海工厂产量再创新高',
                'content': '特斯拉上海超级工厂本季度产量达到历史新高，Model Y成为最畅销车型...',
                'summary': '特斯拉上海工厂产量创新高',
                'source': '财经新闻',
                'keywords': ['特斯拉', '新能源汽车', '电动车', '产量', '上海工厂'],
                'categories': ['汽车', '制造'],
                'impact_industries': ['汽车制造', '新能源'],
                'confidence': 0.85,
                'processed': False,
                'processing_status': 'pending'
            }
        ]
        
        for event in test_events:
            self.events[event['id']] = event
        
        # 创建一些测试关联
        self.relations.append(EventThemeRelation(
            id=1,
            event_id=2001,
            theme_id=1000,  # 人工智能主题
            confidence=0.85,
            confidence_level='high',
            match_type='keyword',
            matched_keywords=['AI', '人工智能']
        ))
        
        self.relations.append(EventThemeRelation(
            id=2,
            event_id=2002,
            theme_id=1001,  # 新能源汽车主题
            confidence=0.9,
            confidence_level='high',
            match_type='keyword',
            matched_keywords=['新能源汽车', '特斯拉']
        ))
    
    def _create_test_theme(self, name: str, code: str, level1_category: str, 
                          level2_category: str, level3_category: str, 
                          heat_score: int, tags: ThemeTags) -> ThemeRecord:
        """创建测试主题"""
        theme_id = self.next_id
        self.next_id += 1
        
        return ThemeRecord(
            id=theme_id,
            name=name,
            code=code,
            description=f"测试主题：{name}",
            status=ThemeStatus.ACTIVE.value,
            
            # 分类信息
            level1_category=level1_category,
            level2_category=level2_category,
            level3_category=level3_category,
            category_path=[level1_category, level2_category, level3_category],
            category1_code=f"{theme_id}00",
            category2_code=f"{theme_id}01",
            category3_code=f"{theme_id}02",
            
            # 标签信息
            tags=tags,
            
            # 类型与状态
            theme_type=ThemeType.INVESTMENT.value,
            lifecycle_stage=LifecycleStage.GROWTH.value,
            
            # 热度与置信度
            heat_score=heat_score,
            confidence_score=0.80,
            
            # 关联统计
            related_stocks=[f"stock_{i}" for i in range(3)],
            stock_count=3,
            news_count=5,
            mention_count=10,
            
            # 时间戳
            last_mentioned=datetime.now(),
            last_active_at=datetime.now(),
            
            # 来源信息
            source_system=SourceSystem.TRANSFORMED.value,
            source_id=f"TEST_{theme_id}",
            created_by="test_user",
            
            # 系统时间戳
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    async def connect(self) -> None:
        """连接（内存数据库无需实际连接）"""
        self.connected = True
        logger.info("✅ 内存数据库管理器就绪")
    
    async def disconnect(self) -> None:
        """断开连接"""
        self.connected = False
    
    async def health_check(self) -> bool:
        """健康检查"""
        return self.connected
    
    def transaction(self) -> AsyncContextManager:
        """内存事务（模拟）"""
        class MemoryTransaction:
            def __init__(self, manager):
                self.manager = manager
                self.snapshot = None
            
            async def __aenter__(self):
                # 创建快照用于回滚
                self.snapshot = {
                    'themes': self.manager.themes.copy(),
                    'relations': self.manager.relations.copy(),
                    'events': self.manager.events.copy()
                }
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type is not None:
                    # 事务失败，回滚到快照
                    if self.snapshot:
                        self.manager.themes = self.snapshot['themes']
                        self.manager.relations = self.snapshot['relations']
                        self.manager.events = self.snapshot['events']
                    logger.warning(f"事务失败，已回滚: {exc_val}")
                return False
        
        return MemoryTransaction(self)
    
    # ========== 主题操作 ==========
    
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题（按ID）"""
        theme = self.themes.get(theme_id)
        if theme:
            logger.debug(f"✅ 获取主题: {theme.name} (ID: {theme_id})")
        return theme
    
    async def get_theme_by_code(self, code: str) -> Optional[ThemeRecord]:
        """获取主题（按code）"""
        for theme in self.themes.values():
            if theme.code == code:
                logger.debug(f"✅ 按code获取主题: {theme.name} (code: {code})")
                return theme
        return None
    
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        for theme in self.themes.values():
            if theme.name == name:
                logger.debug(f"✅ 按名称获取主题: {name}")
                return theme
        return None
    
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃主题"""
        active_themes = [theme for theme in self.themes.values() 
                        if theme.status == ThemeStatus.ACTIVE.value]
        
        # 按热度排序
        active_themes.sort(key=lambda x: x.heat_score, reverse=True)
        result = active_themes[:limit]
        
        logger.info(f"✅ 获取 {len(result)} 个活跃主题")
        return result
    
    async def create_theme(self, name: str, code: str, **kwargs) -> ThemeRecord:
        """创建新主题"""
        # 检查是否已存在（按code）
        existing_by_code = await self.get_theme_by_code(code)
        if existing_by_code:
            raise Exception(f"主题已存在 (code={code})")
        
        # 检查是否已存在（按name）
        existing_by_name = await self.get_theme_by_name(name)
        if existing_by_name:
            raise Exception(f"主题已存在 (name={name})")
        
        theme_id = self.next_id
        self.next_id += 1
        
        # 处理tags字段
        tags_data = kwargs.get('tags', {})
        if isinstance(tags_data, ThemeTags):
            tags = tags_data
        elif isinstance(tags_data, dict):
            tags = ThemeTags.from_dict(tags_data)
        else:
            tags = ThemeTags()
        
        theme = ThemeRecord(
            # 基本信息
            id=theme_id,
            name=name,
            code=code,
            description=kwargs.get('description', f"主题：{name}"),
            status=kwargs.get('status', ThemeStatus.ACTIVE.value),
            
            # 分类信息
            level1_category=kwargs.get('level1_category'),
            level2_category=kwargs.get('level2_category'),
            level3_category=kwargs.get('level3_category'),
            category_path=kwargs.get('category_path', []),
            category1_code=kwargs.get('category1_code'),
            category2_code=kwargs.get('category2_code'),
            category3_code=kwargs.get('category3_code'),
            
            # 标签信息
            tags=tags,
            
            # 类型与状态
            theme_type=kwargs.get('theme_type', ThemeType.INVESTMENT.value),
            lifecycle_stage=kwargs.get('lifecycle_stage', LifecycleStage.GROWTH.value),
            
            # 热度与置信度
            heat_score=kwargs.get('heat_score', 50),
            confidence_score=kwargs.get('confidence_score', 0.80),
            
            # 关联统计
            related_stocks=kwargs.get('related_stocks', []),
            stock_count=kwargs.get('stock_count', 0),
            news_count=kwargs.get('news_count', 0),
            mention_count=kwargs.get('mention_count', 0),
            
            # 时间戳
            last_mentioned=kwargs.get('last_mentioned'),
            last_active_at=datetime.now(),
            
            # 来源信息
            source_system=kwargs.get('source_system', SourceSystem.USER_DEFINED.value),
            source_id=kwargs.get('source_id'),
            created_by=kwargs.get('created_by', 'system'),
            
            # 系统时间戳
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.themes[theme_id] = theme
        logger.info(f"✅ 内存中创建主题: {name} (code: {code}, ID: {theme_id})")
        
        return theme
    
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题"""
        theme = self.themes.get(theme_id)
        if not theme:
            logger.warning(f"主题不存在: {theme_id}")
            return None
        
        # 更新字段
        for key, value in updates.items():
            if hasattr(theme, key):
                if key == 'tags' and isinstance(value, dict):
                    # 合并tags而不是替换
                    current_tags = theme.tags.to_dict()
                    current_tags.update(value)
                    theme.tags = ThemeTags.from_dict(current_tags)
                elif key == 'tags' and isinstance(value, ThemeTags):
                    theme.tags = value
                else:
                    setattr(theme, key, value)
        
        # 更新时间戳
        theme.updated_at = datetime.now()
        theme.last_active_at = datetime.now()
        
        logger.info(f"✅ 更新主题: {theme.name} (ID: {theme_id})")
        return theme
    
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        theme = self.themes.get(theme_id)
        if theme:
            theme.heat_score += increment
            theme.updated_at = datetime.now()
            theme.last_active_at = datetime.now()
            logger.debug(f"✅ 增加主题热度: {theme.name}, 新热度: {theme.heat_score}")
    
    async def increment_mention_count(self, theme_id: int, increment: int = 1) -> None:
        """增加提及次数"""
        theme = self.themes.get(theme_id)
        if theme:
            theme.mention_count += increment
            theme.last_mentioned = datetime.now()
            theme.updated_at = datetime.now()
            theme.last_active_at = datetime.now()
            logger.debug(f"✅ 增加提及次数: {theme.name}, 新次数: {theme.mention_count}")
    
    async def get_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """根据关键词获取主题"""
        if not keywords:
            return []
        
        matched_themes = []
        for theme in self.themes.values():
            # 检查关键词匹配
            theme_keywords = theme.get_keywords()
            match_count = sum(1 for kw in keywords if any(kw in tk for tk in theme_keywords))
            
            if match_count > 0:
                # 复制主题并设置匹配信息
                import copy
                theme_copy = copy.copy(theme)
                theme_copy.matched_keywords = [
                    kw for kw in keywords 
                    if any(kw in tk for tk in theme_keywords)
                ]
                theme_copy.relevance_score = match_count * 10  # 简单评分
                matched_themes.append((theme_copy, match_count))
        
        # 按匹配度排序
        matched_themes.sort(key=lambda x: x[1], reverse=True)
        
        result = [theme for theme, _ in matched_themes[:limit]]
        logger.debug(f"✅ 关键词搜索找到 {len(result)} 个主题: {keywords}")
        return result
    
    async def get_themes_by_category(self, category_code: str, level: int = 1, limit: int = 50) -> List[ThemeRecord]:
        """根据分类代码获取主题"""
        themes = []
        
        for theme in self.themes.values():
            if level == 1 and theme.category1_code == category_code:
                themes.append(theme)
            elif level == 2 and theme.category2_code == category_code:
                themes.append(theme)
            elif level == 3 and theme.category3_code == category_code:
                themes.append(theme)
            
            if len(themes) >= limit:
                break
        
        # 按热度排序
        themes.sort(key=lambda x: x.heat_score, reverse=True)
        
        logger.debug(f"✅ 分类搜索找到 {len(themes)} 个主题 (level={level}, code={category_code})")
        return themes
    
    async def get_themes_by_heat_level(self, min_heat: int = 60, limit: int = 100) -> List[ThemeRecord]:
        """获取热度较高的主题"""
        hot_themes = [theme for theme in self.themes.values() 
                     if theme.heat_score >= min_heat]
        
        # 按热度排序
        hot_themes.sort(key=lambda x: x.heat_score, reverse=True)
        result = hot_themes[:limit]
        
        logger.debug(f"✅ 获取到 {len(result)} 个高热主题 (min_heat={min_heat})")
        return result
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        themes = []
        
        for data in themes_data:
            try:
                theme = await self.create_theme(
                    data['name'],
                    data['code'],
                    description=data.get('description'),
                    level1_category=data.get('level1_category'),
                    level2_category=data.get('level2_category'),
                    level3_category=data.get('level3_category'),
                    category_path=data.get('category_path', []),
                    category1_code=data.get('category1_code'),
                    category2_code=data.get('category2_code'),
                    category3_code=data.get('category3_code'),
                    tags=data.get('tags', {}),
                    theme_type=data.get('theme_type', ThemeType.INVESTMENT.value),
                    heat_score=data.get('heat_score', 50),
                    confidence_score=data.get('confidence_score', 0.80)
                )
                themes.append(theme)
            except Exception as e:
                logger.warning(f"批量创建主题失败 {data.get('name')}: {e}")
                continue
        
        logger.info(f"✅ 批量创建 {len(themes)}/{len(themes_data)} 个主题")
        return themes
    
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题（支持名称、描述、关键词搜索）"""
        if not query:
            return []
        
        query_lower = query.lower()
        matched_themes = []
        
        for theme in self.themes.values():
            score = 0
            
            # 名称匹配（最高权重）
            if query_lower in theme.name.lower():
                score += 30
            
            # 描述匹配
            if theme.description and query_lower in theme.description.lower():
                score += 20
            
            # 关键词匹配
            theme_keywords = theme.get_keywords()
            for keyword in theme_keywords:
                if query_lower in keyword.lower():
                    score += 10
                    break
            
            # 分类匹配
            if (theme.level1_category and query_lower in theme.level1_category.lower() or
                theme.level2_category and query_lower in theme.level2_category.lower() or
                theme.level3_category and query_lower in theme.level3_category.lower()):
                score += 5
            
            if score > 0:
                matched_themes.append((theme, score))
        
        # 按评分排序
        matched_themes.sort(key=lambda x: x[1], reverse=True)
        
        result = [theme for theme, _ in matched_themes[:limit]]
        logger.debug(f"✅ 搜索到 {len(result)} 个相关主题 (query={query})")
        return result
    
    async def find_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
        """查找相关主题 - 基于关键词匹配"""
        # 提取事件关键词
        event_keywords = []
        if 'keywords' in event_data:
            event_keywords = event_data['keywords']
        elif 'impact_industries' in event_data:
            event_keywords = event_data['impact_industries']
        
        if not event_keywords:
            logger.debug("事件无关键词，无法查找相关主题")
            return []
        
        # 调用关键词搜索
        return await self.get_themes_by_keywords(event_keywords, limit)
    
    # ========== 事件-主题关联 ==========
    
    async def create_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> EventThemeRelation:
        """创建事件-主题关联"""
        # 检查主题是否存在
        theme = self.themes.get(theme_id)
        if not theme:
            raise Exception(f"主题不存在: {theme_id}")
        
        relation_id = len(self.relations) + 1
        
        relation = EventThemeRelation(
            id=relation_id,
            event_id=event_id,
            theme_id=theme_id,
            confidence=kwargs.get('confidence', 0.8),
            confidence_level=kwargs.get('confidence_level', 'medium'),
            confidence_weight=kwargs.get('confidence_weight', 50),
            evidence=kwargs.get('evidence'),
            match_type=kwargs.get('match_type', 'keyword'),
            matched_keywords=kwargs.get('matched_keywords', []),
            created_at=datetime.now()
        )
        
        self.relations.append(relation)
        
        # 更新主题统计
        await self.increment_mention_count(theme_id)
        
        logger.info(f"✅ 创建事件-主题关联: event={event_id}, theme={theme.name}")
        return relation
    
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        """获取事件关联的主题"""
        return [r for r in self.relations if r.event_id == event_id]
    
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的事件ID"""
        events = [r.event_id for r in self.relations if r.theme_id == theme_id]
        # 去重并限制数量
        return list(set(events))[:limit]
    
    async def update_event_theme_relation(self, relation_id: int, updates: Dict[str, Any]) -> Optional[EventThemeRelation]:
        """更新事件-主题关联"""
        for relation in self.relations:
            if relation.id == relation_id:
                for key, value in updates.items():
                    if hasattr(relation, key):
                        setattr(relation, key, value)
                logger.info(f"✅ 更新关联: {relation_id}")
                return relation
        
        logger.warning(f"关联不存在: {relation_id}")
        return None
    
    # ========== 事件管理 ==========
    
    async def mark_event_processed(self, event_id: int) -> None:
        """标记事件已处理"""
        event = self.events.get(event_id)
        if event:
            event['processed'] = True
            event['processing_status'] = 'completed'
            logger.info(f"✅ 标记事件已处理: {event_id}")
        else:
            logger.warning(f"事件不存在: {event_id}")
    
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        unprocessed = [event for event in self.events.values() 
                      if not event.get('processed', False) and 
                      event.get('processing_status') == 'pending']
        
        # 按ID排序（模拟时间排序）
        unprocessed.sort(key=lambda x: x['id'], reverse=True)
        
        return unprocessed[:limit]
    
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件"""
        return self.events.get(event_id)
    
    # ========== 统计与监控 ==========
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        active_themes = [t for t in self.themes.values() 
                        if t.status == ThemeStatus.ACTIVE.value]
        
        processed_events = [e for e in self.events.values() 
                          if e.get('processed', False)]
        
        high_confidence_relations = [r for r in self.relations 
                                   if r.confidence_level == 'high']
        
        return {
            'themes': {
                'total': len(self.themes),
                'active': len(active_themes),
                'inactive': len(self.themes) - len(active_themes),
                'archived': 0,
                'avg_heat': sum(t.heat_score for t in self.themes.values()) / max(len(self.themes), 1),
                'max_heat': max((t.heat_score for t in self.themes.values()), default=0),
                'high_heat_count': len([t for t in self.themes.values() if t.heat_score >= 80]),
                'medium_heat_count': len([t for t in self.themes.values() if 60 <= t.heat_score < 80]),
                'low_heat_count': len([t for t in self.themes.values() if t.heat_score < 60])
            },
            'events': {
                'total_events': len(self.events),
                'processed': len(processed_events),
                'unprocessed': len(self.events) - len(processed_events),
                'pending': len([e for e in self.events.values() 
                              if not e.get('processed', False) and 
                              e.get('processing_status') == 'pending'])
            },
            'relations': {
                'total_relations': len(self.relations),
                'avg_confidence': sum(r.confidence for r in self.relations) / max(len(self.relations), 1),
                'high_confidence_count': len(high_confidence_relations),
                'medium_confidence_count': len([r for r in self.relations if r.confidence_level == 'medium']),
                'low_confidence_count': len([r for r in self.relations if r.confidence_level == 'low'])
            },
            'database': {
                'db_size_bytes': 1024 * 1024,  # 模拟1MB
                'db_size_human': '1 MB'
            }
        }
    
    async def get_theme_stats(self) -> Dict[str, Any]:
        """获取主题统计信息"""
        stats = await self.get_stats()
        return stats.get('themes', {})
    
    # ========== 高级查询 ==========
    
    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """执行原始SQL查询（内存中不支持）"""
        logger.warning("内存数据库不支持原始SQL查询")
        return []
    
    # ========== 工具方法 ==========
    
    def clear_test_data(self):
        """清空测试数据（用于测试）"""
        self.themes.clear()
        self.relations.clear()
        self.events.clear()
        self.next_id = 1000
        logger.info("✅ 测试数据已清空")
    
    def add_test_theme(self, theme: ThemeRecord):
        """添加测试主题（用于测试）"""
        self.themes[theme.id] = theme
        logger.info(f"✅ 添加测试主题: {theme.name}")
    
    def add_test_event(self, event: Dict[str, Any]):
        """添加测试事件（用于测试）"""
        event_id = event.get('id')
        if event_id:
            self.events[event_id] = event
            logger.info(f"✅ 添加测试事件: {event.get('title')}")