"""
聚类评估器 - 基于evaluate_service架构的专业评估模块
评估AI主题发现引擎的事件归集能力
"""
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from collections import defaultdict, Counter
import statistics

logger = logging.getLogger(__name__)

@dataclass
class ClusteringMetrics:
    """聚类评估指标"""
    clustering_precision: float  # 聚类精度
    collection_completeness: float  # 归集完整性
    theme_purity: float  # 主题纯度
    theme_separation: float  # 主题分离度
    event_coverage: float  # 事件覆盖率
    overall_score: float  # 综合得分
    
@dataclass 
class ThemeClusteringResult:
    """主题聚类结果"""
    theme: str
    event_count: int
    primary_ai_theme: str
    clustering_consistency: float
    ai_theme_distribution: Dict[str, int]
    event_ids: List[str]

class ClusteringEvaluator:
    """聚类评估器 - 产品级实现"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化聚类评估器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认配置
        """
        self.config = self._load_config(config_path)
        self.results = []
        self.theme_ground_truth = {}  # theme -> set(event_ids)
        self.event_true_themes = {}  # event_id -> true_themes
        
        logger.info("ClusteringEvaluator 初始化完成")
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "evaluation": {
                "name": "主题聚类能力评估",
                "focus": "事件归集能力而非名称相似度",
                "version": "1.0"
            },
            "metrics": {
                "weights": {
                    "clustering_precision": 0.30,
                    "collection_completeness": 0.25, 
                    "theme_purity": 0.20,
                    "theme_separation": 0.15,
                    "event_coverage": 0.10
                },
                "thresholds": {
                    "excellent": 0.85,
                    "good": 0.70,
                    "acceptable": 0.60,
                    "needs_improvement": 0.50
                }
            },
            "sampling": {
                "focus_themes": ["光刻胶", "卫星互联", "稀土永磁", "海洋经济", "对日制裁"],
                "samples_per_theme": 3,
                "max_total_samples": 30
            },
            "output": {
                "save_detailed_results": True,
                "generate_html_report": True,
                "output_dir": "data/results/clustering"
            }
        }
        
        if config_path and Path(config_path).exists():
            try:
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f)
                
                # 深度合并配置
                import copy
                merged = copy.deepcopy(default_config)
                self._deep_update(merged, user_config)
                return merged
                
            except Exception as e:
                logger.warning(f"加载配置文件失败: {e}, 使用默认配置")
        
        return default_config
    
    def _deep_update(self, d: Dict, u: Dict):
        """深度更新字典"""
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._deep_update(d[k], v)
            else:
                d[k] = v
    
    def load_ground_truth(self, dataset: List[Dict[str, Any]]):
        """加载真实标签数据"""
        logger.info(f"加载 {len(dataset)} 个案例的真实标签")
        
        for case in dataset:
            event_id = case.get("test_id", case.get("id", f"event_{len(self.event_true_themes)}"))
            true_themes = case.get("ground_truth_themes", [])
            theme_category = case.get("theme", "unknown")
            
            # 添加到事件真实标签
            self.event_true_themes[event_id] = {
                "themes": true_themes,
                "category": theme_category,
                "case_data": case
            }
            
            # 添加到主题到事件的映射
            for theme in true_themes:
                if theme not in self.theme_ground_truth:
                    self.theme_ground_truth[theme] = set()
                self.theme_ground_truth[theme].add(event_id)
        
        logger.info(f"加载完成: {len(self.event_true_themes)} 个事件, {len(self.theme_ground_truth)} 个真实主题")
        
        # 显示主题分布
        theme_stats = {theme: len(events) for theme, events in self.theme_ground_truth.items()}
        logger.info("真实主题分布:")
        for theme, count in sorted(theme_stats.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {theme}: {count} 个事件")
    
    async def evaluate_ai_results(self, ai_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        评估AI聚类结果
        
        Args:
            ai_results: AI分析结果列表，每个元素包含:
                - event_id: 事件ID
                - discovered_themes: AI发现的主题列表
                - confidence_scores: 置信度分数（可选）
                
        Returns:
            评估结果字典
        """
        logger.info(f"开始评估 {len(ai_results)} 个AI分析结果")
        
        # 准备AI聚类数据
        ai_theme_events = defaultdict(set)  # AI主题 -> 事件集合
        event_ai_themes = {}  # 事件 -> AI主题集合
        
        for result in ai_results:
            event_id = result.get("event_id")
            discovered = result.get("discovered_themes", [])
            
            if not event_id or not discovered:
                continue
            
            # 标准化AI主题名称
            standardized = [self._standardize_theme_name(t) for t in discovered]
            event_ai_themes[event_id] = set(standardized)
            
            for theme in standardized:
                ai_theme_events[theme].add(event_id)
        
        logger.info(f"AI发现 {len(ai_theme_events)} 个主题")
        
        # 计算聚类指标
        metrics = self._calculate_clustering_metrics(
            ai_theme_events, event_ai_themes
        )
        
        # 详细分析
        detailed_analysis = self._analyze_clustering_details(
            ai_theme_events, event_ai_themes
        )
        
        # 生成评估报告
        report = self._generate_evaluation_report(metrics, detailed_analysis, ai_results)
        
        # 保存结果
        self._save_results(report)
        
        return report
    
    def _standardize_theme_name(self, theme: str) -> str:
        """标准化主题名称（简化版）"""
        # 同义词映射
        synonym_map = {
            "智能眼镜": "AI/AR眼镜",
            "AR眼镜": "AI/AR眼镜", 
            "AI眼镜": "AI/AR眼镜",
            "卫星互联网": "卫星互联",
            "星链": "卫星互联",
            "光刻材料": "光刻胶",
            "光阻剂": "光刻胶",
            "稀土磁材": "稀土永磁",
            "钕铁硼": "稀土永磁",
            "蓝色经济": "海洋经济",
            "海洋产业": "海洋经济"
        }
        
        return synonym_map.get(theme, theme)
    
    def _calculate_clustering_metrics(self, ai_theme_events: Dict[str, set],
                                     event_ai_themes: Dict[str, set]) -> ClusteringMetrics:
        """计算聚类指标"""
        
        # 1. 聚类精度
        clustering_precision = self._calculate_clustering_precision(
            ai_theme_events, event_ai_themes
        )
        
        # 2. 归集完整性
        collection_completeness = self._calculate_collection_completeness(
            ai_theme_events
        )
        
        # 3. 主题纯度
        theme_purity = self._calculate_theme_purity(ai_theme_events)
        
        # 4. 主题分离度
        theme_separation = self._calculate_theme_separation(ai_theme_events)
        
        # 5. 事件覆盖率
        event_coverage = self._calculate_event_coverage(event_ai_themes)
        
        # 6. 综合得分
        weights = self.config["metrics"]["weights"]
        overall_score = (
            clustering_precision * weights["clustering_precision"] +
            collection_completeness * weights["collection_completeness"] +
            theme_purity * weights["theme_purity"] +
            theme_separation * weights["theme_separation"] +
            event_coverage * weights["event_coverage"]
        )
        
        return ClusteringMetrics(
            clustering_precision=clustering_precision,
            collection_completeness=collection_completeness,
            theme_purity=theme_purity,
            theme_separation=theme_separation,
            event_coverage=event_coverage,
            overall_score=overall_score
        )
    
    def _calculate_clustering_precision(self, ai_theme_events: Dict[str, set],
                                       event_ai_themes: Dict[str, set]) -> float:
        """计算聚类精度"""
        scores = []
        
        for true_theme, true_event_set in self.theme_ground_truth.items():
            if len(true_event_set) < 2:
                continue  # 需要至少2个事件才能评估聚类
            
            # 找出这些事件在AI中的主题分布
            ai_theme_distribution = Counter()
            for event_id in true_event_set:
                if event_id in event_ai_themes:
                    for ai_theme in event_ai_themes[event_id]:
                        ai_theme_distribution[ai_theme] += 1
            
            if not ai_theme_distribution:
                scores.append(0.0)
                continue
            
            # 计算主要AI主题的覆盖率
            most_common_ai_theme, most_common_count = ai_theme_distribution.most_common(1)[0]
            precision = most_common_count / len(true_event_set)
            scores.append(precision)
        
        return statistics.mean(scores) if scores else 0.0
    
    def _calculate_collection_completeness(self, ai_theme_events: Dict[str, set]) -> float:
        """计算归集完整性"""
        completeness_scores = []
        
        for true_theme, true_event_set in self.theme_ground_truth.items():
            # 查找AI中对应的主题（通过标准化名称）
            matched_ai_events = set()
            std_true_theme = self._standardize_theme_name(true_theme)
            
            for ai_theme, ai_event_set in ai_theme_events.items():
                std_ai_theme = self._standardize_theme_name(ai_theme)
                if std_true_theme == std_ai_theme:
                    matched_ai_events.update(ai_event_set)
            
            # 计算覆盖率
            coverage = len(matched_ai_events & true_event_set) / len(true_event_set)
            completeness_scores.append(coverage)
        
        return statistics.mean(completeness_scores) if completeness_scores else 0.0
    
    def _calculate_theme_purity(self, ai_theme_events: Dict[str, set]) -> float:
        """计算主题纯度"""
        purity_scores = []
        
        for ai_theme, ai_event_set in ai_theme_events.items():
            if len(ai_event_set) < 2:
                continue
            
            # 统计这些事件在真实标签中的主题分布
            true_theme_distribution = Counter()
            for event_id in ai_event_set:
                if event_id in self.event_true_themes:
                    for true_theme in self.event_true_themes[event_id]["themes"]:
                        true_theme_distribution[true_theme] += 1
            
            if not true_theme_distribution:
                continue
            
            # 计算纯度
            most_common_true_theme, most_common_count = true_theme_distribution.most_common(1)[0]
            purity = most_common_count / len(ai_event_set)
            purity_scores.append(purity)
        
        return statistics.mean(purity_scores) if purity_scores else 0.0
    
    def _calculate_theme_separation(self, ai_theme_events: Dict[str, set]) -> float:
        """计算主题分离度"""
        if len(ai_theme_events) < 2:
            return 1.0  # 只有一个主题时完全分离
        
        separation_scores = []
        ai_themes = list(ai_theme_events.keys())
        
        # 计算所有AI主题对之间的分离度
        for i in range(len(ai_themes)):
            for j in range(i + 1, len(ai_themes)):
                theme_a = ai_themes[i]
                theme_b = ai_themes[j]
                
                events_a = ai_theme_events[theme_a]
                events_b = ai_theme_events[theme_b]
                
                # Jaccard分离度：1 - Jaccard相似度
                intersection = len(events_a & events_b)
                union = len(events_a | events_b)
                
                if union == 0:
                    separation = 1.0
                else:
                    jaccard_similarity = intersection / union
                    separation = 1.0 - jaccard_similarity
                
                separation_scores.append(separation)
        
        return statistics.mean(separation_scores) if separation_scores else 1.0
    
    def _calculate_event_coverage(self, event_ai_themes: Dict[str, set]) -> float:
        """计算事件覆盖率"""
        covered_events = 0
        total_events = len(self.event_true_themes)
        
        for event_id, true_info in self.event_true_themes.items():
            if event_id not in event_ai_themes:
                continue
            
            ai_themes = event_ai_themes[event_id]
            true_themes = true_info["themes"]
            
            # 检查是否有匹配的主题
            matched = False
            for true_theme in true_themes:
                std_true_theme = self._standardize_theme_name(true_theme)
                for ai_theme in ai_themes:
                    std_ai_theme = self._standardize_theme_name(ai_theme)
                    if std_true_theme == std_ai_theme:
                        matched = True
                        break
                if matched:
                    break
            
            if matched:
                covered_events += 1
        
        return covered_events / total_events if total_events > 0 else 0.0
    
    def _analyze_clustering_details(self, ai_theme_events: Dict[str, set],
                                   event_ai_themes: Dict[str, set]) -> Dict[str, Any]:
        """详细分析聚类效果"""
        analysis = {
            "theme_clustering": [],
            "problem_cases": [],
            "successful_clusters": [],
            "mixed_clusters": []
        }
        
        # 分析每个真实主题的聚类效果
        for true_theme, true_event_set in self.theme_ground_truth.items():
            if len(true_event_set) < 3:  # 需要足够多的事件来分析
                continue
            
            # 统计AI主题分布
            ai_theme_distribution = Counter()
            for event_id in true_event_set:
                if event_id in event_ai_themes:
                    for ai_theme in event_ai_themes[event_id]:
                        ai_theme_distribution[ai_theme] += 1
            
            if not ai_theme_distribution:
                analysis["problem_cases"].append({
                    "true_theme": true_theme,
                    "issue": "无AI主题匹配",
                    "event_count": len(true_event_set)
                })
                continue
            
            # 分析聚类质量
            most_common_ai_theme, most_common_count = ai_theme_distribution.most_common(1)[0]
            consistency = most_common_count / len(true_event_set)
            
            cluster_result = ThemeClusteringResult(
                theme=true_theme,
                event_count=len(true_event_set),
                primary_ai_theme=most_common_ai_theme,
                clustering_consistency=consistency,
                ai_theme_distribution=dict(ai_theme_distribution.most_common(5)),
                event_ids=list(true_event_set)[:10]  # 只记录前10个事件ID
            )
            
            analysis["theme_clustering"].append(cluster_result)
            
            # 分类聚类效果
            if consistency >= 0.8:
                analysis["successful_clusters"].append({
                    "true_theme": true_theme,
                    "ai_theme": most_common_ai_theme,
                    "consistency": consistency,
                    "event_count": len(true_event_set)
                })
            elif consistency >= 0.6:
                analysis["mixed_clusters"].append({
                    "true_theme": true_theme,
                    "primary_ai_theme": most_common_ai_theme,
                    "consistency": consistency,
                    "ai_theme_distribution": dict(ai_theme_distribution.most_common(3))
                })
            else:
                analysis["problem_cases"].append({
                    "true_theme": true_theme,
                    "issue": f"聚类分散，主要主题仅覆盖{consistency:.0%}",
                    "ai_theme_distribution": dict(ai_theme_distribution.most_common(3)),
                    "event_count": len(true_event_set)
                })
        
        return analysis
    
    def _generate_evaluation_report(self, metrics: ClusteringMetrics,
                                   analysis: Dict[str, Any],
                                   ai_results: List[Dict]) -> Dict[str, Any]:
        """生成评估报告"""
        
        # 评估等级
        thresholds = self.config["metrics"]["thresholds"]
        
        if metrics.overall_score >= thresholds["excellent"]:
            evaluation_level = "优秀"
            recommendation = "可以直接用于生产环境"
        elif metrics.overall_score >= thresholds["good"]:
            evaluation_level = "良好"
            recommendation = "可以在监控下用于生产"
        elif metrics.overall_score >= thresholds["acceptable"]:
            evaluation_level = "一般"
            recommendation = "需要人工复核和优化"
        else:
            evaluation_level = "需改进"
            recommendation = "需要重点优化后再评估"
        
        report = {
            "metadata": {
                "evaluation_id": f"clustering_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "evaluation_time": datetime.now().isoformat(),
                "evaluation_focus": "事件归集能力评估",
                "total_events": len(self.event_true_themes),
                "ai_themes_count": len(set().union(*[set(r.get('discovered_themes', [])) for r in ai_results]))
            },
            "summary": {
                "overall_score": round(metrics.overall_score, 4),
                "evaluation_level": evaluation_level,
                "recommendation": recommendation,
                "metrics_summary": {
                    "clustering_precision": round(metrics.clustering_precision, 4),
                    "collection_completeness": round(metrics.collection_completeness, 4),
                    "theme_purity": round(metrics.theme_purity, 4),
                    "theme_separation": round(metrics.theme_separation, 4),
                    "event_coverage": round(metrics.event_coverage, 4)
                }
            },
            "detailed_analysis": analysis,
            "interpretation": self._generate_interpretation(metrics, analysis)
        }
        
        return report
    
    def _generate_interpretation(self, metrics: ClusteringMetrics,
                                analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成结果解读"""
        
        interpretation = {
            "business_value": "",
            "strengths": [],
            "weaknesses": [],
            "optimization_suggestions": []
        }
        
        # 业务价值解读
        if metrics.overall_score >= 0.8:
            interpretation["business_value"] = "主题聚类效果优秀，可以支持自动化投资组合构建和主题跟踪"
        elif metrics.overall_score >= 0.7:
            interpretation["business_value"] = "主题聚类效果良好，可以支持半自动化的主题投资分析"
        elif metrics.overall_score >= 0.6:
            interpretation["business_value"] = "主题聚类效果一般，需要结合人工判断进行投资决策"
        else:
            interpretation["business_value"] = "主题聚类效果需要改进，暂时不建议直接用于投资决策"
        
        # 识别优势
        if metrics.clustering_precision >= 0.8:
            interpretation["strengths"].append("聚类精度高，能够将相关事件正确归集")
        if metrics.theme_purity >= 0.8:
            interpretation["strengths"].append("主题纯净度高，AI发现的主题内容一致")
        if metrics.theme_separation >= 0.9:
            interpretation["strengths"].append("主题分离度好，不同主题界限清晰")
        
        # 识别弱点
        if metrics.collection_completeness < 0.7:
            interpretation["weaknesses"].append(f"归集完整性不足({metrics.collection_completeness:.0%})，部分相关事件未被发现")
        if metrics.event_coverage < 0.8:
            interpretation["weaknesses"].append(f"事件覆盖率不足({metrics.event_coverage:.0%})，部分事件未被正确标记")
        
        # 生成优化建议
        problem_cases = analysis.get("problem_cases", [])
        if problem_cases:
            problem_themes = [case["true_theme"] for case in problem_cases[:3]]
            interpretation["optimization_suggestions"].append(
                f"重点优化主题: {', '.join(problem_themes)} 的识别能力"
            )
        
        if metrics.clustering_precision < 0.7:
            interpretation["optimization_suggestions"].append(
                "优化聚类算法，提高同类事件的归集精度"
            )
        
        if metrics.collection_completeness < 0.7:
            interpretation["optimization_suggestions"].append(
                "扩展同义词库和关键词匹配，提高事件发现率"
            )
        
        return interpretation
    
    def _save_results(self, report: Dict[str, Any]):
        """保存评估结果"""
        output_dir = Path(self.config["output"]["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存JSON报告
        json_path = output_dir / f"clustering_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"评估报告已保存: {json_path}")
        
        # 生成HTML报告（如果需要）
        if self.config["output"]["generate_html_report"]:
            html_path = output_dir / f"clustering_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            self._generate_html_report(report, html_path)
    
    def _generate_html_report(self, report: Dict[str, Any], output_path: Path):
        """生成HTML报告（简化版）"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>AI主题聚类评估报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background: #f0f0f0; padding: 20px; border-radius: 10px; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
                .metric-card {{ border: 1px solid #ddd; padding: 20px; border-radius: 8px; text-align: center; }}
                .score {{ font-size: 24px; font-weight: bold; margin: 10px 0; }}
                .excellent {{ color: #4CAF50; }}
                .good {{ color: #8BC34A; }}
                .fair {{ color: #FFC107; }}
                .poor {{ color: #F44336; }}
                .recommendation {{ background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f5f5f5; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎯 AI主题聚类评估报告</h1>
                <p>评估ID: {report['metadata']['evaluation_id']}</p>
                <p>评估时间: {report['metadata']['evaluation_time']}</p>
                <p>评估重点: {report['metadata']['evaluation_focus']}</p>
            </div>
            
            <div class="recommendation">
                <h2>📋 评估结论</h2>
                <p><strong>综合得分: {report['summary']['overall_score']:.3f}/1.0</strong></p>
                <p><strong>评估等级: {report['summary']['evaluation_level']}</strong></p>
                <p><strong>建议: {report['summary']['recommendation']}</strong></p>
            </div>
            
            <h2>📊 详细指标</h2>
            <div class="metrics">
        """
        
        # 添加指标卡片
        metrics_data = report['summary']['metrics_summary']
        for metric_name, value in metrics_data.items():
            if value >= 0.8:
                color_class = "excellent"
                rating = "优秀"
            elif value >= 0.7:
                color_class = "good"
                rating = "良好"
            elif value >= 0.6:
                color_class = "fair"
                rating = "一般"
            else:
                color_class = "poor"
                rating = "需改进"
            
            metric_desc = {
                "clustering_precision": "聚类精度",
                "collection_completeness": "归集完整性",
                "theme_purity": "主题纯度",
                "theme_separation": "主题分离度",
                "event_coverage": "事件覆盖率"
            }.get(metric_name, metric_name)
            
            html_content += f"""
                <div class="metric-card">
                    <h3>{metric_desc}</h3>
                    <div class="score {color_class}">{value:.3f}</div>
                    <div>{rating}</div>
                </div>
            """
        
        html_content += """
            </div>
            
            <h2>🔍 聚类效果分析</h2>
            <table>
                <tr>
                    <th>主题</th>
                    <th>事件数量</th>
                    <th>主要AI主题</th>
                    <th>聚类一致性</th>
                    <th>评估</th>
                </tr>
        """
        
        # 添加主题聚类表格
        for cluster in report['detailed_analysis'].get('theme_clustering', []):
            consistency = getattr(cluster, 'clustering_consistency', 0) if hasattr(cluster, 'clustering_consistency') else cluster.get('consistency', 0)
            
            if consistency >= 0.8:
                assessment = "✅ 优秀"
            elif consistency >= 0.6:
                assessment = "⚠️ 良好"
            else:
                assessment = "❌ 需改进"
            
            html_content += f"""
                <tr>
                    <td>{getattr(cluster, 'theme', 'unknown')}</td>
                    <td>{getattr(cluster, 'event_count', 0)}</td>
                    <td>{getattr(cluster, 'primary_ai_theme', 'unknown')}</td>
                    <td>{consistency:.1%}</td>
                    <td>{assessment}</td>
                </tr>
            """
        
        html_content += """
            </table>
            
            <h2>💡 优化建议</h2>
            <ul>
        """
        
        # 添加优化建议
        for suggestion in report['interpretation'].get('optimization_suggestions', []):
            html_content += f"<li>{suggestion}</li>"
        
        html_content += """
            </ul>
            
            <div style="margin-top: 40px; padding: 20px; background: #f9f9f9; border-radius: 8px;">
                <p><strong>业务价值解读:</strong> {}</p>
                <p><strong>生成时间:</strong> {}</p>
            </div>
        </body>
        </html>
        """.format(
            report['interpretation'].get('business_value', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML报告已生成: {output_path}")

# 测试函数
async def test_clustering_evaluator():
    """测试聚类评估器"""
    print("🧪 测试聚类评估器...")
    
    # 创建测试数据
    test_dataset = [
        {
            "test_id": "test_001",
            "theme": "光刻胶",
            "ground_truth_themes": ["光刻胶"],
            "title": "测试光刻胶事件1"
        },
        {
            "test_id": "test_002",
            "theme": "光刻胶",
            "ground_truth_themes": ["光刻胶"],
            "title": "测试光刻胶事件2"
        },
        {
            "test_id": "test_003",
            "theme": "卫星互联",
            "ground_truth_themes": ["卫星互联"],
            "title": "测试卫星互联事件1"
        },
        {
            "test_id": "test_004",
            "theme": "卫星互联",
            "ground_truth_themes": ["卫星互联"],
            "title": "测试卫星互联事件2"
        }
    ]
    
    # 模拟AI结果
    ai_results = [
        {
            "event_id": "test_001",
            "discovered_themes": ["光刻胶", "半导体材料"]
        },
        {
            "event_id": "test_002",
            "discovered_themes": ["光刻胶"]
        },
        {
            "event_id": "test_003",
            "discovered_themes": ["卫星互联网", "通信"]
        },
        {
            "event_id": "test_004",
            "discovered_themes": ["卫星互联"]
        }
    ]
    
    # 创建评估器
    evaluator = ClusteringEvaluator()
    evaluator.load_ground_truth(test_dataset)
    
    # 运行评估
    report = await evaluator.evaluate_ai_results(ai_results)
    
    print(f"✅ 测试完成!")
    print(f"   综合得分: {report['summary']['overall_score']:.3f}")
    print(f"   评估等级: {report['summary']['evaluation_level']}")
    
    return report

if __name__ == "__main__":
    # 运行测试
    import asyncio
    asyncio.run(test_clustering_evaluator())
