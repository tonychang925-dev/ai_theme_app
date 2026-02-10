# evaluate_service/scripts/data_integrity_validator.py
"""
数据完整性验证器
验证重新生成的事件数据是否包含完整上下文
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataIntegrityValidator:
    """数据完整性验证器"""
    
    def __init__(self):
        self.regenerated_path = Path("evaluate_service/data/processed/validation_events_regenerated.json")
        self.original_path = Path("evaluate_service/data/raw/validation_dataset.json")
        self.report_path = Path("evaluate_service/data/results/reports/data_integrity_report.json")
        
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
    
    def validate_integrity(self) -> Dict[str, Any]:
        """验证数据完整性"""
        logger.info("🔍 验证数据完整性...")
        
        # 1. 加载数据
        try:
            with open(self.regenerated_path, "r", encoding="utf-8") as f:
                regenerated_data = json.load(f)
            
            with open(self.original_path, "r", encoding="utf-8") as f:
                original_data = json.load(f)
            
            if isinstance(original_data, dict) and "news_list" in original_data:
                original_news_list = original_data["news_list"]
            elif isinstance(original_data, list):
                original_news_list = original_data
            else:
                return {"error": "原始数据格式错误"}
            
            regenerated_events = regenerated_data.get("events", [])
            metadata = regenerated_data.get("metadata", {})
            
        except Exception as e:
            return {"error": f"加载数据失败: {e}"}
        
        # 2. 进行完整性检查
        integrity_checks = self.perform_integrity_checks(regenerated_events, original_news_list)
        
        # 3. 生成报告
        report = {
            "validation_time": "2024-01-01",  # 实际应该用datetime
            "total_events_checked": len(regenerated_events),
            "total_original_news": len(original_news_list),
            "metadata": metadata,
            "integrity_checks": integrity_checks,
            "summary": self.generate_summary(integrity_checks),
            "critical_issues": self.find_critical_issues(integrity_checks, regenerated_events),
            "recommendations": self.generate_recommendations(integrity_checks)
        }
        
        # 4. 保存报告
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 验证完成，报告保存到: {self.report_path}")
        return report
    
    def perform_integrity_checks(self, events: List[Dict], original_news: List[Dict]) -> Dict[str, Any]:
        """执行完整性检查"""
        checks = {
            "field_completeness": self.check_field_completeness(events),
            "content_preservation": self.check_content_preservation(events, original_news),
            "context_integrity": self.check_context_integrity(events),
            "ai_decision_quality": self.check_ai_decision_quality(events)
        }
        return checks
    
    def check_field_completeness(self, events: List[Dict]) -> Dict[str, Any]:
        """检查字段完整性"""
        required_fields = [
            "news_id", "event_type", "impact_industries", "direction",
            "confidence", "summary", "theme_directive", "original_data"
        ]
        
        field_stats = {}
        for field in required_fields:
            present_count = sum(1 for event in events if field in event)
            field_stats[field] = {
                "present_count": present_count,
                "total_count": len(events),
                "completion_rate": present_count / max(len(events), 1)
            }
        
        return field_stats
    
    def check_content_preservation(self, events: List[Dict], original_news: List[Dict]) -> Dict[str, Any]:
        """检查内容保存情况"""
        # 创建原始新闻ID到内容的映射
        original_content_map = {}
        for news in original_news:
            news_id = news.get("news_id")
            if news_id:
                original_content_map[news_id] = news.get("content", "")
        
        content_stats = {
            "total_checked": 0,
            "full_content_preserved": 0,
            "partial_content_preserved": 0,
            "no_content_preserved": 0,
            "content_preservation_details": []
        }
        
        for event in events:
            news_id = event.get("news_id")
            original_content = original_content_map.get(news_id, "")
            saved_content = event.get("original_data", {}).get("content", "")
            
            if original_content and saved_content:
                content_stats["total_checked"] += 1
                
                if saved_content == original_content:
                    content_stats["full_content_preserved"] += 1
                    status = "full"
                elif len(saved_content) > 100:
                    content_stats["partial_content_preserved"] += 1
                    status = "partial"
                else:
                    content_stats["no_content_preserved"] += 1
                    status = "none"
                
                content_stats["content_preservation_details"].append({
                    "news_id": news_id,
                    "original_length": len(original_content),
                    "saved_length": len(saved_content),
                    "preservation_status": status
                })
        
        return content_stats
    
    def check_context_integrity(self, events: List[Dict]) -> Dict[str, Any]:
        """检查上下文完整性"""
        context_checks = {
            "has_meaningful_summary": 0,
            "has_industries": 0,
            "has_theme_directive": 0,
            "has_confidence": 0,
            "has_ai_response": 0
        }
        
        for event in events:
            if event.get("summary") and len(event["summary"]) > 50:
                context_checks["has_meaningful_summary"] += 1
            
            if event.get("impact_industries") and len(event["impact_industries"]) > 0:
                context_checks["has_industries"] += 1
            
            if event.get("theme_directive"):
                context_checks["has_theme_directive"] += 1
            
            if "confidence" in event and 0 <= event["confidence"] <= 1:
                context_checks["has_confidence"] += 1
            
            if event.get("ai_response"):
                context_checks["has_ai_response"] += 1
        
        # 计算百分比
        total = len(events)
        for key in list(context_checks.keys()):
            context_checks[f"{key}_percent"] = context_checks[key] / max(total, 1)
        
        return context_checks
    
    def check_ai_decision_quality(self, events: List[Dict]) -> Dict[str, Any]:
        """检查AI决策质量"""
        decisions = {
            "CLUSTER": 0,
            "CREATE_NEW": 0,
            "MERGE_INTO": 0,
            "IGNORE": 0,
            "unknown": 0
        }
        
        confidences = []
        
        for event in events:
            directive = event.get("theme_directive", {})
            action = directive.get("action", "unknown")
            decisions[action] = decisions.get(action, 0) + 1
            
            confidence = directive.get("confidence")
            if confidence is not None:
                confidences.append(float(confidence))
        
        return {
            "decision_distribution": decisions,
            "confidence_stats": {
                "average": sum(confidences) / max(len(confidences), 1) if confidences else 0,
                "max": max(confidences) if confidences else 0,
                "min": min(confidences) if confidences else 0,
                "count": len(confidences)
            }
        }
    
    def generate_summary(self, checks: Dict[str, Any]) -> Dict[str, Any]:
        """生成摘要"""
        field_completeness = checks["field_completeness"]
        content_preservation = checks["content_preservation"]
        context_integrity = checks["context_integrity"]
        
        overall_score = (
            sum(field["completion_rate"] for field in field_completeness.values()) / max(len(field_completeness), 1) * 0.3 +
            (content_preservation.get("full_content_preserved", 0) / max(content_preservation.get("total_checked", 1), 1)) * 0.4 +
            sum(v for k, v in context_integrity.items() if k.endswith("_percent")) / sum(1 for k in context_integrity if k.endswith("_percent")) * 0.3
        )
        
        return {
            "overall_integrity_score": overall_score,
            "field_completeness_score": sum(field["completion_rate"] for field in field_completeness.values()) / max(len(field_completeness), 1),
            "content_preservation_score": content_preservation.get("full_content_preserved", 0) / max(content_preservation.get("total_checked", 1), 1),
            "context_integrity_score": sum(v for k, v in context_integrity.items() if k.endswith("_percent")) / sum(1 for k in context_integrity if k.endswith("_percent")),
            "status": "PASS" if overall_score > 0.8 else "WARNING" if overall_score > 0.6 else "FAIL"
        }
    
    def find_critical_issues(self, checks: Dict[str, Any], events: List[Dict]) -> List[Dict[str, Any]]:
        """找到关键问题"""
        issues = []
        
        # 检查缺少关键字段的事件
        for event in events[:10]:  # 只检查前10个
            if "original_data" not in event:
                issues.append({
                    "type": "missing_field",
                    "news_id": event.get("news_id"),
                    "field": "original_data",
                    "severity": "high"
                })
            elif "content" not in event.get("original_data", {}):
                issues.append({
                    "type": "missing_content",
                    "news_id": event.get("news_id"),
                    "severity": "high"
                })
        
        return issues[:5]  # 只返回前5个问题
    
    def generate_recommendations(self, checks: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        summary = self.generate_summary(checks)
        
        if summary["field_completeness_score"] < 0.9:
            recommendations.append("提高字段完整性：确保所有事件都有完整的必填字段")
        
        if summary["content_preservation_score"] < 0.8:
            recommendations.append("改进内容保存：确保原始新闻内容完整保存到original_data中")
        
        if summary["context_integrity_score"] < 0.8:
            recommendations.append("增强上下文完整性：确保事件有详细的摘要和明确的主题指令")
        
        if not recommendations:
            recommendations.append("数据完整性良好，继续保持")
        
        return recommendations


def main():
    """主函数"""
    validator = DataIntegrityValidator()
    report = validator.validate_integrity()
    
    if "error" in report:
        print(f"❌ 验证失败: {report['error']}")
    else:
        summary = report["summary"]
        print("\n📊 数据完整性验证结果:")
        print(f"   整体完整性分数: {summary['overall_integrity_score']:.2f}")
        print(f"   字段完整性: {summary['field_completeness_score']:.2f}")
        print(f"   内容保存率: {summary['content_preservation_score']:.2f}")
        print(f"   上下文完整性: {summary['context_integrity_score']:.2f}")
        print(f"   状态: {summary['status']}")
        
        if report["critical_issues"]:
            print(f"\n⚠️  发现 {len(report['critical_issues'])} 个关键问题")
            for issue in report["critical_issues"]:
                print(f"   - {issue['type']}: {issue.get('news_id')}")


if __name__ == "__main__":
    main()