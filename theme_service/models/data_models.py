# theme_service/models/data_models.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class ThemeType(Enum):
    """题材类型枚举"""
    INVESTMENT = "investment"
    CONCEPT = "concept"
    RELATION = "relation"
    INDUSTRY = "industry"

@dataclass
class Theme:
    """题材数据模型"""
    id: int
    name: str
    code: str
    theme_type: ThemeType
    keywords: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    heat_score: int = 65
    categories: Dict[str, str] = field(default_factory=dict)
    source_system: str = ""
    
    @property
    def all_keywords(self) -> List[str]:
        """所有关键词（包括别名）"""
        return list(set(self.keywords + self.aliases + [self.name]))

@dataclass
class NewsArticle:
    """新闻文章模型"""
    id: str
    title: str
    content: str
    source: str = ""
    publish_time: datetime = None
    url: str = ""
    summary: str = ""
    extracted_keywords: List[str] = field(default_factory=list)

@dataclass
class MatchResult:
    """匹配结果模型"""
    theme: Theme
    match_score: float  # 0-1
    matched_keywords: List[str] = field(default_factory=list)
    match_details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "theme_id": self.theme.id,
            "theme_name": self.theme.name,
            "theme_code": self.theme.code,
            "theme_type": self.theme.theme_type.value,
            "match_score": self.match_score,
            "matched_keywords": self.matched_keywords,
            "categories": self.theme.categories,
            "heat_score": self.theme.heat_score,
            **self.match_details
        }