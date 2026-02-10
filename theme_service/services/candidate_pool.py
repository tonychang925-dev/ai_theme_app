"""
候选池管理 - 存储和管理未匹配的事件
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import time


@dataclass
class Candidate:
    """候选事件"""
    event_id: str
    event_title: str
    event_type: str
    potential_themes: List[Dict]
    confidence: float
    keywords: List[str]
    create_time: datetime
    update_time: datetime
    match_score: float = 0.0
    processing_path: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['create_time'] = self.create_time.isoformat()
        data['update_time'] = self.update_time.isoformat()
        return data
    
    def is_expired(self, ttl_hours: int) -> bool:
        """检查是否过期"""
        return datetime.now() - self.create_time > timedelta(hours=ttl_hours)
    
    def update(self, potential_themes: List[Dict], confidence: float = None):
        """更新候选信息"""
        self.potential_themes = potential_themes
        if confidence is not None:
            self.confidence = confidence
        self.update_time = datetime.now()


class CandidatePool:
    """候选池管理器"""
    
    def __init__(self, max_size: int = 100, ttl_hours: int = 24):
        """
        初始化候选池
        
        Args:
            max_size: 最大容量
            ttl_hours: 生存时间（小时）
        """
        self.max_size = max_size
        self.ttl_hours = ttl_hours
        self.candidates: Dict[str, Candidate] = {}  # event_id -> Candidate
        self.last_cleanup = datetime.now()
        
        print(f"🏊 初始化候选池: 容量={max_size}, TTL={ttl_hours}小时")
    
    def add_candidate(self, event_data: Dict, potential_themes: List[Dict], 
                     match_score: float = 0.0, processing_path: str = "") -> bool:
        """
        添加候选到池中
        
        Args:
            event_data: 事件数据
            potential_themes: 潜在题材列表
            match_score: 匹配分数
            processing_path: 处理路径
        
        Returns:
            是否添加成功
        """
        event_id = event_data.get('event_id')
        if not event_id:
            print("⚠️  事件ID为空，无法添加候选")
            return False
        
        # 自动清理过期候选
        self._auto_cleanup()
        
        # 如果池已满，移除置信度最低的候选
        if len(self.candidates) >= self.max_size:
            removed = self._remove_lowest_confidence()
            if removed:
                print(f"   🗑️  移除低置信度候选: {removed}")
        
        # 计算平均置信度
        avg_confidence = 0.0
        if potential_themes:
            confidences = [t.get('confidence', 0.0) for t in potential_themes]
            avg_confidence = sum(confidences) / len(confidences)
        
        # 提取关键词
        keywords = event_data.get('keywords', [])
        if not keywords:
            # 从标题中提取简单关键词
            title = event_data.get('title', '')
            if title:
                keywords = [word for word in title.split() if len(word) >= 2][:5]
        
        # 创建候选
        candidate = Candidate(
            event_id=event_id,
            event_title=event_data.get('title', '')[:100],
            event_type=event_data.get('event_type', 'normal'),
            potential_themes=potential_themes[:5],  # 最多保存5个潜在题材
            confidence=avg_confidence,
            keywords=keywords[:10],  # 最多10个关键词
            match_score=match_score,
            processing_path=processing_path,
            create_time=datetime.now(),
            update_time=datetime.now(),
            metadata={
                'source': event_data.get('source', ''),
                'content_length': len(event_data.get('content', '')),
                'added_reason': 'no_match' if not potential_themes else 'low_confidence'
            }
        )
        
        # 添加到池中
        self.candidates[event_id] = candidate
        
        print(f"➕ 添加候选: {event_id[:20]}... "
              f"(置信度: {avg_confidence:.3f}, 潜在题材: {len(potential_themes)})")
        
        return True
    
    def get_candidate(self, event_id: str) -> Optional[Dict]:
        """
        获取候选
        
        Args:
            event_id: 事件ID
        
        Returns:
            候选数据（如果存在且未过期）
        """
        if event_id not in self.candidates:
            return None
        
        candidate = self.candidates[event_id]
        
        # 检查是否过期
        if candidate.is_expired(self.ttl_hours):
            self.remove_candidate(event_id)
            return None
        
        # 更新最后访问时间
        candidate.update_time = datetime.now()
        
        return candidate.to_dict()
    
    def get_all_candidates(self, limit: int = 20, sort_by: str = "confidence") -> List[Dict]:
        """
        获取所有候选
        
        Args:
            limit: 数量限制
            sort_by: 排序字段 ('confidence', 'create_time', 'match_score')
        
        Returns:
            候选列表
        """
        self._cleanup_expired()
        
        candidates = list(self.candidates.values())
        
        # 排序
        if sort_by == "confidence":
            candidates.sort(key=lambda x: x.confidence, reverse=True)
        elif sort_by == "create_time":
            candidates.sort(key=lambda x: x.create_time, reverse=True)
        elif sort_by == "match_score":
            candidates.sort(key=lambda x: x.match_score, reverse=True)
        
        # 转换为字典
        result = [c.to_dict() for c in candidates[:limit]]
        
        return result
    
    def remove_candidate(self, event_id: str) -> bool:
        """
        移除候选
        
        Args:
            event_id: 事件ID
        
        Returns:
            是否移除成功
        """
        if event_id in self.candidates:
            del self.candidates[event_id]
            print(f"➖ 移除候选: {event_id[:20]}...")
            return True
        return False
    
    def update_candidate(self, event_id: str, potential_themes: List[Dict], 
                        confidence: float = None) -> bool:
        """
        更新候选
        
        Args:
            event_id: 事件ID
            potential_themes: 新的潜在题材列表
            confidence: 新的置信度（可选）
        
        Returns:
            是否更新成功
        """
        if event_id not in self.candidates:
            return False
        
        candidate = self.candidates[event_id]
        candidate.update(potential_themes, confidence)
        
        print(f"🔄 更新候选: {event_id[:20]}... (新置信度: {candidate.confidence:.3f})")
        
        return True
    
    def clear(self):
        """清空候选池"""
        removed_count = len(self.candidates)
        self.candidates.clear()
        print(f"🗑️  清空候选池: 移除 {removed_count} 个候选")
    
    def get_size(self) -> int:
        """获取当前大小"""
        self._cleanup_expired()
        return len(self.candidates)
    
    def is_full(self) -> bool:
        """检查是否已满"""
        return len(self.candidates) >= self.max_size
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        self._cleanup_expired()
        
        if not self.candidates:
            return {
                'total': 0,
                'avg_confidence': 0.0,
                'type_distribution': {},
                'status': 'empty'
            }
        
        # 计算统计信息
        total = len(self.candidates)
        confidences = [c.confidence for c in self.candidates.values()]
        avg_confidence = sum(confidences) / total if total > 0 else 0.0
        
        # 按类型统计
        type_distribution = {}
        for candidate in self.candidates.values():
            event_type = candidate.event_type
            type_distribution[event_type] = type_distribution.get(event_type, 0) + 1
        
        # 按置信度分级统计
        confidence_distribution = {
            'high': 0,    # >= 0.7
            'medium': 0,  # >= 0.4
            'low': 0      # < 0.4
        }
        
        for confidence in confidences:
            if confidence >= 0.7:
                confidence_distribution['high'] += 1
            elif confidence >= 0.4:
                confidence_distribution['medium'] += 1
            else:
                confidence_distribution['low'] += 1
        
        return {
            'total': total,
            'avg_confidence': round(avg_confidence, 3),
            'type_distribution': type_distribution,
            'confidence_distribution': confidence_distribution,
            'max_size': self.max_size,
            'ttl_hours': self.ttl_hours,
            'full_percentage': round(total / self.max_size * 100, 1),
            'status': 'healthy'
        }
    
    def find_similar_candidates(self, keywords: List[str], 
                               min_similarity: float = 0.3) -> List[Dict]:
        """
        查找相似候选
        
        Args:
            keywords: 关键词列表
            min_similarity: 最小相似度阈值
        
        Returns:
            相似候选列表
        """
        self._cleanup_expired()
        
        if not keywords:
            return []
        
        keyword_set = set(keywords)
        similar_candidates = []
        
        for candidate in self.candidates.values():
            # 计算关键词相似度
            candidate_keywords = set(candidate.keywords)
            
            if not candidate_keywords:
                continue
            
            intersection = len(keyword_set & candidate_keywords)
            union = len(keyword_set | candidate_keywords)
            
            similarity = intersection / union if union > 0 else 0.0
            
            if similarity >= min_similarity:
                candidate_data = candidate.to_dict()
                candidate_data['similarity_score'] = round(similarity, 3)
                similar_candidates.append(candidate_data)
        
        # 按相似度排序
        similar_candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return similar_candidates[:10]  # 最多返回10个
    
    def cluster_candidates(self, min_cluster_size: int = 3) -> List[Dict]:
        """
        聚类候选（简单的基于关键词的聚类）
        
        Args:
            min_cluster_size: 最小簇大小
        
        Returns:
            聚类结果
        """
        self._cleanup_expired()
        
        if len(self.candidates) < min_cluster_size:
            return []
        
        # 简单的聚类实现：基于共同关键词
        clusters = []
        processed = set()
        
        candidates = list(self.candidates.values())
        
        for i, candidate in enumerate(candidates):
            if candidate.event_id in processed:
                continue
            
            # 找到与当前候选相似的候选
            cluster_members = [candidate]
            cluster_keywords = set(candidate.keywords)
            
            for j, other_candidate in enumerate(candidates[i+1:], i+1):
                if other_candidate.event_id in processed:
                    continue
                
                # 计算关键词相似度
                other_keywords = set(other_candidate.keywords)
                if not other_keywords:
                    continue
                
                intersection = len(cluster_keywords & other_keywords)
                min_len = min(len(cluster_keywords), len(other_keywords))
                
                if min_len > 0 and intersection / min_len >= 0.5:  # 50%相似度
                    cluster_members.append(other_candidate)
                    processed.add(other_candidate.event_id)
                    # 合并关键词
                    cluster_keywords.update(other_keywords)
            
            # 如果簇足够大，添加到结果
            if len(cluster_members) >= min_cluster_size:
                clusters.append({
                    'cluster_id': f"cluster_{len(clusters)+1}",
                    'size': len(cluster_members),
                    'keywords': list(cluster_keywords)[:10],
                    'avg_confidence': sum(m.confidence for m in cluster_members) / len(cluster_members),
                    'members': [m.event_id for m in cluster_members],
                    'representative_title': cluster_members[0].event_title
                })
            
            processed.add(candidate.event_id)
        
        return clusters
    
    def _cleanup_expired(self):
        """清理过期候选"""
        now = datetime.now()
        expired = []
        
        for event_id, candidate in self.candidates.items():
            if candidate.is_expired(self.ttl_hours):
                expired.append(event_id)
        
        for event_id in expired:
            del self.candidates[event_id]
        
        if expired:
            print(f"🧹 清理 {len(expired)} 个过期候选")
            self.last_cleanup = now
    
    def _auto_cleanup(self):
        """自动清理（如果距离上次清理超过1小时）"""
        if datetime.now() - self.last_cleanup > timedelta(hours=1):
            self._cleanup_expired()
    
    def _remove_lowest_confidence(self) -> Optional[str]:
        """移除置信度最低的候选"""
        if not self.candidates:
            return None
        
        # 找到置信度最低的候选
        lowest_id = min(self.candidates.items(), key=lambda x: x[1].confidence)[0]
        
        del self.candidates[lowest_id]
        return lowest_id
    
    def to_dict(self) -> Dict:
        """转换为字典表示"""
        stats = self.get_stats()
        
        return {
            'pool_info': stats,
            'candidates_count': self.get_size(),
            'max_capacity': self.max_size,
            'ttl_hours': self.ttl_hours,
            'last_cleanup': self.last_cleanup.isoformat()
        }


# 测试函数
def test_candidate_pool():
    """测试候选池"""
    print("\n" + "="*60)
    print("🧪 测试候选池")
    print("="*60)
    
    # 创建候选池
    pool = CandidatePool(max_size=5, ttl_hours=1)  # 小容量用于测试
    
    # 1. 添加候选
    test_events = [
        {
            'event_id': 'event_001',
            'title': '半导体芯片技术突破',
            'event_type': 'major',
            'keywords': ['芯片', '半导体', '技术'],
            'content': '7纳米芯片技术实现突破...'
        },
        {
            'event_id': 'event_002',
            'title': '人工智能医疗应用',
            'event_type': 'normal',
            'keywords': ['AI', '医疗', '人工智能'],
            'content': 'AI在医疗诊断中的应用...'
        },
        {
            'event_id': 'event_003',
            'title': '新能源电池发展',
            'event_type': 'normal',
            'keywords': ['新能源', '电池', '锂电池'],
            'content': '锂电池技术不断进步...'
        }
    ]
    
    test_themes = [
        {'theme_name': '半导体芯片', 'confidence': 0.6},
        {'theme_name': 'AI医疗', 'confidence': 0.5}
    ]
    
    print("1. 添加候选:")
    for event in test_events:
        pool.add_candidate(event, test_themes[:2], match_score=0.5)
    
    print(f"   当前大小: {pool.get_size()}")
    
    # 2. 获取候选
    print("\n2. 获取候选:")
    candidate = pool.get_candidate('event_001')
    if candidate:
        print(f"   找到候选: {candidate['event_title']}")
        print(f"   置信度: {candidate['confidence']}")
    
    # 3. 获取所有候选
    print("\n3. 获取所有候选:")
    all_candidates = pool.get_all_candidates()
    print(f"   总数: {len(all_candidates)}")
    for cand in all_candidates:
        print(f"   - {cand['event_id']}: {cand['event_title'][:30]}...")
    
    # 4. 统计信息
    print("\n4. 统计信息:")
    stats = pool.get_stats()
    print(f"   总数: {stats['total']}")
    print(f"   平均置信度: {stats['avg_confidence']}")
    print(f"   类型分布: {stats['type_distribution']}")
    
    # 5. 查找相似候选
    print("\n5. 查找相似候选:")
    similar = pool.find_similar_candidates(['芯片', '技术'])
    print(f"   找到 {len(similar)} 个相似候选")
    
    # 6. 测试容量限制
    print("\n6. 测试容量限制:")
    for i in range(4, 8):
        event = {
            'event_id': f'event_00{i}',
            'title': f'测试事件{i}',
            'event_type': 'normal',
            'keywords': ['测试'],
            'content': '测试内容'
        }
        added = pool.add_candidate(event, test_themes)
        print(f"   添加事件{i}: {'成功' if added else '失败'}, 当前大小: {pool.get_size()}")
    
    # 7. 清理测试
    print("\n7. 清理测试:")
    pool.clear()
    print(f"   清理后大小: {pool.get_size()}")
    
    print("\n✅ 候选池测试完成")


if __name__ == "__main__":
    test_candidate_pool()