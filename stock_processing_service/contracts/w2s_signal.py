"""v3.0-A: W2SSignal 统一信号格式。

刻意对齐 Alpha Pilot SignalDecision 结构。
后续 DecisionEngine 就绪时直接 ensure_decision() 包装，不建转换层。

第一版只做兼容输出：旧对象保留，通过 to_w2s_signal() adapter 转换。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))


def generate_trace_id() -> str:
    return f"trace_{datetime.now(TZ_CN).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


def current_run_id() -> str:
    """从环境变量读取 runtime run_id，fallback 为 session 级 ID。"""
    import os
    return os.environ.get("RUNTIME_RUN_ID", f"session_{datetime.now(TZ_CN).strftime('%Y%m%d')}")


def now_iso() -> str:
    return datetime.now(TZ_CN).isoformat()


@dataclass
class W2SSignal:
    """W2S 统一信号格式。

    字段设计原则：
    - scores / evidence / risk_flags 对齐 Alpha Pilot SignalDecision 结构
    - alert_level 对齐 Alpha Pilot §8 告警分层（observation/watch/alert/decision）
    - trace_id / run_id / source_chain 对齐 Envelope 追踪字段
    - factor_snapshot 保留多版本可比性（D1/D2/D3/market 全部因子）
    """

    # ── 身份标识 ──
    signal_id: str              # {biz_date}:{stock_id}:{stage}:{scorer_version}:{source_chain}
    stage: str                  # d1_candidate | auction_confirm | support_observe | intraday_observe
    scorer_version: str         # v2.2（当前默认）

    # ── 标的信息 ──
    stock_code: str
    stock_name: str
    theme_name: str = ""

    # ── 评分（对齐 SignalDecision.scores）──
    scores: dict[str, float] = field(default_factory=dict)
    # 例: {"final": 81, "w2s": 78, "support": 86, "auction": 72, "rel_cross_zero": 1}

    # ── 证据与风险（对齐 SignalDecision.evidence / risk_flags）──
    evidence: list[dict[str, str]] = field(default_factory=list)
    # 例: [{"type": "support", "text": "回踩缺口支撑未破"}]
    risk_flags: list[str] = field(default_factory=list)

    # ── 告警分层（对齐 Alpha Pilot §8）──
    alert_level: str = "observation"   # observation | watch | alert | decision

    # ── 溯源（对齐 Envelope）──
    trace_id: str = ""
    run_id: str = ""
    biz_date: str = ""
    event_time: str = ""
    source_chain: str = "realtime"     # realtime | backtest_replay | shadow

    # ── 因子快照（多版本可比性）──
    factor_snapshot: dict[str, Any] = field(default_factory=dict)
    # 包含 D1/D2/D3/market 全部因子，见 factor_snapshot 字段规范

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = generate_trace_id()
        if not self.run_id:
            self.run_id = current_run_id()
        if not self.event_time:
            self.event_time = now_iso()

    def to_dict(self) -> dict[str, Any]:
        """序列化为扁平 dict，用于 Redis Stream 推送。"""
        import json
        return {
            "signal_id": self.signal_id,
            "stage": self.stage,
            "scorer_version": self.scorer_version,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "theme_name": self.theme_name,
            "scores": json.dumps(self.scores, ensure_ascii=False),
            "evidence": json.dumps(self.evidence, ensure_ascii=False),
            "risk_flags": json.dumps(self.risk_flags, ensure_ascii=False),
            "alert_level": self.alert_level,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "biz_date": self.biz_date,
            "event_time": self.event_time,
            "source_chain": self.source_chain,
            "factor_snapshot": json.dumps(self.factor_snapshot, ensure_ascii=False, default=str),
            "item_type": f"w2s_signal_{self.alert_level}",
        }


# ── factor_snapshot 字段规范 ──
#
# 每条 W2SSignal 的 factor_snapshot 应包含以下字段（按阶段分）：
#
# D1 候选层:
#   d1_candidate_score: float
#   weak_type: str            # bad_limit_up | big_negative_line | upper_shadow | ...
#   support_type: str         # previous_low | gap_support | ma_support | ...
#   support_strength: float
#
# D2 竞价层:
#   auction_level: str        # A / B / C / X / proxy_A / proxy_B / missing
#   auction_score: float
#   auction_data_status: str  # real_auction | auction_snapshot | daily_open_proxy | missing
#   auction_risk_flags: list[str]
#
# D3 盘中层:
#   intraday_scorer_version: str   # v2.2
#   relative_strength_cross_zero: bool
#   above_vwap: bool
#   support_state: str             # near / touch / break / recover
#   early_turn: bool
#   platform_break_30m: bool
#   amount_acceleration: bool
#
# 环境层:
#   market_regime: str       # panic / weak / neutral / strong
#   subject_regime: str      # hot / neutral / cooling / decline
#   market_risk_flags: list[str]
