"""
关键词匹配算法 - 基于数据库tags关键词
增加AI关键词直通匹配功能
"""
import re
import time
import jieba
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import json
from .base_matcher import BaseMatcher, MatchResult


class KeywordMatcher(BaseMatcher):
    """关键词匹配算法 - 纯算法，无业务逻辑"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.algorithm_type = 'keyword'
        
        # 合并配置
        self.config = {
            'match_threshold': 0.5,
            'max_results': 10,
            'min_keyword_matches': 1,
            'use_database_tags': True,
            'enable_analyst_logic': False,
            'classification_first': False,
            'enable_fuzzy_match': True,
            'fuzzy_threshold': 0.6,
            'keyword_weight': 0.6,
            'name_weight': 0.2,
            'heat_weight': 0.2,
            'precision_mode': 'normal',
            # AI相关配置
            'ai_keywords_weight': 0.7,
            'event_keywords_weight': 0.3,
            'use_ai_keywords_first': True,
            'ai_confidence_boost': 0.2,
            'enable_category_inference': True,
            'category_match_threshold': 1
        }
        
        if config:
            self.config.update(config)
        
        # 初始化缓存和索引
        self.theme_keywords_cache = {}
        self.category_keywords_cache = {}
        self.category_hierarchy_cache = {}
        self.keyword_index = defaultdict(list)
        self.reverse_keyword_index = {}
        self.category_index = {
            'level1': defaultdict(list),
            'level2': defaultdict(list),
            'level3': defaultdict(list)
        }
        
        # AI相关缓存
        self.ai_category_index = {}
        self.category_keyword_map = {}
        
        print(f"🔤 {self.__class__.__name__}初始化")
    
    def initialize(self, themes: List[Dict], categories: List[Dict] = None):
        """
        初始化算法，加载数据
        
        Args:
            themes: 题材数据（可以为空列表）
            categories: 分类数据（可以为空列表）
        """
        print(f"🔤 KeywordMatcher.initialize")
        print(f"   接收数据: {len(themes)}题材, {len(categories) if categories else 0}分类")
        
        # 🔥 关键：允许空数据，支持不同场景
        if not themes:
            print(f"   ⚠️  题材数据为空 - 分类优先模式")
        if not categories:
            print(f"   ⚠️  分类数据为空 - 仅题材匹配模式")
        
        # 调用父类initialize方法
        super().initialize(themes, categories)
        
        # 🔥 条件性构建索引
        if themes:
            self._build_theme_index()
        else:
            print(f"   无题材数据，跳过题材索引构建")
            self.theme_keywords_cache = {}
            self.keyword_index = defaultdict(list)
        
        if categories:
            self._build_category_keyword_index()
        else:
            print(f"   无分类数据，跳过分类索引构建")
            self.category_keyword_map = {}
            self.ai_category_index = {}
        
        self.initialized = True
        print(f"✅ {self.__class__.__name__}初始化完成")
    
    def _build_index(self):
        """🔥 实现抽象方法：构建关键词索引"""
        print("🔨 构建关键词索引...")
        
        theme_count = 0
        keyword_count = 0
        
        for theme_id, theme in self.themes.items():
            # 提取题材关键词
            keywords = self._extract_theme_keywords(theme_id)
            self.theme_keywords_cache[theme_id] = keywords
            
            # 构建关键词倒排索引
            for keyword in keywords:
                self.keyword_index[keyword].append(theme_id)
                keyword_count += 1
            
            # 构建分类索引
            level1 = theme.get('level1_category', '')
            level2 = theme.get('level2_category', '')
            level3 = theme.get('level3_category', '')
            
            if level1:
                self.category_index['level1'][level1].append(theme_id)
            if level2:
                self.category_index['level2'][level2].append(theme_id)
            if level3:
                self.category_index['level3'][level3].append(theme_id)
            
            theme_count += 1
        
        print(f"   索引构建完成: {theme_count} 题材, {keyword_count} 关键词索引")
        print(f"   分类索引: L1={len(self.category_index['level1'])}, "
              f"L2={len(self.category_index['level2'])}, "
              f"L3={len(self.category_index['level3'])}")
    
    def _build_category_keyword_index(self):
        """构建分类关键词索引 - 用于AI关键词分类匹配"""
        if not self.categories:
            return
        
        print("🔨 构建分类关键词索引...")
        
        category_count = 0
        total_keywords = 0
        
        for cat_id, category in self.categories.items():
            cat_keywords = self._extract_category_keywords(category)
            
            if cat_keywords:
                self.category_keyword_map[cat_id] = cat_keywords
                
                # 为每个关键词添加分类引用
                for keyword in cat_keywords:
                    if keyword not in self.ai_category_index:
                        self.ai_category_index[keyword] = []
                    self.ai_category_index[keyword].append({
                        'category_id': cat_id,
                        'category_name': category.get('category_name', ''),
                        'category_level': category.get('category_level', 1)
                    })
                    total_keywords += 1
            
            category_count += 1
        
        print(f"   分类关键词索引: {category_count} 个分类, {total_keywords} 个关键词")
    
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """
        统一的匹配方法 - 匹配当前加载的数据
        
        🔥 修改：移除业务逻辑，只进行关键词匹配
        """
        if not self.initialized:
            raise RuntimeError("算法未初始化")
        
        start_time = time.time()
        
        print(f"\n🔍 KeywordMatcher.match 开始")
        print(f"   事件ID: {event_data.get('event_id', 'unknown')}")
        print(f"   当前数据: {len(self.themes)}题材, {len(self.categories)}分类")
        
        # 1. 提取事件文本和关键词
        event_text = self._extract_event_text(event_data)
        event_keywords = self._extract_event_keywords(event_text, event_data)
        
        print(f"🔍 关键词匹配: {len(event_keywords)} 个关键词")
        if event_keywords:
            print(f"   事件关键词前5个: {event_keywords[:5]}")
        
        # 🔥 根据当前数据决定匹配策略
        results = []
        
        # 如果有题材数据，匹配题材
        if self.themes:
            print(f"   匹配题材数据...")
            theme_results = self._match_themes_direct(event_text, event_keywords, event_data)
            results.extend(theme_results)
        
        # 如果有分类数据，匹配分类
        if self.categories:
            print(f"   匹配分类数据...")
            category_results = self._match_categories_direct(event_text, event_keywords, event_data)
            results.extend(category_results)
        
        if not results:
            print(f"   ⚠️  无可用数据匹配")
            return []
        
        # 2. 计算置信度（纯算法逻辑）
        for result in results:
            result.confidence = self._calculate_confidence_algorithm(result, event_data)
        
        # 🔥 关键：不进行阈值过滤，只进行排序
        results.sort(key=lambda x: x.confidence, reverse=True)
        
        processing_time = time.time() - start_time
        print(f"✅ 匹配完成: 找到 {len(results)} 个结果，耗时 {processing_time:.3f}s")
        
        # 返回所有结果，不限制数量（由调用方处理）
        return results
    
    # ==================== 核心匹配算法 ====================
    
    def _match_themes_direct(self, event_text: str, event_keywords: List[str],
                            event_data: Dict) -> List[MatchResult]:
        """直接关键词匹配题材数据"""
        print(f"   直接关键词匹配 {len(self.themes)} 个题材")
        
        results = []
        
        # 🔥 遍历所有题材，计算匹配分数
        for theme_id, theme in self.themes.items():
            # 获取题材关键词
            theme_keywords = self.theme_keywords_cache.get(theme_id, [])
            if not theme_keywords:
                continue
            
            # 🔥 使用现有的复杂匹配算法
            match_score, matched_keywords = self._calculate_theme_match_score_complex(
                theme, theme_keywords, event_keywords, event_text
            )
            
            if match_score > 0:
                # 创建MatchResult
                result = self._create_match_result_direct(
                    theme_id, match_score, matched_keywords, event_data
                )
                results.append(result)
        
        return results
    
    def _match_categories_direct(self, event_text: str, event_keywords: List[str],
                                event_data: Dict) -> List[MatchResult]:
        """直接关键词匹配分类数据"""
        print(f"   直接关键词匹配 {len(self.categories)} 个分类")
        
        results = []
        
        for cat_id, cat_keywords in self.category_keyword_map.items():
            category = self.categories.get(cat_id, {})
            
            # 计算匹配分数
            match_score, matched_keywords = self._calculate_category_match_score_complex(
                category, cat_keywords, event_keywords, event_text
            )
            
            if match_score > 0:
                # 创建MatchResult（标识为分类数据）
                result = MatchResult(
                    theme_id=cat_id,
                    theme_name=category.get('category_name', ''),
                    match_score=match_score,
                    matched_keywords=matched_keywords,
                    match_type='category_match',
                    level1_category=category.get('level1_category', ''),
                    level2_category=category.get('level2_category', ''),
                    level3_category=category.get('level3_category', ''),
                    is_hot=False,
                    match_details={
                        'data_type': 'category',
                        'category_level': category.get('category_level', 1)
                    }
                )
                results.append(result)
        
        return results
    
    # ==================== 复用原有的复杂算法 ====================
    
    def _calculate_theme_match_score_complex(self, theme: Dict, theme_keywords: List[str],
                                           event_keywords: List[str], event_text: str) -> Tuple[float, List[str]]:
        """复杂的题材匹配分数计算（复用原始代码）"""
        if not event_keywords or not theme_keywords:
            return 0.0, []
        
        theme_name = theme.get('name', 'Unknown')
        
        # 1. 名称完全匹配
        theme_name_lower = theme.get('name', '').lower()
        event_text_lower = event_text.lower()
        
        if theme_name_lower and theme_name_lower in event_text_lower:
            return 0.9, ['名称完全匹配']
        
        # 2. 名称部分匹配
        name_words = set(jieba.lcut(theme_name_lower))
        event_words = set(jieba.lcut(event_text_lower))
        name_common_words = name_words & event_words
        
        if name_common_words:
            name_match_score = min(len(name_common_words) * 0.3, 0.6)
            return name_match_score, list(name_common_words)
        
        # 3. 关键词匹配（复杂逻辑）
        event_set = set(event_keywords)
        theme_set = set(theme_keywords)
        
        matched_keywords = list(event_set & theme_set)
        match_count = len(matched_keywords)
        
        # 复用 min_keyword_matches 逻辑
        min_matches = self.config.get('min_keyword_matches', 2)
        
        if match_count < min_matches:
            return 0.0, []
        
        # 复杂的分数计算公式
        theme_keyword_count = len(theme_keywords)
        if theme_keyword_count == 0:
            return 0.0, []
        
        # 基础分数：匹配的关键词占比
        base_score = match_count / theme_keyword_count
        
        # 匹配数量加成
        if match_count >= 3:
            base_score *= 1.3
        elif match_count >= 2:
            base_score *= 1.2
        
        # 重要关键词检查
        important_keywords = ['半导体', '芯片', '航天', '航空', '数据中心']
        important_matches = [kw for kw in matched_keywords if any(imp in kw for imp in important_keywords)]
        if important_matches:
            base_score *= 1.3
        
        # 确保分数在合理范围内
        final_score = min(base_score, 1.0)
        
        return final_score, matched_keywords
    
    def _calculate_category_match_score_complex(self, category: Dict, cat_keywords: List[str],
                                              event_keywords: List[str], event_text: str) -> Tuple[float, List[str]]:
        """复杂的分类匹配分数计算"""
        if not event_keywords or not cat_keywords:
            return 0.0, []
        
        # 名称匹配检查
        category_name = category.get('category_name', '').lower()
        event_text_lower = event_text.lower()
        
        if category_name and category_name in event_text_lower:
            return 0.9, ['分类名称匹配']
        
        # 关键词匹配
        event_set = set(event_keywords)
        cat_set = set(cat_keywords)
        
        matched_keywords = list(event_set & cat_set)
        match_count = len(matched_keywords)
        
        if match_count < self.config.get('category_match_threshold', 1):
            return 0.0, []
        
        # 复杂分数计算
        cat_keyword_count = len(cat_keywords)
        base_score = match_count / cat_keyword_count
        
        # 匹配数量加成
        if match_count >= 3:
            base_score *= 1.3
        elif match_count >= 2:
            base_score *= 1.2
        
        return min(base_score, 1.0), matched_keywords
    
    def _calculate_confidence_algorithm(self, result: MatchResult, event_data: Dict = None) -> float:
        """算法级别的置信度计算"""
        # 基础置信度就是匹配分数
        confidence = result.match_score
        
        # 根据匹配类型微调
        if result.match_type == 'strong_match':
            confidence *= 1.1
        elif result.match_type == 'category_match':
            # 分类匹配有额外的置信度加成
            confidence *= 1.05
        
        # 匹配关键词数量影响
        keyword_count = len(result.matched_keywords)
        if keyword_count >= 5:
            confidence *= 1.2
        elif keyword_count >= 3:
            confidence *= 1.1
        
        # AI置信度加成（算法逻辑）
        if event_data and 'ai_analysis' in event_data:
            ai_analysis = event_data['ai_analysis']
            ai_confidence = ai_analysis.get('concept_confidence', 0.8)
            impact_level = ai_analysis.get('impact_level', 'medium')
            
            ai_boost = self.config.get('ai_confidence_boost', 0.1) * ai_confidence
            impact_boost = {
                'high': 0.15,
                'medium': 0.1,
                'low': 0.05
            }.get(impact_level, 0.0)
            
            confidence = min(confidence + ai_boost + impact_boost, 1.0)
        
        return min(confidence, 1.0)
    
    def _create_match_result_direct(self, theme_id: str, match_score: float,
                                   matched_keywords: List[str], event_data: Dict = None) -> MatchResult:
        """创建匹配结果（简化版）"""
        theme = self.themes.get(theme_id, {})
        
        # 判断匹配类型
        match_type = self._determine_match_type_by_score(match_score, matched_keywords)
        
        # 获取分类信息
        level1_category = theme.get('level1_category', '')
        level2_category = theme.get('level2_category', '')
        level3_category = theme.get('level3_category', '')
        
        # 判断是否为热点
        is_hot = self._is_hot_theme(theme_id)
        
        # 匹配详情
        match_details = {
            'data_type': 'theme',
            'keyword_count': len(matched_keywords)
        }
        
        return MatchResult(
            theme_id=theme_id,
            theme_name=theme.get('name', ''),
            match_score=match_score,
            matched_keywords=matched_keywords,
            match_type=match_type,
            level1_category=level1_category,
            level2_category=level2_category,
            level3_category=level3_category,
            is_hot=is_hot,
            match_details=match_details
        )
    
    def _determine_match_type_by_score(self, score: float, matched_keywords: List[str]) -> str:
        """根据分数和关键词判断匹配类型"""
        if score >= 0.8:
            return 'strong_match'
        elif score >= 0.6:
            return 'good_match'
        elif score >= 0.4:
            return 'moderate_match'
        elif len(matched_keywords) >= 5:
            return 'multiple_keyword_match'
        elif len(matched_keywords) >= 3:
            return 'keyword_match'
        elif len(matched_keywords) >= 1:
            return 'single_keyword_match'
        else:
            return 'weak_match'
    
    # ==================== 复用原有的基础设施方法 ====================
    
    def _build_theme_index(self):
        """构建题材关键词索引（复用原始代码）"""
        print("🔨 构建题材关键词索引...")
        
        self.theme_keywords_cache = {}
        self.keyword_index = defaultdict(list)
        
        theme_count = 0
        keyword_count = 0
        
        for theme_id, theme in self.themes.items():
            # 提取题材关键词
            keywords = self._extract_theme_keywords(theme_id)
            self.theme_keywords_cache[theme_id] = keywords
            
            # 构建关键词倒排索引
            for keyword in keywords:
                self.keyword_index[keyword].append(theme_id)
                keyword_count += 1
            
            # 构建分类索引
            level1 = theme.get('level1_category', '')
            level2 = theme.get('level2_category', '')
            level3 = theme.get('level3_category', '')
            
            if level1:
                self.category_index['level1'][level1].append(theme_id)
            if level2:
                self.category_index['level2'][level2].append(theme_id)
            if level3:
                self.category_index['level3'][level3].append(theme_id)
            
            theme_count += 1
        
        print(f"   题材索引构建完成: {theme_count} 题材, {keyword_count} 关键词索引")
    
    def _build_category_keyword_index(self):
        """构建分类关键词索引（复用原始代码）"""
        if not self.categories:
            return
        
        print("🔨 构建分类关键词索引...")
        
        self.category_keyword_map = {}
        self.ai_category_index = {}
        
        category_count = 0
        total_keywords = 0
        
        for cat_id, category in self.categories.items():
            cat_keywords = self._extract_category_keywords(category)
            
            if cat_keywords:
                self.category_keyword_map[cat_id] = cat_keywords
                
                # 为每个关键词添加分类引用
                for keyword in cat_keywords:
                    if keyword not in self.ai_category_index:
                        self.ai_category_index[keyword] = []
                    self.ai_category_index[keyword].append({
                        'category_id': cat_id,
                        'category_name': category.get('category_name', ''),
                        'category_level': category.get('category_level', 1)
                    })
                    total_keywords += 1
            
            category_count += 1
        
        print(f"   分类关键词索引: {category_count} 个分类, {total_keywords} 个关键词")
    
    # ==================== 复用原有的提取方法 ====================
    
    def _extract_event_text(self, event_data: Dict) -> str:
        """提取事件文本（复用原始代码）"""
        text_parts = []
        
        title = event_data.get('title', '')
        if title:
            text_parts.append(title)
        
        content = event_data.get('content', '')
        if content:
            text_parts.append(content)
        
        keywords = event_data.get('keywords', [])
        if keywords:
            text_parts.append(' '.join(keywords))
        
        return ' '.join(text_parts)
    
    def _extract_event_keywords(self, event_text: str, event_data: Dict = None) -> List[str]:
        """提取事件关键词 - 支持AI关键词直通（复用原始代码）"""
        # ✅ 优先使用AI分析的行业关键词
        if event_data and 'ai_analysis' in event_data:
            ai_analysis = event_data['ai_analysis']
            
            # 1. 获取AI关键词（最高优先级）
            ai_industry_keywords = ai_analysis.get('industry_keywords', [])
            ai_event_keywords = ai_analysis.get('event_keywords', [])
            
            if ai_industry_keywords or ai_event_keywords:
                all_keywords = list(set(ai_industry_keywords + ai_event_keywords))
                
                # 如果AI提供了关键词，直接返回（不再分词）
                if all_keywords:
                    return all_keywords[:30]
        
        # 2. 如果没有AI关键词，使用传统分词
        if not event_text:
            return []
        
        # 分词
        words = jieba.lcut(event_text)
        
        # 过滤停用词
        stop_words = {
            '的', '了', '在', '是', '和', '与', '及', '对', '为', '有', '也', '都',
            '就', '但', '而', '且', '或', '还', '又', '更', '这', '那', '此', '该',
            '各', '每', '各', '某', '本', '此', '该', '各', '某', '本', '此', '该'
        }
        
        # 过滤并保留长度>=2的词
        filtered = [w for w in words if len(w) >= 2 and w not in stop_words]
        
        # 去重
        seen = set()
        unique_keywords = []
        for word in filtered:
            if word not in seen:
                seen.add(word)
                unique_keywords.append(word)
        
        return unique_keywords[:30]
    
    def _extract_theme_keywords(self, theme_id: str) -> List[str]:
        """提取题材关键词（复用原始代码）"""
        theme = self.themes.get(theme_id, {})
        keywords = set()
        
        # 1. 优先使用数据库tags关键词
        if self.config['use_database_tags']:
            tags_keywords = self._extract_theme_tags_keywords(theme_id)
            if tags_keywords:
                keywords.update(tags_keywords)
                return list(keywords)
        
        # 2. 从名称提取
        name = theme.get('name', '')
        if name:
            name_words = jieba.lcut(name)
            keywords.update([w for w in name_words if len(w) >= 2])
        
        # 3. 从keywords字段提取
        theme_keywords = theme.get('keywords', [])
        if isinstance(theme_keywords, list):
            keywords.update([kw for kw in theme_keywords if kw and len(kw) >= 2])
        
        return list(keywords)[:50]
    
    def _extract_theme_tags_keywords(self, theme_id: str) -> List[str]:
        """从数据库tags字段提取关键词（复用原始代码）"""
        theme = self.themes.get(theme_id, {})
        tags = theme.get('tags', {})
        
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except:
                return []
        
        if not isinstance(tags, dict):
            return []
        
        # 从tags中提取keywords
        keywords = tags.get('keywords', [])
        if isinstance(keywords, list):
            return [kw for kw in keywords if kw and len(kw) >= 2]
        
        return []
    
    def _extract_category_keywords(self, category: Dict) -> List[str]:
        """提取分类关键词（复用原始代码）"""
        keywords = set()
        
        # 1. 分类名称
        name = category.get('category_name', '')
        if name:
            # 全称
            keywords.add(name)
            # 分词
            name_words = jieba.lcut(name)
            keywords.update([w for w in name_words if len(w) >= 2])
        
        # 2. 关键词字段
        cat_keywords = category.get('keywords', [])
        if isinstance(cat_keywords, list):
            keywords.update([kw for kw in cat_keywords if kw])
        elif isinstance(cat_keywords, str) and cat_keywords:
            try:
                parsed = json.loads(cat_keywords)
                if isinstance(parsed, list):
                    keywords.update([str(kw) for kw in parsed if kw])
            except:
                # 如果不是JSON，按逗号分隔
                if ',' in cat_keywords:
                    keywords.update([kw.strip() for kw in cat_keywords.split(',') if kw.strip()])
        
        # 3. 别名
        aliases = category.get('aliases', [])
        if isinstance(aliases, list):
            keywords.update([alias for alias in aliases if alias])
        elif isinstance(aliases, str) and aliases:
            try:
                parsed = json.loads(aliases)
                if isinstance(parsed, list):
                    keywords.update([str(alias) for alias in parsed if alias])
            except:
                pass
        
        # 4. 描述（提取关键词）
        description = category.get('description', '')
        if description:
            desc_words = jieba.lcut(description)
            keywords.update([w for w in desc_words if len(w) >= 2])
        
        return list(keywords)
    
    # ==================== 复用原有的辅助方法 ====================
    
    def _is_hot_theme(self, theme_id: str) -> bool:
        """判断是否为热点题材（简化版）"""
        theme = self.themes.get(theme_id, {})
        heat_score = theme.get('heat_score', 0)
        return heat_score > 70  # 简化的热点判断
    
    def infer_category_from_ai_keywords(self, ai_analysis: Dict) -> Dict:
        """
        从AI关键词推断行业分类
        """
        print(f"   🔍 [DEBUG] 从AI关键词推断分类开始")
        print(f"   🔍 [DEBUG] 配置 enable_category_inference: {self.config.get('enable_category_inference', True)}")
        print(f"   🔍 [DEBUG] 分类数据数量: {len(self.categories)}")
        print(f"   🔍 [DEBUG] 分类关键词映射数量: {len(self.category_keyword_map)}")
        
        if not self.config.get('enable_category_inference', True) or not self.categories:
            print(f"   ⚠️  [DEBUG] 分类推断未启用或无分类数据")
            return {
                'matched': False,
                'theme_type': 'concept',
                'level1_category': '概念题材',
                'level2_category': '新兴概念'
            }
        
        ai_keywords = ai_analysis.get('industry_keywords', [])
        print(f"   🔍 [DEBUG] AI关键词: {ai_keywords}")
        print(f"   🔍 [DEBUG] AI关键词数量: {len(ai_keywords)}")
        
        if not ai_keywords:
            print(f"   ⚠️  [DEBUG] 无AI关键词")
            return {
                'matched': False,
                'theme_type': '概念题材',
                'level1_category': '概念题材',
                'level2_category': '新兴概念'
            }
        
        # 🔍 显示分类关键词映射的前几个示例
        print(f"   🔍 [DEBUG] 显示分类关键词映射的前3个示例:")
        for i, (cat_id, cat_keywords) in enumerate(list(self.category_keyword_map.items())[:3]):
            category = self.categories.get(cat_id, {})
            cat_name = category.get('category_name', '未知')
            cat_level = category.get('category_level', 1)
            print(f"     分类{i+1}: ID={cat_id}, 名称={cat_name}, 等级={cat_level}")
            print(f"         关键词数量: {len(cat_keywords)}")
            print(f"         关键词示例: {cat_keywords[:5]}")
        
        # 1. 先尝试匹配二级分类（更具体）
        print(f"   🔍 [DEBUG] 开始匹配二级分类...")
        best_match = None
        best_score = 0
        threshold = self.config.get('category_match_threshold', 2)
        print(f"   🔍 [DEBUG] 匹配阈值: {threshold}")
        
        secondary_matches = []
        
        for cat_id, cat_keywords in self.category_keyword_map.items():
            category = self.categories.get(cat_id, {})
            cat_level = category.get('category_level', 1)
            
            if cat_level != 2:  # 只检查二级分类
                continue
            
            # 计算匹配的关键词
            matched_keywords = []
            for ai_kw in ai_keywords[:20]:  # 只检查前20个关键词
                ai_kw_lower = ai_kw.lower().strip()
                for cat_kw in cat_keywords:
                    cat_kw_str = str(cat_kw).lower().strip()
                    if ai_kw_lower in cat_kw_str or cat_kw_str in ai_kw_lower:
                        matched_keywords.append(ai_kw)
                        break
            
            if matched_keywords:
                match_score = len(matched_keywords) / max(len(ai_keywords[:20]), 1)
                
                print(f"   🔍 [DEBUG] 二级分类匹配: {category.get('category_name', cat_id)}")
                print(f"     匹配关键词: {matched_keywords}")
                print(f"     匹配分数: {match_score:.3f}, 匹配数: {len(matched_keywords)}, 阈值要求: {threshold}")
                
                secondary_matches.append({
                    'category_name': category.get('category_name', ''),
                    'match_score': match_score,
                    'matched_count': len(matched_keywords)
                })
                
                if match_score > best_score and len(matched_keywords) >= threshold:
                    best_score = match_score
                    
                    # 获取父分类（一级分类）
                    parent_id = category.get('parent_code', '')
                    parent_category = self._get_category_by_id(parent_id)
                    
                    best_match = {
                        'matched': True,
                        'level1_category': parent_category.get('category_name', '') if parent_category else '',
                        'level2_category': category.get('category_name', ''),
                        'level1_code': parent_id,
                        'level2_code': category.get('category_code', ''),
                        'match_confidence': min(best_score, 1.0),
                        'matched_keywords': matched_keywords[:5],
                        'theme_type': 'investment',
                        'category_level': 2
                    }
                    print(f"   🔍 [DEBUG] 更新最佳匹配: {best_match['level2_category']} (分数: {best_score:.3f})")
        
        print(f"   🔍 [DEBUG] 二级分类匹配统计: {len(secondary_matches)} 个分类有匹配")
        for match in secondary_matches[:3]:  # 显示前3个匹配
            print(f"     - {match['category_name']}: 分数={match['match_score']:.3f}, 匹配数={match['matched_count']}")
        
        # 2. 如果匹配到二级分类，直接返回
        if best_match and best_match['match_confidence'] >= 0.2:
            print(f"   ✅ 匹配到二级分类: {best_match['level2_category']} (置信度: {best_match['match_confidence']:.2f})")
            return best_match
        
        print(f"   ⚠️  [DEBUG] 二级分类未匹配或置信度不足 (要求: ≥0.2)")
        
        # 3. 尝试匹配一级分类
        print(f"   🔍 [DEBUG] 开始匹配一级分类...")
        primary_matches = []
        
        for cat_id, cat_keywords in self.category_keyword_map.items():
            category = self.categories.get(cat_id, {})
            cat_level = category.get('category_level', 1)
            
            if cat_level != 1:  # 只检查一级分类
                continue
            
            matched_keywords = []
            for ai_kw in ai_keywords[:20]:
                ai_kw_lower = ai_kw.lower().strip()
                for cat_kw in cat_keywords:
                    cat_kw_str = str(cat_kw).lower().strip()
                    if ai_kw_lower in cat_kw_str or cat_kw_str in ai_kw_lower:
                        matched_keywords.append(ai_kw)
                        break
            
            if matched_keywords:
                match_score = len(matched_keywords) / max(len(ai_keywords[:20]), 1)
                
                print(f"   🔍 [DEBUG] 一级分类匹配: {category.get('category_name', cat_id)}")
                print(f"     匹配关键词: {matched_keywords}")
                print(f"     匹配分数: {match_score:.3f}, 匹配数: {len(matched_keywords)}")
                
                primary_matches.append({
                    'category_name': category.get('category_name', ''),
                    'match_score': match_score,
                    'matched_count': len(matched_keywords)
                })
                
                if match_score > best_score and len(matched_keywords) >= threshold:
                    best_score = match_score
                    
                    # 尝试获取一个默认的二级分类
                    child_categories = self._get_child_categories(category.get('category_code', ''))
                    child_category = child_categories[0] if child_categories else None
                    
                    best_match = {
                        'matched': True,
                        'level1_category': category.get('category_name', ''),
                        'level2_category': child_category.get('category_name', '') if child_category else category.get('category_name', ''),
                        'level1_code': category.get('category_code', ''),
                        'level2_code': child_category.get('category_code', '') if child_category else '',
                        'match_confidence': min(best_score, 1.0),
                        'matched_keywords': matched_keywords[:5],
                        'theme_type': 'investment',
                        'category_level': 1
                    }
                    print(f"   🔍 [DEBUG] 更新一级分类最佳匹配: {best_match['level1_category']} (分数: {best_score:.3f})")
        
        print(f"   🔍 [DEBUG] 一级分类匹配统计: {len(primary_matches)} 个分类有匹配")
        for match in primary_matches[:3]:
            print(f"     - {match['category_name']}: 分数={match['match_score']:.3f}, 匹配数={match['matched_count']}")
        
        # 4. 如果匹配到一级分类
        if best_match and best_match['match_confidence'] >= 0.3:
            print(f"   ✅ 匹配到一级分类: {best_match['level1_category']} (置信度: {best_match['match_confidence']:.2f})")
            return best_match
        
        # 5. 未匹配到分类，创建概念题材
        print(f"   ⚠️  未匹配到行业分类，创建概念题材")
        print(f"   🔍 [DEBUG] 诊断信息:")
        print(f"     - AI关键词: {ai_keywords}")
        print(f"     - 分类总数: {len(self.categories)}")
        print(f"     - 分类关键词映射: {len(self.category_keyword_map)}")
        print(f"     - 匹配阈值: {threshold}")
        print(f"     - 二级分类匹配数: {len(secondary_matches)}")
        print(f"     - 一级分类匹配数: {len(primary_matches)}")
        print(f"     - 最高分数: {best_score:.3f}")
        
        return {
            'matched': False,
            'theme_type': 'concept',
            'level1_category': '概念题材',
            'level2_category': ai_analysis.get('core_concept', '新兴概念') or '新兴概念',
            'match_confidence': 0.0,
            'matched_keywords': []
        }
    
    def _get_category_by_id(self, category_id: str) -> Optional[Dict]:
        """根据分类ID获取分类"""
        if not category_id:
            return None
        return self.categories.get(category_id)

    def _get_child_categories(self, parent_id: str) -> List[Dict]:
        """获取子分类列表"""
        if not parent_id:
            return []
        
        children = []
        for cat_id, category in self.categories.items():
            if category.get('parent_code') == parent_id:
                children.append(category)
        return children

    
    def _infer_category_from_keywords(self, keywords: List[str]) -> Dict:
        """从关键词推断分类（复用逻辑）"""
        best_match = None
        best_score = 0
        
        for cat_id, cat_keywords in self.category_keyword_map.items():
            category = self.categories.get(cat_id, {})
            cat_level = category.get('category_level', 1)
            
            if cat_level != 2:
                continue
            
            matched_keywords = []
            for ai_kw in keywords[:20]:
                for cat_kw in cat_keywords:
                    if ai_kw in cat_kw or cat_kw in ai_kw:
                        matched_keywords.append(ai_kw)
                        break
            
            if matched_keywords:
                match_score = len(matched_keywords) / max(len(keywords[:20]), 1)
                
                if match_score > best_score and len(matched_keywords) >= self.config['category_match_threshold']:
                    best_score = match_score
                    
                    parent_id = category.get('parent_code', '')
                    parent_category = self._get_category_by_id(parent_id)
                    
                    best_match = {
                        'matched': True,
                        'level1_category': parent_category.get('category_name', '') if parent_category else '',
                        'level2_category': category.get('category_name', ''),
                        'level1_code': parent_id,
                        'level2_code': category.get('category_code', ''),
                        'match_confidence': min(best_score, 1.0),
                        'matched_keywords': matched_keywords[:5],
                        'theme_type': 'investment',
                        'category_level': 2
                    }
        
        if best_match and best_match['match_confidence'] >= 0.3:
            return best_match
        
        return {
            'matched': False,
            'theme_type': 'concept',
            'level1_category': '概念题材',
            'level2_category': '新兴概念',
            'match_confidence': 0.0,
            'matched_keywords': []
        }
    
    def _get_category_by_id(self, category_id: str) -> Optional[Dict]:
        """根据分类ID获取分类"""
        return self.categories.get(category_id)
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息（保持原有格式）"""
        info = super().get_algorithm_info()
        
        if 'features' not in info:
            info['features'] = []
        
        # 添加功能描述
        info['features'].extend([
            'keyword_direct_matching',
            'ai_keyword_support',
            'category_inference',
            'multi_level_scoring'
        ])
        
        # 添加数据信息
        info['data_status'] = {
            'themes_loaded': len(self.themes) > 0,
            'categories_loaded': len(self.categories) > 0,
            'theme_count': len(self.themes),
            'category_count': len(self.categories)
        }
        
        return info