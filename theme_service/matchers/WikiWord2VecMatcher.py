"""
WikiWord2VecMatcher.py - 完整可用的中文维基百科词向量匹配器
带自动下载功能，一键使用
"""
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import jieba
import os
import sys
import logging
from pathlib import Path
import hashlib

from .base_matcher import BaseMatcher, MatchResult

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WikiWord2VecMatcher(BaseMatcher):
    """
    中文维基百科Word2Vec词向量匹配器
    
    特点：
    1. 自动下载预训练模型（如果本地没有）
    2. 能识别航天航空=航空航天
    3. 纯Python实现，无复杂依赖
    4. 完整的错误处理和回退机制
    """
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.algorithm_type = 'wiki_word2vec'
        
        # 默认配置
        default_config = {
            # 模型下载配置
            'model_urls': [
                # 备用源1：GitHub（较小，100维）
                'https://github.com/Embedding/Chinese-Word-Vectors/releases/download/v1.0/sgns.wiki.word',
                # 备用源2：清华镜像
                'https://thunlp.oss-cn-qingdao.aliyuncs.com/word2vec/sgns.wiki.word',
            ],
            'local_model_path': 'models/wiki_word2vec.bin',  # 本地模型路径
            'vector_size': 300,  # 向量维度
            
            # 匹配配置
            'similarity_threshold': 0.65,
            'keyword_weight': 0.4,
            'semantic_weight': 0.6,
            'min_word_length': 2,
            'max_word_length': 10,
            
            # 缓存配置
            'use_cache': True,
            'cache_size': 5000,
            'theme_vector_cache': {},  # 题材向量缓存
            
            # 回退配置
            'enable_fallback': True,
            'fallback_similarity_threshold': 0.5,
            
            # 下载配置
            'download_timeout': 300,  # 下载超时时间（秒）
            'download_chunk_size': 8192,  # 下载块大小
        }
        
        # 合并配置
        self.config = {**default_config, **(config or {})}
        
        # 初始化属性
        self.model = None
        self.word_vectors = {}
        self.theme_vectors_cache = {}
        self.vector_cache = {}
        
        # 创建模型目录
        model_dir = os.path.dirname(self.config['local_model_path'])
        if model_dir:
            os.makedirs(model_dir, exist_ok=True)
        
        # 加载模型
        self._load_or_download_model()
        
        logger.info(f"📚 {self.__class__.__name__}初始化完成")
    
    def _load_or_download_model(self):
        """加载或下载模型"""
        local_path = self.config['local_model_path']
        
        # 1. 尝试加载本地模型
        if os.path.exists(local_path):
            try:
                logger.info(f"📖 尝试加载本地模型: {local_path}")
                self._load_model(local_path)
                if self.model is not None:
                    return
            except Exception as e:
                logger.warning(f"本地模型加载失败: {e}")
        
        # 2. 尝试下载模型
        logger.info("🌐 本地模型不存在，尝试下载...")
        success = self._download_model()
        
        if not success and self.config['enable_fallback']:
            logger.warning("⚠️  模型下载失败，使用增强关键词匹配回退")
            self._initialize_fallback()
    
    def _download_model(self) -> bool:
        """下载模型文件"""
        import requests
        import shutil
        from tqdm import tqdm
        
        local_path = self.config['local_model_path']
        temp_path = f"{local_path}.tmp"
        
        for model_url in self.config['model_urls']:
            try:
                logger.info(f"🔄 尝试从 {model_url} 下载...")
                
                # 发送HEAD请求检查文件大小
                try:
                    head_response = requests.head(model_url, timeout=10)
                    file_size = int(head_response.headers.get('content-length', 0))
                    if file_size > 0:
                        logger.info(f"📦 文件大小: {file_size / 1024 / 1024:.1f} MB")
                except:
                    file_size = 0
                
                # 下载文件
                response = requests.get(
                    model_url, 
                    stream=True,
                    timeout=self.config['download_timeout']
                )
                response.raise_for_status()
                
                # 下载并显示进度条
                with open(temp_path, 'wb') as f:
                    if file_size > 0:
                        # 显示进度条
                        with tqdm(
                            total=file_size, 
                            unit='B', 
                            unit_scale=True, 
                            desc="下载进度"
                        ) as pbar:
                            for chunk in response.iter_content(chunk_size=self.config['download_chunk_size']):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                    else:
                        # 不显示进度条
                        for chunk in response.iter_content(chunk_size=self.config['download_chunk_size']):
                            if chunk:
                                f.write(chunk)
                
                logger.info(f"✅ 下载完成: {temp_path}")
                
                # 重命名临时文件
                if os.path.exists(temp_path):
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    os.rename(temp_path, local_path)
                    logger.info(f"✅ 文件已保存: {local_path}")
                    
                    # 尝试加载下载的模型
                    self._load_model(local_path)
                    return self.model is not None
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"下载失败 {model_url}: {e}")
                continue
            except Exception as e:
                logger.error(f"下载过程中出错: {e}")
                continue
        
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return False
    
    def _load_model(self, model_path: str):
        """加载Word2Vec模型"""
        try:
            # 尝试使用gensim加载
            from gensim.models import KeyedVectors
            
            # 检查文件格式
            if model_path.endswith('.bin'):
                # 二进制格式
                self.model = KeyedVectors.load(model_path, mmap='r')
            else:
                # 文本格式
                logger.info("📝 检测到文本格式，正在加载...")
                self.model = KeyedVectors.load_word2vec_format(
                    model_path, 
                    binary=False,
                    unicode_errors='ignore'
                )
                
                # 保存为二进制格式以便下次快速加载
                binary_path = f"{model_path}.bin"
                self.model.save(binary_path)
                logger.info(f"💾 已保存为二进制格式: {binary_path}")
            
            logger.info(f"✅ 模型加载成功")
            logger.info(f"   词汇量: {len(self.model):,}")
            logger.info(f"   向量维度: {self.model.vector_size}")
            
            # 测试模型效果
            self._test_model()
            
        except ImportError:
            logger.error("❌ 需要安装 gensim: pip install gensim")
            self.model = None
        except Exception as e:
            logger.error(f"❌ 模型加载失败: {e}")
            self.model = None
    
    def _test_model(self):
        """测试模型基本功能"""
        test_cases = [
            ('航天', '航空'),
            ('半导体', '芯片'),
            ('人工智能', 'AI'),
            ('新能源汽车', '电动车'),
            ('光伏', '太阳能'),
        ]
        
        logger.info("🧪 模型功能测试:")
        available_count = 0
        
        for w1, w2 in test_cases:
            try:
                similarity = self.model.similarity(w1, w2)
                logger.info(f"  {w1} ≈ {w2}: {similarity:.3f}")
                available_count += 1
            except KeyError:
                logger.info(f"  {w1}或{w2}: 不在词汇表中")
            except Exception as e:
                logger.info(f"  {w1}/{w2}: 测试失败 ({e})")
        
        coverage = available_count / len(test_cases)
        logger.info(f"📊 词汇覆盖率: {coverage:.1%}")
        
        if coverage < 0.4:
            logger.warning("⚠️  词汇覆盖率较低，某些关键词可能无法匹配")
    
    def _initialize_fallback(self):
        """初始化回退方案（增强关键词匹配）"""
        logger.info("🔄 初始化增强关键词匹配回退方案")
        
        # 中文同义词词典
        self.synonyms = {
            '航天': {'航空航天', '航空', '太空', '宇航', '航天工程'},
            '航空': {'航天', '飞行', '飞机', '民航', '航空运输'},
            '航空航天': {'航天航空', '航天', '航空', '太空探索'},
            '航天航空': {'航空航天', '航天', '航空', '太空飞行'},
            '半导体': {'芯片', '集成电路', 'IC', '微电子', '半导体器件'},
            '芯片': {'半导体', '集成电路', '处理器', '微芯片', '晶片'},
            '人工智能': {'AI', '机器学习', '深度学习', '智能计算'},
            'AI': {'人工智能', '机器学习', '深度学习', '智能算法'},
            '新能源汽车': {'电动车', '电动汽车', '新能源车', '电动轿车'},
            '电动车': {'电动汽车', '新能源汽车', '电动车辆', '电动交通'},
            '锂电池': {'锂离子电池', '锂电', '锂聚合物电池', '锂电芯'},
            '光伏': {'太阳能', '光伏发电', '太阳能电池', '光伏组件'},
            '太阳能': {'光伏', '太阳能发电', '太阳光能', '光热发电'},
            '5G': {'第五代移动通信', '5G通信', '5G网络', '第五代无线技术'},
            '数据中心': {'IDC', '服务器中心', '云计算中心', '数据机房'},
        }
        
        # 构建反向索引
        self.reverse_synonyms = {}
        for term, syns in self.synonyms.items():
            for syn in syns:
                if syn not in self.reverse_synonyms:
                    self.reverse_synonyms[syn] = set()
                self.reverse_synonyms[syn].add(term)
        
        # 字符相似度缓存
        self.char_similarity_cache = {}
        
        logger.info("✅ 回退方案初始化完成")
    
    def initialize(self, themes: List[Dict], categories: List[Dict] = None):
        """初始化匹配器"""
        super().initialize(themes, categories)
        
        logger.info(f"🔨 初始化数据: {len(themes)} 个题材")
        
        # 构建关键词索引
        self._build_theme_keywords_index()
        
        # 如果模型可用，预计算题材向量
        if self.model is not None:
            self._precompute_theme_vectors()
        else:
            logger.warning("⚠️  无词向量模型，使用增强关键词匹配模式")
        
        self.initialized = True
        logger.info(f"✅ {self.__class__.__name__} 初始化完成")
    
    def _build_theme_keywords_index(self):
        """构建题材关键词索引"""
        self.theme_keywords_cache = {}
        
        for theme_id, theme_data in self.themes.items():
            keywords = self._extract_theme_keywords(theme_data)
            self.theme_keywords_cache[theme_id] = keywords
    
    def _extract_theme_keywords(self, theme_data: Dict) -> List[str]:
        """从题材数据中提取关键词"""
        keywords = set()
        
        # 1. 题材名称
        name = theme_data.get('name', '')
        if name:
            # 分词并过滤
            name_words = jieba.lcut(name)
            keywords.update([w for w in name_words if len(w) >= 2])
        
        # 2. 关键词字段
        theme_keywords = theme_data.get('keywords', [])
        if isinstance(theme_keywords, list):
            keywords.update([kw for kw in theme_keywords if kw and isinstance(kw, str)])
        
        # 3. 标签中的关键词
        tags = theme_data.get('tags', {})
        if isinstance(tags, dict):
            tag_keywords = tags.get('keywords', [])
            if isinstance(tag_keywords, list):
                keywords.update([kw for kw in tag_keywords if kw])
        
        # 4. 概念
        concepts = theme_data.get('concepts', [])
        if concepts:
            keywords.update([c for c in concepts if c])
        
        return list(keywords)[:50]  # 限制数量
    
    def _precompute_theme_vectors(self):
        """预计算所有题材的向量"""
        logger.info("🔨 预计算题材向量...")
        
        batch_size = 32
        theme_ids = list(self.themes.keys())
        
        processed = 0
        for i in range(0, len(theme_ids), batch_size):
            batch_ids = theme_ids[i:i+batch_size]
            
            for theme_id in batch_ids:
                theme_keywords = self.theme_keywords_cache.get(theme_id, [])
                if theme_keywords:
                    vector = self._calculate_keywords_vector(theme_keywords)
                    if vector is not None:
                        self.theme_vectors_cache[theme_id] = vector
                        processed += 1
            
            if batch_ids:
                logger.debug(f"  进度: {min(i+batch_size, len(theme_ids))}/{len(theme_ids)}")
        
        logger.info(f"✅ 题材向量预计算完成: {processed} 个")
    
    def _calculate_keywords_vector(self, keywords: List[str]) -> Optional[np.ndarray]:
        """计算关键词列表的平均向量"""
        if not self.model or not keywords:
            return None
        
        vectors = []
        
        for keyword in keywords:
            if not keyword or len(keyword) < 2:
                continue
            
            # 获取词向量
            vector = self._get_word_vector(keyword)
            if vector is not None:
                vectors.append(vector)
            else:
                # 分词后尝试
                segments = jieba.lcut(keyword)
                for seg in segments:
                    if len(seg) >= 2:
                        seg_vector = self._get_word_vector(seg)
                        if seg_vector is not None:
                            vectors.append(seg_vector)
        
        if not vectors:
            return None
        
        # 返回平均向量
        return np.mean(vectors, axis=0)
    
    def _get_word_vector(self, word: str) -> Optional[np.ndarray]:
        """获取词向量（带缓存）"""
        if not self.model:
            return None
        
        # 检查缓存
        if self.config['use_cache'] and word in self.vector_cache:
            return self.vector_cache[word]
        
        try:
            # 从模型获取
            if word in self.model:
                vector = self.model[word]
                
                # 缓存
                if self.config['use_cache']:
                    if len(self.vector_cache) < self.config['cache_size']:
                        self.vector_cache[word] = vector
                
                return vector
        except Exception:
            pass
        
        return None
    
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """执行匹配"""
        if not self.initialized:
            raise RuntimeError("匹配器未初始化")
        
        import time
        start_time = time.time()
        
        event_id = event_data.get('event_id', 'unknown')
        logger.info(f"\n🎯 开始匹配事件: {event_id}")
        
        # 1. 提取事件关键词
        event_text = self._extract_event_text(event_data)
        event_keywords = self._extract_event_keywords(event_text, event_data)
        
        logger.info(f"📝 事件关键词: {len(event_keywords)} 个")
        if event_keywords:
            logger.info(f"   示例: {event_keywords[:8]}")
        
        # 2. 获取事件向量（如果有模型）
        event_vector = None
        if self.model and event_keywords:
            event_vector = self._calculate_keywords_vector(event_keywords)
        
        # 3. 匹配所有题材
        results = []
        for theme_id, theme_data in self.themes.items():
            theme_keywords = self.theme_keywords_cache.get(theme_id, [])
            if not theme_keywords:
                continue
            
            # 计算匹配分数
            match_score, matched_keywords = self._calculate_match_score(
                event_keywords, event_vector, theme_id, theme_keywords
            )
            
            if match_score > 0:
                result = self._create_match_result(
                    theme_id, theme_data, match_score, matched_keywords,
                    event_data, event_vector is not None
                )
                results.append(result)
        
        # 4. 过滤和排序
        threshold = self.config['similarity_threshold']
        
        # 根据精度调整阈值
        if precision == 'high':
            threshold = max(threshold, 0.7)
        elif precision == 'low':
            threshold = max(threshold - 0.1, 0.4)
        
        filtered_results = [
            r for r in results 
            if r.match_score >= threshold
        ]
        
        # 排序
        filtered_results.sort(key=lambda x: x.match_score, reverse=True)
        
        # 限制数量
        max_results = min(len(filtered_results), self.config.get('max_results', 10))
        final_results = filtered_results[:max_results]
        
        processing_time = time.time() - start_time
        logger.info(f"✅ 匹配完成: {len(final_results)} 个结果，耗时 {processing_time:.3f}s")
        
        return final_results
    
    def _calculate_match_score(self, event_keywords: List[str], 
                              event_vector: Optional[np.ndarray],
                              theme_id: str, 
                              theme_keywords: List[str]) -> Tuple[float, List[str]]:
        """计算匹配分数"""
        # 1. 关键词匹配分数
        keyword_score, keyword_matches = self._calculate_keyword_match_score(
            event_keywords, theme_keywords
        )
        
        # 2. 语义匹配分数（如果有向量）
        semantic_score, semantic_matches = 0.0, []
        if event_vector is not None and theme_id in self.theme_vectors_cache:
            theme_vector = self.theme_vectors_cache[theme_id]
            semantic_score = self._cosine_similarity(event_vector, theme_vector)
            
            if semantic_score >= self.config['similarity_threshold']:
                semantic_matches = keyword_matches  # 使用关键词匹配结果
        
        # 3. 如果无模型或语义匹配失败，使用增强关键词匹配
        if semantic_score == 0 and self.model is None:
            enhanced_score, enhanced_matches = self._calculate_enhanced_keyword_match(
                event_keywords, theme_keywords
            )
            if enhanced_score > keyword_score:
                keyword_score = enhanced_score
                keyword_matches = enhanced_matches
        
        # 4. 合并分数
        total_score = (
            keyword_score * self.config['keyword_weight'] + 
            semantic_score * self.config['semantic_weight']
        )
        
        # 合并匹配的关键词
        all_matches = list(set(keyword_matches + semantic_matches))
        
        return total_score, all_matches
    
    def _calculate_keyword_match_score(self, event_keywords: List[str], 
                                      theme_keywords: List[str]) -> Tuple[float, List[str]]:
        """基础关键词匹配"""
        if not event_keywords or not theme_keywords:
            return 0.0, []
        
        matched = []
        for ekw in event_keywords:
            if ekw in theme_keywords:
                matched.append(ekw)
        
        if matched:
            score = len(matched) / len(event_keywords)
            return min(score, 1.0), matched
        
        return 0.0, []
    
    def _calculate_enhanced_keyword_match(self, event_keywords: List[str], 
                                         theme_keywords: List[str]) -> Tuple[float, List[str]]:
        """增强关键词匹配（同义词+字符相似度）"""
        if not event_keywords or not theme_keywords:
            return 0.0, []
        
        matched = []
        
        for ekw in event_keywords:
            # 1. 精确匹配
            if ekw in theme_keywords:
                matched.append(ekw)
                continue
            
            # 2. 同义词匹配
            if hasattr(self, 'synonyms'):
                # 检查正向同义词
                if ekw in self.synonyms:
                    synonyms = self.synonyms[ekw]
                    if any(syn in theme_keywords for syn in synonyms):
                        matched.append(ekw)
                        continue
                
                # 检查反向同义词
                if ekw in self.reverse_synonyms:
                    sources = self.reverse_synonyms[ekw]
                    if any(src in theme_keywords for src in sources):
                        matched.append(ekw)
                        continue
            
            # 3. 包含关系
            for tkw in theme_keywords:
                if ekw in tkw or tkw in ekw:
                    matched.append(ekw)
                    break
            
            # 4. 分词匹配
            if not matched or matched[-1] != ekw:
                ekw_terms = set(jieba.lcut(ekw))
                for tkw in theme_keywords:
                    tkw_terms = set(jieba.lcut(tkw))
                    if ekw_terms & tkw_terms:
                        matched.append(ekw)
                        break
        
        if matched:
            score = len(matched) / len(event_keywords)
            return min(score, 1.0), matched
        
        return 0.0, []
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if vec1 is None or vec2 is None:
            return 0.0
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _create_match_result(self, theme_id: str, theme_data: Dict,
                            match_score: float, matched_keywords: List[str],
                            event_data: Dict, semantic_used: bool) -> MatchResult:
        """创建匹配结果"""
        # 判断匹配类型
        if semantic_used:
            if match_score >= 0.8:
                match_type = 'strong_semantic_match'
            elif match_score >= 0.6:
                match_type = 'semantic_match'
            else:
                match_type = 'weak_semantic_match'
        else:
            if match_score >= 0.7:
                match_type = 'strong_keyword_match'
            elif match_score >= 0.5:
                match_type = 'keyword_match'
            else:
                match_type = 'weak_keyword_match'
        
        # 提取分类信息
        level1_category = theme_data.get('level1_category', '')
        level2_category = theme_data.get('level2_category', '')
        level3_category = theme_data.get('level3_category', '')
        
        # 判断热点
        is_hot = self._is_hot_theme(theme_id)
        
        # 构建详情
        match_details = {
            'data_type': 'theme',
            'match_type': match_type,
            'semantic_used': semantic_used,
            'keyword_count': len(matched_keywords),
            'model_available': self.model is not None,
        }
        
        return MatchResult(
            theme_id=theme_id,
            theme_name=theme_data.get('name', ''),
            match_score=match_score,
            matched_keywords=matched_keywords,
            match_type=match_type,
            level1_category=level1_category,
            level2_category=level2_category,
            level3_category=level3_category,
            is_hot=is_hot,
            match_details=match_details
        )
    
    def _is_hot_theme(self, theme_id: str) -> bool:
        """判断是否为热点题材"""
        theme = self.themes.get(theme_id, {})
        heat_score = theme.get('heat_score', 0)
        return heat_score > 70
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        info = super().get_algorithm_info()
        
        info.update({
            'algorithm_type': 'wiki_word2vec',
            'model_available': self.model is not None,
            'vocabulary_size': len(self.model) if self.model else 0,
            'theme_vector_cache_size': len(self.theme_vectors_cache),
            'word_vector_cache_size': len(self.vector_cache),
            'using_fallback': self.model is None,
            'config': {
                'similarity_threshold': self.config['similarity_threshold'],
                'keyword_weight': self.config['keyword_weight'],
                'semantic_weight': self.config['semantic_weight'],
                'model_path': self.config['local_model_path'],
            }
        })
        
        return info