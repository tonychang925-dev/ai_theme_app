"""v3.0-A: W2SSignal 统一信号格式。

刻意对齐 Alpha Pilot SignalDecision 结构。
后续 DecisionEngine 就绪时直接 ensure_decision() 包装，不建转换层。

第一版只做兼容输出：旧对象保留，通过 to_w2s_signal() adapter 转换。
"""
from __future__ import annotations

import uuid, os, json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))


def generate_trace_id() -> str:
    return f"trace_{datetime.now(TZ_CN).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


def current_run_id() -> str:
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

    signal_id: str              # {biz_date}:{stock_id}:{stage}:{scorer_version}:{source_chain}
    stage: str                  # d1_candidate | auction_confirm | support_observe | intraday_observe
    scorer_version: str         # v2.2（当前默认）

    stock_code: str
    stock_name: str
    theme_name: str = ""

    scores: dict[str, float] = field(default_factory=dict)
    evidence: list[dict[str, str]] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    alert_level: str = "observation"   # observation | watch | alert | decision

    trace_id: str = ""
    run_id: str = ""
    biz_date: str = ""
    event_time: str = ""
    source_chain: str = "realtime"     # realtime | backtest_replay | shadow

    factor_snapshot: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = generate_trace_id()
        if not self.run_id:
            self.run_id = current_run_id()
        if not self.event_time:
            self.event_time = now_iso()

    def to_dict(self) -> dict[str, str]:
        """序列化为扁平 str dict，用于 Redis Stream 推送。"""
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


def w2s_signal_from_unified_alert(alert) -> W2SSignal:
    """v3.0-A: 兼容适配器 — UnifiedW2SAlert → W2SSignal。

    不修改旧 dataclass，作为独立函数提供。旧对象只需有对应属性即可工作。
    """
    stage = getattr(alert, "phase", "intraday")
    if stage not in ("auction", "intraday"):
        stage = "intraday_observe"

    unified = getattr(alert, "unified_level", "")
    if unified == "high_confidence":
        alert_level = "alert"
    elif unified in ("turn_observe", "early_observe"):
        alert_level = "watch"
    elif unified == "risk":
        alert_level = "observation"
    else:
        alert_level = "observation"

    intraday_score = getattr(alert, "intraday_score", 0) or 0
    d2_score = getattr(alert, "d2_score", 0) or 0

    scores = {
        "final": intraday_score if intraday_score else d2_score,
        "auction": d2_score,
        "intraday": intraday_score,
    }

    evidence = []
    for r in (getattr(alert, "evidence_rules", None) or []):
        evidence.append({"type": "rule", "text": str(r)})
    d2_level = getattr(alert, "d2_level", "")
    if d2_level:
        evidence.append({"type": "auction", "text": f"竞价确认: {d2_level}"})
    intraday_level = getattr(alert, "intraday_level", "")
    if intraday_level:
        evidence.append({"type": "intraday", "text": f"盘中信号: {intraday_level}"})

    risk_flags = []
    if getattr(alert, "capital_flow", "") == "outflow":
        risk_flags.append("竞价资金净流出")
    if getattr(alert, "chase_risk_penalty", 0) > 10:
        risk_flags.append("追高风险")

    trade_date = str(getattr(alert, "trade_date", ""))
    stock_id = str(getattr(alert, "stock_id", ""))

    return W2SSignal(
        signal_id=f"{trade_date}:{stock_id}:{stage}:v2.2:realtime",
        stage=stage,
        scorer_version="v2.2",
        stock_code=stock_id,
        stock_name=str(getattr(alert, "stock_name", "")),
        theme_name=str(getattr(alert, "theme_name", "")),
        scores=scores,
        evidence=evidence,
        risk_flags=risk_flags,
        alert_level=alert_level,
        trace_id=generate_trace_id(),
        run_id=current_run_id(),
        biz_date=trade_date,
        event_time=str(getattr(alert, "generated_at", "") or now_iso()),
        source_chain="realtime",
        factor_snapshot={
            "d2_level": d2_level,
            "d2_score": d2_score,
            "auction_open_pct": getattr(alert, "auction_open_pct", 0),
            "carry_ratio": getattr(alert, "carry_ratio", 0),
            "capital_flow": getattr(alert, "capital_flow", ""),
            "capital_imbalance": getattr(alert, "capital_imbalance", 0),
            "intraday_level": intraday_level,
            "intraday_score": intraday_score,
            "relative_strength_cross_zero": getattr(alert, "relative_strength_cross_zero", False),
            "above_vwap": getattr(alert, "above_vwap_ratio", 0) > 0,
            "support_state": str(getattr(alert, "support_state", "")),
            "chase_risk_penalty": getattr(alert, "chase_risk_penalty", 0),
            "break_platform_30m": getattr(alert, "break_platform_30m", False),
            "amount_acceleration": getattr(alert, "amount_acceleration", False),
            "unified_level": unified,
        },
    )


# ── factor_snapshot 字段规范 ──
# D1 候选层: d1_candidate_score, weak_type, support_type, support_strength
# D2 竞价层: auction_level, auction_score, auction_data_status, auction_risk_flags
# D3 盘中层: intraday_scorer_version, relative_strength_cross_zero, above_vwap,
#            support_state, early_turn, platform_break_30m, amount_acceleration
# 环境层:   market_regime, subject_regime, market_risk_flags
