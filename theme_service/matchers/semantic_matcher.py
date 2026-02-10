# -*- coding: utf-8 -*-
"""
基于 Transformer 的语义题材匹配器（完整保留业务方法版）
"""
import time
import json
import re
import numpy as np
import jieba
from typing import List, Dict, Optional, Tuple
import warnings
from collections import defaultdict
warnings.filterwarnings('ignore')
import os

# 🔥 彻底禁用所有联网检查
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'

from .base_matcher import BaseMatcher, MatchResult


class TransformerSemanticMatcher(BaseMatcher):
    """
    基于 Transformer 的语义匹配算法
    完整保留 KeywordMatcher 的所有业务方法
    """

    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.algorithm_type = 'semantic'
        
        # 🔥 语义匹配特有配置
        self.semantic_config = {
            'model_name': 'shibing624/text2vec-base-chinese',
            'semantic_threshold': 0.95,
            'batch_size': 32,
            'use_cache': True,
            'cache_max_size': 1000,
            'max_text_length': 512,
            'enable_ai_boost': True,
            'ai_boost_factor': 0.1
        }

        # 🔥 合并配置
        if config:
            self._deep_update(self.semantic_config, config)
            self._deep_update(self.config, config)
        
        # 🔥 初始化语义匹配特有属性
        self.model = None
        self.theme_embeddings = {}  # theme_id -> vector
        self.theme_texts = {}       # theme_id -> text
        self.text_cache = {}
        
        # 🔥 初始化缓存和索引（与 KeywordMatcher 一致）
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
        
        # 🔥 AI相关缓存（完整保留）
        self.ai_category_index = {}
        self.category_keyword_map = {}
        
        print(f"🧠 {self.__class__.__name__} 初始化 (模型: {self.semantic_config['model_name']})")

    # ===================== 初始化方法 =====================

    def initialize(self, themes: List[Dict], categories: List[Dict] = None) -> "TransformerSemanticMatcher":
        """
        🔥 完整保留 KeywordMatcher 的初始化逻辑
        """
        print(f"🧠 TransformerSemanticMatcher.initialize")
        print(f"   接收数据: {len(themes)}题材, {len(categories) if categories else 0}分类")
        
        # 🔥 允许空数据，支持不同场景
        if not themes:
            print(f"   ⚠️  题材数据为空 - 分类优先模式")
        if not categories:
            print(f"   ⚠️  分类数据为空 - 仅题材匹配模式")
        
        # 🔥 调用父类initialize方法
        super().initialize(themes, categories)
        
        # 🔥 条件性构建索引（完整保留 KeywordMatcher 逻辑）
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
        
        # 🔥 加载语义模型并构建语义索引
        self._load_semantic_model()
        if themes:
            self._build_semantic_index()
        
        self.initialized = True
        print(f"✅ {self.__class__.__name__} 初始化完成")
        return self

    def _build_index(self):
        """🔥 实现抽象方法：构建关键词索引（完整保留 KeywordMatcher 逻辑）"""
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

    def _build_semantic_index(self):
        """
        🔥 构建语义索引（语义匹配特有）
        """
        if not self.themes:
            print(f"⚠️  无题材数据，跳过语义索引构建")
            return
        
        print(f"🔨 构建语义索引...")
        start_time = time.time()
        
        theme_count = 0
        for theme_id, theme in self.themes.items():
            # 构建题材文本
            text = self._build_theme_text(theme)
            self.theme_texts[theme_id] = text
            
            # 编码文本
            if self.model is not None:
                try:
                    embedding = self._encode(text)
                    self.theme_embeddings[theme_id] = embedding
                    theme_count += 1
                except Exception as e:
                    print(f"⚠️  题材 {theme_id} 编码失败: {e}")
                    self.theme_embeddings[theme_id] = self._get_random_vector(text)
            else:
                self.theme_embeddings[theme_id] = self._get_random_vector(text)
            
            # 显示进度
            if theme_count % 50 == 0:
                print(f"   已处理 {theme_count} 个题材...")
        
        elapsed = time.time() - start_time
        print(f"✅ 语义索引构建完成: {theme_count} 个题材向量，耗时 {elapsed:.2f}s")
        print(f"   模型状态: {'已加载' if self.model else '未加载，使用随机向量'}")

    def _build_category_keyword_index(self):
        """🔥 完整保留 KeywordMatcher 的分类索引构建逻辑"""
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

    # ===================== 模型加载 =====================

    def _load_semantic_model(self):
        """加载 text2vec 模型 - 强制使用本地缓存"""
        if self.model is not None:
            return
        
        model_name = self.semantic_config.get('model_name', 'shibing624/text2vec-base-chinese')
        print(f"🔄 加载 text2vec 模型: {model_name}")
        
        try:
            # 🔥 关键：设置离线模式后再导入
            import warnings
            warnings.filterwarnings('ignore')
            
            # 方法1：直接使用 transformers 加载 text2vec 的模型
            # text2vec-base-chinese 的底层就是 BERT 模型
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            print(f"   直接加载模型: {model_name}")
            
            # 🔥 关键：local_files_only=True 强制只用本地缓存
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                local_files_only=True,
                trust_remote_code=True
            )
            
            self.model = AutoModel.from_pretrained(
                model_name,
                local_files_only=True,  # 🔥 强制离线
                trust_remote_code=True,
                torch_dtype=torch.float32
            )
            
            self.model.eval()
            
            # 标记为使用 transformers 方式
            self._use_transformers = True
            
            # 设备设置
            if self.semantic_config.get('device') == 'cuda' and torch.cuda.is_available():
                self.model = self.model.cuda()
                print("✅ 使用 GPU 加速")
            else:
                self.model = self.model.cpu()
                print("✅ 使用 CPU 运行")
            
            print(f"✅ 成功加载模型: {model_name}")
            
        except Exception as e:
            print(f"❌ 直接加载失败: {e}")
            print("🔄 尝试使用 text2vec 的 SentenceModel...")
            
            try:
                # 方法2：尝试 text2vec（可能还会联网，但本地缓存应该能工作）
                from text2vec import SentenceModel
                
                # 临时设置更长的超时
                import requests
                requests.sessions.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=1)
                
                self.model = SentenceModel(model_name)
                self._use_transformers = False
                print(f"✅ text2vec SentenceModel 加载成功: {model_name}")
                
            except Exception as e2:
                print(f"❌ text2vec 也失败: {e2}")
                self.model = None

    # ===================== 核心匹配方法 =====================

    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """
        🔥 语义匹配方法 - 使用向量相似度
        """
        if not self.initialized:
            raise RuntimeError("算法未初始化")
        
        start_time = time.time()
        
        print(f"\n🧠 TransformerSemanticMatcher.match 开始")
        print(f"   事件ID: {event_data.get('event_id', 'unknown')}")
        print(f"   当前数据: {len(self.themes)}题材, {len(self.categories)}分类")
        
        # 🔥 完整保留 KeywordMatcher 的文本和关键词提取
        event_text = self._extract_event_text(event_data)
        event_keywords = self._extract_event_keywords(event_text, event_data)
        
        print(f"🔍 语义匹配: 事件文本长度 {len(event_text)}, 关键词 {len(event_keywords)} 个")
        if event_keywords:
            print(f"   事件关键词前5个: {event_keywords[:5]}")
        
        # 🔥 如果有题材数据，进行语义匹配
        results = []
        if self.themes and self.theme_embeddings:
            print(f"   语义匹配题材数据...")
            semantic_results = self._match_themes_semantic(event_text, event_keywords, event_data)
            results.extend(semantic_results)
        
        if not results:
            print(f"   ⚠️  无匹配结果")
            return []
        
        # 🔥 计算置信度
        for result in results:
            result.confidence = self.calculate_confidence(result)
        
        # 🔥 排序
        results.sort(key=lambda x: x.confidence, reverse=True)
        
        processing_time = time.time() - start_time
        print(f"✅ 语义匹配完成: 找到 {len(results)} 个结果，耗时 {processing_time:.3f}s")
        
        return results[:self.config['max_results']]

    def _match_themes_semantic(self, event_text: str, event_keywords: List[str],
                          event_data: Dict) -> List[MatchResult]:
        """语义匹配题材数据 - 修复版"""
        if not event_text or not self.theme_embeddings:
            return []
        
        # 🔥 编码事件文本
        event_embedding = self._encode_text(event_text)
        if event_embedding is None:
            return []
        
        results = []
        semantic_threshold = self.semantic_config.get('semantic_threshold', 0.8)
        final_score_threshold = semantic_threshold  # 🔥 最终分数也要过滤
        
        print(f"\n🔍 语义匹配详细信息:")
        print(f"   语义阈值: {semantic_threshold}")
        print(f"   最终分数阈值: {final_score_threshold}")
        print(f"   题材总数: {len(self.theme_embeddings)}")
        
        # 🔥 收集所有分数用于分析
        all_semantic_scores = []
        all_final_scores = []
        
        # 🔥 遍历所有题材
        passed_count = 0
        filtered_semantic_count = 0
        filtered_final_count = 0
        
        for theme_id, theme_embedding in self.theme_embeddings.items():
            theme = self.themes.get(theme_id, {})
            theme_name = theme.get('name', theme_id)[:20]
            
            # 1. 计算语义相似度
            semantic_score = self._cosine_similarity(event_embedding, theme_embedding)
            all_semantic_scores.append(semantic_score)
            
            # 2. 语义相似度阈值过滤
            if semantic_score < semantic_threshold:
                filtered_semantic_count += 1
                if filtered_semantic_count <= 3:
                    print(f"   ❌ 过滤[语义分低]: {theme_name}... - 语义分: {semantic_score:.3f} < {semantic_threshold}")
                continue
            
            # 3. 提取题材关键词
            theme_keywords = self.theme_keywords_cache.get(theme_id, [])
            matched_keywords = list(set(event_keywords) & set(theme_keywords))
            
            # 4. 计算最终分数（使用修复后的方法）
            final_score = self._calculate_semantic_score(
                semantic_score, 
                matched_keywords,
                theme_id,
                event_data
            )
            all_final_scores.append(final_score)
            
            # 🔥 关键修复：对final_score也应用阈值过滤
            if final_score < final_score_threshold:
                filtered_final_count += 1
                if filtered_final_count <= 3:
                    print(f"   ❌ 过滤[总分低]: {theme_name}... - 总分: {final_score:.3f} < {final_score_threshold} (语义分: {semantic_score:.3f})")
                continue
            
            # 5. 创建匹配结果
            result = self._create_match_result(
                theme_id, 
                final_score, 
                matched_keywords,
                event_data
            )
            
            results.append(result)
            passed_count += 1
            
            # 显示前几个通过的
            if passed_count <= 3:
                print(f"   ✅ 通过: {theme_name}... - 语义分: {semantic_score:.3f}, 总分: {final_score:.3f}")
        
        # 🔥 分析相似度分布
        if all_semantic_scores and all_final_scores:
            import numpy as np
            semantic_array = np.array(all_semantic_scores)
            final_array = np.array(all_final_scores)
            
            print(f"\n📈 相似度分布分析:")
            print(f"   语义相似度:")
            print(f"     最小值: {semantic_array.min():.4f}")
            print(f"     最大值: {semantic_array.max():.4f}")
            print(f"     平均值: {semantic_array.mean():.4f}")
            print(f"     中位数: {np.median(semantic_array):.4f}")
            print(f"     标准差: {semantic_array.std():.4f}")
            
            print(f"   最终分数:")
            print(f"     最小值: {final_array.min():.4f}")
            print(f"     最大值: {final_array.max():.4f}")
            print(f"     平均值: {final_array.mean():.4f}")
            
            # 阈值分析
            above_semantic_threshold = sum(1 for s in semantic_array if s >= semantic_threshold)
            above_final_threshold = sum(1 for s in final_array if s >= final_score_threshold)
            
            print(f"   阈值分析:")
            print(f"     语义分≥{semantic_threshold}: {above_semantic_threshold}/{len(semantic_array)}")
            print(f"     最终分≥{final_score_threshold}: {above_final_threshold}/{len(final_array)}")
        
        print(f"\n📊 过滤统计:")
        print(f"   总题材数: {len(self.theme_embeddings)}")
        print(f"   语义分过滤: {filtered_semantic_count} 个")
        print(f"   最终分过滤: {filtered_final_count} 个")
        print(f"   最终通过: {passed_count} 个")
        print(f"   通过率: {passed_count/len(self.theme_embeddings)*100:.1f}%")
        
        return results

    # ===================== 编码和向量计算 =====================

    def _encode(self, text: str) -> np.ndarray:
        """
        🔥 正确的编码方法 - 使用 transformers 方式编码
        注意：这个方法名必须是 _encode，因为你的代码在调用它
        """
        if not text:
            return np.zeros(768)
        
        try:
            # 检查是否有 tokenizer 和 model
            if not hasattr(self, 'tokenizer') or not self.tokenizer:
                return self._get_random_vector(text)
            
            if not hasattr(self, 'model') or not self.model:
                return self._get_random_vector(text)
            
            import torch
            
            # 使用 tokenizer 编码文本
            inputs = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt"
            )
            
            # 确保模型在正确的设备上
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # 使用 mean pooling 获取句子向量
            last_hidden_state = outputs.last_hidden_state  # [batch_size, seq_len, hidden_size]
            attention_mask = inputs['attention_mask']      # [batch_size, seq_len]
            
            # 扩展 attention_mask
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
            
            # 加权平均
            sum_embeddings = torch.sum(last_hidden_state * input_mask_expanded, 1)
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            embeddings = sum_embeddings / sum_mask
            
            # L2 归一化
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            
            return embeddings[0].cpu().numpy()
            
        except Exception as e:
            print(f"⚠️  BERT编码失败: {e}")
            return np.zeros(768)

    def _encode_text(self, text: str) -> np.ndarray:
        """编码文本 - 修复版"""
        if not text:
            return np.zeros(768)
        
        try:
            if hasattr(self, '_use_transformers') and self._use_transformers:
                # 🔥 使用 transformers 方式编码
                return self._encode_with_transformers(text)
            elif self.model is not None and hasattr(self.model, 'encode'):
                # 🔥 使用 text2vec 的 encode 方法
                return self.model._encode([text])[0]
            else:
                return self._get_random_vector(text)
                
        except Exception as e:
            print(f"⚠️  编码失败，使用随机向量: {e}")
            return np.zeros(768)

    def _encode_with_transformers(self, text: str) -> np.ndarray:
        """使用 transformers 模型编码"""
        import torch
        
        if not hasattr(self, 'tokenizer') or not self.tokenizer:
            return self._get_random_vector(text)
        
        try:
            # 编码
            inputs = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt"
            )
            
            # 移动设备
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # mean pooling
            last_hidden_state = outputs.last_hidden_state
            attention_mask = inputs['attention_mask']
            
            # 扩展 attention_mask
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
            
            # 加权平均
            sum_embeddings = torch.sum(last_hidden_state * input_mask_expanded, 1)
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            embeddings = sum_embeddings / sum_mask
            
            # L2 归一化
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            
            return embeddings[0].cpu().numpy()
            
        except Exception as e:
            print(f"⚠️  transformers 编码失败: {e}")
            return self._get_random_vector(text)

    @staticmethod
    def _get_random_vector(text: str) -> np.ndarray:
        """生成随机向量（回退方案）"""
        np.random.seed(abs(hash(text)) % (2**32))
        return np.random.rand(768)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # ===================== 分数计算和结果构建 =====================

    def _calculate_semantic_score(self, semantic_score: float, matched_keywords: List[str],
                                 theme_id: str, event_data: Dict = None) -> float:
        """计算语义匹配分数 - 修复过度加成"""
        # 🔥 基础分数就是语义相似度
        base_score = semantic_score
        
        # 🔥 如果语义分已经很高，减少加成
        if semantic_score >= 0.95:
            # 0.95以上的高分，最多加成0.02
            max_bonus = 0.02
        elif semantic_score >= 0.9:
            # 0.9-0.95，最多加成0.05
            max_bonus = 0.05
        elif semantic_score >= 0.8:
            # 0.8-0.9，最多加成0.1
            max_bonus = 0.1
        else:
            # 低于0.8，最多加成0.15
            max_bonus = 0.15
        
        # 🔥 计算加成
        total_bonus = 0.0
        
        # 1. 关键词匹配加成
        if matched_keywords:
            keyword_bonus = min(len(matched_keywords) * 0.015, 0.04)
            total_bonus += keyword_bonus
        
        # 2. 热门题材加成
        if self._is_hot_theme(theme_id):
            total_bonus += 0.02
        
        # 3. AI 分析加成
        if event_data and 'ai_analysis' in event_data and self.semantic_config.get('enable_ai_boost', True):
            ai_confidence = event_data['ai_analysis'].get('concept_confidence', 0.8)
            ai_bonus = min(ai_confidence * 0.02, 0.02)
            total_bonus += ai_bonus
        
        # 🔥 限制总加成
        total_bonus = min(total_bonus, max_bonus)
        
        # 计算最终分数
        final_score = base_score + total_bonus
        
        # 🔥 确保不超过1.0
        return min(final_score, 1.0)

    def _create_match_result(self, theme_id: str, match_score: float,
                            matched_keywords: List[str], event_data: Dict = None) -> MatchResult:
        """创建语义匹配结果"""
        theme = self.themes.get(theme_id, {})
        
        # 🔥 判断匹配类型
        match_type = self._determine_semantic_match_type(match_score, matched_keywords)
        
        # 🔥 获取分类信息
        level1_category, level2_category, level3_category = self._extract_theme_categories(theme_id)
        
        # 🔥 判断是否为热点
        is_hot = self._is_hot_theme(theme_id)
        
        # 🔥 匹配详情
        match_details = {
            'data_type': 'theme',
            'match_method': 'semantic',
            'keyword_count': len(matched_keywords),
            'has_ai_analysis': event_data and 'ai_analysis' in event_data,
            'embedding_used': self.model is not None
        }
        
        result = MatchResult(
            theme_id=theme_id,
            theme_name=theme.get('name', theme_id),
            match_score=match_score,
            matched_keywords=matched_keywords,
            match_type=match_type,
            level1_category=level1_category,
            level2_category=level2_category,
            level3_category=level3_category,
            is_hot=is_hot,
            match_details=match_details
        )
        
        return result

    def _determine_semantic_match_type(self, score: float, matched_keywords: List[str]) -> str:
        """根据语义匹配分数判断匹配类型"""
        if score >= 0.8:
            return 'semantic_strong_match'
        elif score >= 0.7:
            return 'semantic_good_match'
        elif score >= 0.6:
            return 'semantic_match'
        elif len(matched_keywords) >= 3:
            return 'semantic_keyword_enhanced'
        elif len(matched_keywords) >= 1:
            return 'semantic_weak_match'
        else:
            return 'semantic_minimal_match'

    # ===================== 🔥 完整保留的业务方法 =====================
    # 以下方法完全复制自 KeywordMatcher，不做任何修改

    def _build_theme_index(self):
        """构建题材关键词索引（完整保留）"""
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

    def _extract_event_text(self, event_data: Dict) -> str:
        """提取事件文本（完整保留）"""
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
        """提取事件关键词 - 支持AI关键词直通（完整保留）"""
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
        """提取题材关键词（完整保留）"""
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
        """从数据库tags字段提取关键词（完整保留）"""
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
        """提取分类关键词（完整保留）"""
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

    def infer_category_from_ai_keywords(self, ai_analysis: Dict) -> Dict:
        """
        从AI关键词推断行业分类（完整保留）
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
                'theme_type': 'concept',
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

    # ===================== 其他必要方法 =====================

    def _build_theme_text(self, theme: Dict) -> str:
        """构建题材文本用于语义编码"""
        parts = [
            theme.get('name', ''),
            theme.get('description', ''),
            ' '.join(theme.get('keywords', [])),
            theme.get('level2_category', ''),
            theme.get('level3_category', '')
        ]
        
        text = ' '.join([str(p) for p in parts if p and str(p).strip()])
        
        max_length = self.semantic_config.get('max_text_length', 512)
        if len(text) > max_length:
            text = text[:max_length]
        
        return text.strip()

    def batch_match(self, events_data: List[Dict]) -> List[List[MatchResult]]:
        """批量匹配"""
        return [self.match(event) for event in events_data]

    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        info = super().get_algorithm_info()
        info['type'] = self.algorithm_type
        
        info['semantic_model'] = {
            'name': self.semantic_config.get('model_name'),
            'loaded': self.model is not None,
            'embedding_dim': 768,
            'theme_vectors': len(self.theme_embeddings)
        }
        
        info['keyword_index'] = {
            'themes': len(self.theme_keywords_cache),
            'categories': len(self.category_keyword_map),
            'keywords': sum(len(kw) for kw in self.theme_keywords_cache.values())
        }
        
        return info

    def _deep_update(self, target: Dict, source: Dict):
        """深度更新配置"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value