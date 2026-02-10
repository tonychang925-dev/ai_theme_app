"""
algorithms/major_matcher.py
Major事件匹配算法 - 高精度、严格匹配
"""
import re
import jieba
import jieba.analyse
from typing import List, Dict, Any
from collections import defaultdict
from .base_matcher import BaseMatcher, MatchResult

class MajorEventMatcher(BaseMatcher):
    """Major事件匹配算法 - 高精度"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.keyword_index = defaultdict(list)  # 关键词倒排索引
        self.name_index = defaultdict(list)     # 名称索引
        self.category_index = defaultdict(list) # 分类索引
        
        # Major算法特有配置
        self.major_config = {
            'match_threshold': 0.7,      # 高阈值
            'min_keyword_matches': 3,    # 最少关键词匹配数
            'require_name_match': True,  # 要求名称匹配
            'keyword_weight': 0.4,
            'name_weight': 0.3,
            'category_weight': 0.3,
            'use_strict_filter': True    # 使用严格过滤
        }
        self.config.update(self.major_config)
        
    def _build_index(self):
        """为Major算法构建高级索引"""
        print(f"🔨 构建Major算法索引...")
        
        for theme_id, theme in self.themes.items():
            # 关键词索引
            keywords = self._extract_theme_keywords(theme)
            for keyword in keywords:
                self.keyword_index[keyword].append(theme_id)
            
            # 名称索引
            theme_name = theme.get('name', '')
            if theme_name:
                # 名称分词索引
                name_words = jieba.lcut(theme_name)
                for word in name_words:
                    if len(word) >= 2:
                        self.name_index[word].append(theme_id)
            
            # 分类索引
            level1 = theme.get('level1_category', '')
            level2 = theme.get('level2_category', '')
            if level1:
                self.category_index[level1].append(theme_id)
            if level2:
                self.category_index[level2].append(theme_id)
        
        print(f"   关键词索引: {len(self.keyword_index)} 项")
        print(f"   名称索引: {len(self.name_index)} 项")
        print(f"   分类索引: {len(self.category_index)} 项")
    
    def _extract_theme_keywords(self, theme: Dict) -> List[str]:
        """从题材中提取关键词"""
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
        
        # 从描述中提取
        description = theme.get('description', '')
        if description:
            desc_words = jieba.lcut(description)
            keywords.update([w for w in desc_words if len(w) >= 2])
        
        return list(keywords)
    
    def match(self, event_data: Dict, precision: str = 'major') -> List[MatchResult]:
        """Major事件匹配 - 高精度"""
        if not self.initialized:
            raise RuntimeError("Matcher not initialized")
        
        # 提取事件信息
        event_text = f"{event_data.get('title', '')} {event_data.get('content', '')}"
        event_keywords = self._extract_event_keywords(event_text)
        
        # 筛选候选题材
        candidate_themes = self._get_candidate_themes(event_text, event_keywords)
        
        # 严格过滤候选
        if self.config['use_strict_filter']:
            candidate_themes = self._strict_filter(candidate_themes, event_data)
        
        # 计算匹配分数
        results = []
        for theme_id in candidate_themes:
            theme = self.themes[theme_id]
            
            # 计算各种匹配分数
            keyword_score = self._calculate_keyword_match(theme, event_keywords)
            name_score = self._calculate_name_match(theme, event_data.get('title', ''))
            category_score = self._calculate_category_match(theme, event_text)
            
            # 综合分数（加权平均）
            weights = {
                'keyword': self.config['keyword_weight'],
                'name': self.config['name_weight'],
                'category': self.config['category_weight']
            }
            
            total_score = (
                keyword_score * weights['keyword'] +
                name_score * weights['name'] +
                category_score * weights['category']
            )
            
            # 应用严格阈值
            if total_score >= self.config['match_threshold']:
                # 收集匹配的关键词
                matched_keywords = self._get_matched_keywords(theme, event_keywords)
                
                result = MatchResult(
                    theme_id=theme_id,
                    theme_name=theme.get('name', ''),
                    match_score=total_score,
                    matched_keywords=matched_keywords,
                    match_details={
                        'keyword_score': keyword_score,
                        'name_score': name_score,
                        'category_score': category_score,
                        'weights': weights
                    }
                )
                result.confidence = self.calculate_confidence(result)
                results.append(result)
        
        # 排序
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results[:10]  # 返回前10个
    
    def _extract_event_keywords(self, text: str) -> List[str]:
        """从事件文本提取关键词（Major专用，更精确）"""
        if not text:
            return []
        
        # TF-IDF提取
        tfidf_keywords = jieba.analyse.extract_tags(
            text, 
            topK=20,
            withWeight=False,
            allowPOS=('n', 'ns', 'nr', 'nt', 'nz', 'vn')  # 只提取名词和动词
        )
        
        # TextRank提取
        textrank_keywords = jieba.analyse.textrank(
            text,
            topK=15,
            withWeight=False,
            allowPOS=('n', 'ns', 'nr', 'nt', 'nz', 'vn')
        )
        
        # 合并去重
        all_keywords = list(set(tfidf_keywords + textrank_keywords))
        
        # 过滤停用词
        stop_words = {'的', '了', '在', '是', '和', '与', '及'}
        filtered = [kw for kw in all_keywords if kw not in stop_words and len(kw) >= 2]
        
        return filtered
    
    def _get_candidate_themes(self, event_text: str, event_keywords: List[str]) -> List[str]:
        """获取候选题材（Major专用，更严格）"""
        candidates = set()
        
        # 1. 关键词匹配
        for keyword in event_keywords:
            if keyword in self.keyword_index:
                candidates.update(self.keyword_index[keyword])
        
        # 2. 名称匹配
        event_words = jieba.lcut(event_text)
        for word in event_words:
            if len(word) >= 2 and word in self.name_index:
                candidates.update(self.name_index[word])
        
        # 3. 如果没有足够候选，放宽条件
        if len(candidates) < 5:
            # 添加分类匹配
            for word in event_words:
                if word in self.category_index:
                    candidates.update(self.category_index[word])
        
        return list(candidates)
    
    def _strict_filter(self, candidate_themes: List[str], event_data: Dict) -> List[str]:
        """严格过滤候选题材"""
        filtered = []
        event_title = event_data.get('title', '').lower()
        
        for theme_id in candidate_themes:
            theme = self.themes[theme_id]
            
            # 检查名称匹配
            theme_name = theme.get('name', '').lower()
            name_match_score = self._calculate_name_match(theme, event_title)
            
            # 检查关键词匹配数量
            event_keywords = self._extract_event_keywords(event_title)
            theme_keywords = self._extract_theme_keywords(theme)
            keyword_intersection = len(set(event_keywords) & set(theme_keywords))
            
            # 过滤条件
            if (name_match_score >= 0.3 or  # 名称匹配度至少30%
                keyword_intersection >= 2):  # 或至少2个关键词匹配
                filtered.append(theme_id)
        
        return filtered
    
    def _calculate_keyword_match(self, theme: Dict, event_keywords: List[str]) -> float:
        """计算关键词匹配度"""
        theme_keywords = self._extract_theme_keywords(theme)
        
        if not event_keywords or not theme_keywords:
            return 0.0
        
        # 计算Jaccard相似度
        event_set = set(event_keywords)
        theme_set = set(theme_keywords)
        
        intersection = len(event_set & theme_set)
        union = len(event_set | theme_set)
        
        if union == 0:
            return 0.0
        
        similarity = intersection / union
        
        # 重要关键词加成
        important_keywords = event_keywords[:5]  # 前5个关键词更重要
        important_matches = len(set(important_keywords) & theme_set)
        importance_boost = min(important_matches * 0.1, 0.3)
        
        return min(similarity + importance_boost, 1.0)
    
    def _calculate_name_match(self, theme: Dict, event_title: str) -> float:
        """计算名称匹配度"""
        theme_name = theme.get('name', '').lower()
        event_title_lower = event_title.lower()
        
        if not theme_name or not event_title_lower:
            return 0.0
        
        # 完全包含
        if theme_name in event_title_lower or event_title_lower in theme_name:
            return 1.0
        
        # 分词匹配
        theme_words = set([ch for ch in theme_name if '\u4e00' <= ch <= '\u9fff'])
        event_words = set([ch for ch in event_title_lower if '\u4e00' <= ch <= '\u9fff'])
        
        if not theme_words or not event_words:
            return 0.0
        
        intersection = len(theme_words & event_words)
        min_len = min(len(theme_words), len(event_words))
        
        return intersection / min_len if min_len > 0 else 0.0
    
    def _calculate_category_match(self, theme: Dict, event_text: str) -> float:
        """计算分类匹配度"""
        # 从主题中获取分类
        theme_level1 = theme.get('level1_category', '').lower()
        theme_level2 = theme.get('level2_category', '').lower()
        
        if not theme_level1:
            return 0.0
        
        # 从事件文本中提取可能的分类关键词
        event_text_lower = event_text.lower()
        
        # 分类关键词映射
        category_keywords = {
            '电子': ['芯片', '半导体', '电路', '电子', '处理器', '集成电路'],
            '计算机': ['软件', '算法', 'AI', '人工智能', '数据', '计算', '系统'],
            '医药生物': ['医药', '医疗', '药品', '医院', '治疗', '健康', '生物'],
            '电力设备': ['电池', '光伏', '太阳能', '新能源', '储能', '充电', '电力'],
            '汽车': ['汽车', '电动车', '新能源车', '自动驾驶', '智能驾驶', '整车']
        }
        
        # 检查主题分类是否与事件内容匹配
        if theme_level1 in category_keywords:
            keywords = category_keywords[theme_level1]
            matches = sum(1 for kw in keywords if kw in event_text_lower)
            score = min(matches / 3, 1.0)  # 最多匹配3个关键词
            return score
        
        return 0.3  # 默认值
    
    def _get_matched_keywords(self, theme: Dict, event_keywords: List[str]) -> List[str]:
        """获取匹配的关键词"""
        theme_keywords = self._extract_theme_keywords(theme)
        return list(set(event_keywords) & set(theme_keywords))
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        return {
            **super().get_algorithm_info(),
            'name': 'MajorEventMatcher',
            'type': 'major',
            'precision': 'high',
            'threshold': self.config['match_threshold'],
            'description': 'Major事件高精度匹配算法'
        }