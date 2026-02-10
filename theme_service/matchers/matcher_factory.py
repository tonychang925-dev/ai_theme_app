"""
算法工厂 - 负责创建和管理匹配算法
"""
from typing import Dict, Any
from .base_matcher import BaseMatcher
from .keyword_matcher import KeywordMatcher
from .semantic_matcher import TransformerSemanticMatcher
from .clustering_matcher import ClusteringMatcher

class MatcherFactory:
    """匹配算法工厂"""
    
    @staticmethod
    def create_matcher(matcher_type: str, config: Dict = None) -> BaseMatcher:
        """
        创建匹配算法实例
        
        Args:
            matcher_type: 算法类型 ('keyword', 'semantic', 'clustering')
            config: 算法配置
        
        Returns:
            算法实例
        """
        if matcher_type == 'keyword':
            return KeywordMatcher(config)
        elif matcher_type == 'transformer':
            return TransformerSemanticMatcher(config)
        elif matcher_type == 'clustering':
            return ClusteringMatcher(config)
        else:
            raise ValueError(f"未知的算法类型: {matcher_type}")
    
    @staticmethod
    def create_matchers_for_system() -> Dict[str, BaseMatcher]:
        """
        创建系统所需的算法实例
        
        Returns:
            {'major': MajorMatcher, 'normal': NormalMatcher, 'clustering': ClusteringMatcher}
        """
        # Major事件使用高精度配置
        major_config = {
            'match_threshold': 0.8,
            'max_results': 10,
            'min_keyword_matches': 3,
            'enable_analyst_logic': True,
            'classification_first': True
        }
        
        # Normal事件使用中精度配置
        normal_config = {
            'match_threshold': 0.7,
            'max_results': 15,
            'min_keyword_matches': 2,
            'enable_analyst_logic': False,
            'classification_first': False
        }
        
        # 聚类分析配置
        clustering_config = {
            'min_cluster_size': 3,
            'similarity_threshold': 0.6,
            'max_clusters': 20,
            'max_unmatched_events': 100,
            'clustering_interval_minutes': 30,
            'min_quality_threshold': 0.4
        }
        
        return {
            'major': MatcherFactory.create_matcher('transformer', major_config),
            'normal': MatcherFactory.create_matcher('transformer', normal_config),
            'clustering': MatcherFactory.create_matcher('clustering', clustering_config)
        }