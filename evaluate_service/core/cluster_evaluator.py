# evaluate_service/core/cluster_evaluator.py
#!/usr/bin/env python3
"""
聚类评估器 - 评估AI聚类效果的正确性
不再要求主题名与ground truth相同，而是评估聚类质量
"""
import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class ClusterEvaluator:
    """
    聚类评估器
    评估AI将事件聚类到主题的能力
    """
    
    def __init__(self, ground_truth_path: str = None):
        """
        初始化评估器
        
        Args:
            ground_truth_path: 地面真值映射文件路径
        """
        if ground_truth_path is None:
            ground_truth_path = 'evaluate_service/config/ground_truth_correct.json'
        
        self.ground_truth_path = ground_truth_path
        self.ground_truth = self._load_ground_truth()
        self.evaluation_results = []
        
        # 聚类分析数据结构
        self.cluster_analysis = {
            'theme_clusters': defaultdict(list),  # theme -> [event_ids]
            'event_to_theme': {},  # event_id -> theme
            'ai_clusters': defaultdict(list),  # ai_theme -> [event_ids]
            'event_to_ai_theme': {}  # event_id -> ai_theme
        }
        
        logger.info(f"ClusterEvaluator 初始化完成，加载了 {len(self.ground_truth)} 条映射")
    
    def _load_ground_truth(self) -> Dict[str, str]:
        """加载地面真值映射"""
        try:
            import os
            if os.path.exists(self.ground_truth_path):
                with open(self.ground_truth_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"地面真值文件不存在: {self.ground_truth_path}")
                return {}
        except Exception as e:
            logger.error(f"加载地面真值失败: {e}")
            return {}
    
    def record_decision(self, 
                       event_id: str, 
                       ai_theme: str,
                       ground_truth_theme: str = None) -> Dict[str, Any]:
        """
        记录AI决策结果
        
        Args:
            event_id: 事件ID
            ai_theme: AI分配的主题
            ground_truth_theme: 地面真值主题（可选）
            
        Returns:
            记录结果
        """
        if ground_truth_theme is None:
            ground_truth_theme = self.ground_truth.get(event_id, "未知")
        
        # 记录到聚类分析
        self.cluster_analysis['theme_clusters'][ground_truth_theme].append(event_id)
        self.cluster_analysis['event_to_theme'][event_id] = ground_truth_theme
        self.cluster_analysis['ai_clusters'][ai_theme].append(event_id)
        self.cluster_analysis['event_to_ai_theme'][event_id] = ai_theme
        
        # 构建记录
        record = {
            'event_id': event_id,
            'ground_truth_theme': ground_truth_theme,
            'ai_theme': ai_theme,
            'recorded_at': datetime.now().isoformat()
        }
        
        self.evaluation_results.append(record)
        logger.debug(f"记录决策: {event_id} -> {ai_theme} (ground: {ground_truth_theme})")
        
        return record
    
    def calculate_clustering_metrics(self) -> Dict[str, Any]:
        """
        计算聚类评估指标
        
        Returns:
            聚类评估指标
        """
        # 1. 纯度 (Purity): 每个聚类中最频繁主题的比例
        purity_scores = []
        
        for ai_theme, event_ids in self.cluster_analysis['ai_clusters'].items():
            if not event_ids:
                continue
            
            # 统计该聚类中各个ground truth主题的数量
            theme_counts = defaultdict(int)
            for event_id in event_ids:
                gt_theme = self.cluster_analysis['event_to_theme'].get(event_id)
                if gt_theme:
                    theme_counts[gt_theme] += 1
            
            if theme_counts:
                max_count = max(theme_counts.values())
                purity = max_count / len(event_ids)
                purity_scores.append(purity)
        
        avg_purity = sum(purity_scores) / len(purity_scores) if purity_scores else 0
        
        # 2. 聚类数量
        cluster_count = len(self.cluster_analysis['ai_clusters'])
        ground_truth_cluster_count = len(self.cluster_analysis['theme_clusters'])
        
        # 3. 平均聚类大小
        avg_cluster_size = 0
        if self.cluster_analysis['ai_clusters']:
            cluster_sizes = [len(events) for events in self.cluster_analysis['ai_clusters'].values()]
            avg_cluster_size = sum(cluster_sizes) / len(cluster_sizes)
        
        # 4. 主题一致性 (同一ground truth主题的事件是否被分到同一AI主题)
        consistency_scores = []
        
        for gt_theme, event_ids in self.cluster_analysis['theme_clusters'].items():
            if len(event_ids) <= 1:
                continue
            
            # 统计这些事件被分到了哪些AI主题
            ai_theme_counts = defaultdict(int)
            for event_id in event_ids:
                ai_theme = self.cluster_analysis['event_to_ai_theme'].get(event_id)
                if ai_theme:
                    ai_theme_counts[ai_theme] += 1
            
            if ai_theme_counts:
                # 计算最大一致性（最多事件被分到的AI主题的比例）
                max_count = max(ai_theme_counts.values())
                consistency = max_count / len(event_ids)
                consistency_scores.append(consistency)
        
        avg_consistency = sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0
        
        # 5. 主题分离度 (不同ground truth主题的事件是否被错误合并)
        separation_errors = 0
        total_pairs = 0
        
        for ai_theme, event_ids in self.cluster_analysis['ai_clusters'].items():
            if len(event_ids) <= 1:
                continue
            
            # 检查该聚类中是否有不同ground truth主题的事件
            gt_themes_in_cluster = set()
            for event_id in event_ids:
                gt_theme = self.cluster_analysis['event_to_theme'].get(event_id)
                if gt_theme:
                    gt_themes_in_cluster.add(gt_theme)
            
            # 如果有多个ground truth主题，计算错误率
            if len(gt_themes_in_cluster) > 1:
                # 统计所有事件对
                for i in range(len(event_ids)):
                    for j in range(i + 1, len(event_ids)):
                        total_pairs += 1
                        gt1 = self.cluster_analysis['event_to_theme'].get(event_ids[i])
                        gt2 = self.cluster_analysis['event_to_theme'].get(event_ids[j])
                        if gt1 != gt2:
                            separation_errors += 1
        
        separation_error_rate = separation_errors / total_pairs if total_pairs > 0 else 0
        
        return {
            'clustering_quality': {
                'purity': round(avg_purity, 4),  # 聚类纯度 (越高越好)
                'consistency': round(avg_consistency, 4),  # 主题一致性 (越高越好)
                'separation_error_rate': round(separation_error_rate, 4),  # 分离错误率 (越低越好)
            },
            'cluster_statistics': {
                'ai_cluster_count': cluster_count,  # AI创建的聚类数
                'ground_truth_cluster_count': ground_truth_cluster_count,  # 地面真值聚类数
                'avg_cluster_size': round(avg_cluster_size, 2),  # 平均聚类大小
                'total_events': len(self.cluster_analysis['event_to_theme']),
            },
            'target_metrics': {
                'purity_target': 0.85,  # 目标纯度
                'consistency_target': 0.80,  # 目标一致性
                'separation_error_target': 0.10,  # 目标分离错误率
                'meets_purity_target': avg_purity >= 0.85,
                'meets_consistency_target': avg_consistency >= 0.80,
                'meets_separation_target': separation_error_rate <= 0.10,
            }
        }
    
    def analyze_cluster_distribution(self) -> Dict[str, Any]:
        """分析聚类分布"""
        analysis = {
            'ground_truth_distribution': {},
            'ai_cluster_distribution': {},
            'mapping_analysis': []
        }
        
        # 地面真值分布
        for theme, event_ids in self.cluster_analysis['theme_clusters'].items():
            analysis['ground_truth_distribution'][theme] = {
                'event_count': len(event_ids),
                'event_ids': event_ids[:10]  # 只显示前10个
            }
        
        # AI聚类分布
        for ai_theme, event_ids in self.cluster_analysis['ai_clusters'].items():
            # 分析该聚类中的ground truth主题分布
            gt_distribution = defaultdict(int)
            for event_id in event_ids:
                gt_theme = self.cluster_analysis['event_to_theme'].get(event_id)
                if gt_theme:
                    gt_distribution[gt_theme] += 1
            
            analysis['ai_cluster_distribution'][ai_theme] = {
                'event_count': len(event_ids),
                'ground_truth_distribution': dict(gt_distribution),
                'dominant_theme': max(gt_distribution.items(), key=lambda x: x[1])[0] if gt_distribution else None
            }
        
        # 映射分析：每个ground truth主题被映射到了哪些AI主题
        for gt_theme in self.cluster_analysis['theme_clusters'].keys():
            ai_theme_counts = defaultdict(int)
            for event_id in self.cluster_analysis['theme_clusters'][gt_theme]:
                ai_theme = self.cluster_analysis['event_to_ai_theme'].get(event_id)
                if ai_theme:
                    ai_theme_counts[ai_theme] += 1
            
            if ai_theme_counts:
                analysis['mapping_analysis'].append({
                    'ground_truth_theme': gt_theme,
                    'mapped_to_ai_themes': dict(ai_theme_counts),
                    'primary_ai_theme': max(ai_theme_counts.items(), key=lambda x: x[1])[0]
                })
        
        return analysis
    
    def generate_report(self, output_path: str = None) -> Dict[str, Any]:
        """生成评估报告"""
        metrics = self.calculate_clustering_metrics()
        cluster_analysis = self.analyze_cluster_distribution()
        
        report = {
            'evaluation_summary': {
                'evaluation_time': datetime.now().isoformat(),
                'total_events_evaluated': len(self.evaluation_results),
                'ground_truth_source': self.ground_truth_path
            },
            'clustering_metrics': metrics,
            'cluster_analysis': cluster_analysis,
            'detailed_results': self.evaluation_results[:100],  # 只保存前100个详细结果
            'recommendations': self._generate_recommendations(metrics)
        }
        
        # 保存报告
        if output_path:
            import os
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"聚类评估报告已保存到: {output_path}")
        
        return report
    
    def _generate_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        clustering_quality = metrics.get('clustering_quality', {})
        target_metrics = metrics.get('target_metrics', {})
        
        purity = clustering_quality.get('purity', 0)
        consistency = clustering_quality.get('consistency', 0)
        separation_error = clustering_quality.get('separation_error_rate', 0)
        
        if purity < target_metrics.get('purity_target', 0.85):
            recommendations.append(f"聚类纯度({purity:.2f})低于目标值(0.85)，需要改进AI的主题归并准确性")
        
        if consistency < target_metrics.get('consistency_target', 0.80):
            recommendations.append(f"主题一致性({consistency:.2f})低于目标值(0.80)，相同主题的事件应更一致地聚类")
        
        if separation_error > target_metrics.get('separation_error_target', 0.10):
            recommendations.append(f"分离错误率({separation_error:.2f})高于目标值(0.10)，不同主题的事件被错误合并")
        
        cluster_stats = metrics.get('cluster_statistics', {})
        ai_cluster_count = cluster_stats.get('ai_cluster_count', 0)
        gt_cluster_count = cluster_stats.get('ground_truth_cluster_count', 0)
        
        if ai_cluster_count > gt_cluster_count * 1.5:
            recommendations.append(f"AI创建了过多聚类({ai_cluster_count} vs 地面真值{gt_cluster_count})，可能存在过度细分问题")
        elif ai_cluster_count < gt_cluster_count * 0.5:
            recommendations.append(f"AI创建了过少聚类({ai_cluster_count} vs 地面真值{gt_cluster_count})，可能存在过度合并问题")
        
        return recommendations
    
    def clear(self):
        """清除评估数据"""
        self.evaluation_results.clear()
        self.cluster_analysis['theme_clusters'].clear()
        self.cluster_analysis['event_to_theme'].clear()
        self.cluster_analysis['ai_clusters'].clear()
        self.cluster_analysis['event_to_ai_theme'].clear()
        logger.info("聚类评估器数据已清除")