# database_service/interface.py
"""
数据库接口定义 - 基于实际的theme_master表结构
表结构（2026-01-16版本）：28个字段，包含申万行业分类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ThemeStatus(str, Enum):
    """主题状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    PENDING = "pending"


class ThemeType(str, Enum):
    """主题类型"""
    INVESTMENT = "investment"      # 投资主题
    CONCEPT = "concept"           # 概念主题
    INDUSTRY = "industry"         # 行业主题
    EVENT = "event"               # 事件主题
    STRATEGY = "strategy"         # 策略主题


class LifecycleStage(str, Enum):
    """主题生命周期阶段"""
    INTRODUCTION = "introduction"  # 引入期
    GROWTH = "growth"             # 成长期
    MATURE = "mature"             # 成熟期
    DECLINE = "decline"           # 衰退期
    SUNSET = "sunset"             # 消亡期


class SourceSystem(str, Enum):
    """数据来源系统"""
    TRANSFORMED = "transformed"    # 转换后数据
    SHENWAN = "shenwan"           # 申万行业
    USER_DEFINED = "user_defined" # 用户定义
    AI_GENERATED = "ai_generated" # AI生成


@dataclass
class ThemeTags:
    """主题标签（tags字段的Python表示）"""
    source: str = "shenwan"                     # 数据来源
    aliases: List[str] = field(default_factory=list)  # 别名列表
    version: str = "2.0"                        # 标签版本
    concepts: List[str] = field(default_factory=list)  # 相关概念
    keywords: List[str] = field(default_factory=list)  # 关键词
    heat_level: str = "medium"                  # 热度级别：low/medium/high
    industries: List[str] = field(default_factory=list)  # 所属行业
    industry_code: Optional[str] = None         # 行业代码
    merge_candidates: List[str] = field(default_factory=list)  # 合并候选
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "source": self.source,
            "aliases": self.aliases,
            "version": self.version,
            "concepts": self.concepts,
            "keywords": self.keywords,
            "heat_level": self.heat_level,
            "industries": self.industries,
            "industry_code": self.industry_code,
            "merge_candidates": self.merge_candidates
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThemeTags':
        """从字典创建ThemeTags"""
        return cls(
            source=data.get("source", "shenwan"),
            aliases=data.get("aliases", []),
            version=data.get("version", "2.0"),
            concepts=data.get("concepts", []),
            keywords=data.get("keywords", []),
            heat_level=data.get("heat_level", "medium"),
            industries=data.get("industries", []),
            industry_code=data.get("industry_code"),
            merge_candidates=data.get("merge_candidates", [])
        )


