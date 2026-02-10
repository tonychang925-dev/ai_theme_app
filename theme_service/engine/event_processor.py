"""
algorithms/normal_matcher.py
Normal事件匹配算法 - 中精度、快速匹配
"""
import re
import jieba
from typing import List, Dict, Any
from collections import defaultdict
from .base_matcher import BaseMatcher, MatchResult

class NormalEventMatcher(BaseMatcher):
    """Normal事件匹配算法 - 中精度"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.keyword_index = defaultdict(list)
        
        # Normal算法特有配置
        self.normal_config = {
            'match_threshold': 0.5,      # 中阈值
            'min_keyword_matches': 2,    # 最少关键词匹配数
            'require_name_match': False, # 不要求名称匹配
            'keyword_weight': 0.6,
            'name_weight': 0.2,
            'category_weight': 0.2,
            'enable_fuzzy_match': True,  # 启用模糊匹配
            'fuzzy_threshold': 0.6       # 模糊匹配阈值
        }
        self.config.update(self.normal_config)
        
    def _build_index(self):
        """为Normal算法构建索引"""
        print(f"🔨 构建Normal算法索引...")
        
        for theme_id, theme in self.themes.items():
            # 只构建关键词索引，更简单快速
            keywords = self._extract_theme_keywords(theme)
            for keyword in keywords:
                self.keyword_index[keyword].append(theme_id)
        
        print(f"   关键词索引: {len(self.keyword_index)} 项")
    
    def _extract_theme_keywords(self, theme: Dict) -> List[str]:
        """从题材中提取关键词（简化版）"""
        keywords = set()
        
        # 从名称提取
        name = theme.get('name', '')
        if name:
            name_words = jieba.lcut(name)
            keywords.update([w for w in name_words if len(w) >= 2])
        
        # 从tags中提取
        tags = theme.get('tags', {})
        if isinstance(tags, dict):
            tags_keywords = tags.get('keywords', [])
            keywords.update(tags_keywords)
        
        return list(keywords)[:20]  # 最多20个关键词
    
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """Normal事件匹配 - 中精度"""
        if not self.initialized:
            raise RuntimeError("Matcher not initialized")
        
        # 提取事件信息（简化版）
        event_text = f"{event_data.get('title', '')} {event_data.get('content', '')}"
        event_keywords = self._extract_event_keywords(event_text)
        
        # 快速获取候选题材
        candidate_themes = self._get_candidate_themes(event_keywords)
        
        # 如果候选太少，启用模糊匹配
        if len(candidate_themes) < 3 and self.config['enable_fuzzy_match']:
            fuzzy_candidates = self._fuzzy_match(event_text, event_keywords)
            candidate_themes.extend(fuzzy_candidates)
            candidate_themes = list(set(candidate_themes))
        
        # 计算匹配分数
        results = []
        for theme_id in candidate_themes[:50]:  # 最多处理50个候选
            theme = self.themes[theme_id]
            
            # 快速计算匹配分数
            match_score = self._calculate_quick_match(theme, event_keywords)
            
            if match_score >= self.config['match_threshold']:
                # 收集匹配的关键词
                matched_keywords = self._get_matched_keywords(theme, event_keywords)
                
                result = MatchResult(
                    theme_id=theme_id,
                    theme_name=theme.get('name', ''),
                    match_score=match_score,
                    matched_keywords=matched_keywords,
                    match_details={'quick_match_score': match_score}
                )
                result.confidence = self.calculate_confidence(result)
                results.append(result)
        
        # 排序
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results[:15]  # 返回前15个
    
    def _extract_event_keywords(self, text: str) -> List[str]:
        """从事件文本提取关键词（简化版）"""
        if not text:
            return []
        
        # 简单的分词提取
        words = jieba.lcut(text)
        
        # 过滤
        stop_words = {'的', '了', '在', '是', '和', '与', '及', '对', '为', '有'}
        filtered = [w for w in words if len(w) >= 2 and w not in stop_words]
        
        return filtered[:25]  # 最多25个关键词
    
    def _get_candidate_themes(self, event_keywords: List[str]) -> List[str]:
        """快速获取候选题材"""
        candidates = set()
        
        for keyword in event_keywords:
            if keyword in self.keyword_index:
                candidates.update(self.keyword_index[keyword])
        
        return list(candidates)
    
    def _fuzzy_match(self, event_text: str, event_keywords: List[str]) -> List[str]:
        """模糊匹配"""
        candidates = set()
        
        for index_keyword in self.keyword_index.keys():
            # 检查是否有部分匹配
            for event_keyword in event_keywords:
                if (event_keyword in index_keyword or 
                    index_keyword in event_keyword):
                    candidates.update(self.keyword_index[index_keyword])
        
        return list(candidates)[:20]  # 最多20个模糊匹配
    
    def _calculate_quick_match(self, theme: Dict, event_keywords: List[str]) -> float:
        """快速计算匹配分数"""
        theme_keywords = self._extract_theme_keywords(theme)
        
        if not event_keywords or not theme_keywords:
            return 0.0
        
        # 简单计数匹配
        event_set = set(event_keywords)
        theme_set = set(theme_keywords)
        
        matches = len(event_set & theme_set)
        
        # 基于匹配数量的分数
        max_possible = min(len(event_set), 10)  # 最多考虑10个关键词
        score = matches / max_possible if max_possible > 0 else 0.0
        
        return min(score * 1.2, 1.0)  # 稍微放大
    
    def _get_matched_keywords(self, theme: Dict, event_keywords: List[str]) -> List[str]:
        """获取匹配的关键词"""
        theme_keywords = self._extract_theme_keywords(theme)
        return list(set(event_keywords) & set(theme_keywords))
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        return {
            **super().get_algorithm_info(),
            'name': 'NormalEventMatcher',
            'type': 'normal',
            'precision': 'medium',
            'threshold': self.config['match_threshold'],
            'description': 'Normal事件中精度快速匹配算法'
        }