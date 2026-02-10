# evaluate_service/core/comparison_analyzer.py
#!/usr/bin/env python3
"""
三方对比分析器
对比：优化系统 vs 基线系统 vs Ground Truth标准
"""
import json
import logging
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict
import numpy as np

logger = logging.getLogger(__name__)

class TripleComparisonAnalyzer:
    """三方对比分析器"""
    
    def __init__(self, ground_truth_path: str = None):
        """
        初始化分析器
        
        Args:
            ground_truth_path: ground truth映射文件路径
        """
        if ground_truth_path is None:
            ground_truth_path = 'evaluate_service/config/ground_truth_correct.json'
        
        self.ground_truth_path = ground_truth_path
        self.ground_truth = self._load_ground_truth()
        
        # 分析结果存储
        self.comparison_results = {}
        
        logger.info(f"TripleComparisonAnalyzer 初始化完成，{len(self.ground_truth)} 个ground truth映射")
    
    def _load_ground_truth(self) -> Dict[str, str]:
        """加载ground truth"""
        try:
            import os
            if os.path.exists(self.ground_truth_path):
                with open(self.ground_truth_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"Ground truth文件不存在: {self.ground_truth_path}")
                return {}
        except Exception as e:
            logger.error(f"加载ground truth失败: {e}")
            return {}
    
    def analyze(self, 
                optimized_results: Dict[str, str],
                baseline_results: Dict[str, str]) -> Dict[str, Any]:
        """
        执行三方对比分析
        
        Args:
            optimized_results: 优化系统结果 {event_id: theme}
            baseline_results: 基线系统结果 {event_id: theme}
            
        Returns:
            对比分析报告
        """
        # 1. 基本统计
        theme_counts = {
            'optimized': len(set(optimized_results.values())),
            'baseline': len(set(baseline_results.values())),
            'ground_truth': len(set(self.ground_truth.values()))
        }
        
        # 2. 聚类一致性准确率
        clustering_accuracy = {
            'optimized': self._calculate_clustering_accuracy(optimized_results),
            'baseline': self._calculate_clustering_accuracy(baseline_results)
        }
        
        # 3. 严重错配分析
        severe_mismatches = {
            'optimized': self._find_severe_mismatches(optimized_results),
            'baseline': self._find_severe_mismatches(baseline_results)
        }
        
        # 4. 错配案例详细分析
        mismatch_analysis = {
            'optimized': self._analyze_mismatch_cases(optimized_results),
            'baseline': self._analyze_mismatch_cases(baseline_results)
        }
        
        # 5. 题材映射关系分析
        theme_mapping_analysis = self._analyze_theme_mapping(
            optimized_results, baseline_results
        )
        
        # 6. 性能指标（处理时间）
        # 注：这里需要从测试报告中提取，暂时使用估算值
        performance_metrics = {
            'optimized': {'avg_processing_time': 1.8},  # 估计值，实际应从测试报告获取
            'baseline': {'avg_processing_time': 0.9}
        }
        
        # 7. 综合评估
        overall_assessment = self._assess_overall_performance(
            theme_counts, clustering_accuracy, severe_mismatches
        )
        
        self.comparison_results = {
            'theme_count_comparison': theme_counts,
            'clustering_accuracy_comparison': clustering_accuracy,
            'severe_mismatch_comparison': severe_mismatches,
            'detailed_mismatch_analysis': mismatch_analysis,
            'theme_mapping_analysis': theme_mapping_analysis,
            'performance_comparison': performance_metrics,
            'overall_assessment': overall_assessment,
            'improvement_summary': self._calculate_improvement_summary(
                theme_counts, clustering_accuracy, severe_mismatches
            )
        }
        
        return self.comparison_results
    
    def _calculate_clustering_accuracy(self, system_results: Dict[str, str]) -> float:
        """计算聚类一致性准确率"""
        correct_count = 0
        total_count = 0
        
        # 按ground truth主题分组
        gt_theme_to_events = defaultdict(list)
        for event_id, gt_theme in self.ground_truth.items():
            gt_theme_to_events[gt_theme].append(event_id)
        
        # 对每个ground truth主题
        for gt_theme, event_ids in gt_theme_to_events.items():
            if len(event_ids) <= 1:
                continue
            
            # 统计这些事件被系统分配到了哪些主题
            system_theme_counts = defaultdict(int)
            for event_id in event_ids:
                if event_id in system_results:
                    system_theme = system_results[event_id]
                    system_theme_counts[system_theme] += 1
            
            if system_theme_counts:
                # 找出最常被分配的系统主题
                most_common_theme = max(system_theme_counts.items(), key=lambda x: x[1])[0]
                correct_count += system_theme_counts[most_common_theme]
                total_count += len(event_ids)
        
        return correct_count / total_count if total_count > 0 else 0.0
    
    def _find_severe_mismatches(self, system_results: Dict[str, str]) -> List[Dict]:
        """查找严重错配案例"""
        severe_cases = []
        
        for event_id, system_theme in system_results.items():
            if event_id not in self.ground_truth:
                continue
            
            gt_theme = self.ground_truth[event_id]
            
            # 定义严重错配规则
            if self._is_severe_mismatch(gt_theme, system_theme):
                severe_cases.append({
                    'event_id': event_id,
                    'ground_truth_theme': gt_theme,
                    'system_assigned_theme': system_theme,
                    'error_type': 'severe_mismatch',
                    'description': f"{gt_theme} → {system_theme}"
                })
        
        return severe_cases
    
    def _is_severe_mismatch(self, gt_theme: str, system_theme: str) -> bool:
        """判断是否为严重错配"""
        # 定义严重错配规则（可根据实际情况扩展）
        severe_pairs = [
            # 深海经济不应该被分到AI/AR相关
            ("深海", ["AI", "AR", "人工智能", "智能眼镜"]),
            # AI/AR不应该被分到深海/海洋经济
            ("AI", ["深海", "海洋", "渔业"]),
            ("人工智能", ["深海", "海洋", "渔业"]),
            # 医药不应该被分到半导体
            ("医药", ["半导体", "芯片", "集成电路"]),
            # 半导体不应该被分到消费电子（除非明确相关）
            ("半导体", ["消费电子", "家电", "手机"]),
        ]
        
        gt_lower = gt_theme.lower()
        system_lower = system_theme.lower()
        
        for gt_keyword, forbidden_keywords in severe_pairs:
            if gt_keyword.lower() in gt_lower:
                for forbidden in forbidden_keywords:
                    if forbidden.lower() in system_lower:
                        return True
        
        return False
    
    def _analyze_mismatch_cases(self, system_results: Dict[str, str]) -> Dict[str, Any]:
        """详细分析错配案例"""
        all_mismatches = []
        mismatch_by_type = defaultdict(list)
        
        for event_id, system_theme in system_results.items():
            if event_id not in self.ground_truth:
                continue
            
            gt_theme = self.ground_truth[event_id]
            
            if system_theme != gt_theme:
                mismatch_type = self._classify_mismatch_type(gt_theme, system_theme)
                
                mismatch_case = {
                    'event_id': event_id,
                    'ground_truth': gt_theme,
                    'system_assigned': system_theme,
                    'mismatch_type': mismatch_type,
                    'is_severe': self._is_severe_mismatch(gt_theme, system_theme)
                }
                
                all_mismatches.append(mismatch_case)
                mismatch_by_type[mismatch_type].append(mismatch_case)
        
        return {
            'total_mismatches': len(all_mismatches),
            'severe_mismatches': len([m for m in all_mismatches if m['is_severe']]),
            'mismatch_type_distribution': {k: len(v) for k, v in mismatch_by_type.items()},
            'sample_cases': all_mismatches[:10]  # 只显示前10个示例
        }
    
    def _classify_mismatch_type(self, gt_theme: str, system_theme: str) -> str:
        """分类错配类型"""
        gt_lower = gt_theme.lower()
        system_lower = system_theme.lower()
        
        # 1. 语义相似但名称不同
        if self._are_themes_semantically_similar(gt_theme, system_theme):
            return 'semantic_similarity'
        
        # 2. 包含关系
        if gt_lower in system_lower or system_lower in gt_lower:
            return 'inclusion_relationship'
        
        # 3. 行业相关但不相同
        if self._are_industries_related(gt_theme, system_theme):
            return 'related_industry'
        
        # 4. 完全不相关
        return 'unrelated'
    
    def _are_themes_semantically_similar(self, theme1: str, theme2: str) -> bool:
        """判断两个主题是否语义相似"""
        # 简化的语义相似度判断
        synonyms = {
            "AI": ["人工智能", "AI技术", "智能技术"],
            "AR": ["增强现实", "AR技术"],
            "新能源": ["新能源汽车", "电动车", "电动汽车"],
            "半导体": ["芯片", "集成电路"],
            "医药": ["医疗", "生物医药"],
        }
        
        for main_word, word_list in synonyms.items():
            if (theme1 in word_list or main_word in theme1) and \
               (theme2 in word_list or main_word in theme2):
                return True
        
        return False
    
    def _are_industries_related(self, theme1: str, theme2: str) -> bool:
        """判断两个主题是否行业相关"""
        # 简化的行业相关性判断
        industry_groups = {
            "科技": ["AI", "人工智能", "半导体", "芯片", "5G", "物联网"],
            "新能源": ["新能源", "电动车", "锂电池", "光伏", "风电"],
            "医药": ["医药", "医疗", "生物医药", "医疗器械"],
            "消费": ["消费电子", "家电", "手机", "零售"],
        }
        
        for group_name, industries in industry_groups.items():
            theme1_in_group = any(ind in theme1 for ind in industries)
            theme2_in_group = any(ind in theme2 for ind in industries)
            
            if theme1_in_group and theme2_in_group:
                return True
        
        return False
    
    def _analyze_theme_mapping(self, optimized_results: Dict, baseline_results: Dict) -> Dict:
        """分析题材映射关系"""
        analysis = {
            'optimized_theme_distribution': defaultdict(int),
            'baseline_theme_distribution': defaultdict(int),
            'ground_truth_distribution': defaultdict(int),
            'mapping_cross_analysis': []
        }
        
        # 统计各个系统的题材分布
        for theme in optimized_results.values():
            analysis['optimized_theme_distribution'][theme] += 1
        
        for theme in baseline_results.values():
            analysis['baseline_theme_distribution'][theme] += 1
        
        for theme in self.ground_truth.values():
            analysis['ground_truth_distribution'][theme] += 1
        
        # 分析优化系统与ground truth的映射关系
        for gt_theme in set(self.ground_truth.values()):
            gt_events = [eid for eid, theme in self.ground_truth.items() if theme == gt_theme]
            
            optimized_mapping = defaultdict(int)
            baseline_mapping = defaultdict(int)
            
            for event_id in gt_events:
                if event_id in optimized_results:
                    optimized_mapping[optimized_results[event_id]] += 1
                if event_id in baseline_results:
                    baseline_mapping[baseline_results[event_id]] += 1
            
            if optimized_mapping or baseline_mapping:
                analysis['mapping_cross_analysis'].append({
                    'ground_truth_theme': gt_theme,
                    'event_count': len(gt_events),
                    'optimized_mapping': dict(optimized_mapping),
                    'baseline_mapping': dict(baseline_mapping),
                    'optimized_primary_theme': max(optimized_mapping.items(), key=lambda x: x[1])[0] if optimized_mapping else None,
                    'baseline_primary_theme': max(baseline_mapping.items(), key=lambda x: x[1])[0] if baseline_mapping else None
                })
        
        return analysis
    
    def _assess_overall_performance(self, theme_counts, clustering_accuracy, severe_mismatches):
        """综合评估性能"""
        assessments = []
        
        # 1. 题材数量评估
        gt_count = theme_counts['ground_truth']
        optimized_count = theme_counts['optimized']
        baseline_count = theme_counts['baseline']
        
        optimized_diff = abs(optimized_count - gt_count)
        baseline_diff = abs(baseline_count - gt_count)
        
        if optimized_diff <= 3:
            assessments.append({
                'dimension': 'theme_count',
                'status': '达标',
                'score': max(0, 1 - optimized_diff/gt_count),
                'comment': f'优化后题材数量({optimized_count})接近目标({gt_count})'
            })
        else:
            assessments.append({
                'dimension': 'theme_count',
                'status': '未达标',
                'score': max(0, 1 - optimized_diff/gt_count),
                'comment': f'优化后题材数量({optimized_count})偏离目标较多'
            })
        
        # 2. 聚类准确率评估
        optimized_accuracy = clustering_accuracy['optimized']
        baseline_accuracy = clustering_accuracy['baseline']
        
        if optimized_accuracy >= 0.85:
            assessments.append({
                'dimension': 'clustering_accuracy',
                'status': '达标',
                'score': optimized_accuracy,
                'comment': f'准确率({optimized_accuracy:.1%})达到85%目标'
            })
        else:
            assessments.append({
                'dimension': 'clustering_accuracy',
                'status': '未达标',
                'score': optimized_accuracy,
                'comment': f'准确率({optimized_accuracy:.1%})未达85%目标'
            })
        
        # 3. 严重错配评估
        optimized_severe = len(severe_mismatches['optimized'])
        baseline_severe = len(severe_mismatches['baseline'])
        
        if optimized_severe <= 1:
            assessments.append({
                'dimension': 'severe_mismatches',
                'status': '达标',
                'score': max(0, 1 - optimized_severe/7),  # 相对于基线7例
                'comment': f'严重错配仅{optimized_severe}例，问题得到控制'
            })
        else:
            assessments.append({
                'dimension': 'severe_mismatches',
                'status': '未达标',
                'score': max(0, 1 - optimized_severe/7),
                'comment': f'仍有{optimized_severe}例严重错配'
            })
        
        # 4. 总体评估
        all_domains_passed = all(
            a['status'] == '达标' 
            for a in assessments 
            if a['dimension'] in ['theme_count', 'clustering_accuracy', 'severe_mismatches']
        )
        
        return {
            'domain_assessments': assessments,
            'overall_status': '通过' if all_domains_passed else '需要改进',
            'recommendation': '可以推进至真实数据库连接' if all_domains_passed else '需要进一步优化算法'
        }
    
    def _calculate_improvement_summary(self, theme_counts, clustering_accuracy, severe_mismatches):
        """计算改进总结"""
        optimized_accuracy = clustering_accuracy['optimized']
        baseline_accuracy = clustering_accuracy['baseline']
        
        optimized_severe = len(severe_mismatches['optimized'])
        baseline_severe = len(severe_mismatches['baseline'])
        
        return {
            'accuracy_improvement': {
                'absolute': optimized_accuracy - baseline_accuracy,
                'percentage': (optimized_accuracy - baseline_accuracy) / baseline_accuracy * 100 if baseline_accuracy > 0 else 0
            },
            'severe_mismatch_reduction': {
                'absolute': baseline_severe - optimized_severe,
                'percentage': (baseline_severe - optimized_severe) / baseline_severe * 100 if baseline_severe > 0 else 0
            },
            'theme_count_convergence': {
                'optimized_diff': abs(theme_counts['optimized'] - theme_counts['ground_truth']),
                'baseline_diff': abs(theme_counts['baseline'] - theme_counts['ground_truth']),
                'improvement': abs(theme_counts['baseline'] - theme_counts['ground_truth']) - abs(theme_counts['optimized'] - theme_counts['ground_truth'])
            }
        }
    
    def generate_html_report(self, comparison_results: Dict, output_path: str):
        """生成HTML格式的三方对比报告"""
        html_content = self._build_html_content(comparison_results)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML报告已生成: {output_path}")
    
    def _build_html_content(self, results: Dict) -> str:
        """构建HTML内容"""
        # 这里提供HTML模板，实际实现中需要更完整
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>三方对比评估报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f5f5f5; }}
            </style>
        </head>
        <body>
            <h1>📊 三方对比评估报告</h1>
            <h2>核心指标对比表</h2>
            <table>
                <tr>
                    <th>评估维度</th>
                    <th>优化后系统</th>
                    <th>基线系统</th>
                    <th>久赢恒丰标准</th>
                    <th>结论与洞见</th>
                </tr>
                <tr>
                    <td>题材数量</td>
                    <td>{results['theme_count_comparison']['optimized']}个</td>
                    <td>{results['theme_count_comparison']['baseline']}个</td>
                    <td>{results['theme_count_comparison']['ground_truth']}个</td>
                    <td>{self._generate_theme_count_insight(results)}</td>
                </tr>
                <tr>
                    <td>聚类一致性准确率</td>
                    <td>{results['clustering_accuracy_comparison']['optimized']:.1%}</td>
                    <td>{results['clustering_accuracy_comparison']['baseline']:.1%}</td>
                    <td>100% (参考标准)</td>
                    <td>{self._generate_accuracy_insight(results)}</td>
                </tr>
                <tr>
                    <td>严重错配数</td>
                    <td>{len(results['severe_mismatch_comparison']['optimized'])}例</td>
                    <td>{len(results['severe_mismatch_comparison']['baseline'])}例</td>
                    <td>0例</td>
                    <td>{self._generate_mismatch_insight(results)}</td>
                </tr>
            </table>
        </body>
        </html>
        """
    
    def _generate_theme_count_insight(self, results):
        """生成题材数量洞见"""
        optimized = results['theme_count_comparison']['optimized']
        baseline = results['theme_count_comparison']['baseline']
        gt = results['theme_count_comparison']['ground_truth']
        
        if abs(optimized - gt) <= 2:
            return f"✅ 优化后数量({optimized})显著收敛，接近目标({gt})"
        else:
            return f"⚠️  数量({optimized})仍偏离目标({gt})"
    
    def _generate_accuracy_insight(self, results):
        """生成准确率洞见"""
        optimized = results['clustering_accuracy_comparison']['optimized']
        baseline = results['clustering_accuracy_comparison']['baseline']
        improvement = results['improvement_summary']['accuracy_improvement']['percentage']
        
        if optimized >= 0.85:
            return f"✅ 准确率提升{improvement:.1f}%，达到目标"
        else:
            return f"⚠️  准确率{optimized:.1%}未达85%目标"
    
    def _generate_mismatch_insight(self, results):
        """生成错配洞见"""
        optimized = len(results['severe_mismatch_comparison']['optimized'])
        baseline = len(results['severe_mismatch_comparison']['baseline'])
        reduction = results['improvement_summary']['severe_mismatch_reduction']['percentage']
        
        if optimized <= 1:
            return f"✅ 错配减少{reduction:.1f}%，问题得到有效遏制"
        else:
            return f"⚠️  仍有{optimized}例严重错配"