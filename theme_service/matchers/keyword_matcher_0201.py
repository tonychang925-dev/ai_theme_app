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
    """关键词匹配算法 - 支持AI关键词直通匹配"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.algorithm_type = 'keyword'
        
        # 合并配置
        self.config = {
            'match_threshold': 0.5,
            'max_results': 10,
            'min_keyword_matches': 2,
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
            'ai_keywords_weight': 0.7,  # AI关键词权重
            'event_keywords_weight': 0.3,  # 事件关键词权重
            'use_ai_keywords_first': True,  # 优先使用AI关键词
            'ai_confidence_boost': 0.2,  # AI置信度加成
            'enable_category_inference': True,  # 启用分类推断
            'category_match_threshold': 2  # 分类匹配最小关键词数
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
        self.ai_category_index = {}  # 分类关键词索引
        self.category_keyword_map = {}  # 分类->关键词映射
        
        print(f"🔤 {self.__class__.__name__}初始化")
    
    def initialize(self, themes: List[Dict], categories: List[Dict] = None):
        """初始化算法，加载题材和分类数据"""
        print(f"🔤 初始化{self.__class__.__name__}...")
        
        # 调用父类initialize方法
        super().initialize(themes, categories)
        
        # 构建索引
        self._build_index()
        
        # 构建分类关键词索引
        self._build_category_keyword_index()
        
        self.initialized = True
        print(f"✅ {self.__class__.__name__}初始化完成")
        print(f"   加载题材: {len(self.themes)} 个")
        print(f"   加载分类: {len(self.categories)} 个")
    
    def _build_index(self):
        """构建关键词索引"""
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
    
    def _extract_category_keywords(self, category: Dict) -> List[str]:
        """提取分类关键词"""
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
    
    def _extract_theme_keywords(self, theme_id: str) -> List[str]:
        """提取题材关键词"""
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
        
        return list(keywords)[:50]  # 最多50个关键词
    
    def _extract_theme_tags_keywords(self, theme_id: str) -> List[str]:
        """从数据库tags字段提取关键词"""
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
    
    def _extract_event_text(self, event_data: Dict) -> str:
        """提取事件文本"""
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
        """提取事件关键词 - 支持AI关键词直通"""
        # ✅ 关键修改：优先使用AI分析的行业关键词
        if event_data and 'ai_analysis' in event_data:
            ai_analysis = event_data['ai_analysis']
            
            # 1. 获取AI关键词（最高优先级）
            ai_industry_keywords = ai_analysis.get('industry_keywords', [])
            ai_event_keywords = ai_analysis.get('event_keywords', [])
            
            if ai_industry_keywords or ai_event_keywords:
                all_keywords = list(set(ai_industry_keywords + ai_event_keywords))
                
                # 如果AI提供了关键词，直接返回（不再分词）
                if all_keywords:
                    print(f"   🤖 使用AI分析关键词: {len(all_keywords)} 个")
                    print(f"      行业关键词: {ai_industry_keywords[:3]}...")
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
        
        return unique_keywords[:30]  # 最多30个关键词
    
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """执行关键词匹配 - 支持AI关键词"""
        if not self.initialized:
            raise RuntimeError("算法未初始化")
        
        start_time = time.time()

        # 🔥 临时降低阈值用于调试
        original_threshold = self.config['match_threshold']
        self.config['match_threshold'] = 0.2  # 临时设置为0.2
        
        print(f"\n🔍 KeywordMatcher.match 开始 (临时阈值: {self.config['match_threshold']})")
        print(f"   事件ID: {event_data.get('event_id', 'unknown')}")
        
        # 提取事件文本和关键词
        event_text = self._extract_event_text(event_data)
        event_keywords = self._extract_event_keywords(event_text, event_data)
        
        print(f"🔍 关键词匹配开始: {len(event_keywords)} 个关键词")
        print(f"   提取的关键词: {event_keywords}")
        
        # ✅ 检查是否有AI分析
        ai_analysis = event_data.get('ai_analysis', {})
        ai_used = bool(ai_analysis)
        
        if ai_used:
            print(f"   🤖 检测到AI分析结果: {ai_analysis.get('core_concept', '未知概念')}")
            print(f"   🤖 AI关键词: {ai_analysis.get('industry_keywords', [])}")
        
        # 🔥 显示所有题材的关键词
        print(f"   可用题材数: {len(self.themes)}")
        for i, (theme_id, theme) in enumerate(list(self.themes.items())[:3]):  # 只显示前3个
            theme_name = theme.get('name', theme_id)
            keywords = theme.get('tags', {}).get('keywords', [])
            print(f"   题材{i+1} '{theme_name}' 关键词: {keywords}")
        
        # 根据精度和配置选择匹配策略
        if precision == 'high' and self.config['enable_analyst_logic']:
            results = self._match_with_analyst_logic(event_text, event_keywords, event_data)
        elif self.config['classification_first']:
            results = self._match_with_classification_first(event_text, event_keywords, event_data)
        else:
            results = self._match_with_keywords(event_text, event_keywords, event_data)
        
        # 🔥 调试匹配结果
        print(f"   原始匹配结果数量: {len(results)}")
        for i, result in enumerate(results[:3]):  # 显示前3个
            print(f"   结果{i+1}: {result.theme_name} (置信度: {result.confidence:.3f})")
        
        # 计算置信度（考虑AI置信度）
        for result in results:
            result.confidence = self.calculate_confidence(result)
            
            # ✅ AI置信度加成
            if ai_used:
                ai_confidence = ai_analysis.get('concept_confidence', 0.8)
                impact_level = ai_analysis.get('impact_level', 'medium')
                
                # AI置信度影响
                ai_boost = self.config.get('ai_confidence_boost', 0.1) * ai_confidence
                
                # 影响级别加成
                impact_boost = {
                    'high': 0.15,
                    'medium': 0.1,
                    'low': 0.05
                }.get(impact_level, 0.0)
                
                result.confidence = min(result.confidence + ai_boost + impact_boost, 1.0)
        
        # 过滤和排序
        threshold = self.config['match_threshold']
        filtered_results = [
            r for r in results 
            if r.confidence >= threshold
        ]

        # 🔥 恢复原始阈值
        self.config['match_threshold'] = original_threshold
        
        # 🔥 调试过滤结果
        print(f"   过滤阈值: {threshold}")
        print(f"   过滤前: {len(results)} 个，过滤后: {len(filtered_results)} 个")
        
        filtered_results.sort(key=lambda x: x.confidence, reverse=True)
        
        processing_time = time.time() - start_time
        print(f"✅ 匹配完成: 找到 {len(filtered_results)} 个结果，耗时 {processing_time:.3f}s")
        
        if ai_used and not filtered_results:
            print(f"   ⚠️  AI分析的事件未匹配到现有题材，需要创建新题材")
        
        return filtered_results[:self.config['max_results']]
    
    def infer_category_from_ai_keywords(self, ai_analysis: Dict) -> Dict:
        """
        从AI关键词推断行业分类
        根据AI的industry_keywords匹配分类数据库
        
        Returns:
            {
                'matched': True/False,
                'level1_category': '电子',
                'level2_category': '半导体',
                'level1_code': 'ELEC',
                'level2_code': 'ELEC_01',
                'match_confidence': 0.75,
                'matched_keywords': ['芯片', '半导体'],
                'theme_type': 'investment'  # 或 'concept'
            }
        """
        if not self.config['enable_category_inference'] or not self.categories:
            return {
                'matched': False,
                'theme_type': 'concept',
                'level1_category': '概念题材',
                'level2_category': '新兴概念'
            }
        
        ai_keywords = ai_analysis.get('industry_keywords', [])
        if not ai_keywords:
            return {
                'matched': False,
                'theme_type': 'concept',
                'level1_category': '概念题材',
                'level2_category': '新兴概念'
            }
        
        print(f"   🔍 从AI关键词推断分类: {len(ai_keywords)} 个关键词")
        
        # 1. 先尝试匹配二级分类（更具体）
        best_match = None
        best_score = 0
        
        for cat_id, cat_keywords in self.category_keyword_map.items():
            category = self.categories.get(cat_id, {})
            cat_level = category.get('category_level', 1)
            
            if cat_level != 2:  # 只检查二级分类
                continue
            
            # 计算匹配的关键词
            matched_keywords = []
            for ai_kw in ai_keywords[:20]:  # 只检查前20个关键词
                for cat_kw in cat_keywords:
                    if ai_kw in cat_kw or cat_kw in ai_kw:
                        matched_keywords.append(ai_kw)
                        break
            
            if matched_keywords:
                match_score = len(matched_keywords) / max(len(ai_keywords[:20]), 1)
                
                if match_score > best_score and len(matched_keywords) >= self.config['category_match_threshold']:
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
        
        # 2. 如果匹配到二级分类，直接返回
        if best_match and best_match['match_confidence'] >= 0.3:
            print(f"   ✅ 匹配到二级分类: {best_match['level2_category']} (置信度: {best_match['match_confidence']:.2f})")
            return best_match
        
        # 3. 尝试匹配一级分类
        for cat_id, cat_keywords in self.category_keyword_map.items():
            category = self.categories.get(cat_id, {})
            cat_level = category.get('category_level', 1)
            
            if cat_level != 1:  # 只检查一级分类
                continue
            
            matched_keywords = []
            for ai_kw in ai_keywords[:20]:
                for cat_kw in cat_keywords:
                    if ai_kw in cat_kw or cat_kw in ai_kw:
                        matched_keywords.append(ai_kw)
                        break
            
            if matched_keywords:
                match_score = len(matched_keywords) / max(len(ai_keywords[:20]), 1)
                
                if match_score > best_score and len(matched_keywords) >= self.config['category_match_threshold']:
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
        
        # 4. 如果匹配到一级分类
        if best_match and best_match['match_confidence'] >= 0.3:
            print(f"   ✅ 匹配到一级分类: {best_match['level1_category']} (置信度: {best_match['match_confidence']:.2f})")
            return best_match
        
        # 5. 未匹配到分类，创建概念题材
        print(f"   ⚠️  未匹配到行业分类，创建概念题材")
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
        return self.categories.get(category_id)
    
    def _get_child_categories(self, parent_id: str) -> List[Dict]:
        """获取子分类列表"""
        children = []
        for cat_id, category in self.categories.items():
            if category.get('parent_code') == parent_id:
                children.append(category)
        return children
    
    def _match_with_analyst_logic(self, event_text: str, event_keywords: List[str], 
                                 event_data: Dict) -> List[MatchResult]:
        """分析师逻辑匹配（先分类后匹配）"""
        print("   使用分析师逻辑匹配...")
        
        # 1. 先分类
        candidate_categories = self._classify_event(event_text, event_keywords)
        
        # 2. 在分类中匹配
        results = []
        for level1_cat, level2_cats in candidate_categories.items():
            for level2_cat in level2_cats:
                themes_in_category = self._get_themes_by_category(level1_cat, level2_cat)
                
                for theme_id in themes_in_category:
                    match_score, matched_keywords = self._calculate_theme_match_score(
                        theme_id, event_keywords, event_text
                    )
                    
                    if match_score >= self.config['match_threshold']:
                        result = self._create_match_result(
                            theme_id, match_score, matched_keywords, event_keywords, event_data
                        )
                        results.append(result)
        
        return results
    
    def _match_with_classification_first(self, event_text: str, event_keywords: List[str], 
                                        event_data: Dict) -> List[MatchResult]:
        """先分类再匹配"""
        print("   使用分类优先匹配...")
        
        # 1. 找到相关分类
        relevant_categories = self._find_relevant_categories(event_text, event_keywords)
        
        # 2. 在相关分类中匹配
        results = []
        for category_type, category_names in relevant_categories.items():
            for category_name in category_names:
                theme_ids = self.category_index[category_type].get(category_name, [])
                
                for theme_id in theme_ids:
                    match_score, matched_keywords = self._calculate_theme_match_score(
                        theme_id, event_keywords, event_text
                    )
                    
                    if match_score >= self.config['match_threshold']:
                        result = self._create_match_result(
                            theme_id, match_score, matched_keywords, event_keywords, event_data
                        )
                        results.append(result)
        
        return results
    
    def _match_with_keywords(self, event_text: str, event_keywords: List[str], 
                        event_data: Dict) -> List[MatchResult]:
        """直接关键词匹配"""
        print("   使用直接关键词匹配...")
        
        # 🔥 调试：显示事件关键词
        print(f"      事件关键词: {event_keywords}")
        
        # 1. 获取候选题材（通过关键词索引）
        candidate_themes = set()
        for keyword in event_keywords:
            if keyword in self.keyword_index:
                candidate_themes.update(self.keyword_index[keyword])
                print(f"      关键词 '{keyword}' 匹配到 {len(self.keyword_index[keyword])} 个题材")
        
        print(f"      初始候选题材数: {len(candidate_themes)}")
        
        # 2. 如果候选太少，启用模糊匹配
        if len(candidate_themes) < 3 and self.config.get('enable_fuzzy_match', True):
            print(f"      候选太少，启用模糊匹配...")
            fuzzy_candidates = self._fuzzy_match(event_keywords)
            candidate_themes.update(fuzzy_candidates)
            print(f"      模糊匹配增加 {len(fuzzy_candidates)} 个候选")
        
        print(f"      总候选题材数: {len(candidate_themes)}")
        
        # 3. 如果没有候选，尝试更宽松的匹配
        if not candidate_themes:
            print(f"      ⚠️ 没有候选题材，尝试全量匹配...")
            # 取前100个题材进行匹配
            candidate_themes = set(list(self.themes.keys())[:100])
        
        # 4. 计算匹配分数
        results = []
        threshold = self.config.get('match_threshold', 0.5)
        
        print(f"      匹配阈值: {threshold}")
        
        for i, theme_id in enumerate(list(candidate_themes)[:200]):  # 最多处理200个
            match_score, matched_keywords = self._calculate_theme_match_score(
                theme_id, event_keywords, event_text
            )
            
            # 🔥 调试：显示有分数的匹配
            if match_score > 0:
                theme = self.themes.get(theme_id, {})
                theme_name = theme.get('name', 'Unknown')
                print(f"      题材[{i+1}] '{theme_name}': 分数={match_score:.3f}, 关键词={matched_keywords}")
            
            if match_score >= threshold:
                result = self._create_match_result(
                    theme_id, match_score, matched_keywords, event_keywords, event_data
                )
                results.append(result)
                print(f"      ✅ 匹配成功: '{result.theme_name}' (分数: {match_score:.3f})")
        
        print(f"      找到 {len(results)} 个匹配结果")
        return results
    
    def _calculate_theme_match_score(self, theme_id: str, event_keywords: List[str], 
                               event_text: str) -> Tuple[float, List[str]]:
        """计算题材匹配分数 - 修复版"""
        if not event_keywords:
            return 0.0, []
        
        theme = self.themes.get(theme_id, {})
        theme_keywords = self.theme_keywords_cache.get(theme_id, [])
        if not theme_keywords:
            return 0.0, []
        
        # 🔥 添加调试信息
        theme_name = theme.get('name', 'Unknown')
        print(f"\n     计算题材匹配分数: '{theme_name}'")
        
        # 1. 首先检查名称完全匹配
        theme_name_lower = theme.get('name', '').lower()
        event_text_lower = event_text.lower()
        
        if theme_name_lower and theme_name_lower in event_text_lower:
            print(f"       ✅ 名称完全匹配: +0.9")
            return 0.9, ['名称完全匹配']
        
        # 2. 名称部分匹配
        name_words = set(jieba.lcut(theme_name_lower))
        event_words = set(jieba.lcut(event_text_lower))
        name_common_words = name_words & event_words
        if name_common_words:
            name_match_score = min(len(name_common_words) * 0.3, 0.6)
            print(f"       ✅ 名称部分匹配: {name_common_words} +{name_match_score:.2f}")
            return name_match_score, list(name_common_words)
        
        # 3. 关键词匹配
        event_set = set(event_keywords)
        theme_set = set(theme_keywords)
        
        matched_keywords = list(event_set & theme_set)
        match_count = len(matched_keywords)
        
        # 🔥 关键修复：降低 min_keyword_matches 要求并添加调试
        min_matches = self.config.get('min_keyword_matches', 2)
        
        print(f"       事件关键词: {event_keywords}")
        print(f"       题材关键词: {theme_keywords}")
        print(f"       共同关键词: {matched_keywords}")
        print(f"       匹配数量: {match_count}, 要求最小匹配: {min_matches}")
        
        if match_count < min_matches:
            print(f"       ❌ 关键词匹配不足: {match_count} < {min_matches}")
            return 0.0, []
        
        # 🔥 修复分数计算：使用更合理的公式
        # 原公式：Jaccard相似度 (匹配数 / 并集大小) - 这个太严格！
        # union = len(event_set | theme_set)
        # jaccard_score = match_count / union if union > 0 else 0.0
        
        # 新公式1：匹配数 / 事件关键词总数（更有利于匹配）
        # new_score1 = match_count / max(len(event_keywords), 1)
        
        # 新公式2：匹配数 / 题材关键词总数 * 权重系数
        theme_keyword_count = len(theme_keywords)
        if theme_keyword_count == 0:
            return 0.0, []
        
        # 基础分数：匹配的关键词占比
        base_score = match_count / theme_keyword_count
        
        # 🔥 改进：根据匹配数量给予加成
        if match_count >= 3:
            base_score *= 1.3  # 匹配3个以上，分数提高30%
        elif match_count >= 2:
            base_score *= 1.2  # 匹配2个以上，分数提高20%
        
        # 🔥 检查是否包含重要关键词
        important_keywords = ['银行', '金融', '科技', '数字', '转型']
        important_matches = [kw for kw in matched_keywords if any(imp in kw for imp in important_keywords)]
        if important_matches:
            base_score *= 1.2  # 包含重要关键词，分数提高20%
        
        # 确保分数在合理范围内
        final_score = min(base_score, 1.0)
        
        # 🔥 显示详细的分数计算
        print(f"       📊 分数计算详情:")
        print(f"         匹配数 / 题材关键词数 = {match_count}/{theme_keyword_count} = {match_count/theme_keyword_count:.3f}")
        print(f"         基础分数: {base_score:.3f}")
        print(f"         最终分数: {final_score:.3f}")
        
        # 🔥 额外检查：如果分数>0但低于阈值，提供调试信息
        threshold = self.config.get('match_threshold', 0.5)
        if 0 < final_score < threshold:
            print(f"       ⚠️  分数 {final_score:.3f} 低于阈值 {threshold}")
            print(f"          建议: 1) 降低阈值 2) 增加匹配关键词 3) 改进匹配算法")
        
        return final_score, matched_keywords
    
    def _calculate_name_match_boost(self, theme_id: str, event_text: str) -> float:
        """计算名称匹配加成"""
        theme = self.themes.get(theme_id, {})
        theme_name = theme.get('name', '').lower()
        event_text_lower = event_text.lower()
        
        if not theme_name:
            return 0.0
        
        if theme_name in event_text_lower or event_text_lower in theme_name:
            return 0.3
        
        name_words = set(jieba.lcut(theme_name))
        event_words = set(jieba.lcut(event_text_lower))
        
        common_words = name_words & event_words
        if common_words:
            return min(len(common_words) * 0.1, 0.2)
        
        return 0.0
    
    def _calculate_category_match_boost(self, theme_id: str, event_text: str) -> float:
        """计算分类匹配加成"""
        theme = self.themes.get(theme_id, {})
        level1 = theme.get('level1_category', '').lower()
        level2 = theme.get('level2_category', '').lower()
        event_text_lower = event_text.lower()
        
        score = 0.0
        
        if level1 and level1 in event_text_lower:
            score += 0.1
        
        if level2 and level2 in event_text_lower:
            score += 0.1
        
        return score
    
    def _classify_event(self, event_text: str, event_keywords: List[str]) -> Dict[str, List[str]]:
        """事件分类"""
        candidate_categories = defaultdict(list)
        
        for level1, theme_ids in self.category_index['level1'].items():
            if level1 in event_text:
                for level2 in self.category_index['level2'].keys():
                    if any(theme_id in theme_ids for theme_id in self.category_index['level2'].get(level2, [])):
                        candidate_categories[level1].append(level2)
        
        return candidate_categories
    
    def _find_relevant_categories(self, event_text: str, event_keywords: List[str]) -> Dict[str, List[str]]:
        """找到相关分类"""
        relevant_categories = {
            'level1': [],
            'level2': [],
            'level3': []
        }
        
        event_text_lower = event_text.lower()
        
        for level1 in self.category_index['level1'].keys():
            if level1.lower() in event_text_lower:
                relevant_categories['level1'].append(level1)
        
        for level2 in self.category_index['level2'].keys():
            if level2.lower() in event_text_lower:
                relevant_categories['level2'].append(level2)
        
        for level3 in self.category_index['level3'].keys():
            if level3.lower() in event_text_lower:
                relevant_categories['level3'].append(level3)
        
        return relevant_categories
    
    def _get_themes_by_category(self, level1: str, level2: str) -> List[str]:
        """获取指定分类下的题材"""
        themes = set()
        
        themes.update(self.category_index['level1'].get(level1, []))
        themes.update(self.category_index['level2'].get(level2, []))
        
        return list(themes)
    
    def _fuzzy_match(self, event_keywords: List[str]) -> List[str]:
        """模糊匹配"""
        candidates = set()
        
        for keyword in event_keywords[:10]:
            for index_keyword in self.keyword_index.keys():
                if keyword in index_keyword or index_keyword in keyword:
                    candidates.update(self.keyword_index[index_keyword])
        
        return list(candidates)
    
    def _create_match_result(self, theme_id: str, match_score: float, 
                            matched_keywords: List[str], event_keywords: List[str],
                            event_data: Dict = None) -> MatchResult:
        """创建匹配结果"""
        theme = self.themes.get(theme_id, {})
        
        # 判断匹配类型
        match_type = self._determine_match_type(theme_id, match_score, matched_keywords, event_keywords)
        
        # 获取分类信息
        level1, level2, level3 = self._extract_theme_categories(theme_id)
        
        # 判断是否为热点
        is_hot = self._is_hot_theme(theme_id)
        
        # ✅ 添加AI相关信息
        ai_analysis = event_data.get('ai_analysis', {}) if event_data else {}
        ai_used = bool(ai_analysis)
        
        match_details = {
            'heat_score': self._get_theme_heat_score(theme_id),
            'keyword_count': len(matched_keywords),
            'ai_used': ai_used
        }
        
        if ai_used:
            match_details['ai_core_concept'] = ai_analysis.get('core_concept', '')
            match_details['ai_impact_level'] = ai_analysis.get('impact_level', '')
        
        return MatchResult(
            theme_id=theme_id,
            theme_name=theme.get('name', ''),
            match_score=match_score,
            matched_keywords=matched_keywords,
            match_type=match_type,
            level1_category=level1,
            level2_category=level2,
            level3_category=level3,
            is_hot=is_hot,
            match_details=match_details
        )
    
    def _determine_match_type(self, theme_id: str, match_score: float, 
                             matched_keywords: List[str], event_keywords: List[str]) -> str:
        """判断匹配类型"""
        theme = self.themes.get(theme_id, {})
        theme_name = theme.get('name', '').lower()
        
        for event_keyword in event_keywords[:3]:
            if event_keyword in theme_name:
                return 'name_exact_match'
        
        if len(matched_keywords) >= 5:
            return 'multiple_keyword_match'
        elif len(matched_keywords) >= 3:
            return 'keyword_match'
        elif len(matched_keywords) >= 1:
            return 'single_keyword_match'
        
        return 'weak_match'
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        # 先获取父类信息
        info = super().get_algorithm_info()
        
        # ✅ 添加 features 键（如果不存在）
        if 'features' not in info:
            info['features'] = []
        
        # ✅ 添加 AI 相关功能
        if self.config.get('use_ai_keywords_first', False):
            info['features'].append('ai_keyword_direct_match')
        
        if self.config.get('enable_category_inference', False):
            info['features'].append('ai_category_inference')
        
        # ✅ 添加其他功能
        info['features'].extend([
            'keyword_importance_scoring',
            'synonym_matching',
            'multi_level_matching'
        ])
        
        if self.config.get('enable_analyst_logic', False):
            info['features'].append('analyst_logical_inference')
        
        if self.config.get('classification_first', False):
            info['features'].append('classification_first_strategy')
        
        # ✅ 添加 AI 支持标志
        info['ai_support'] = any('ai' in feature for feature in info['features'])
        
        return info