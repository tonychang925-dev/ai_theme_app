# evaluate_service/scripts/evaluators/comparison_evaluator.py
"""
对比评估器 - 比较基线系统和增强系统的性能差异
"""
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import statistics

logger = logging.getLogger(__name__)

class ComparisonEvaluator:
    """对比评估器 - 分析优化效果"""
    
    def __init__(self):
        self.results_dir = Path("data/results/comparison")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
    async def run_comparison(self) -> Dict[str, Any]:
        """运行对比分析"""
        logger.info("开始系统对比分析")
        
        # 加载基线结果
        baseline_results = self._load_baseline_results()
        
        # 加载增强结果
        enhanced_results = self._load_enhanced_results()
        
        if not baseline_results or not enhanced_results:
            logger.error("缺少基线或增强系统结果")
            return {}
        
        # 对比分析
        comparison = self._compare_systems(baseline_results, enhanced_results)
        
        # 生成报告
        report = self._generate_comparison_report(comparison)
        
        # 保存结果
        self._save_results(report)
        
        return report
    
    def _load_baseline_results(self) -> Dict[str, Any]:
        """加载基线系统结果"""
        baseline_path = Path("data/results/baseline/latest_results.json")
        if baseline_path.exists():
            with open(baseline_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_enhanced_results(self) -> Dict[str, Any]:
        """加载增强系统结果"""
        enhanced_path = Path("data/results/enhanced/latest_results.json")
        if enhanced_path.exists():
            with open(enhanced_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _compare_systems(self, baseline: Dict, enhanced: Dict) -> Dict[str, Any]:
        """对比两个系统的性能"""
        
        # 提取关键指标
        baseline_metrics = baseline.get('summary', {}).get('key_metrics', {})
        enhanced_metrics = enhanced.get('summary', {}).get('key_metrics', {})
        
        # 计算改进百分比
        improvements = {}
        for metric_name in baseline_metrics.keys():
            if metric_name in enhanced_metrics:
                baseline_value = baseline_metrics[metric_name]
                enhanced_value = enhanced_metrics[metric_name]
                
                if baseline_value != 0:
                    if "time" in metric_name or "rate" in metric_name:
                        # 响应时间和重复率是越低越好
                        improvement = (baseline_value - enhanced_value) / baseline_value
                    else:
                        # 准确率、质量等是越高越好
                        improvement = (enhanced_value - baseline_value) / baseline_value
                else:
                    improvement = 0
                
                improvements[metric_name] = {
                    "baseline": baseline_value,
                    "enhanced": enhanced_value,
                    "improvement": improvement,
                    "improvement_percent": round(improvement * 100, 1)
                }
        
        # 分析聚类效果对比
        clustering_comparison = self._compare_clustering_effectiveness(baseline, enhanced)
        
        return {
            "metric_comparisons": improvements,
            "clustering_comparison": clustering_comparison,
            "overall_improvement": self._calculate_overall_improvement(improvements),
            "optimization_goals_achieved": self._check_goals_achieved(improvements)
        }
    
    def _compare_clustering_effectiveness(self, baseline: Dict, enhanced: Dict) -> Dict[str, Any]:
        """对比聚类效果"""
        # 从您的聚类评估结果中提取数据
        baseline_clustering = baseline.get('clustering_metrics', {})
        enhanced_clustering = enhanced.get('clustering_metrics', {})
        
        return {
            "theme_count_comparison": {
                "baseline_unique_themes": baseline_clustering.get('unique_themes', 0),
                "enhanced_unique_themes": enhanced_clustering.get('unique_themes', 0),
                "reduction": self._calculate_reduction(
                    baseline_clustering.get('unique_themes', 0),
                    enhanced_clustering.get('unique_themes', 0)
                )
            },
            "duplication_comparison": {
                "baseline_duplicate_groups": baseline_clustering.get('duplicate_groups', 0),
                "enhanced_duplicate_groups": enhanced_clustering.get('duplicate_groups', 0),
                "reduction": self._calculate_reduction(
                    baseline_clustering.get('duplicate_groups', 0),
                    enhanced_clustering.get('duplicate_groups', 0)
                )
            }
        }
    
    def _calculate_overall_improvement(self, improvements: Dict) -> float:
        """计算总体改进程度"""
        if not improvements:
            return 0
        
        # 加权计算总体改进
        weights = {
            "decision_accuracy": 0.30,
            "theme_duplication_rate": 0.25,
            "avg_response_time_ms": 0.20,
            "naming_quality_score": 0.15,
            "system_stability": 0.10
        }
        
        weighted_sum = 0
        for metric_name, data in improvements.items():
            weight = weights.get(metric_name, 0.1)
            # 对于负向指标（时间、重复率），改进是负值表示减少
            if "time" in metric_name or "rate" in metric_name:
                improvement = -data["improvement"]  # 负的改进表示减少
            else:
                improvement = data["improvement"]
            
            weighted_sum += improvement * weight
        
        return weighted_sum
    
    def _check_goals_achieved(self, improvements: Dict) -> Dict[str, bool]:
        """检查优化目标是否达成"""
        goals = {
            "decision_accuracy_85": improvements.get("decision_accuracy", {}).get("enhanced", 0) >= 0.85,
            "response_time_2s": improvements.get("avg_response_time_ms", {}).get("enhanced", 9999) <= 2000,
            "duplication_rate_80_reduction": improvements.get("theme_duplication_rate", {}).get("improvement", 0) <= -0.8,
            "naming_quality_90": improvements.get("naming_quality_score", {}).get("enhanced", 0) >= 0.9,
            "stability_95": improvements.get("system_stability", {}).get("enhanced", 0) >= 0.95
        }
        
        # 计算达成率
        achieved = sum(1 for v in goals.values() if v)
        total = len(goals)
        
        return {
            "goals": goals,
            "achieved_count": achieved,
            "total_goals": total,
            "achievement_rate": achieved / total if total > 0 else 0
        }
    
    def _calculate_reduction(self, baseline: float, enhanced: float) -> float:
        """计算减少百分比"""
        if baseline == 0:
            return 0
        return (baseline - enhanced) / baseline
    
    def _generate_comparison_report(self, comparison: Dict) -> Dict[str, Any]:
        """生成对比报告"""
        
        goals_achieved = comparison.get("optimization_goals_achieved", {})
        
        return {
            "metadata": {
                "report_id": f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "generated_at": datetime.now().isoformat(),
                "baseline_source": "data/results/baseline/latest_results.json",
                "enhanced_source": "data/results/enhanced/latest_results.json"
            },
            "executive_summary": {
                "overall_improvement": round(comparison.get("overall_improvement", 0) * 100, 1),
                "goals_achieved": f"{goals_achieved.get('achieved_count', 0)}/{goals_achieved.get('total_goals', 0)}",
                "achievement_rate": round(goals_achieved.get('achievement_rate', 0) * 100, 1),
                "key_findings": self._generate_key_findings(comparison)
            },
            "detailed_comparison": comparison,
            "recommendations": self._generate_recommendations(comparison)
        }
    
    def _generate_key_findings(self, comparison: Dict) -> List[str]:
        """生成关键发现"""
        findings = []
        
        metric_comparisons = comparison.get("metric_comparisons", {})
        
        for metric_name, data in metric_comparisons.items():
            improvement = data.get("improvement_percent", 0)
            if abs(improvement) > 10:  # 显著变化
                direction = "提升" if improvement > 0 else "降低"
                metric_display = {
                    "decision_accuracy": "决策准确率",
                    "avg_response_time_ms": "响应时间",
                    "theme_duplication_rate": "题材重复率",
                    "naming_quality_score": "命名质量",
                    "system_stability": "系统稳定性"
                }.get(metric_name, metric_name)
                
                findings.append(f"{metric_display}{direction}了{abs(improvement):.1f}%")
        
        return findings
    
    def _generate_recommendations(self, comparison: Dict) -> List[str]:
        """生成建议"""
        recommendations = []
        
        goals = comparison.get("optimization_goals_achieved", {}).get("goals", {})
        
        if not goals.get("decision_accuracy_85", False):
            recommendations.append("继续优化AI决策逻辑，提高准确率到85%以上")
        
        if not goals.get("response_time_2s", False):
            recommendations.append("优化系统性能，确保单事件处理时间在2秒以内")
        
        if not goals.get("duplication_rate_80_reduction", False):
            recommendations.append("加强判重机制，确保重复率降低80%的目标")
        
        if not goals.get("naming_quality_90", False):
            recommendations.append("完善命名规则，提高题材命名质量")
        
        return recommendations
    
    def _save_results(self, report: Dict[str, Any]):
        """保存对比结果"""
        report_path = self.results_dir / f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"对比报告已保存: {report_path}")

# 运行对比分析
async def main():
    """主函数"""
    evaluator = ComparisonEvaluator()
    report = await evaluator.run_comparison()
    
    if report:
        print("\n📊 对比分析完成!")
        print(f"   总体改进: {report['executive_summary']['overall_improvement']}%")
        print(f"   目标达成: {report['executive_summary']['goals_achieved']}")
        print(f"   达成率: {report['executive_summary']['achievement_rate']}%")
        
        print("\n🔍 关键发现:")
        for finding in report['executive_summary']['key_findings']:
            print(f"   • {finding}")
        
        print("\n💡 建议:")
        for recommendation in report['recommendations']:
            print(f"   • {recommendation}")

if __name__ == "__main__":
    asyncio.run(main())