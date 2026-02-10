"""
匹配算法基类 - 定义算法接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field
import numpy as np

@dataclass
class MatchResult:
    """匹配结果数据类"""
    theme_id: str
    theme_name: str
    match_score: float
    matched_keywords: List[str]
    match_details: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    level1_category: str = ""
    level2_category: str = ""
    level3_category: str = ""
    is_hot: bool = False
    match_type: str = ""
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'theme_id': self.theme_id,
            'theme_name': self.theme_name,
            'match_score': round(self.match_score, 4),
            'confidence': round(self.confidence, 3),
            'matched_keywords': self.matched_keywords,
            'level1_category': self.level1_category,
            'level2_category': self.level2_category,
            'level3_category': self.level3_category,
            'is_hot': self.is_hot,
            'match_type': self.match_type,
            'details': self.match_details
        }

class BaseMatcher(ABC):
    """匹配算法基类"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.themes: Dict[str, Dict] = {}  # {theme_id: theme_data}
        self.categories: Dict[str, Dict] = {}  # {category_id: category_data}
        self.initialized = False
        
        # 默认配置
        self.default_config = {
            'match_threshold': 0.5,
            'max_results': 10,
            'min_keyword_matches': 2,
            'use_database_tags': True,
            'enable_analyst_logic': False,
            'classification_first': False
        }
        
        if config:
            self._deep_update(self.default_config, config)
        self.config = self.default_config
    
    def _deep_update(self, target: Dict, source: Dict):
        """深度更新配置"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    def initialize(self, themes: List[Dict], categories: List[Dict] = None) -> None:
        """
        初始化算法，加载题材数据
        
        Args:
            themes: 题材数据列表
            categories: 分类数据列表（可选）
        """
        # 存储题材数据
        for theme in themes:
            theme_id = theme.get('code') or theme.get('name', '')
            if theme_id:
                self.themes[theme_id] = theme
        
        # 存储分类数据
        if categories:
            for category in categories:
                cat_id = category.get('category_code') or category.get('name', '')
                if cat_id:
                    self.categories[cat_id] = category
        
        # 构建索引
        self._build_index()
        self.initialized = True
        
        print(f"✅ {self.__class__.__name__} 初始化完成: {len(self.themes)} 个题材")
    
    @abstractmethod
    def _build_index(self):
        """构建算法索引"""
        pass
    
    @abstractmethod
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """
        匹配入口
        
        Args:
            event_data: 事件数据 {title, content, keywords, ...}
            precision: 'high' | 'normal' | 'low' 匹配精度
        
        Returns:
            匹配结果列表
        """
        pass
    
    def calculate_confidence(self, match_result: MatchResult) -> float:
        """
        计算置信度
        
        Args:
            match_result: 匹配结果
        
        Returns:
            置信度 (0.0-1.0)
        """
        # 基础置信度 = 匹配分数
        base_confidence = match_result.match_score
        
        # 关键词匹配数量加成
        keyword_factor = min(len(match_result.matched_keywords) / 5, 0.3)
        
        # 热点题材加成
        heat_factor = 0.1 if match_result.is_hot else 0.0
        
        # 匹配类型加成
        type_factor = 0.0
        if match_result.match_type in ['name_exact_match', 'category_exact_match']:
            type_factor = 0.2
        elif match_result.match_type in ['keyword_exact_match', 'multiple_keyword_match']:
            type_factor = 0.1
        
        confidence = base_confidence + keyword_factor + heat_factor + type_factor
        return min(confidence, 1.0)
    
    def _extract_event_text(self, event_data: Dict) -> str:
        """提取事件文本"""
        return f"{event_data.get('title', '')} {event_data.get('content', '')}"
    
    def _get_theme_heat_score(self, theme_id: str) -> float:
        """获取题材热度分数"""
        theme = self.themes.get(theme_id, {})
        return float(theme.get('heat_score', 50.0))
    
    def _is_hot_theme(self, theme_id: str) -> bool:
        """判断是否是热点题材"""
        heat_score = self._get_theme_heat_score(theme_id)
        return heat_score > 70.0
    
    def _extract_theme_categories(self, theme_id: str) -> Tuple[str, str, str]:
        """提取题材分类"""
        theme = self.themes.get(theme_id, {})
        return (
            theme.get('level1_category', ''),
            theme.get('level2_category', ''),
            theme.get('level3_category', '')
        )
    
    def _extract_theme_tags_keywords(self, theme_id: str) -> List[str]:
        """提取题材tags中的关键词"""
        theme = self.themes.get(theme_id, {})
        tags = theme.get('tags', {})
        
        if isinstance(tags, dict):
            return tags.get('keywords', [])
        return []
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        return {
            'name': self.__class__.__name__,
            'type': getattr(self, 'algorithm_type', 'unknown'),
            'version': '1.0.0',
            'themes_count': len(self.themes),
            'categories_count': len(self.categories),
            'initialized': self.initialized,
            'config': {
                'match_threshold': self.config['match_threshold'],
                'max_results': self.config['max_results'],
                'use_database_tags': self.config['use_database_tags']
            }
        }
    
    def get_config(self) -> Dict:
        """获取算法配置"""
        return self.config.copy()