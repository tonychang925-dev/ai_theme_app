"""
题材质量指标计算 - 简化版本
"""
import logging
from typing import List, Dict, Any
import statistics

logger = logging.getLogger(__name__)

class ThemeQualityMetrics:
    """题材质量指标计算器"""
    
    @staticmethod
    def calculate_naming_quality(themes: List[str]) -> Dict[str, Any]:
        """计算命名质量"""
        if not themes:
            return {"score": 0, "reason": "无题材数据"}
        
        scores = []
        issues = []
        
        for theme in themes:
            score = 1.0
            
            # 检查长度
            if len(theme) < 2 or len(theme) > 10:
                score -= 0.3
                issues.append(f"题材'{theme}'长度不合适")
            
            # 检查是否包含宽泛词
            broad_terms = ["科技", "创新", "发展", "产业", "经济"]
            if any(term in theme for term in broad_terms):
                score -= 0.2
                issues.append(f"题材'{theme}'包含宽泛词")
            
            scores.append(max(0.0, min(1.0, score)))
        
        avg_score = statistics.mean(scores) if scores else 0
        
        return {
            "average_score": round(avg_score, 3),
            "min_score": round(min(scores), 3) if scores else 0,
            "max_score": round(max(scores), 3) if scores else 0,
            "issue_count": len(issues),
            "sample_issues": issues[:3]  # 只显示前3个问题
        }
    
    @staticmethod
    def calculate_duplication_rate(themes: List[str]) -> Dict[str, Any]:
        """计算重复率"""
        if not themes:
            return {"rate": 0, "reason": "无题材数据"}
        
        unique_themes = set(themes)
        total = len(themes)
        unique_count = len(unique_themes)
        
        duplication_rate = (total - unique_count) / total if total > 0 else 0
        
        # 找出重复的题材
        theme_counts = {}
        for theme in themes:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
        
        duplicate_groups = {theme: count for theme, count in theme_counts.items() if count > 1}
        
        return {
            "duplication_rate": round(duplication_rate, 3),
            "total_themes": total,
            "unique_themes": unique_count,
            "duplicate_groups_count": len(duplicate_groups),
            "duplicate_groups": list(duplicate_groups.items())[:5]  # 只显示前5组
        }
    
    @staticmethod
    def calculate_theme_coverage(true_themes: List[str], predicted_themes: List[str]) -> Dict[str, Any]:
        """计算题材覆盖率"""
        if not true_themes:
            return {"coverage": 0, "reason": "无真实题材数据"}
        
        true_set = set(true_themes)
        predicted_set = set(predicted_themes)
        
        matched = true_set & predicted_set
        coverage = len(matched) / len(true_set) if true_set else 0
        
        return {
            "coverage_rate": round(coverage, 3),
            "total_true_themes": len(true_set),
            "matched_themes": len(matched),
            "unmatched_themes": list(true_set - predicted_set)[:5]  # 只显示前5个未匹配的
        }
