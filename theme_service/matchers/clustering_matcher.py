"""
聚类分析算法 - 用于Normal事件未匹配池的智能聚类
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Set, Optional
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass, field
import hashlib

from .base_matcher import BaseMatcher, MatchResult

logger = logging.getLogger(__name__)

@dataclass
class Cluster:
    """聚类簇"""
    cluster_id: str
    events: List[Dict] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    category_distribution: Dict[str, int] = field(default_factory=dict)
    representative_event: Dict = None
    quality_score: float = 0.0
    event_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def add_event(self, event_data: Dict, category_result: Dict = None):
        """添加事件到簇"""
        self.events.append({
            'event_data': event_data,
            'category': category_result,
            'timestamp': datetime.now()
        })
        self.event_count += 1
        self.last_updated = datetime.now()
        
    def calculate_quality(self) -> float:
        """计算簇的质量分数"""
        if self.event_count < 2:
            self.quality_score = 0.0
            return self.quality_score
            
        # 1. 事件数量分数 (0-0.3)
        size_score = min(self.event_count / 10, 0.3)
        
        # 2. 关键词一致性分数 (0-0.3)
        keyword_consistency = self._calculate_keyword_consistency()
        
        # 3. 分类一致性分数 (0-0.3)
        category_consistency = self._calculate_category_consistency()
        
        # 4. 时间密集度分数 (0-0.1)
        time_density = self._calculate_time_density()
        
        self.quality_score = size_score + keyword_consistency + category_consistency + time_density
        return self.quality_score
    
    def _calculate_keyword_consistency(self) -> float:
        """计算关键词一致性"""
        if self.event_count < 2:
            return 0.0
            
        # 收集所有事件的关键词
        all_keywords = []
        for event_record in self.events:
            event_data = event_record['event_data']
            keywords = event_data.get('keywords', [])
            all_keywords.extend([kw.lower() for kw in keywords])
        
        if not all_keywords:
            return 0.0
            
        # 计算最常见关键词的占比
        keyword_counter = Counter(all_keywords)
        most_common_keywords = keyword_counter.most_common(5)
        
        if not most_common_keywords:
            return 0.0
            
        total_keywords = len(all_keywords)
        top_keywords_count = sum(count for _, count in most_common_keywords[:3])
        
        consistency = top_keywords_count / total_keywords if total_keywords > 0 else 0.0
        return min(consistency * 0.3, 0.3)
    
    def _calculate_category_consistency(self) -> float:
        """计算分类一致性"""
        if self.event_count < 2:
            return 0.0
            
        # 收集所有事件的分类
        categories = []
        for event_record in self.events:
            category = event_record.get('category', {})
            level2_code = category.get('level2_code', 'unknown')
            categories.append(level2_code)
        
        if not categories:
            return 0.0
            
        # 计算最频繁分类的占比
        category_counter = Counter(categories)
        most_common_category, count = category_counter.most_common(1)[0]
        
        consistency = count / len(categories)
        return min(consistency * 0.3, 0.3)
    
    def _calculate_time_density(self) -> float:
        """计算时间密集度"""
        if self.event_count < 2:
            return 0.0
            
        # 获取所有事件的时间戳
        timestamps = []
        for event_record in self.events:
            if 'timestamp' in event_record:
                timestamps.append(event_record['timestamp'])
            elif 'event_data' in event_record:
                event_data = event_record['event_data']
                event_time = event_data.get('timestamp')
                if isinstance(event_time, str):
                    try:
                        event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                        timestamps.append(event_time)
                    except:
                        pass
        
        if len(timestamps) < 2:
            return 0.0
            
        # 计算时间跨度
        timestamps.sort()
        time_span = (timestamps[-1] - timestamps[0]).total_seconds()
        
        # 时间越密集，分数越高（24小时内为最高分）
        if time_span <= 86400:  # 24小时
            return 0.1
        elif time_span <= 259200:  # 3天
            return 0.05
        else:
            return 0.02
    
    def extract_core_concept(self) -> Dict:
        """提取核心概念"""
        # 收集所有信息
        all_keywords = []
        all_titles = []
        all_categories = []
        
        for event_record in self.events:
            event_data = event_record['event_data']
            
            # 关键词
            keywords = event_data.get('keywords', [])
            all_keywords.extend([kw.lower() for kw in keywords])
            
            # 标题
            title = event_data.get('title', '')
            if title:
                all_titles.append(title)
            
            # 分类
            category = event_record.get('category', {})
            level2_name = category.get('level2_name', '')
            if level2_name:
                all_categories.append(level2_name)
        
        # 找出最频繁的关键词
        keyword_counter = Counter(all_keywords)
        top_keywords = [kw for kw, _ in keyword_counter.most_common(5)]
        
        # 找出最频繁的分类
        category_counter = Counter(all_categories)
        top_category = category_counter.most_common(1)[0][0] if category_counter else ""
        
        # 分析标题中的共同主题
        common_theme = self._extract_common_theme_from_titles(all_titles)
        
        return {
            'core_keywords': top_keywords,
            'primary_category': top_category,
            'common_theme': common_theme,
            'event_count': self.event_count,
            'quality_score': self.quality_score,
            'time_span_hours': self._get_time_span_hours()
        }
    
    def _extract_common_theme_from_titles(self, titles: List[str]) -> str:
        """从标题中提取共同主题"""
        if not titles:
            return ""
            
        # 简单的提取方法：找出共同的名词
        words = []
        for title in titles:
            # 简单的分词（按空格）
            words.extend([w.lower() for w in title.split() if len(w) > 2])
        
        word_counter = Counter(words)
        common_words = [word for word, count in word_counter.most_common(3) if count > 1]
        
        if common_words:
            return " ".join(common_words)
        return titles[0][:20] if titles else "新概念"
    
    def _get_time_span_hours(self) -> float:
        """获取时间跨度（小时）"""
        if len(self.events) < 2:
            return 0.0
            
        timestamps = []
        for event_record in self.events:
            if 'timestamp' in event_record:
                timestamps.append(event_record['timestamp'])
        
        if len(timestamps) < 2:
            return 0.0
            
        timestamps.sort()
        time_span = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        return round(time_span, 2)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'cluster_id': self.cluster_id,
            'event_count': self.event_count,
            'quality_score': round(self.quality_score, 3),
            'created_at': self.created_at.isoformat(),
            'last_updated': self.last_updated.isoformat(),
            'core_concept': self.extract_core_concept()
        }


class ClusteringMatcher(BaseMatcher):
    """聚类分析算法"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.algorithm_type = 'clustering'
        
        # 聚类配置
        self.cluster_config = {
            'min_cluster_size': 3,
            'similarity_threshold': 0.6,
            'max_clusters': 20,
            'max_unmatched_events': 100,
            'clustering_interval_minutes': 60,
            'min_quality_threshold': 0.4
        }
        
        # 聚类数据
        self.clusters: Dict[str, Cluster] = {}  # cluster_id -> Cluster
        self.unmatched_events: List[Dict] = []  # 未匹配事件
        self.last_clustering_time: Optional[datetime] = None
        
        # 特征缓存
        self.event_features: Dict[str, Dict] = {}  # event_id -> features
        
        logger.info(f"🎯 聚类分析算法初始化")
    
    def _build_index(self):
        """构建聚类索引"""
        logger.info("🔨 构建聚类分析索引...")
        # 聚类分析不需要预构建索引，会在运行时动态聚类
        
    def match(self, event_data: Dict, precision: str = 'normal') -> List[MatchResult]:
        """
        执行聚类分析匹配
        
        注意：聚类分析是批量进行的，不是单事件匹配
        这个方法用于检查未匹配事件是否能形成新簇
        """
        # 聚类分析返回空列表，因为它不是传统的匹配算法
        # 真正的聚类分析通过 analyze_unmatched_events() 方法进行
        return []
    
    def add_unmatched_event(self, event_data: Dict, category_result: Dict = None) -> bool:
        """
        添加未匹配事件到聚类池
        
        Args:
            event_data: 事件数据
            category_result: 申万分类结果
        
        Returns:
            bool: 是否成功添加
        """
        try:
            event_id = event_data.get('event_id', f'event_{len(self.unmatched_events)}')
            
            # 检查是否已存在
            for event in self.unmatched_events:
                if event['event_data'].get('event_id') == event_id:
                    return False
            
            # 添加到未匹配池
            self.unmatched_events.append({
                'event_data': event_data,
                'category_result': category_result,
                'added_at': datetime.now(),
                'processed': False
            })
            
            # 控制池大小
            max_size = self.cluster_config['max_unmatched_events']
            if len(self.unmatched_events) > max_size:
                removed = self.unmatched_events.pop(0)
                logger.debug(f"📊 移除旧事件，池大小超限: {max_size}")
            
            # 检查是否需要立即聚类
            if len(self.unmatched_events) >= self.cluster_config['min_cluster_size'] * 2:
                self._try_clustering()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 添加未匹配事件失败: {e}")
            return False
    
    def _try_clustering(self):
        """尝试执行聚类"""
        # 检查时间间隔
        if self.last_clustering_time:
            elapsed = (datetime.now() - self.last_clustering_time).total_seconds() / 60
            if elapsed < self.cluster_config['clustering_interval_minutes']:
                return False
        
        # 检查事件数量
        if len(self.unmatched_events) < self.cluster_config['min_cluster_size']:
            return False
        
        # 执行聚类
        new_clusters = self.perform_clustering()
        
        if new_clusters:
            logger.info(f"🎯 聚类分析完成: 形成 {len(new_clusters)} 个新簇")
            self.last_clustering_time = datetime.now()
            return True
        
        return False
    
    def perform_clustering(self) -> List[Dict]:
        """
        执行聚类分析
        
        Returns:
            List[Dict]: 新形成的簇信息
        """
        if len(self.unmatched_events) < self.cluster_config['min_cluster_size']:
            return []
        
        logger.info(f"🔍 开始聚类分析: {len(self.unmatched_events)} 个未匹配事件")
        
        # 1. 提取事件特征
        event_features = self._extract_all_event_features()
        
        # 2. 计算相似度矩阵
        similarity_matrix = self._calculate_similarity_matrix(event_features)
        
        # 3. 执行聚类算法
        new_clusters = self._dbscan_clustering(event_features, similarity_matrix)
        
        # 4. 创建簇对象
        created_clusters = []
        for cluster_events in new_clusters:
            if len(cluster_events) >= self.cluster_config['min_cluster_size']:
                cluster = self._create_cluster_from_events(cluster_events)
                if cluster and cluster.quality_score >= self.cluster_config['min_quality_threshold']:
                    self.clusters[cluster.cluster_id] = cluster
                    created_clusters.append(cluster.to_dict())
                    
                    # 标记事件为已处理
                    for event_idx in cluster_events:
                        if event_idx < len(self.unmatched_events):
                            self.unmatched_events[event_idx]['processed'] = True
        
        # 5. 清理已处理的事件
        self.unmatched_events = [
            event for event in self.unmatched_events 
            if not event.get('processed', False)
        ]
        
        logger.info(f"📊 聚类分析结果: 创建 {len(created_clusters)} 个新簇, 剩余 {len(self.unmatched_events)} 个未匹配事件")
        
        return created_clusters
    
    def _extract_all_event_features(self) -> List[Dict]:
        """提取所有事件的特征"""
        features = []
        
        for idx, event_record in enumerate(self.unmatched_events):
            event_data = event_record['event_data']
            category_result = event_record['category_result']
            
            feature = self._extract_single_event_features(event_data, category_result)
            feature['event_idx'] = idx
            features.append(feature)
        
        return features
    
    def _extract_single_event_features(self, event_data: Dict, category_result: Dict) -> Dict:
        """提取单个事件的特征"""
        features = {
            'keywords': set(),
            'category_level1': '',
            'category_level2': '',
            'title_words': set()
        }
        
        # 关键词特征
        keywords = event_data.get('keywords', [])
        features['keywords'] = set([kw.lower() for kw in keywords if kw])
        
        # 分类特征
        if category_result:
            features['category_level1'] = category_result.get('level1_code', '')
            features['category_level2'] = category_result.get('level2_code', '')
        
        # 标题特征
        title = event_data.get('title', '')
        if title:
            title_words = [word.lower() for word in title.split() if len(word) >= 2]
            features['title_words'] = set(title_words)
        
        return features
    
    def _calculate_similarity_matrix(self, features: List[Dict]) -> np.ndarray:
        """计算相似度矩阵"""
        n = len(features)
        similarity_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                similarity = self._calculate_pairwise_similarity(features[i], features[j])
                similarity_matrix[i][j] = similarity
                similarity_matrix[j][i] = similarity
        
        return similarity_matrix
    
    def _calculate_pairwise_similarity(self, feat1: Dict, feat2: Dict) -> float:
        """计算两个事件的相似度"""
        scores = []
        
        # 1. 关键词相似度 (权重: 0.4)
        keywords1 = feat1.get('keywords', set())
        keywords2 = feat2.get('keywords', set())
        
        if keywords1 and keywords2:
            intersection = len(keywords1 & keywords2)
            union = len(keywords1 | keywords2)
            keyword_similarity = intersection / union if union > 0 else 0.0
            scores.append(('keywords', keyword_similarity, 0.4))
        
        # 2. 分类相似度 (权重: 0.3)
        cat1_l2 = feat1.get('category_level2', '')
        cat2_l2 = feat2.get('category_level2', '')
        
        if cat1_l2 and cat2_l2:
            category_similarity = 1.0 if cat1_l2 == cat2_l2 else 0.0
            scores.append(('category', category_similarity, 0.3))
        
        # 3. 标题相似度 (权重: 0.3)
        title1 = feat1.get('title_words', set())
        title2 = feat2.get('title_words', set())
        
        if title1 and title2:
            intersection = len(title1 & title2)
            union = len(title1 | title2)
            title_similarity = intersection / union if union > 0 else 0.0
            scores.append(('title', title_similarity, 0.3))
        
        # 计算加权平均
        if not scores:
            return 0.0
        
        total_weight = sum(weight for _, _, weight in scores)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(score * weight for _, score, weight in scores)
        return weighted_sum / total_weight
    
    def _dbscan_clustering(self, features: List[Dict], similarity_matrix: np.ndarray) -> List[List[int]]:
        """DBSCAN聚类算法简化版"""
        n = len(features)
        visited = [False] * n
        clusters = []
        
        for i in range(n):
            if visited[i]:
                continue
            
            # 寻找邻域
            neighbors = []
            for j in range(n):
                if i != j and similarity_matrix[i][j] >= self.cluster_config['similarity_threshold']:
                    neighbors.append(j)
            
            # 如果邻域足够大，形成新簇
            if len(neighbors) >= self.cluster_config['min_cluster_size'] - 1:
                cluster = [i] + neighbors
                
                # 扩展簇
                for neighbor in neighbors:
                    if not visited[neighbor]:
                        cluster.append(neighbor)
                        visited[neighbor] = True
                
                clusters.append(cluster)
                visited[i] = True
        
        return clusters
    
    def _create_cluster_from_events(self, event_indices: List[int]) -> Optional[Cluster]:
        """从事件索引创建簇"""
        if not event_indices:
            return None
        
        # 生成簇ID
        hash_input = str(sorted(event_indices)) + datetime.now().isoformat()
        cluster_id = f"CLUSTER_{hashlib.md5(hash_input.encode()).hexdigest()[:8]}"
        
        cluster = Cluster(cluster_id=cluster_id)
        
        # 添加事件到簇
        for idx in event_indices:
            if idx < len(self.unmatched_events):
                event_record = self.unmatched_events[idx]
                cluster.add_event(
                    event_record['event_data'],
                    event_record['category_result']
                )
        
        # 计算质量分数
        cluster.calculate_quality()
        
        # 设置代表事件
        if cluster.events:
            cluster.representative_event = cluster.events[0]
        
        return cluster
    
    def get_new_theme_candidates(self, min_quality: float = 0.5) -> List[Dict]:
        """
        获取新题材候选
        
        Args:
            min_quality: 最小质量阈值
        
        Returns:
            List[Dict]: 新题材候选数据
        """
        candidates = []
        
        for cluster_id, cluster in self.clusters.items():
            if cluster.quality_score >= min_quality:
                # 提取核心概念
                core_concept = cluster.extract_core_concept()
                
                # 生成题材候选
                candidate = self._create_theme_candidate_from_cluster(cluster, core_concept)
                if candidate:
                    candidates.append(candidate)
        
        return candidates
    
    def _create_theme_candidate_from_cluster(self, cluster: Cluster, core_concept: Dict) -> Dict:
        """从簇创建题材候选"""
        if not cluster.events:
            return None
        
        representative = cluster.events[0]
        event_data = representative['event_data']
        category_result = representative['category']
        
        # 生成题材代码
        timestamp = datetime.now().strftime("%y%m%d%H%M")
        hash_str = f"{cluster.cluster_id}_{timestamp}"
        hash_code = hashlib.md5(hash_str.encode()).hexdigest()[:6]
        
        # 使用核心关键词生成名称
        core_keywords = core_concept.get('core_keywords', [])
        if core_keywords:
            theme_name = f"{core_keywords[0]}概念"
        else:
            theme_name = f"聚类主题_{timestamp}"
        
        # 生成描述
        event_count = cluster.event_count
        description = f"基于{event_count}个相关事件聚类的主题，核心概念: {core_concept.get('common_theme', theme_name)}"
        
        return {
            'name': theme_name,
            'code': f"TH_CLUSTER_{hash_code}",
            'description': description,
            'level1_category': category_result.get('level1_name', '') if category_result else '',
            'level2_category': category_result.get('level2_name', '') if category_result else '',
            'level3_category': theme_name,
            'theme_type': 'concept',
            'heat_score': 55.0 + (cluster.quality_score * 10),
            'confidence_score': cluster.quality_score,
            'lifecycle_stage': 'emerging',
            'source_system': 'clustering_algorithm',
            'metadata': {
                'cluster_id': cluster.cluster_id,
                'cluster_quality': cluster.quality_score,
                'event_count': event_count,
                'core_keywords': core_keywords,
                'creation_method': 'clustering_analysis',
                'timestamp': datetime.now().isoformat()
            }
        }
    
    def get_clustering_status(self) -> Dict:
        """获取聚类状态"""
        return {
            'unmatched_events_count': len(self.unmatched_events),
            'active_clusters_count': len(self.clusters),
            'last_clustering_time': self.last_clustering_time.isoformat() if self.last_clustering_time else None,
            'config': self.cluster_config,
            'cluster_quality_summary': {
                'high_quality': len([c for c in self.clusters.values() if c.quality_score >= 0.7]),
                'medium_quality': len([c for c in self.clusters.values() if 0.4 <= c.quality_score < 0.7]),
                'low_quality': len([c for c in self.clusters.values() if c.quality_score < 0.4])
            }
        }
    
    def cleanup_old_data(self, max_age_hours: int = 72):
        """清理旧数据"""
        now = datetime.now()
        
        # 清理旧簇
        old_clusters = []
        for cluster_id, cluster in list(self.clusters.items()):
            age_hours = (now - cluster.last_updated).total_seconds() / 3600
            if age_hours > max_age_hours:
                old_clusters.append(cluster_id)
        
        for cluster_id in old_clusters:
            del self.clusters[cluster_id]
        
        # 清理未匹配事件
        self.unmatched_events = [
            event for event in self.unmatched_events
            if (now - event['added_at']).total_seconds() / 3600 <= max_age_hours
        ]
        
        if old_clusters:
            logger.info(f"🧹 清理数据: 移除 {len(old_clusters)} 个旧簇, {len(self.unmatched_events)} 个事件保留")
    
    def get_algorithm_info(self) -> Dict:
        """获取算法信息"""
        info = super().get_algorithm_info()
        info.update({
            'description': '聚类分析算法 - 从未匹配事件中智能发现新主题',
            'clustering_status': self.get_clustering_status(),
            'features': ['事件聚类', '新主题发现', '质量评估', '自动清理']
        })
        return info
    
    def get_performance_stats(self) -> Dict:
        """获取性能统计"""
        return {
            'total_events_processed': len(self.unmatched_events) + sum(c.event_count for c in self.clusters.values()),
            'current_unmatched_events': len(self.unmatched_events),
            'clusters_created': len(self.clusters),
            'clusters_formed_total': len(self.clusters),  # 总形成的簇数
            'avg_cluster_quality': np.mean([c.quality_score for c in self.clusters.values()]) if self.clusters else 0.0,
            'high_quality_clusters': len([c for c in self.clusters.values() if c.quality_score >= 0.7]),
            'last_operation_time': datetime.now().isoformat()
        }