@dataclass
class ThemeRecord:
    """
    主题记录 - 基于实际的theme_master表结构（28个字段）
    
    对应数据库字段：
    - 基本信息：id, name, code, description
    - 分类信息：三级分类 + 路径
    - 标签信息：tags (JSONB)
    - 状态指标：status, theme_type, lifecycle_stage
    - 热度统计：heat_score, confidence_score
    - 关联统计：stock_count, news_count, mention_count
    - 时间戳：created_at, updated_at, last_active_at, last_mentioned
    - 来源信息：source_system, source_id, created_by
    """
    # ========== 基本信息 ==========
    id: int
    name: str
    code: str  # 唯一标识符：INVEST_SW_630504
    
    # ========== 描述信息 ==========
    description: Optional[str] = None
    status: str = ThemeStatus.ACTIVE.value  # active/inactive/archived/pending
    
    # ========== 分类信息（申万三级分类） ==========
    level1_category: Optional[str] = None      # 一级分类：电力设备
    level2_category: Optional[str] = None      # 二级分类：光伏设备
    level3_category: Optional[str] = None      # 三级分类：光伏辅材
    category_path: List[str] = field(default_factory=list)  # 分类路径：["电力设备", "光伏设备", "光伏辅材"]
    
    category1_code: Optional[str] = None       # 一级代码：630000
    category2_code: Optional[str] = None       # 二级代码：630500
    category3_code: Optional[str] = None       # 三级代码：630504
    
    # ========== 标签信息（JSONB字段） ==========
    tags: ThemeTags = field(default_factory=ThemeTags)
    
    # ========== 类型与状态 ==========
    theme_type: str = ThemeType.INVESTMENT.value  # investment/concept/industry/event/strategy
    lifecycle_stage: str = LifecycleStage.GROWTH.value  # growth/mature/decline等
    
    # ========== 热度与置信度 ==========
    heat_score: int = 50                       # 热度评分：0-100
    confidence_score: float = 0.80             # 置信度评分：0.0-1.0
    
    # ========== 关联统计 ==========
    related_stocks: List[str] = field(default_factory=list)  # 关联股票列表
    stock_count: int = 0                       # 股票数量
    news_count: int = 0                        # 新闻数量
    mention_count: int = 0                     # 提及次数
    
    # ========== 时间戳 ==========
    last_mentioned: Optional[datetime] = None  # 最后提及时间
    last_active_at: Optional[datetime] = None  # 最后活跃时间
    
    # ========== 来源信息 ==========
    source_system: str = SourceSystem.TRANSFORMED.value  # 来源系统
    source_id: Optional[str] = None            # 来源ID：SW_630504
    created_by: str = "system"                 # 创建者
    
    # ========== 系统时间戳 ==========
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # ========== 扩展属性 ==========
    # 这些不在数据库表中，但可能在业务逻辑中使用
    matched_keywords: List[str] = field(default_factory=list)  # 匹配的关键词
    relevance_score: float = 0.0               # 相关度评分
    match_confidence: float = 0.0              # 匹配置信度
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于缓存和API返回）"""
        return {
            # 基本信息
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'status': self.status,
            
            # 分类信息
            'level1_category': self.level1_category,
            'level2_category': self.level2_category,
            'level3_category': self.level3_category,
            'category_path': self.category_path,
            'category1_code': self.category1_code,
            'category2_code': self.category2_code,
            'category3_code': self.category3_code,
            
            # 标签信息
            'tags': self.tags.to_dict(),
            
            # 类型与状态
            'theme_type': self.theme_type,
            'lifecycle_stage': self.lifecycle_stage,
            
            # 热度与置信度
            'heat_score': self.heat_score,
            'confidence_score': self.confidence_score,
            
            # 关联统计
            'related_stocks': self.related_stocks,
            'stock_count': self.stock_count,
            'news_count': self.news_count,
            'mention_count': self.mention_count,
            
            # 时间戳
            'last_mentioned': self.last_mentioned.isoformat() if self.last_mentioned else None,
            'last_active_at': self.last_active_at.isoformat() if self.last_active_at else None,
            
            # 来源信息
            'source_system': self.source_system,
            'source_id': self.source_id,
            'created_by': self.created_by,
            
            # 系统时间戳
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            
            # 扩展属性
            'matched_keywords': self.matched_keywords,
            'relevance_score': self.relevance_score,
            'match_confidence': self.match_confidence
        }
    
    def get_keywords(self) -> List[str]:
        """获取主题的所有关键词"""
        keywords = []
        
        # 从tags中获取关键词
        keywords.extend(self.tags.keywords)
        
        # 从aliases中获取关键词
        keywords.extend(self.tags.aliases)
        
        # 从名称中提取关键词
        keywords.append(self.name)
        
        # 从分类路径中提取关键词
        keywords.extend(self.category_path)
        
        # 去重并清理
        unique_keywords = []
        seen = set()
        for kw in keywords:
            if kw and kw not in seen:
                unique_keywords.append(kw)
                seen.add(kw)
        
        return unique_keywords
    
    def get_search_text(self) -> str:
        """获取搜索文本（用于全文搜索）"""
        parts = [
            self.name,
            self.description or "",
            " ".join(self.tags.keywords),
            " ".join(self.tags.aliases),
            " ".join(self.category_path)
        ]
        return " ".join(filter(None, parts))
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThemeRecord':
        """从字典创建ThemeRecord"""
        # 处理时间字段
        def parse_datetime(value):
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except:
                return None
        
        # 处理tags字段
        tags_data = data.get('tags', {})
        if isinstance(tags_data, dict):
            tags = ThemeTags.from_dict(tags_data)
        elif isinstance(tags_data, ThemeTags):
            tags = tags_data
        else:
            tags = ThemeTags()
        
        return cls(
            # 基本信息
            id=data.get('id', 0),
            name=data.get('name', ''),
            code=data.get('code', ''),
            description=data.get('description'),
            status=data.get('status', ThemeStatus.ACTIVE.value),
            
            # 分类信息
            level1_category=data.get('level1_category'),
            level2_category=data.get('level2_category'),
            level3_category=data.get('level3_category'),
            category_path=data.get('category_path', []),
            category1_code=data.get('category1_code'),
            category2_code=data.get('category2_code'),
            category3_code=data.get('category3_code'),
            
            # 标签信息
            tags=tags,
            
            # 类型与状态
            theme_type=data.get('theme_type', ThemeType.INVESTMENT.value),
            lifecycle_stage=data.get('lifecycle_stage', LifecycleStage.GROWTH.value),
            
            # 热度与置信度
            heat_score=data.get('heat_score', 50),
            confidence_score=data.get('confidence_score', 0.80),
            
            # 关联统计
            related_stocks=data.get('related_stocks', []),
            stock_count=data.get('stock_count', 0),
            news_count=data.get('news_count', 0),
            mention_count=data.get('mention_count', 0),
            
            # 时间戳
            last_mentioned=parse_datetime(data.get('last_mentioned')),
            last_active_at=parse_datetime(data.get('last_active_at')),
            
            # 来源信息
            source_system=data.get('source_system', SourceSystem.TRANSFORMED.value),
            source_id=data.get('source_id'),
            created_by=data.get('created_by', 'system'),
            
            # 系统时间戳
            created_at=parse_datetime(data.get('created_at')),
            updated_at=parse_datetime(data.get('updated_at')),
            
            # 扩展属性
            matched_keywords=data.get('matched_keywords', []),
            relevance_score=data.get('relevance_score', 0.0),
            match_confidence=data.get('match_confidence', 0.0)
        )
    
    @property
    def is_active(self) -> bool:
        """是否活跃"""
        return self.status == ThemeStatus.ACTIVE.value
    
    @property
    def is_investment_theme(self) -> bool:
        """是否是投资主题"""
        return self.theme_type == ThemeType.INVESTMENT.value
    
    @property
    def heat_level(self) -> str:
        """获取热度级别"""
        if self.heat_score >= 80:
            return "high"
        elif self.heat_score >= 60:
            return "medium"
        else:
            return "low"


@dataclass
class EventThemeRelation:
    """事件-主题关联记录"""
    id: int
    event_id: int
    theme_id: int
    confidence: float = 0.0                     # 关联置信度：0.0-1.0
    confidence_level: str = "medium"            # 置信度级别：low/medium/high
    confidence_weight: int = 50                 # 置信度权重：0-100
    evidence: Optional[str] = None              # 关联证据
    match_type: str = "keyword"                 # 匹配类型：keyword/ai_model/rule
    matched_keywords: List[str] = field(default_factory=list)  # 匹配的关键词
    created_at: Optional[datetime] = None       # 创建时间
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'event_id': self.event_id,
            'theme_id': self.theme_id,
            'confidence': self.confidence,
            'confidence_level': self.confidence_level,
            'confidence_weight': self.confidence_weight,
            'evidence': self.evidence,
            'match_type': self.match_type,
            'matched_keywords': self.matched_keywords,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class NewsEvent:
    """新闻事件记录"""
    id: int
    title: str
    content: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    publish_time: Optional[datetime] = None
    
    # 状态
    processed: bool = False                     # 是否已处理
    processing_status: str = "pending"          # 处理状态：pending/processing/completed/failed
    processing_result: Optional[Dict[str, Any]] = None  # 处理结果
    
    # 分析字段
    keywords: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    impact_industries: List[str] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=dict)  # 实体识别
    
    # 置信度
    confidence: float = 0.0                     # 事件置信度：0.0-1.0
    sentiment_score: float = 0.0                # 情感评分：-1.0到1.0
    
    # 时间戳
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'summary': self.summary,
            'source': self.source,
            'url': self.url,
            'publish_time': self.publish_time.isoformat() if self.publish_time else None,
            
            'processed': self.processed,
            'processing_status': self.processing_status,
            'processing_result': self.processing_result,
            
            'keywords': self.keywords,
            'categories': self.categories,
            'impact_industries': self.impact_industries,
            'entities': self.entities,
            
            'confidence': self.confidence,
            'sentiment_score': self.sentiment_score,
            
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DatabaseManager(ABC):
    """数据库管理器接口 - 针对实际表结构调整"""
    
    # ========== 连接管理 ==========
    @abstractmethod
    async def connect(self) -> None:
        """建立数据库连接"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """关闭数据库连接"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    def transaction(self) -> AsyncContextManager:
        """事务上下文管理器"""
        pass
    
    # ========== 主题操作（基于实际表结构） ==========
    @abstractmethod
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题（按ID）"""
        pass
    
    async def get_theme_by_code(self, code: str) -> Optional[ThemeRecord]:
        """获取主题（按code）"""
        # 默认实现，子类可以重写
        themes = await self.search_themes(code, limit=1)
        return themes[0] if themes else None
    
    @abstractmethod
    async def get_theme_by_name(self, name: str) -> Optional[ThemeRecord]:
        """根据名称获取主题"""
        pass
    
    @abstractmethod
    async def get_all_active_themes(self, limit: int = 1000) -> List[ThemeRecord]:
        """获取所有活跃主题"""
        pass
    
    @abstractmethod
    async def create_theme(self, name: str, code: str, **kwargs) -> ThemeRecord:
        """创建新主题（必须包含code字段）"""
        pass
    
    @abstractmethod
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题"""
        pass
    
    @abstractmethod
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度"""
        pass
    
    @abstractmethod
    async def increment_mention_count(self, theme_id: int, increment: int = 1) -> None:
        """增加提及次数"""
        pass
    
    async def find_related_themes(self, event_data: Dict[str, Any], limit: int = 5) -> List[ThemeRecord]:
        """
        查找相关主题 - 基于关键词匹配
        
        参数:
            event_data: 事件数据，应包含keywords或impact_industries字段
            limit: 返回的最大主题数量
        
        返回:
            相关主题列表（按相关度排序）
        """
        # 基础实现，子类可以重写
        keywords = event_data.get('keywords', [])
        impact_industries = event_data.get('impact_industries', [])
        
        all_keywords = keywords + impact_industries
        if not all_keywords:
            return []
        
        return await self.get_themes_by_keywords(all_keywords, limit)
    
    @abstractmethod
    async def get_themes_by_keywords(self, keywords: List[str], limit: int = 20) -> List[ThemeRecord]:
        """根据关键词获取主题"""
        pass
    
    @abstractmethod
    async def get_themes_by_category(self, category_code: str, level: int = 1, limit: int = 50) -> List[ThemeRecord]:
        """根据分类代码获取主题"""
        pass
    
    @abstractmethod
    async def get_themes_by_heat_level(self, min_heat: int = 60, limit: int = 100) -> List[ThemeRecord]:
        """获取热度较高的主题"""
        pass
    
    async def batch_create_themes(self, themes_data: List[Dict[str, Any]]) -> List[ThemeRecord]:
        """批量创建主题"""
        themes = []
        for data in themes_data:
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
        return themes
    
    @abstractmethod
    async def search_themes(self, query: str, limit: int = 10) -> List[ThemeRecord]:
        """搜索主题（支持名称、描述、关键词搜索）"""
        pass
    
    # ========== 事件-主题关联 ==========
    @abstractmethod
    async def create_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> EventThemeRelation:
        """创建事件-主题关联"""
        pass
    
    @abstractmethod
    async def get_event_themes(self, event_id: int) -> List[EventThemeRelation]:
        """获取事件关联的主题"""
        pass
    
    @abstractmethod
    async def get_theme_events(self, theme_id: int, limit: int = 100) -> List[int]:
        """获取主题关联的事件ID"""
        pass
    
    @abstractmethod
    async def update_event_theme_relation(self, relation_id: int, updates: Dict[str, Any]) -> Optional[EventThemeRelation]:
        """更新事件-主题关联"""
        pass
    
    # ========== 事件管理 ==========
    @abstractmethod
    async def mark_event_processed(self, event_id: int) -> None:
        """标记事件已处理"""
        pass
    
    @abstractmethod
    async def get_unprocessed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取未处理的事件"""
        pass
    
    @abstractmethod
    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件"""
        pass
    
    # ========== 统计与监控 ==========
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pass
    
    async def get_theme_stats(self) -> Dict[str, Any]:
        """获取主题统计信息"""
        stats = await self.get_stats()
        return stats.get('themes', {})
    
    # ========== 高级查询 ==========
    @abstractmethod
    async def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """执行原始SQL查询"""
        pass