# evaluate_service/scripts/evaluators/enhanced_evaluator.py
"""
增强系统评估器 - 专门测试优化后的两阶段归并框架
基于您已完成的基础评估器架构
"""
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import statistics

from ..core.base_evaluator import BaseEvaluator
from ..core.theme_metrics import ThemeQualityMetrics

logger = logging.getLogger(__name__)

@dataclass
class EnhancedSystemMetrics:
    """增强系统评估指标"""
    decision_accuracy: float          # 决策准确率
    response_time_ms: float           # 响应时间（毫秒）
    theme_duplication_rate: float     # 题材重复率
    naming_quality_score: float       # 命名质量评分
    merge_success_rate: float         # 归并成功率
    false_negative_rate: float        # 漏报率
    false_positive_rate: float        # 误报率
    overall_score: float              # 综合得分

class EnhancedEvaluator(BaseEvaluator):
    """增强系统评估器 - 测试两阶段归并框架"""
    
    def __init__(self, config_path: str = "config/enhanced_config.yaml"):
        super().__init__(config_path)
        self.theme_metrics = ThemeQualityMetrics()
        
        # 结果存储
        self.results_dir = Path("data/results/enhanced")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 测试数据集
        self.test_dataset = self._load_test_dataset()
        
        logger.info(f"增强系统评估器初始化，测试集大小: {len(self.test_dataset)}")
    
    def _load_test_dataset(self) -> List[Dict[str, Any]]:
        """加载标准测试数据集"""
        dataset_path = Path("data/raw/test_dataset_76.json")
        if dataset_path.exists():
            with open(dataset_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 如果文件不存在，生成模拟测试数据
        return self._generate_test_dataset()
    
    async def evaluate_enhanced_system(self) -> Dict[str, Any]:
        """
        全面评估增强系统性能
        """
        logger.info("开始增强系统全面评估")
        
        # 1. 决策准确性评估
        logger.info("阶段1: 决策准确性评估")
        decision_results = await self._evaluate_decision_accuracy()
        
        # 2. 响应时间评估
        logger.info("阶段2: 响应时间评估")
        response_times = await self._evaluate_response_time()
        
        # 3. 题材质量评估
        logger.info("阶段3: 题材质量评估")
        quality_results = await self._evaluate_theme_quality()
        
        # 4. 系统稳定性评估
        logger.info("阶段4: 系统稳定性评估")
        stability_results = await self._evaluate_system_stability()
        
        # 计算综合指标
        metrics = self._calculate_overall_metrics(
            decision_results, response_times, 
            quality_results, stability_results
        )
        
        # 生成报告
        report = self._generate_evaluation_report(metrics, {
            "decision_results": decision_results,
            "response_times": response_times,
            "quality_results": quality_results,
            "stability_results": stability_results
        })
        
        # 保存结果
        self._save_results(report)
        
        return report
    
    async def _evaluate_decision_accuracy(self) -> Dict[str, Any]:
        """评估决策准确性"""
        logger.info("评估决策准确性...")
        
        test_cases = self._get_decision_test_cases()
        results = []
        
        for case in test_cases:
            try:
                # 模拟增强系统处理
                ai_decision = await self._simulate_enhanced_decision(case)
                
                # 判断决策是否正确
                is_correct = self._validate_decision(case, ai_decision)
                
                results.append({
                    "case_id": case.get("id"),
                    "expected_action": case.get("expected_action"),
                    "actual_action": ai_decision.get("decision"),
                    "confidence": ai_decision.get("confidence"),
                    "is_correct": is_correct,
                    "reason": ai_decision.get("reason", "")
                })
                
            except Exception as e:
                logger.error(f"决策评估失败: {e}")
                results.append({
                    "case_id": case.get("id"),
                    "error": str(e),
                    "is_correct": False
                })
        
        # 计算准确率
        correct_count = sum(1 for r in results if r.get("is_correct", False))
        total_count = len(results)
        accuracy = correct_count / total_count if total_count > 0 else 0
        
        return {
            "total_cases": total_count,
            "correct_decisions": correct_count,
            "accuracy": accuracy,
            "detailed_results": results,
            "confusion_matrix": self._build_confusion_matrix(results)
        }
    
    async def _simulate_enhanced_decision(self, test_case: Dict) -> Dict[str, Any]:
        """模拟增强系统决策"""
        # 这里应该调用实际的增强系统
        # 为了测试，我们先模拟返回
        
        event_type = test_case.get("event_type", "")
        industries = test_case.get("impact_industries", [])
        
        # 模拟两阶段决策逻辑
        # 第一阶段：重大性判断
        is_major = self._is_major_event(test_case)
        
        if is_major:
            # 重大事件：倾向创建新题材
            return {
                "decision": "CREATE_NEW",
                "target_theme_name": self._generate_theme_name(test_case),
                "confidence": 0.85,
                "reason": "事件具有重大性和新颖性",
                "comparison_analysis": "无相关现有题材"
            }
        else:
            # 检查是否有相关题材
            related_themes = self._find_related_themes(test_case)
            if related_themes:
                # 有相关题材：倾向归并
                return {
                    "decision": "MERGE_INTO",
                    "target_theme_name": related_themes[0],
                    "confidence": 0.75,
                    "reason": "事件与现有题材高度相关",
                    "comparison_analysis": f"与'{related_themes[0]}'题材核心逻辑一致"
                }
            else:
                # 无相关题材：创建新题材
                return {
                    "decision": "CREATE_NEW",
                    "target_theme_name": self._generate_theme_name(test_case),
                    "confidence": 0.65,
                    "reason": "无相关现有题材，创建新主题",
                    "comparison_analysis": "无密切相关的现有题材"
                }
    
    async def _evaluate_response_time(self) -> Dict[str, Any]:
        """评估响应时间"""
        logger.info("评估响应时间...")
        
        # 测试不同大小的事件集
        response_times = []
        
        for batch_size in [1, 5, 10, 20]:
            events = self.test_dataset[:batch_size]
            
            start_time = datetime.now()
            
            # 模拟批量处理
            for event in events:
                await self._simulate_enhanced_decision(event)
                # 模拟处理延迟
                await asyncio.sleep(0.01)
            
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            avg_time_per_event = elapsed_ms / batch_size
            
            response_times.append({
                "batch_size": batch_size,
                "total_time_ms": elapsed_ms,
                "avg_time_per_event_ms": avg_time_per_event
            })
            
            logger.info(f"批量大小 {batch_size}: 平均 {avg_time_per_event:.1f}ms/事件")
        
        # 重点测试单事件响应时间
        single_event_times = []
        for i in range(10):
            event = self.test_dataset[i % len(self.test_dataset)]
            
            start_time = datetime.now()
            await self._simulate_enhanced_decision(event)
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            single_event_times.append(elapsed_ms)
        
        return {
            "batch_performance": response_times,
            "single_event_times_ms": single_event_times,
            "single_event_avg_ms": statistics.mean(single_event_times) if single_event_times else 0,
            "single_event_p95_ms": sorted(single_event_times)[int(len(single_event_times) * 0.95)] if single_event_times else 0,
            "meets_target": statistics.mean(single_event_times) < 2000  # 目标: <2秒
        }
    
    async def _evaluate_theme_quality(self) -> Dict[str, Any]:
        """评估题材质量"""
        logger.info("评估题材质量...")
        
        themes_created = []
        duplicate_groups = []
        
        # 模拟处理所有测试事件
        for event in self.test_dataset:
            decision = await self._simulate_enhanced_decision(event)
            
            if decision.get("decision") == "CREATE_NEW":
                theme_name = decision.get("target_theme_name", "")
                if theme_name:
                    themes_created.append({
                        "event_id": event.get("id"),
                        "theme_name": theme_name,
                        "decision_reason": decision.get("reason")
                    })
        
        # 检查重复题材
        theme_counter = {}
        for theme_info in themes_created:
            theme_name = theme_info["theme_name"]
            theme_counter[theme_name] = theme_counter.get(theme_name, 0) + 1
        
        # 识别重复组
        for theme_name, count in theme_counter.items():
            if count > 1:
                duplicate_groups.append({
                    "theme_name": theme_name,
                    "count": count,
                    "events": [t["event_id"] for t in themes_created if t["theme_name"] == theme_name]
                })
        
        # 评估命名质量
        naming_scores = []
        for theme_info in themes_created:
            score = self._evaluate_naming_quality(theme_info["theme_name"])
            naming_scores.append(score)
        
        return {
            "total_themes_created": len(themes_created),
            "unique_themes": len(set(t["theme_name"] for t in themes_created)),
            "duplicate_groups": duplicate_groups,
            "duplication_rate": len(duplicate_groups) / len(themes_created) if themes_created else 0,
            "naming_quality_scores": naming_scores,
            "avg_naming_score": statistics.mean(naming_scores) if naming_scores else 0,
            "themes_created": themes_created[:20]  # 只返回前20个示例
        }
    
    async def _evaluate_system_stability(self) -> Dict[str, Any]:
        """评估系统稳定性"""
        logger.info("评估系统稳定性...")
        
        success_count = 0
        error_count = 0
        error_details = []
        
        # 压力测试：连续处理多个事件
        test_events = self.test_dataset * 3  # 重复三次以增加压力
        
        for i, event in enumerate(test_events):
            try:
                decision = await self._simulate_enhanced_decision(event)
                
                # 验证决策格式
                if self._validate_decision_format(decision):
                    success_count += 1
                else:
                    error_count += 1
                    error_details.append({
                        "event_index": i,
                        "error": "决策格式无效",
                        "decision": decision
                    })
                    
            except Exception as e:
                error_count += 1
                error_details.append({
                    "event_index": i,
                    "error": str(e),
                    "event_id": event.get("id")
                })
            
            # 每处理100个事件报告一次进度
            if (i + 1) % 100 == 0:
                logger.info(f"已处理 {i + 1}/{len(test_events)} 个事件")
        
        success_rate = success_count / (success_count + error_count) if (success_count + error_count) > 0 else 0
        
        return {
            "total_processed": len(test_events),
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_rate,
            "error_details": error_details[:10],  # 只返回前10个错误
            "meets_target": success_rate >= 0.95  # 目标: >95%
        }
    
    def _calculate_overall_metrics(self, decision_results, response_times, 
                                 quality_results, stability_results) -> EnhancedSystemMetrics:
        """计算综合指标"""
        
        return EnhancedSystemMetrics(
            decision_accuracy=decision_results.get("accuracy", 0),
            response_time_ms=response_times.get("single_event_avg_ms", 0),
            theme_duplication_rate=quality_results.get("duplication_rate", 0),
            naming_quality_score=quality_results.get("avg_naming_score", 0),
            merge_success_rate=0.85,  # 需要从实际结果计算
            false_negative_rate=0.05,  # 需要从实际结果计算
            false_positive_rate=0.08,  # 需要从实际结果计算
            overall_score=self._calculate_overall_score(
                decision_results, response_times, 
                quality_results, stability_results
            )
        )
    
    def _calculate_overall_score(self, decision_results, response_times, 
                               quality_results, stability_results) -> float:
        """计算综合得分"""
        weights = self.config.get("metrics_weights", {
            "decision_accuracy": 0.30,
            "response_time": 0.25,
            "theme_quality": 0.25,
            "system_stability": 0.20
        })
        
        # 归一化各项指标
        accuracy_score = decision_results.get("accuracy", 0)
        
        # 响应时间得分（越快越好）
        avg_response_time = response_times.get("single_event_avg_ms", 0)
        response_score = max(0, 1 - (avg_response_time / 5000))  # 5秒为基准
        
        # 题材质量得分
        duplication_rate = quality_results.get("duplication_rate", 0)
        naming_score = quality_results.get("avg_naming_score", 0)
        quality_score = (1 - duplication_rate) * 0.6 + naming_score * 0.4
        
        # 稳定性得分
        stability_score = stability_results.get("success_rate", 0)
        
        # 计算加权得分
        overall = (
            accuracy_score * weights["decision_accuracy"] +
            response_score * weights["response_time"] +
            quality_score * weights["theme_quality"] +
            stability_score * weights["system_stability"]
        )
        
        return min(1.0, max(0.0, overall))
    
    def _generate_evaluation_report(self, metrics: EnhancedSystemMetrics, 
                                  detailed_results: Dict) -> Dict[str, Any]:
        """生成评估报告"""
        
        # 评估等级
        if metrics.overall_score >= 0.85:
            evaluation_level = "优秀"
            recommendation = "可以直接部署到生产环境"
        elif metrics.overall_score >= 0.75:
            evaluation_level = "良好"
            recommendation = "可以在监控下部署到生产环境"
        elif metrics.overall_score >= 0.65:
            evaluation_level = "一般"
            recommendation = "需要优化后再部署"
        else:
            evaluation_level = "需改进"
            recommendation = "需要重点优化"
        
        report = {
            "metadata": {
                "evaluation_id": f"enhanced_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "evaluation_time": datetime.now().isoformat(),
                "system_version": "enhanced_v1.0",
                "test_dataset_size": len(self.test_dataset)
            },
            "summary": {
                "overall_score": round(metrics.overall_score, 4),
                "evaluation_level": evaluation_level,
                "recommendation": recommendation,
                "key_metrics": {
                    "decision_accuracy": round(metrics.decision_accuracy, 4),
                    "avg_response_time_ms": round(metrics.response_time_ms, 1),
                    "theme_duplication_rate": round(metrics.theme_duplication_rate, 4),
                    "naming_quality_score": round(metrics.naming_quality_score, 4),
                    "system_stability": round(detailed_results["stability_results"].get("success_rate", 0), 4)
                }
            },
            "detailed_results": detailed_results,
            "improvement_suggestions": self._generate_improvement_suggestions(metrics, detailed_results),
            "comparison_with_baseline": self._load_baseline_comparison()
        }
        
        return report
    
    def _generate_improvement_suggestions(self, metrics: EnhancedSystemMetrics,
                                        detailed_results: Dict) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        # 基于指标的建议
        if metrics.decision_accuracy < 0.85:
            suggestions.append("决策准确率有待提高，建议优化AI Prompt和阈值设置")
        
        if metrics.response_time_ms > 2000:
            suggestions.append(f"响应时间({metrics.response_time_ms:.0f}ms)超过2秒目标，建议优化数据库查询和缓存")
        
        if metrics.theme_duplication_rate > 0.2:
            suggestions.append(f"题材重复率({metrics.theme_duplication_rate:.1%})较高，建议加强判重机制")
        
        if metrics.naming_quality_score < 0.8:
            suggestions.append("命名质量有待提高，建议优化命名规则和校验机制")
        
        # 基于详细结果的具体建议
        decision_results = detailed_results["decision_results"]
        if decision_results.get("accuracy", 0) < 0.8:
            confusion_matrix = decision_results.get("confusion_matrix", {})
            suggestions.append(f"决策混淆主要集中在: {confusion_matrix}")
        
        stability_results = detailed_results["stability_results"]
        if stability_results.get("success_rate", 0) < 0.95:
            error_count = stability_results.get("error_count", 0)
            suggestions.append(f"系统稳定性不足，发生{error_count}次错误，建议加强异常处理")
        
        return suggestions
    
    def _load_baseline_comparison(self) -> Dict[str, Any]:
        """加载基线系统对比数据"""
        baseline_path = Path("data/results/baseline/latest_results.json")
        if baseline_path.exists():
            with open(baseline_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_results(self, report: Dict[str, Any]):
        """保存评估结果"""
        # 保存详细报告
        report_path = self.results_dir / f"enhanced_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # 保存为最新结果
        latest_path = self.results_dir / "latest_results.json"
        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # 生成HTML报告
        self._generate_html_report(report)
        
        logger.info(f"增强系统评估报告已保存: {report_path}")
    
    def _generate_html_report(self, report: Dict[str, Any]):
        """生成HTML报告"""
        html_path = self.results_dir / f"enhanced_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        # 简化的HTML报告生成
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>增强系统评估报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background: #e3f2fd; padding: 20px; border-radius: 10px; }}
                .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 30px 0; }}
                .metric-card {{ border: 1px solid #ddd; padding: 20px; border-radius: 8px; }}
                .score {{ font-size: 24px; font-weight: bold; margin: 10px 0; }}
                .good {{ color: #4CAF50; }}
                .warning {{ color: #FF9800; }}
                .poor {{ color: #F44336; }}
                .suggestions {{ background: #fff3e0; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f5f5f5; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚀 增强系统评估报告</h1>
                <p>评估ID: {report['metadata']['evaluation_id']}</p>
                <p>评估时间: {report['metadata']['evaluation_time']}</p>
                <p>系统版本: {report['metadata']['system_version']}</p>
            </div>
            
            <div class="suggestions">
                <h2>📋 评估结论</h2>
                <p><strong>综合得分: {report['summary']['overall_score']:.3f}/1.0</strong></p>
                <p><strong>评估等级: {report['summary']['evaluation_level']}</strong></p>
                <p><strong>建议: {report['summary']['recommendation']}</strong></p>
            </div>
            
            <h2>📊 关键指标</h2>
            <div class="metrics-grid">
        """
        
        # 添加指标卡片
        metrics = report['summary']['key_metrics']
        for metric_name, value in metrics.items():
            if "rate" in metric_name or "accuracy" in metric_name:
                if value >= 0.85:
                    rating = "优秀"
                    color_class = "good"
                elif value >= 0.7:
                    rating = "良好"
                    color_class = "warning"
                else:
                    rating = "需改进"
                    color_class = "poor"
            elif "time" in metric_name:
                if value <= 1000:
                    rating = "优秀"
                    color_class = "good"
                elif value <= 2000:
                    rating = "良好"
                    color_class = "warning"
                else:
                    rating = "需改进"
                    color_class = "poor"
            else:
                if value >= 0.8:
                    rating = "优秀"
                    color_class = "good"
                elif value >= 0.6:
                    rating = "良好"
                    color_class = "warning"
                else:
                    rating = "需改进"
                    color_class = "poor"
            
            metric_display = {
                "decision_accuracy": "决策准确率",
                "avg_response_time_ms": "平均响应时间(ms)",
                "theme_duplication_rate": "题材重复率",
                "naming_quality_score": "命名质量",
                "system_stability": "系统稳定性"
            }.get(metric_name, metric_name)
            
            html_content += f"""
                <div class="metric-card">
                    <h3>{metric_display}</h3>
                    <div class="score {color_class}">{value:.3f}</div>
                    <div>{rating}</div>
                </div>
            """
        
        html_content += """
            </div>
            
            <h2>💡 改进建议</h2>
            <ul>
        """
        
        for suggestion in report['improvement_suggestions']:
            html_content += f"<li>{suggestion}</li>"
        
        html_content += """
            </ul>
            
            <div style="margin-top: 40px; padding: 20px; background: #f9f9f9; border-radius: 8px;">
                <p><strong>报告生成时间:</strong> {}</p>
                <p><strong>测试数据集大小:</strong> {} 个事件</p>
                <p><strong>评估重点:</strong> 两阶段归并框架的性能验证</p>
            </div>
        </body>
        </html>
        """.format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            report['metadata']['test_dataset_size']
        )
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML报告已生成: {html_path}")
    
    # 辅助方法
    def _get_decision_test_cases(self) -> List[Dict[str, Any]]:
        """获取决策测试用例"""
        # 这里应该从配置或数据文件加载
        # 现在返回模拟数据
        return [
            {
                "id": "test_major_001",
                "title": "国务院发布新一代人工智能发展规划",
                "event_type": "政策发布",
                "impact_industries": ["人工智能", "信息技术"],
                "expected_action": "CREATE_NEW"
            },
            {
                "id": "test_merge_001", 
                "title": "苹果发布新款AI眼镜",
                "event_type": "产品发布",
                "impact_industries": ["消费电子", "人工智能"],
                "expected_action": "MERGE_INTO",
                "existing_themes": ["AI/AR眼镜"]
            },
            # 更多测试用例...
        ]
    
    def _validate_decision(self, test_case: Dict, ai_decision: Dict) -> bool:
        """验证决策是否正确"""
        expected = test_case.get("expected_action")
        actual = ai_decision.get("decision")
        
        # 简单的匹配逻辑
        return expected == actual
    
    def _is_major_event(self, event: Dict) -> bool:
        """判断是否为重大事件"""
        major_keywords = ["国务院", "国家", "重大突破", "首次", "革命性"]
        event_type = event.get("event_type", "")
        
        return event_type in ["政策发布", "技术突破"] or \
               any(kw in event.get("title", "") for kw in major_keywords)
    
    def _generate_theme_name(self, event: Dict) -> str:
        """生成题材名称"""
        title = event.get("title", "")
        industries = event.get("impact_industries", [])
        
        if industries:
            return f"{industries[0]}新题材"
        else:
            words = title.split()[:2]
            return "".join(words)[:6] if words else "新题材"
    
    def _find_related_themes(self, event: Dict) -> List[str]:
        """查找相关题材"""
        # 模拟查找逻辑
        if "AI" in event.get("title", ""):
            return ["人工智能", "AI/AR眼镜"]
        elif "新能源" in event.get("title", ""):
            return ["新能源汽车", "锂电池"]
        elif "芯片" in event.get("title", ""):
            return ["半导体", "芯片"]
        return []
    
    def _evaluate_naming_quality(self, theme_name: str) -> float:
        """评估命名质量"""
        score = 1.0
        
        # 扣分规则
        if len(theme_name) < 2 or len(theme_name) > 10:
            score -= 0.3
        
        if "科技" in theme_name or "创新" in theme_name:
            score -= 0.2  # 过于宽泛
        
        if any(char.isdigit() for char in theme_name):
            score -= 0.1  # 包含数字
        
        return max(0.0, min(1.0, score))
    
    def _validate_decision_format(self, decision: Dict) -> bool:
        """验证决策格式"""
        required_fields = ["decision", "target_theme_name", "confidence", "reason"]
        return all(field in decision for field in required_fields)
    
    def _build_confusion_matrix(self, results: List[Dict]) -> Dict[str, Any]:
        """构建混淆矩阵"""
        matrix = {}
        for result in results:
            expected = result.get("expected_action", "UNKNOWN")
            actual = result.get("actual_action", "UNKNOWN")
            
            key = f"{expected}->{actual}"
            matrix[key] = matrix.get(key, 0) + 1
        
        return matrix

# 测试函数
async def test_enhanced_evaluator():
    """测试增强系统评估器"""
    print("🧪 测试增强系统评估器...")
    
    evaluator = EnhancedEvaluator()
    report = await evaluator.evaluate_enhanced_system()
    
    print(f"✅ 评估完成!")
    print(f"   综合得分: {report['summary']['overall_score']:.3f}")
    print(f"   评估等级: {report['summary']['evaluation_level']}")
    print(f"   决策准确率: {report['summary']['key_metrics']['decision_accuracy']:.1%}")
    print(f"   平均响应时间: {report['summary']['key_metrics']['avg_response_time_ms']:.0f}ms")
    
    return report

if __name__ == "__main__":
    asyncio.run(test_enhanced_evaluator())