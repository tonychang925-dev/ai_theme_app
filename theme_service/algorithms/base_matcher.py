"""
algorithms/base_matcher.py
匹配算法基类 - 定义算法接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np

@dataclass
class MatchResult:
    """匹配结果数据类"""
    theme_id: str
    theme_name: str
    match_score: float
    matched_keywords: List[str]
    match_details: Dict[str, Any]
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'theme_id': self.theme_id,
            'theme_name': self.theme_name,
            'match_score': round(self.match_score, 4),
            'matched_keywords': self.matched_keywords,
            'confidence': round(self.confidence, 3),
            'details': self.match_details
        }

class BaseMatcher(ABC):
    """匹配算法基类"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.themes = {}  # {theme_id: theme_data}
        self.initialized = False
    
    def initialize(self, themes: List[Dict]) -> None:
        """初始化算法，加载题材数据"""
        self.themes = {t['code']: t for t in themes}
        self._build_index()
        self.initialized = True
    
    @abstractmethod
    def _build_index(self):
        """构建索引（如倒排索引等）"""
        pass
    
    @abstractmethod
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """
        匹配入口
        
        Args:
            event_data: 事件数据 {title, content, keywords, ...}
            precision: 'major' | 'normal' 匹配精度
        
        Returns:
            匹配结果列表
        """
        pass
    
    @abstractmethod
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        return {
            'name': self.__class__.__name__,
            'version': '1.0.0',
            'type': 'base'
        }
    
    def set_precision_mode(self, mode: str):
        """设置匹配精度模式"""
        if mode not in ['major', 'normal']:
            raise ValueError(f"Unsupported precision mode: {mode}")
        self.config['precision_mode'] = mode
    
    def calculate_confidence(self, match_result: MatchResult) -> float:
        """计算置信度"""
        # 基础置信度计算
        base_confidence = min(match_result.match_score * 1.2, 0.95)
        
        # 根据匹配关键词数量调整
        keyword_factor = min(len(match_result.matched_keywords) / 5, 1.0) * 0.3
        
        # 根据热度调整
        theme = self.themes.get(match_result.theme_id)
        heat_factor = 0.0
        if theme and 'heat_score' in theme:
            heat_factor = min(theme['heat_score'] / 100, 0.2)
        
        confidence = base_confidence + keyword_factor + heat_factor
        return min(confidence, 1.0)