"""
local_qwen_matcher.py - 使用本地Qwen嵌入模型的语义匹配器
完全离线，无需API调用，继承现有BaseMatcher架构
"""
import time
import json
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import os
import torch
from transformers import AutoModel, AutoTokenizer
import jieba

from .base_matcher import BaseMatcher, MatchResult


class LocalQwenEmbeddingMatcher(BaseMatcher):
    """本地Qwen嵌入语义匹配算法 - 完全离线部署"""
    
    def __init__(self, config: Dict = None):
        os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'  # 禁用警告
        os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'  # 启用MPS回退
        os.environ['HF_HUB_OFFLINE'] = '1'  # 强制离线，禁止下载
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        super().__init__(config)
        self.algorithm_type = 'local_qwen_embedding'
        
        # 默认配置
        default_config = {
            # 模型配置
            'model_name': 'Qwen/Qwen2.5-0.5B-Instruct',  # 轻量级版本，约500MB
            'device': 'auto',  # 'cuda', 'cpu', 'mps'(Apple Silicon), 'auto'
            'torch_dtype': 'auto',  # 自动选择数据类型
            'max_length': 512,  # 最大输入长度
            'normalize_embeddings': True,  # 是否归一化向量
            
            # 缓存配置
            'use_cache': True,
            'cache_dir': './.qwen_cache',
            'theme_vectors_file': 'theme_vectors.npz',  # 预计算向量存储
            
            # 匹配配置
            'match_threshold': 0.5,
            'max_results': 10,
            'min_keyword_matches': 1,
            'semantic_weight': 0.8,
            'keyword_weight': 0.2,
            'name_weight': 0.1,
            'heat_weight': 0.05,
            
            # 批量处理配置
            'batch_size': 8,
            'enable_keyword_fallback': True,
            
            # 关键词配置
            'use_database_tags': True,
            'use_ai_analysis': True,
            'ai_keywords_boost': 0.15,
        }
        
        # 合并配置
        self.config = {**default_config, **(config or {})}
        
        # 初始化组件
        self.model = None
        self.tokenizer = None
        self.device = None
        
        # 数据存储
        self.theme_vectors = {}  # {theme_id: np.ndarray}
        self.theme_keywords_cache = {}  # {theme_id: List[str]}
        self.embedding_dimension = None
        
        # 性能统计
        self.stats = {
            'encode_calls': 0,
            'match_calls': 0,
            'total_themes': 0,
            'load_time': 0,
            'init_time': 0
        }
        
        print(f"🏠 {self.__class__.__name__}初始化 - 本地Qwen嵌入模型")
    
    def _setup_device(self) -> str:
        """自动设置运行设备"""
        if self.config['device'] != 'auto':
            return self.config['device']
        
        # 自动检测最佳设备
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            if gpu_count > 0:
                device = f'cuda:{torch.cuda.current_device()}'
                gpu_name = torch.cuda.get_device_name(0)
                print(f"  检测到GPU: {gpu_name} ({gpu_count}个)")
                return device
        
        # 检查Apple Silicon (MPS)
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print(f"  检测到Apple Silicon (MPS)")
            return 'mps'
        
        # 默认使用CPU
        print(f"  使用CPU")
        return 'cpu'
    
    def _load_local_model(self):
        """加载本地Qwen模型"""
        start_time = time.time()
        model_name = self.config['model_name']
        model_name_str = str(model_name)
        
        print(f"🔧 加载本地Qwen模型: {model_name}")
        print(f"  缓存目录: {self.config['cache_dir']}")

        # gguf 不是 transformers 模型目录，必须走 llama.cpp 服务
        if model_name_str.endswith(".gguf"):
            raise RuntimeError(
                "local_qwen_matcher 仅支持 transformers 本地目录模型；"
                "检测到 .gguf，请改用 llama.cpp 服务链路。"
            )

        # 若提供了本地目录则强制本地加载；否则按离线缓存查找
        model_path = Path(model_name_str)
        force_local_only = model_path.exists()
        
        try:
            # 设置设备
            self.device = self._setup_device()
            
            # 1. 加载tokenizer
            print("  1. 加载tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
                cache_dir=self.config['cache_dir'],
                local_files_only=True if force_local_only else True
            )
            
            # 确保有pad token
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # 2. 确定数据类型
            torch_dtype = self.config['torch_dtype']
            if torch_dtype == 'auto':
                if self.device.startswith('cuda'):
                    torch_dtype = torch.float16  # GPU使用半精度
                else:
                    torch_dtype = torch.float32  # CPU使用单精度
            
            # 3. 加载模型
            print(f"  2. 加载模型到 {self.device}...")
            # CPU环境不要传device_map，否则transformers会要求accelerate依赖
            model_load_kwargs = {
                "trust_remote_code": True,
                "torch_dtype": torch_dtype,
                "cache_dir": self.config['cache_dir'],
                "local_files_only": True if force_local_only else True,
            }
            if self.device.startswith('cuda:'):
                model_load_kwargs["device_map"] = "auto"

            self.model = AutoModel.from_pretrained(
                model_name,
                **model_load_kwargs
            )
            
            # 设置为评估模式
            self.model.eval()
            
            # 4. 获取模型信息
            self.embedding_dimension = self.model.config.hidden_size
            param_count = sum(p.numel() for p in self.model.parameters())
            
            load_time = time.time() - start_time
            self.stats['load_time'] = load_time
            
            print(f"✅ 本地模型加载成功")
            print(f"   设备: {self.device}")
            print(f"   参数量: {param_count:,}")
            print(f"   向量维度: {self.embedding_dimension}")
            print(f"   加载时间: {load_time:.2f}秒")
            
            # 5. 测试模型功能
            self._test_model_functionality()
            
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            print("\n💡 解决方案：")
            print("   1. 使用本地 transformers 模型目录（包含 config.json/tokenizer/model 权重）")
            print("   2. 或使用 .gguf + llama.cpp 服务，不走 local_qwen_matcher")
            print(f"   3. 当前已强制离线(local_files_only=True)，不会联网下载")
            raise
    
    def _test_model_functionality(self):
        """测试模型嵌入功能"""
        print("🧪 测试模型嵌入功能...")
        
        test_texts = ["航天航空", "航空航天", "半导体芯片", "人工智能"]
        
        try:
            with torch.no_grad():
                embeddings = self._encode_batch_direct(test_texts)
            
            if embeddings and len(embeddings) == len(test_texts):
                # 计算相似度
                sim_aircraft = self._cosine_similarity(embeddings[0], embeddings[1])
                sim_chip = self._cosine_similarity(embeddings[0], embeddings[2])
                
                print(f"   ✅ '航天航空' vs '航空航天': {sim_aircraft:.4f}")
                print(f"   ✅ '航天航空' vs '半导体芯片': {sim_chip:.4f}")
                
                if sim_aircraft > 0.7:
                    print(f"   🚀 语义相似度检测正常，能识别'航天航空'问题")
                else:
                    print(f"   ⚠️  相似度较低，考虑使用更大模型")
                
                return True
            else:
                print(f"   ⚠️  嵌入生成失败")
                return False
                
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
            return False
    
    def initialize(self, themes: List[Dict], categories: List[Dict] = None):
        """
        初始化算法，加载题材数据并预计算嵌入向量
        
        Args:
            themes: 题材数据列表
            categories: 分类数据列表（可选）
        """
        init_start = time.time()
        
        print(f"📥 {self.__class__.__name__}.initialize 开始")
        print(f"   接收数据: {len(themes)}题材, {len(categories) if categories else 0}分类")
        
        # 1. 加载本地模型（如果尚未加载）
        if self.model is None:
            self._load_local_model()
        
        # 2. 调用父类初始化
        super().initialize(themes, categories)
        
        # 3. 构建关键词索引
        self._build_keyword_index()
        
        # 4. 预计算或加载题材向量
        if themes:
            self._load_or_compute_theme_vectors()
        
        # 5. 标记完成
        self.initialized = True
        
        init_time = time.time() - init_start
        self.stats['init_time'] = init_time
        self.stats['total_themes'] = len(self.themes)
        
        print(f"✅ {self.__class__.__name__}初始化完成")
        print(f"   预计算向量: {len(self.theme_vectors)} 个")
        print(f"   向量维度: {self.embedding_dimension}")
        print(f"   初始化时间: {init_time:.2f}秒")
    
    def _build_index(self):
        """构建语义匹配索引（实现抽象方法）"""
        print("🔨 构建语义匹配索引...")
        
        # 提取并缓存每个题材的关键词
        for theme_id, theme in self.themes.items():
            keywords = self._extract_theme_keywords_smart(theme_id)
            self.theme_keywords_cache[theme_id] = keywords
        
        print(f"   关键词索引构建完成: {len(self.theme_keywords_cache)} 个题材")
    
    def _build_keyword_index(self):
        """构建关键词索引"""
        # 复用_build_index的逻辑
        self._build_index()
    
    def _load_or_compute_theme_vectors(self):
        """加载或预计算题材向量"""
        if not self.config['use_cache']:
            self._precompute_all_theme_vectors()
            return
        
        # 检查是否有缓存的向量文件
        cache_dir = Path(self.config['cache_dir'])
        vectors_file = cache_dir / self.config['theme_vectors_file']
        
        if vectors_file.exists():
            print(f"📂 尝试加载缓存的题材向量...")
            try:
                loaded = np.load(vectors_file, allow_pickle=True)
                
                # 检查数据完整性
                theme_ids = loaded['theme_ids']
                embeddings = loaded['embeddings']

                # 部分命中也可复用，避免每次全量重算
                cache_map = {}
                for i, theme_id in enumerate(theme_ids):
                    try:
                        cache_map[str(theme_id)] = embeddings[i]
                    except Exception:
                        continue

                hit = 0
                for theme_id in self.themes.keys():
                    if theme_id in cache_map:
                        self.theme_vectors[theme_id] = cache_map[theme_id]
                        hit += 1

                miss = len(self.themes) - hit
                if miss <= 0:
                    print(f"✅ 加载缓存的题材向量: {len(self.theme_vectors)} 个")
                    return

                print(f"⚠️  缓存部分命中: {hit}/{len(self.themes)}，补算缺失: {miss}")
            except Exception as e:
                print(f"⚠️  缓存加载失败: {e}")
        
        # 仅补算缺失项
        self._precompute_missing_theme_vectors()
        self._save_theme_vectors_to_cache()

    def _precompute_missing_theme_vectors(self):
        """仅预计算缺失的题材向量"""
        missing_theme_ids = [tid for tid in self.themes.keys() if tid not in self.theme_vectors]
        if not missing_theme_ids:
            print("✅ 题材向量完整，无需补算")
            return

        print(f"🔨 补算题材向量: {len(missing_theme_ids)} 个")
        theme_texts = []
        for theme_id in missing_theme_ids:
            theme = self.themes[theme_id]
            theme_text = self._build_theme_embedding_text(theme)
            theme_texts.append(theme_text)

        total = len(theme_texts)
        batch_size = self.config['batch_size']
        total_batches = (total + batch_size - 1) // batch_size

        for batch_idx in range(0, total, batch_size):
            batch_texts = theme_texts[batch_idx:batch_idx + batch_size]
            batch_ids = missing_theme_ids[batch_idx:batch_idx + batch_size]

            batch_num = batch_idx // batch_size + 1
            print(f"   补算批次 {batch_num}/{total_batches}: {len(batch_texts)} 个题材")

            try:
                embeddings = self._encode_batch_direct(batch_texts)
                for i, theme_id in enumerate(batch_ids):
                    if i < len(embeddings) and embeddings[i] is not None:
                        self.theme_vectors[theme_id] = embeddings[i]

                progress = min(batch_idx + batch_size, total)
                print(f"     进度: {progress}/{total} ({progress/total*100:.1f}%)")
            except Exception as e:
                print(f"   ⚠️  补算批次失败: {e}")

        print(f"✅ 补算完成: 当前总向量 {len(self.theme_vectors)} 个")
    
    def _precompute_all_theme_vectors(self):
        """预计算所有题材的向量"""
        print(f"🔨 预计算题材向量...")
        
        theme_texts = []
        theme_ids = []
        
        # 准备批量文本
        for theme_id, theme in self.themes.items():
            theme_text = self._build_theme_embedding_text(theme)
            theme_texts.append(theme_text)
            theme_ids.append(theme_id)
        
        total = len(theme_texts)
        print(f"   需要编码 {total} 个题材")
        
        # 批量编码
        batch_size = self.config['batch_size']
        total_batches = (total + batch_size - 1) // batch_size
        
        for batch_idx in range(0, total, batch_size):
            batch_texts = theme_texts[batch_idx:batch_idx + batch_size]
            batch_ids = theme_ids[batch_idx:batch_idx + batch_size]
            
            batch_num = batch_idx // batch_size + 1
            print(f"   批次 {batch_num}/{total_batches}: {len(batch_texts)} 个题材")
            
            try:
                embeddings = self._encode_batch_direct(batch_texts)
                
                # 存储向量
                for i, theme_id in enumerate(batch_ids):
                    if i < len(embeddings) and embeddings[i] is not None:
                        self.theme_vectors[theme_id] = embeddings[i]
                
                # 更新进度
                progress = min(batch_idx + batch_size, total)
                print(f"     进度: {progress}/{total} ({progress/total*100:.1f}%)")
                
            except Exception as e:
                print(f"   ⚠️  批次编码失败: {e}")
                # 继续处理下一个批次
        
        print(f"✅ 预计算完成: {len(self.theme_vectors)}/{total} 个向量")
    
    def _save_theme_vectors_to_cache(self):
        """保存题材向量到缓存文件"""
        if not self.config['use_cache'] or not self.theme_vectors:
            return
        
        cache_dir = Path(self.config['cache_dir'])
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        vectors_file = cache_dir / self.config['theme_vectors_file']
        
        try:
            # 准备数据
            theme_ids = list(self.theme_vectors.keys())
            embeddings = np.stack([self.theme_vectors[tid] for tid in theme_ids])
            
            # 保存
            np.savez_compressed(
                vectors_file,
                theme_ids=theme_ids,
                embeddings=embeddings,
                config=json.dumps(self.config, ensure_ascii=False),
                timestamp=time.time()
            )
            
            print(f"💾 保存题材向量到缓存: {vectors_file}")
            print(f"   文件大小: {vectors_file.stat().st_size / 1024 / 1024:.2f} MB")
            
        except Exception as e:
            print(f"⚠️  保存缓存失败: {e}")
    
    def _build_theme_embedding_text(self, theme: Dict) -> str:
        """构建用于嵌入的题材文本"""
        parts = []
        
        # 1. 题材名称（最高权重）
        name = theme.get('name', '')
        if name:
            parts.append(name)
        
        # 2. 数据库tags关键词
        if self.config['use_database_tags']:
            tags_keywords = self._extract_theme_tags_keywords_from_theme(theme)
            if tags_keywords:
                parts.extend(tags_keywords)
        
        # 3. 关键词字段
        keywords = theme.get('keywords', [])
        if isinstance(keywords, list) and keywords:
            parts.extend(keywords)
        
        # 4. 概念
        concepts = theme.get('concepts', [])
        if concepts:
            parts.extend(concepts)
        
        # 5. 描述（限制长度）
        description = theme.get('description', '')
        if description:
            parts.append(description[:200])
        
        # 6. 分类信息
        for key in ['level1_category', 'level2_category', 'level3_category']:
            value = theme.get(key, '')
            if value:
                parts.append(value)
        
        # 用句号连接
        return '。'.join(parts)
    
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """
        语义匹配入口
        
        Args:
            event_data: 事件数据
            precision: 'high' | 'normal' | 'low' 匹配精度
        
        Returns:
            匹配结果列表
        """
        if not self.initialized:
            raise RuntimeError("算法未初始化")
        
        start_time = time.time()
        self.stats['match_calls'] += 1
        
        print(f"\n🏠 {self.__class__.__name__}.match 开始")
        print(f"   事件ID: {event_data.get('event_id', 'unknown')}")
        print(f"   精度模式: {precision}")
        print(f"   本地模型: {self.config['model_name']}")
        
        # 1. 提取事件文本和关键词
        event_text = self._extract_event_text(event_data)
        event_keywords = self._extract_event_keywords_smart(event_text, event_data)
        
        print(f"   事件文本: {len(event_text)} 字符")
        print(f"   事件关键词: {len(event_keywords)} 个")
        if event_keywords:
            print(f"   关键词示例: {event_keywords[:5]}")
        
        # 2. 编码事件文本（本地计算）
        event_embedding = self._encode_single_direct(event_text)
        if event_embedding is None:
            print(f"   ⚠️  事件编码失败，使用关键词回退")
            return self._fallback_to_keyword_match(event_keywords, event_data)
        
        # 3. 计算语义相似度
        semantic_results = []
        theme_ids = list(self.theme_vectors.keys())
        theme_vectors = [self.theme_vectors[tid] for tid in theme_ids]
        
        # 批量计算相似度（优化性能）
        print(f"   计算与 {len(theme_vectors)} 个题材的相似度...")
        similarities = self._batch_similarity(event_embedding, theme_vectors)
        
        # 4. 创建匹配结果
        for idx, similarity in enumerate(similarities):
            theme_id = theme_ids[idx]
            
            # 应用精度调整
            threshold = self._get_adjusted_threshold(precision)
            if similarity < threshold:
                continue
            
            theme = self.themes[theme_id]
            theme_keywords = self.theme_keywords_cache.get(theme_id, [])
            
            # 计算关键词匹配
            keyword_score, matched_keywords = self._calculate_keyword_match_score(
                event_keywords, theme_keywords
            )
            
            # 综合评分
            total_score = self._calculate_total_score(
                similarity, keyword_score, theme, event_text, event_data
            )
            
            # 创建结果
            result = self._create_semantic_match_result(
                theme_id, theme, total_score, similarity,
                keyword_score, matched_keywords, event_data
            )
            
            semantic_results.append(result)
        
        # 5. 排序和过滤
        semantic_results.sort(key=lambda x: x.match_score, reverse=True)
        max_results = min(len(semantic_results), self.config['max_results'])
        final_results = semantic_results[:max_results]
        
        # 6. 性能统计
        processing_time = time.time() - start_time
        print(f"✅ 本地语义匹配完成")
        print(f"   匹配结果: {len(final_results)} 个")
        print(f"   处理时间: {processing_time:.3f}秒")
        top_score = final_results[0].match_score if final_results else 0.0
        print(f"   最高相似度: {top_score:.4f}")
        
        return final_results
    
    def _encode_single_direct(self, text: str) -> Optional[np.ndarray]:
        """直接编码单个文本"""
        if not text or not text.strip():
            return None
        
        try:
            self.stats['encode_calls'] += 1
            
            # Tokenize
            inputs = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=self.config['max_length'],
                return_tensors="pt"
            )
            
            # 移动到模型设备
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # 获取嵌入
            with torch.no_grad():
                outputs = self.model(**inputs)
                
                # 使用最后一层隐藏状态的平均作为文本表示
                embeddings = outputs.last_hidden_state.mean(dim=1)
                
                # 归一化
                if self.config['normalize_embeddings']:
                    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
                # 转换为numpy数组
                embeddings_np = embeddings.cpu().numpy()[0]
                
            return embeddings_np
            
        except Exception as e:
            print(f"   ⚠️  编码失败: {e}")
            return None
    
    def _encode_batch_direct(self, texts: List[str]) -> List[np.ndarray]:
        """批量编码文本"""
        if not texts:
            return []
        
        try:
            self.stats['encode_calls'] += 1
            
            # Tokenize
            inputs = self.tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=self.config['max_length'],
                return_tensors="pt"
            )
            
            # 移动到模型设备
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # 获取嵌入
            with torch.no_grad():
                outputs = self.model(**inputs)
                
                # 使用最后一层隐藏状态的平均作为文本表示
                embeddings = outputs.last_hidden_state.mean(dim=1)
                
                # 归一化
                if self.config['normalize_embeddings']:
                    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
                # 转换为numpy数组
                embeddings_np = embeddings.cpu().numpy()
                
            return embeddings_np
            
        except Exception as e:
            print(f"   ⚠️  批量编码失败: {e}")
            return []
    
    def _batch_similarity(self, query_vector: np.ndarray, theme_vectors: List[np.ndarray]) -> np.ndarray:
        """批量计算相似度"""
        if not theme_vectors:
            return np.array([])
        
        # 堆叠所有题材向量
        theme_matrix = np.stack(theme_vectors)
        
        # 批量计算余弦相似度
        norms_query = np.linalg.norm(query_vector)
        norms_themes = np.linalg.norm(theme_matrix, axis=1)
        
        # 避免除零
        norms_themes[norms_themes == 0] = 1e-10
        
        similarities = np.dot(theme_matrix, query_vector) / (norms_themes * norms_query)
        
        # 处理数值误差
        similarities = np.clip(similarities, -1.0, 1.0)
        
        return similarities
    
    def _calculate_total_score(self, semantic_score: float, keyword_score: float,
                             theme: Dict, event_text: str, event_data: Dict) -> float:
        """计算综合评分"""
        # 基础权重
        semantic_weight = self.config['semantic_weight']
        keyword_weight = self.config['keyword_weight']
        
        # 基础分数
        total_score = (semantic_score * semantic_weight + 
                      keyword_score * keyword_weight)
        
        # 名称匹配加成
        theme_name = theme.get('name', '')
        if theme_name and theme_name in event_text:
            total_score = min(total_score + self.config['name_weight'], 1.0)
        
        # 热度加成
        theme_id = theme.get('code', '')
        if theme_id and self._is_hot_theme(theme_id):
            total_score = min(total_score + self.config['heat_weight'], 1.0)
        
        # AI分析加成
        if self.config['use_ai_analysis'] and 'ai_analysis' in event_data:
            ai_confidence = event_data['ai_analysis'].get('concept_confidence', 0.8)
            ai_boost = self.config['ai_keywords_boost'] * ai_confidence
            total_score = min(total_score + ai_boost, 1.0)
        
        # 高相似度奖励
        if semantic_score >= 0.8:
            total_score = min(total_score * 1.1, 1.0)
        
        return total_score
    
    def _create_semantic_match_result(self, theme_id: str, theme: Dict, 
                                     total_score: float, semantic_score: float,
                                     keyword_score: float, matched_keywords: List[str],
                                     event_data: Dict) -> MatchResult:
        """创建语义匹配结果对象"""
        # 确定匹配类型
        if semantic_score >= 0.8:
            match_type = 'strong_semantic_match'
        elif semantic_score >= 0.6:
            match_type = 'semantic_match'
        elif keyword_score >= 0.5:
            match_type = 'keyword_semantic_hybrid'
        else:
            match_type = 'weak_semantic_match'
        
        # 提取分类信息
        level1_category = theme.get('level1_category', '')
        level2_category = theme.get('level2_category', '')
        level3_category = theme.get('level3_category', '')
        
        # 判断热点
        is_hot = self._is_hot_theme(theme_id)
        
        # 匹配详情
        match_details = {
            'data_type': 'theme',
            'match_type': match_type,
            'algorithm': 'local_qwen_embedding',
            'model': self.config['model_name'],
            'semantic_score': round(semantic_score, 4),
            'keyword_score': round(keyword_score, 4),
            'keyword_count': len(matched_keywords),
            'embedding_dim': self.embedding_dimension,
        }
        
        # 添加AI分析信息（如果有）
        if 'ai_analysis' in event_data:
            match_details['ai_confidence'] = round(
                event_data['ai_analysis'].get('concept_confidence', 0.0), 3
            )
        
        # 创建结果
        result = MatchResult(
            theme_id=theme_id,
            theme_name=theme.get('name', ''),
            match_score=total_score,
            matched_keywords=matched_keywords,
            match_type=match_type,
            level1_category=level1_category,
            level2_category=level2_category,
            level3_category=level3_category,
            is_hot=is_hot,
            match_details=match_details
        )
        
        # 计算置信度
        result.confidence = self.calculate_confidence(result)
        
        return result
    
    def _get_adjusted_threshold(self, precision: str) -> float:
        """根据精度调整阈值"""
        base_threshold = self.config['match_threshold']
        
        if precision == 'high':
            return max(base_threshold, 0.6)
        elif precision == 'low':
            return max(base_threshold - 0.1, 0.3)
        else:  # normal
            return base_threshold
    
    def _extract_event_keywords_smart(self, event_text: str, event_data: Dict = None) -> List[str]:
        """智能提取事件关键词"""
        keywords = []
        
        # 1. 优先使用AI分析的关键词
        if self.config['use_ai_analysis'] and event_data and 'ai_analysis' in event_data:
            ai_analysis = event_data['ai_analysis']
            
            ai_industry = ai_analysis.get('industry_keywords', [])
            ai_event = ai_analysis.get('event_keywords', [])
            
            if ai_industry or ai_event:
                combined = list(set(ai_industry + ai_event))
                if combined:
                    return combined[:20]  # 限制数量
        
        # 2. 从事件文本中提取
        if event_text:
            words = jieba.lcut(event_text)
            
            # 过滤停用词
            stop_words = {
                '的', '了', '在', '是', '和', '与', '及', '对', '为', '有', '也', '都',
                '就', '但', '而', '且', '或', '还', '又', '更', '这', '那', '此', '该',
            }
            
            filtered = [
                w for w in words 
                if len(w) >= 2 and w not in stop_words
            ]
            
            # 去重
            seen = set()
            unique = []
            for word in filtered:
                if word not in seen:
                    seen.add(word)
                    unique.append(word)
            
            keywords.extend(unique[:15])  # 限制数量
        
        return keywords
    
    def _extract_theme_keywords_smart(self, theme_id: str) -> List[str]:
        """智能提取题材关键词"""
        theme = self.themes.get(theme_id, {})
        keywords = set()
        
        # 1. 优先使用数据库tags关键词
        if self.config['use_database_tags']:
            tags_keywords = self._extract_theme_tags_keywords(theme_id)
            if tags_keywords:
                keywords.update(tags_keywords)
        
        # 2. 从名称提取
        name = theme.get('name', '')
        if name:
            name_words = jieba.lcut(name)
            keywords.update([w for w in name_words if len(w) >= 2])
        
        # 3. 从keywords字段提取
        theme_keywords = theme.get('keywords', [])
        if isinstance(theme_keywords, list):
            keywords.update([kw for kw in theme_keywords if kw and len(kw) >= 2])
        
        return list(keywords)[:20]  # 限制数量
    
    def _extract_theme_tags_keywords_from_theme(self, theme: Dict) -> List[str]:
        """直接从theme字典提取tags关键词"""
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
    
    def _calculate_keyword_match_score(self, event_keywords: List[str], 
                                      theme_keywords: List[str]) -> Tuple[float, List[str]]:
        """计算关键词匹配分数"""
        if not event_keywords or not theme_keywords:
            return 0.0, []
        
        matched = []
        event_set = set(event_keywords)
        
        for keyword in theme_keywords:
            if keyword in event_set:
                matched.append(keyword)
        
        if not matched:
            return 0.0, []
        
        # 分数计算：匹配关键词数量 / 题材关键词总数
        score = len(matched) / max(len(theme_keywords), 1)
        return min(score, 1.0), matched
    
    def _fallback_to_keyword_match(self, event_keywords: List[str], 
                                  event_data: Dict) -> List[MatchResult]:
        """语义匹配失败时的关键词回退"""
        if not self.config['enable_keyword_fallback']:
            return []
        
        print(f"   🔄 启用关键词回退匹配")
        
        results = []
        
        for theme_id, theme in self.themes.items():
            theme_keywords = self.theme_keywords_cache.get(theme_id, [])
            
            if not theme_keywords:
                continue
            
            keyword_score, matched_keywords = self._calculate_keyword_match_score(
                event_keywords, theme_keywords
            )
            
            if keyword_score > 0:
                result = self._create_keyword_fallback_result(
                    theme_id, theme, keyword_score, matched_keywords, event_data
                )
                results.append(result)
        
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results[:self.config['max_results']]
    
    def _create_keyword_fallback_result(self, theme_id: str, theme: Dict, 
                                       keyword_score: float, matched_keywords: List[str],
                                       event_data: Dict) -> MatchResult:
        """创建回退匹配结果"""
        match_type = 'keyword_fallback_match'
        
        # 提取分类信息
        level1_category = theme.get('level1_category', '')
        level2_category = theme.get('level2_category', '')
        level3_category = theme.get('level3_category', '')
        
        # 判断热点
        is_hot = self._is_hot_theme(theme_id)
        
        # 匹配详情
        match_details = {
            'data_type': 'theme',
            'match_type': match_type,
            'algorithm': 'keyword_fallback',
            'keyword_score': round(keyword_score, 4),
            'keyword_count': len(matched_keywords)
        }
        
        result = MatchResult(
            theme_id=theme_id,
            theme_name=theme.get('name', ''),
            match_score=keyword_score,
            matched_keywords=matched_keywords,
            match_type=match_type,
            level1_category=level1_category,
            level2_category=level2_category,
            level3_category=level3_category,
            is_hot=is_hot,
            match_details=match_details
        )
        
        # 计算置信度
        result.confidence = self.calculate_confidence(result)
        
        return result
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if vec1 is None or vec2 is None:
            return 0.0
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # 处理数值误差
        similarity = max(min(similarity, 1.0), -1.0)
        
        return similarity
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        info = super().get_algorithm_info()
        
        info.update({
            'algorithm_type': 'local_qwen_embedding',
            'model_name': self.config['model_name'],
            'embedding_dimension': self.embedding_dimension,
            'device': self.device,
            'precomputed_vectors': len(self.theme_vectors),
            'performance_stats': self.stats,
            'config': {
                'semantic_weight': self.config['semantic_weight'],
                'keyword_weight': self.config['keyword_weight'],
                'match_threshold': self.config['match_threshold'],
                'batch_size': self.config['batch_size'],
                'normalize_embeddings': self.config['normalize_embeddings']
            }
        })
        
        return info
    
    def clear_cache(self):
        """清除缓存"""
        cache_dir = Path(self.config['cache_dir'])
        if cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir)
            print(f"🗑️  清除缓存: {cache_dir}")
        
        # 重置内存缓存
        self.theme_vectors = {}
        self.theme_keywords_cache = {}
        
        print(f"🔄 缓存已清除")


