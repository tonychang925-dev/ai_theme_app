# evaluate_service/scripts/metric_calculator.py
"""
指标计算工具
提供各种评估指标的计算方法
"""
import numpy as np
from typing import Dict, List, Any, Optional
import statistics
from datetime import datetime

class MetricCalculator:
    """指标计算器"""
    
    @staticmethod
    def calculate_success_rate(successful: int, total: int) -> float:
        """计算成功率"""
        return successful / max(total, 1)
    
    @staticmethod
    def calculate_average(values: List[float]) -> float:
        """计算平均值"""
        if not values:
            return 0.0
        return sum(values) / len(values)
    
    @staticmethod
    def calculate_median(values: List[float]) -> float:
        """计算中位数"""
        if not values:
            return 0.0
        return statistics.median(values)
    
    @staticmethod
    def calculate_std_dev(values: List[float]) -> float:
        """计算标准差"""
        if not values or len(values) < 2:
            return 0.0
        return statistics.stdev(values)
    
    @staticmethod
    def calculate_percentile(values: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not values:
            return 0.0
        return np.percentile(values, percentile)
    
    @staticmethod
    def calculate_completeness_score(field_presence: Dict[str, bool]) -> float:
        """计算完整性分数"""
        if not field_presence:
            return 0.0
        return sum(field_presence.values()) / len(field_presence)
    
    @staticmethod
    def calculate_confidence_interval(values: List[float], confidence: float = 0.95) -> tuple:
        """计算置信区间"""
        if not values or len(values) < 2:
            return (0.0, 0.0)
        
        mean = np.mean(values)
        std_err = np.std(values) / np.sqrt(len(values))
        z_score = 1.96  # 95%置信度对应的Z分数
        
        lower = mean - z_score * std_err
        upper = mean + z_score * std_err
        return (lower, upper)
    
    @staticmethod
    def analyze_distribution(values: List[float]) -> Dict[str, Any]:
        """分析数值分布"""
        if not values:
            return {"error": "没有数据"}
        
        return {
            "count": len(values),
            "mean": np.mean(values),
            "median": np.median(values),
            "std": np.std(values),
            "min": np.min(values),
            "max": np.max(values),
            "q1": np.percentile(values, 25),
            "q3": np.percentile(values, 75),
            "range": np.max(values) - np.min(values)
        }
    
    @staticmethod
    def calculate_correlation(x: List[float], y: List[float]) -> Optional[float]:
        """计算相关系数"""
        if len(x) != len(y) or len(x) < 2:
            return None
        
        try:
            return np.corrcoef(x, y)[0, 1]
        except:
            return None