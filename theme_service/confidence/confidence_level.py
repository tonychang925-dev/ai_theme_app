from enum import Enum
from typing import Tuple


class ConfidenceLevel(str, Enum):
    STRONG = "strong"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    IGNORE = "ignore"

def confidence_to_level(confidence: float) -> Tuple[ConfidenceLevel, int]:
    """
    将连续置信度映射为离散层级 + 权重
    返回：(level, weight)
    weight 用于后续题材聚合
    """

    if confidence >= 0.99:
        return ConfidenceLevel.STRONG, 100
    elif confidence >= 0.7:
        return ConfidenceLevel.HIGH, 70
    elif confidence >= 0.4:
        return ConfidenceLevel.MEDIUM, 40
    elif confidence >= 0.2:
        return ConfidenceLevel.LOW, 20
    else:
        return ConfidenceLevel.IGNORE, 0
