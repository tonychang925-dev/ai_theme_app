"""
WikiWord2VecMatcher.py - 使用中文维基百科词向量
这个模型虽然小，但能解决你的航天航空问题
"""
import numpy as np
from typing import List, Dict, Any, Tuple
import jieba
import gzip
import os
from gensim.models import KeyedVectors

from .base_matcher import BaseMatcher, MatchResult


class WikiWord2VecMatcher(BaseMatcher):
    """中文维基百科词向量匹配器"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.algorithm_type = 'wiki_word2vec'
        
        # 配置
        self.wiki_config = {
            'auto_download': True,  # 自动下载模型
            'model_url': 'https://wikipedia2vec.s3.amazonaws.com/models/zh/2018-04-20/zhwiki_20180420_100d.txt.gz',
            'local_path': 'zhwiki_word2vec.bin',
            'vector_size': 100,  # 维基百科词向量维度
            'similarity_threshold': 0.6,
            'keyword_weight': 0.5,
            'semantic_weight': 0.5,
            'min_word_length': 2,
        }
        
        if config:
            self.wiki_config.update(config)
        
        self.config.update(self.wiki_config)
        
        # 初始化
        self.model = None
        self._download_and_load_model()
        
        print(f"📚 {self.__class__.__name__}初始化 - 维基百科词向量")
    
    def _download_and_load_model(self):
        """下载并加载维基百科词向量"""
        import requests
        import shutil
        
        model_path = self.wiki_config['local_path']
        
        # 如果本地已有模型，直接加载
        if os.path.exists(model_path):
            try:
                print(f"📖 加载本地模型: {model_path}")
                self.model = KeyedVectors.load(model_path, mmap='r')
                print(f"✅ 模型加载成功，词汇量: {len(self.model)}")
                return
            except:
                print("⚠️  本地模型加载失败，重新下载")
        
        # 下载模型
        if self.wiki_config['auto_download']:
            print("🌐 下载中文维基百科词向量...")
            
            try:
                # 使用较小的备用链接
                backup_url = "https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.zh.300.vec.gz"
                
                # 下载
                response = requests.get(backup_url, stream=True, timeout=30)
                if response.status_code == 200:
                    gz_path = 'cc.zh.300.vec.gz'
                    
                    with open(gz_path, 'wb') as f:
                        shutil.copyfileobj(response.raw, f)
                    
                    print(f"✅ 下载完成，解压...")
                    
                    # 解压并转换格式
                    self._convert_fasttext_to_word2vec(gz_path, model_path)
                    
                    # 加载模型
                    self.model = KeyedVectors.load(model_path, mmap='r')
                    print(f"✅ 模型加载成功，词汇量: {len(self.model)}")
                    
                    # 清理临时文件
                    if os.path.exists(gz_path):
                        os.remove(gz_path)
                    
                    return
                    
            except Exception as e:
                print(f"❌ 模型下载失败: {e}")
        
        print("⚠️  无法加载词向量模型，使用增强关键词匹配")
        self.model = None
    
    def _convert_fasttext_to_word2vec(self, gz_path: str, output_path: str):
        """转换FastText格式为Word2Vec格式"""
        print("🔄 转换模型格式...")
        
        import gzip
        
        # 读取FastText格式（第一行是词汇量和维度）
        with gzip.open(gz_path, 'rt', encoding='utf-8', errors='ignore') as f:
            # 跳过第一行（元信息）
            next(f)
            
            # 写入Word2Vec格式
            vocab = {}
            for line in f:
                parts = line.rstrip().split(' ')
                word = parts[0]
                vector = np.array([float(x) for x in parts[1:]], dtype=np.float32)
                vocab[word] = vector
        
        # 创建KeyedVectors对象
        from gensim.models import KeyedVectors
        kv = KeyedVectors(vector_size=300)  # FastText是300维
        kv.add_vectors(list(vocab.keys()), list(vocab.values()))
        
        # 保存为二进制格式
        kv.save(output_path)
        print(f"✅ 格式转换完成: {output_path}")