# 便捷函数：创建小型模型版本
def create_tiny_qwen_matcher(config: Dict = None) -> LocalQwenEmbeddingMatcher:
    """创建轻量Qwen模型匹配器（兼容旧函数名，默认0.5B）"""
    config = config or {}
    # 兼容历史调用入口：统一切到当前项目标准模型 0.5B。
    config.setdefault('model_name', 'Qwen/Qwen2.5-0.5B-Instruct')
    config.setdefault('batch_size', 8)
    return LocalQwenEmbeddingMatcher(config)


def create_medium_qwen_matcher(config: Dict = None) -> LocalQwenEmbeddingMatcher:
    """创建使用中等Qwen模型的匹配器（500MB）"""
    config = config or {}
    config['model_name'] = 'Qwen/Qwen2.5-0.5B-Instruct'  # 500MB
    return LocalQwenEmbeddingMatcher(config)


def create_large_qwen_matcher(config: Dict = None) -> LocalQwenEmbeddingMatcher:
    """创建使用大型Qwen模型的匹配器（1.5GB）"""
    config = config or {}
    config['model_name'] = 'Qwen/Qwen2.5-1.5B-Instruct'  # 1.5GB
    config['batch_size'] = 4  # 大模型需要更小的批次
    return LocalQwenEmbeddingMatcher(config)
