"""
判重引擎 - 防止创建重复题材的兜底机制
实现多重判重策略和相似度计算
"""
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
import jieba  # 中文分词

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """判重结果"""
    should_merge: bool = False
    target_theme: Optional[Dict[str, Any]] = None
    similarity_score: float = 0.0
    match_type: str = ""  # exact, inclusion, semantic, event_overlap
    reason: str = ""
    confidence: float = 0.0
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "should_merge": self.should_merge,
            "target_theme": self.target_theme,
            "similarity_score": round(self.similarity_score, 4),
            "match_type": self.match_type,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
            "suggestions": self.suggestions
        }


class ThemeDeduplicationEngine:
    """
    题材判重引擎
    实现多重判重策略，防止创建重复题材
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化判重引擎
        
        Args:
            config: 配置参数
        """
        self.config = config or self._get_default_config()
        
        # 阈值配置
        self.thresholds = self.config.get('thresholds', {})
        
        # 初始化分词器
        self._init_tokenizer()
        
        # 同义词词典
        self.synonyms = self._load_synonyms()
        
        # 停用词
        self.stop_words = self._load_stop_words()
        
        logger.info("ThemeDeduplicationEngine 初始化完成")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "name": "题材判重引擎配置",
            "version": "1.0",
            "description": "防止创建重复题材的兜底机制",
            
            "thresholds": {
                "exact_match": 1.0,          # 精确匹配阈值
                "inclusion_match": 0.9,      # 包含关系匹配阈值
                "semantic_similarity": 0.85,  # 语义相似度阈值
                "event_overlap": 0.7,        # 事件重合度阈值
                "auto_merge": 0.90,          # 自动合并阈值
                "suggest_merge": 0.75,       # 建议合并阈值
                "keep_separate": 0.5         # 保持独立阈值
            },
            
            "weights": {
                "name_similarity": 0.4,      # 名称相似度权重
                "keyword_overlap": 0.3,      # 关键词重叠权重
                "industry_match": 0.2,       # 行业匹配权重
                "semantic_similarity": 0.1   # 语义相似度权重
            },
            
            "strategies": {
                "enable_exact_match": True,
                "enable_inclusion_check": True,
                "enable_semantic_analysis": True,
                "enable_event_overlap": True,
                "use_jieba": True,
                "cache_enabled": True
            },
            
            "cache": {
                "max_size": 1000,
                "ttl_seconds": 300
            }
        }
    
    def _init_tokenizer(self):
        """初始化分词器"""
        self.use_jieba = self.config.get('strategies', {}).get('use_jieba', True)
        
        if self.use_jieba:
            try:
                # 加载自定义词典（如果有）
                custom_dict = self.config.get('custom_dictionary')
                if custom_dict:
                    jieba.load_userdict(custom_dict)
                logger.info("Jieba分词器初始化成功")
            except Exception as e:
                logger.warning(f"Jieba初始化失败: {e}, 使用简单分词")
                self.use_jieba = False
        else:
            logger.info("使用简单分词器")
    
    def _load_synonyms(self) -> Dict[str, List[str]]:
        """加载同义词词典"""
        # 基础同义词映射
        synonyms = {
            "AI": ["人工智能", "AI技术", "机器学习", "深度学习", "智能算法"],
            "AR": ["增强现实", "AR技术", "混合现实", "扩展现实"],
            "VR": ["虚拟现实", "VR技术", "沉浸式体验"],
            "新能源": ["新能源汽车", "电动车", "电动汽车", "新能源车", "电动化"],
            "半导体": ["芯片", "集成电路", "IC", "半导体材料", "晶圆"],
            "医药": ["医疗", "生物医药", "医药生物", "医疗器械", "生物制药"],
            "消费电子": ["电子产品", "智能设备", "数码产品", "电子消费品"],
            "光伏": ["太阳能", "光伏发电", "太阳能电池", "光伏组件"],
            "5G": ["第五代移动通信", "5G通信", "5G网络"],
            "物联网": ["IoT", "万物互联", "物联网技术", "智能物联网"],
            "云计算": ["云服务", "云平台", "云端计算", "云技术"],
            "大数据": ["数据技术", "数据分析", "数据科学", "大数据分析"],
            "区块链": ["分布式账本", "数字货币", "加密技术", "去中心化"],
            "元宇宙": ["虚拟世界", "数字孪生", "虚拟空间", "元宇宙概念"]
        }
        
        # 添加反向映射
        expanded_synonyms = {}
        for main_word, words in synonyms.items():
            for word in words:
                if word not in expanded_synonyms:
                    expanded_synonyms[word] = []
                expanded_synonyms[word].append(main_word)
                expanded_synonyms[word].extend([w for w in words if w != word])
        
        # 合并
        synonyms.update(expanded_synonyms)
        
        return synonyms
    
    def _load_stop_words(self) -> set:
        """加载停用词"""
        stop_words = {
            "的", "了", "在", "是", "和", "与", "及", "或", "等", "之",
            "相关", "领域", "行业", "产业", "市场", "投资", "主题", "概念",
            "发展", "创新", "技术", "产品", "服务", "平台", "系统", "应用"
        }
        return stop_words
    
    async def check_duplication(self,
                              new_theme_name: str,
                              event_data: Dict[str, Any],
                              existing_themes: List[Dict[str, Any]]) -> DeduplicationResult:
        """
        检查新题材是否与现有题材重复
        
        Args:
            new_theme_name: 新题材名称
            event_data: 事件数据
            existing_themes: 现有题材列表
            
        Returns:
            判重结果
        """
        logger.info(f"开始判重检查: {new_theme_name}, 现有题材数: {len(existing_themes)}")
        
        if not existing_themes:
            return DeduplicationResult(
                should_merge=False,
                reason="无现有题材可比较",
                confidence=0.0
            )
        
        # 策略1: 精确匹配
        if self.config['strategies']['enable_exact_match']:
            exact_result = self._check_exact_match(new_theme_name, existing_themes)
            if exact_result.should_merge:
                logger.info(f"精确匹配: {new_theme_name} -> {exact_result.target_theme.get('name')}")
                return exact_result
        
        # 策略2: 包含关系检查
        if self.config['strategies']['enable_inclusion_check']:
            inclusion_result = self._check_inclusion_match(new_theme_name, existing_themes)
            if inclusion_result.should_merge:
                logger.info(f"包含关系匹配: {new_theme_name}")
                return inclusion_result
        
        # 策略3: 语义相似度分析
        if self.config['strategies']['enable_semantic_analysis']:
            semantic_result = await self._check_semantic_similarity(new_theme_name, existing_themes)
            if semantic_result.should_merge:
                logger.info(f"语义相似度过高: {new_theme_name}")
                return semantic_result
        
        # 策略4: 事件重合度分析（如果有事件数据）
        if self.config['strategies']['enable_event_overlap'] and event_data:
            overlap_result = await self._check_event_overlap(event_data, existing_themes)
            if overlap_result.should_merge:
                logger.info(f"事件重合度过高: {new_theme_name}")
                return overlap_result
        
        # 综合相似度计算
        best_match, max_similarity = self._calculate_comprehensive_similarity(
            new_theme_name, event_data, existing_themes
        )
        
        # 根据相似度决定处理方式
        return self._make_final_decision(new_theme_name, best_match, max_similarity)
    
    def _check_exact_match(self, new_theme_name: str, 
                          existing_themes: List[Dict[str, Any]]) -> DeduplicationResult:
        """精确匹配检查"""
        new_name_clean = self._clean_theme_name(new_theme_name)
        
        for theme in existing_themes:
            existing_name = theme.get('name', '')
            existing_name_clean = self._clean_theme_name(existing_name)
            
            # 直接相等
            if new_name_clean == existing_name_clean:
                return DeduplicationResult(
                    should_merge=True,
                    target_theme=theme,
                    similarity_score=1.0,
                    match_type="exact",
                    reason=f"名称完全匹配: {new_theme_name} == {existing_name}",
                    confidence=1.0
                )
            
            # 考虑同义词后的相等
            if self._are_names_equal_with_synonyms(new_name_clean, existing_name_clean):
                return DeduplicationResult(
                    should_merge=True,
                    target_theme=theme,
                    similarity_score=0.95,
                    match_type="exact_with_synonyms",
                    reason=f"考虑同义词后名称匹配: {new_theme_name} ≈ {existing_name}",
                    confidence=0.9
                )
        
        return DeduplicationResult(should_merge=False)
    
    def _check_inclusion_match(self, new_theme_name: str,
                              existing_themes: List[Dict[str, Any]]) -> DeduplicationResult:
        """包含关系检查"""
        new_name_clean = self._clean_theme_name(new_theme_name)
        
        for theme in existing_themes:
            existing_name = theme.get('name', '')
            existing_name_clean = self._clean_theme_name(existing_name)
            
            # 新名称包含在现有名称中
            if new_name_clean in existing_name_clean:
                similarity = len(new_name_clean) / len(existing_name_clean) if existing_name_clean else 0
                if similarity >= self.thresholds['inclusion_match']:
                    return DeduplicationResult(
                        should_merge=True,
                        target_theme=theme,
                        similarity_score=similarity,
                        match_type="inclusion",
                        reason=f"新题材名被现有题材名包含: {new_theme_name} ⊆ {existing_name}",
                        confidence=min(0.9, similarity)
                    )
            
            # 现有名称包含在新名称中
            elif existing_name_clean in new_name_clean:
                similarity = len(existing_name_clean) / len(new_name_clean) if new_name_clean else 0
                if similarity >= self.thresholds['inclusion_match']:
                    return DeduplicationResult(
                        should_merge=True,
                        target_theme=theme,
                        similarity_score=similarity,
                        match_type="inclusion",
                        reason=f"现有题材名被新题材名包含: {existing_name} ⊆ {new_theme_name}",
                        confidence=min(0.9, similarity)
                    )
        
        return DeduplicationResult(should_merge=False)
    
    async def _check_semantic_similarity(self, new_theme_name: str,
                                        existing_themes: List[Dict[str, Any]]) -> DeduplicationResult:
        """语义相似度分析"""
        new_name_tokens = self._tokenize_theme_name(new_theme_name)
        
        best_match = None
        max_similarity = 0.0
        
        for theme in existing_themes:
            existing_name = theme.get('name', '')
            existing_tokens = self._tokenize_theme_name(existing_name)
            
            # 计算Jaccard相似度
            similarity = self._calculate_jaccard_similarity(new_name_tokens, existing_tokens)
            
            # 考虑同义词
            synonym_similarity = self._calculate_synonym_similarity(new_name_tokens, existing_tokens)
            similarity = max(similarity, synonym_similarity)
            
            if similarity > max_similarity:
                max_similarity = similarity
                best_match = theme
        
        if best_match and max_similarity >= self.thresholds['semantic_similarity']:
            return DeduplicationResult(
                should_merge=True,
                target_theme=best_match,
                similarity_score=max_similarity,
                match_type="semantic",
                reason=f"语义相似度过高: {max_similarity:.2f}",
                confidence=max_similarity
            )
        
        return DeduplicationResult(should_merge=False)
    
    async def _check_event_overlap(self, event_data: Dict[str, Any],
                                 existing_themes: List[Dict[str, Any]]) -> DeduplicationResult:
        """事件重合度分析"""
        # 这里需要访问数据库来获取事件重合信息
        # 现在返回模拟结果
        return DeduplicationResult(should_merge=False)
    
    def _calculate_comprehensive_similarity(self,
                                          new_theme_name: str,
                                          event_data: Dict[str, Any],
                                          existing_themes: List[Dict[str, Any]]) -> Tuple[Optional[Dict], float]:
        """计算综合相似度"""
        best_match = None
        max_similarity = 0.0
        
        new_name_tokens = self._tokenize_theme_name(new_theme_name)
        event_industries = set(event_data.get('impact_industries', []))
        
        for theme in existing_themes:
            existing_name = theme.get('name', '')
            existing_tokens = self._tokenize_theme_name(existing_name)
            theme_keywords = set(theme.get('keywords', '').split(','))
            theme_industries = set(filter(None, theme_keywords))
            
            # 计算各项相似度
            name_similarity = self._calculate_name_similarity(new_name_tokens, existing_tokens)
            keyword_similarity = self._calculate_keyword_similarity(event_industries, theme_industries)
            industry_similarity = self._calculate_industry_similarity(event_industries, theme_industries)
            semantic_similarity = self._calculate_semantic_similarity(new_name_tokens, existing_tokens)
            
            # 加权计算综合相似度
            weights = self.config['weights']
            total_similarity = (
                name_similarity * weights['name_similarity'] +
                keyword_similarity * weights['keyword_overlap'] +
                industry_similarity * weights['industry_match'] +
                semantic_similarity * weights['semantic_similarity']
            )
            
            if total_similarity > max_similarity:
                max_similarity = total_similarity
                best_match = theme
        
        return best_match, max_similarity
    
    def _make_final_decision(self, new_theme_name: str,
                            best_match: Optional[Dict[str, Any]],
                            similarity: float) -> DeduplicationResult:
        """根据相似度做出最终决策"""
        
        if similarity >= self.thresholds['auto_merge']:
            return DeduplicationResult(
                should_merge=True,
                target_theme=best_match,
                similarity_score=similarity,
                match_type="auto_merge",
                reason=f"综合相似度过高，建议自动合并: {similarity:.2f}",
                confidence=similarity,
                suggestions=["立即自动合并"]
            )
        
        elif similarity >= self.thresholds['suggest_merge']:
            return DeduplicationResult(
                should_merge=True,
                target_theme=best_match,
                similarity_score=similarity,
                match_type="suggest_merge",
                reason=f"综合相似度较高，建议合并: {similarity:.2f}",
                confidence=similarity,
                suggestions=["推荐合并，可自动执行"]
            )
        
        elif similarity >= self.thresholds['keep_separate']:
            return DeduplicationResult(
                should_merge=False,
                similarity_score=similarity,
                match_type="keep_separate",
                reason=f"有一定相似度({similarity:.2f})，但建议保持独立",
                confidence=1 - similarity,
                suggestions=["保持独立，监控后续发展"]
            )
        
        else:
            return DeduplicationResult(
                should_merge=False,
                similarity_score=similarity,
                match_type="distinct",
                reason=f"相似度较低({similarity:.2f})，可以创建新题材",
                confidence=1 - similarity,
                suggestions=["可以创建新题材"]
            )
    
    # 辅助方法
    def _clean_theme_name(self, name: str) -> str:
        """清洗题材名称"""
        if not name:
            return ""
        
        # 移除空格和特殊字符
        cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '', name)
        return cleaned
    
    def _are_names_equal_with_synonyms(self, name1: str, name2: str) -> bool:
        """考虑同义词的名称相等性检查"""
        if name1 == name2:
            return True
        
        # 检查同义词
        synonyms1 = self.synonyms.get(name1, [])
        synonyms2 = self.synonyms.get(name2, [])
        
        return (name1 in synonyms2 or name2 in synonyms1 or 
                any(s1 == name2 for s1 in synonyms1) or 
                any(s2 == name1 for s2 in synonyms2))
    
    def _tokenize_theme_name(self, name: str) -> List[str]:
        """分词处理"""
        if not name:
            return []
        
        cleaned = self._clean_theme_name(name)
        
        if self.use_jieba:
            try:
                tokens = list(jieba.cut(cleaned))
            except Exception:
                tokens = list(cleaned)  # 回退到字符级别
        else:
            tokens = list(cleaned)  # 字符级别分词
        
        # 移除停用词
        tokens = [t for t in tokens if t and t not in self.stop_words]
        
        return tokens
    
    def _calculate_jaccard_similarity(self, tokens1: List[str], tokens2: List[str]) -> float:
        """计算Jaccard相似度"""
        if not tokens1 or not tokens2:
            return 0.0
        
        set1 = set(tokens1)
        set2 = set(tokens2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_synonym_similarity(self, tokens1: List[str], tokens2: List[str]) -> float:
        """计算同义词相似度"""
        if not tokens1 or not tokens2:
            return 0.0
        
        # 扩展同义词
        expanded1 = set(tokens1)
        expanded2 = set(tokens2)
        
        for token in tokens1:
            if token in self.synonyms:
                expanded1.update(self.synonyms[token])
        
        for token in tokens2:
            if token in self.synonyms:
                expanded2.update(self.synonyms[token])
        
        # 计算扩展后的Jaccard相似度
        intersection = len(expanded1 & expanded2)
        union = len(expanded1 | expanded2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_name_similarity(self, tokens1: List[str], tokens2: List[str]) -> float:
        """计算名称相似度"""
        if not tokens1 or not tokens2:
            return 0.0
        
        # 使用SequenceMatcher计算字符串相似度
        str1 = ''.join(tokens1)
        str2 = ''.join(tokens2)
        
        return SequenceMatcher(None, str1, str2).ratio()
    
    def _calculate_keyword_similarity(self, keywords1: set, keywords2: set) -> float:
        """计算关键词相似度"""
        if not keywords1 or not keywords2:
            return 0.0
        
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_industry_similarity(self, industries1: set, industries2: set) -> float:
        """计算行业相似度"""
        return self._calculate_keyword_similarity(industries1, industries2)
    
    def _calculate_semantic_similarity(self, tokens1: List[str], tokens2: List[str]) -> float:
        """计算语义相似度"""
        # 这里可以集成更复杂的语义模型
        # 现在使用Jaccard相似度作为代理
        return self._calculate_jaccard_similarity(tokens1, tokens2)
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            "config": self.config,
            "synonym_count": len(self.synonyms),
            "stop_word_count": len(self.stop_words),
            "use_jieba": self.use_jieba,
            "thresholds": self.thresholds
        }


# 测试函数
async def test_deduplication_engine():
    """测试判重引擎"""
    print("🧪 测试ThemeDeduplicationEngine...")
    
    # 创建判重引擎
    engine = ThemeDeduplicationEngine()
    
    # 测试数据
    new_theme_name = "人工智能发展规划"
    event_data = {
        "id": 1001,
        "title": "国家发布人工智能发展规划",
        "impact_industries": ["人工智能", "信息技术", "软件"]
    }
    
    existing_themes = [
        {
            "id": 1,
            "name": "人工智能",
            "keywords": "AI,人工智能,机器学习",
            "event_count": 50
        },
        {
            "id": 2,
            "name": "信息技术",
            "keywords": "IT,软件,硬件",
            "event_count": 30
        },
        {
            "id": 3,
            "name": "大数据",
            "keywords": "数据,分析,云计算",
            "event_count": 25
        }
    ]
    
    # 执行判重检查
    result = await engine.check_duplication(new_theme_name, event_data, existing_themes)
    
    print(f"✅ 判重检查完成!")
    print(f"   新题材: {new_theme_name}")
    print(f"   是否合并: {result.should_merge}")
    
    if result.should_merge:
        print(f"   目标题材: {result.target_theme.get('name')}")
        print(f"   相似度: {result.similarity_score:.2f}")
        print(f"   匹配类型: {result.match_type}")
        print(f"   原因: {result.reason}")
    
    # 显示建议
    if result.suggestions:
        print(f"   建议: {result.suggestions}")
    
    # 显示引擎信息
    engine_info = engine.get_engine_info()
    print(f"\n🔧 引擎配置:")
    print(f"   同义词数量: {engine_info['synonym_count']}")
    print(f"   停用词数量: {engine_info['stop_word_count']}")
    print(f"   使用Jieba: {engine_info['use_jieba']}")
    
    return result


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_deduplication_engine())