from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class ThemeState:
    theme_state_id: str
    theme_id: str
    theme_name: str
    trade_date: date

    # 热度与强度
    heat_score: float
    strength_score: float
    confidence_score: float

    # 生命周期
    lifecycle_stage: str

    # 事件支撑
    event_count: int
    core_event_id: Optional[str]
    event_consistency: float

    # 行情验证
    avg_stock_return: float
    limit_up_count: int
    limit_down_count: int
    capital_inflow: Optional[float]

    # 龙头结构
    leader_stock_code: Optional[str]
    leader_strength: Optional[float]
    top3_concentration: float

    # 输出控制
    is_active: bool
    is_recommended: bool
    output_priority: int
