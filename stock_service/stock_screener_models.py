"""
选股器数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, Any, List


@dataclass
class ScreeningStrategy:
    """选股策略"""
    strategy_id: str
    strategy_name: str
    strategy_type: str  # 'mainline', 'cycle', 'leader', 'technical', 'composite', 'weak_to_strong'
    description: str
    weight_config: Dict[str, float]  # {mainline: 0.35, cycle: 0.30, leader: 0.20, technical: 0.15}
    filter_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    is_active: bool = True


@dataclass
class DimensionScores:
    """各维度得分"""
    mainline: float  # 主线题材得分
    cycle: float     # 周期阶段得分
    leader: float    # 龙头判断得分
    technical: float # 技术面得分


@dataclass
class ScreeningResult:
    """选股结果"""
    stock_id: str
    stock_name: str
    composite_score: float  # 综合得分 (0-100)
    dimension_scores: DimensionScores
    result_id: Optional[str] = None
    strategy_id: Optional[str] = None
    trade_date: Optional[date] = None
    rank_position: Optional[int] = None  # 排名位置
    screening_reason: str = ""
    theme_info: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


@dataclass
class DimensionDetails:
    """各维度详情"""
    mainline: Dict[str, Any]
    cycle: Dict[str, Any]
    leader: Dict[str, Any]
    technical: Dict[str, Any]


@dataclass
class ScreeningResultDetail(ScreeningResult):
    """选股结果详情"""
    dimension_details: Optional[DimensionDetails] = None


@dataclass
class LlmReviewResult:
    """LLM复核结果"""
    result_id: str
    stock_id: str
    decision: str  # pass/watch/reject/failed
    llm_score: Optional[float] = None
    confidence: Optional[float] = None
    reasoning: str = ""
    risk_flags: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    model_name: Optional[str] = None
    prompt_version: str = "screener_llm_v1"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class UserFavorite:
    """用户收藏"""
    favorite_id: str
    user_id: str
    result_id: str
    notes: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ScreeningExecution:
    """选股执行记录"""
    execution_id: str
    strategy_id: str
    trade_date: date
    status: str  # 'pending', 'running', 'completed', 'failed'
    total_stocks: int = 0
    screened_stocks: int = 0
    results_count: int = 0
    execution_time_ms: int = 0
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class ScreeningStatistics:
    """选股统计"""
    total_executions: int
    avg_composite_score: float
    top_themes: List[Dict[str, Any]]
    score_distribution: List[Dict[str, Any]]


@dataclass
class ExportConfig:
    """导出配置"""
    format: str  # 'csv', 'excel', 'json'
    include_columns: List[str]
    filename: Optional[str] = None
    include_details: bool = False


# 默认策略配置
DEFAULT_STRATEGIES = [
    ScreeningStrategy(
        strategy_id="default_composite",
        strategy_name="综合选股策略",
        strategy_type="composite",
        description="基于35%/30%/20%/15%决策序列的默认综合选股策略",
        weight_config={
            "mainline": 0.35,
            "cycle": 0.30,
            "leader": 0.20,
            "technical": 0.15
        },
        filter_config={
            "min_composite_score": 60,
            "min_mainline_score": 50,
            "min_cycle_score": 50,
            "min_leader_score": 40,
            "min_technical_score": 40
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by="system",
        is_active=True
    ),
    ScreeningStrategy(
        strategy_id="mainline_focus",
        strategy_name="主线题材策略",
        strategy_type="mainline",
        description="侧重主线题材判断的选股策略",
        weight_config={
            "mainline": 0.60,
            "cycle": 0.20,
            "leader": 0.10,
            "technical": 0.10
        },
        filter_config={
            "min_composite_score": 65,
            "min_mainline_score": 70
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by="system",
        is_active=True
    ),
    ScreeningStrategy(
        strategy_id="cycle_timing",
        strategy_name="周期择时策略",
        strategy_type="cycle",
        description="侧重周期阶段判断的选股策略",
        weight_config={
            "mainline": 0.20,
            "cycle": 0.60,
            "leader": 0.10,
            "technical": 0.10
        },
        filter_config={
            "min_composite_score": 65,
            "min_cycle_score": 70
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by="system",
        is_active=True
    ),
    ScreeningStrategy(
        strategy_id="leader_following",
        strategy_name="龙头跟随策略",
        strategy_type="leader",
        description="侧重龙头判断的选股策略",
        weight_config={
            "mainline": 0.20,
            "cycle": 0.20,
            "leader": 0.50,
            "technical": 0.10
        },
        filter_config={
            "min_composite_score": 65,
            "min_leader_score": 70
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by="system",
        is_active=True
    ),
    ScreeningStrategy(
        strategy_id="weak_to_strong",
        strategy_name="弱转强策略",
        strategy_type="weak_to_strong",
        description="侧重弱转强信号识别的选股策略，重点关注分歧回流、支撑反弹等弱转强信号",
        weight_config={
            "mainline": 0.25,
            "cycle": 0.50,  # 弱转强主要关注周期阶段
            "leader": 0.15,
            "technical": 0.10
        },
        filter_config={
            "min_composite_score": 65,
            "min_cycle_score": 60,
            "weak_to_strong_required": True  # 新增：要求弱转强信号
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by="system",
        is_active=True
    ),
]
