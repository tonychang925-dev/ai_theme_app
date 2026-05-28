"""P1-3: 统一 Decision 结构 — 告警收口层。

不修改现有 scorer 逻辑，只做 facade 封装。
所有告警先包装为 SignalDecision，再决定是否展示。

告警分层:
  L0 noise       — 不展示
  L1 observation — 后台/日志
  L2 watch       — 前端弱提示
  L3 alert       — Intel 页面
  L4 decision    — 盘前必读/盘中置顶
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

CST = timezone(timedelta(hours=8))

# ── 告警级别 ──

NOISE = "noise"
OBSERVATION = "observation"
WATCH = "watch"
ALERT = "alert"
DECISION = "decision"

LEVEL_RANK: dict[str, int] = {
    NOISE: 0,
    OBSERVATION: 1,
    WATCH: 2,
    ALERT: 3,
    DECISION: 4,
}

# ── 决策类型 ──

DECISION_TYPES = {
    "event_news": "新闻事件",
    "theme_match": "题材匹配",
    "event_review": "待复核",
    "support_alert": "支撑告警",
    "w2s_alert": "弱转强告警",
    "auction_alert": "竞价观察",
    "market_alert": "盘中异动",
    "decision": "综合决策",
    "report": "报告项",
}


@dataclass
class Evidence:
    type: str
    text: str


@dataclass
class SignalDecision:
    """统一决策输出结构。"""

    decision_id: str = field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}")
    decision_type: str = ""           # event_news | support_alert | w2s_alert | ...
    level: str = WATCH                # noise | observation | watch | alert | decision
    trace_id: str = ""

    stock_code: str = ""
    stock_name: str = ""
    theme_id: str = ""
    theme_name: str = ""

    title: str = ""
    summary: str = ""

    scores: dict[str, float] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    suggested_action: str = "watch"   # watch | ignore | review | alert
    expires_at: str = ""

    source_type: str = ""
    source_channel: str = ""
    biz_date: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(CST).isoformat())

    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [{"type": e["type"], "text": e["text"]} for e in d["evidence"]]
        d["schema_type"] = "SignalDecision"
        return d

    def to_feed_item(self) -> dict:
        """转为 Intel Feed item 格式（兼容现有前端）。"""
        return {
            "item_id": self.decision_id,
            "item_type": self.decision_type,
            "source_type": self.source_type or "decision",
            "source_channel": self.source_channel or "decision_engine",
            "title": self.title,
            "summary": self.summary,
            "stock_id": self.stock_code,
            "stock_name": self.stock_name,
            "theme_name": self.theme_name,
            "confidence": self.scores.get("final_score", 0) / 100.0,
            "impact_score": int(self.scores.get("final_score", 50)),
            "occurred_at": self.created_at,
            "driver_title": self.title,
            "driver_desc": self.summary,
            "review_required": self.level == OBSERVATION,
            "decision_level": self.level,
        }


def _safe_float(v: any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _extract_scores(alert: dict, d: SignalDecision) -> None:
    """P1-3.5: 从原始告警中提取数值评分。"""

    # support 相关
    strength = _safe_float(alert.get("support_strength"))
    distance = _safe_float(alert.get("distance_pct"))
    confidence = _safe_float(alert.get("confidence"))

    if strength > 0:
        d.scores["support_strength"] = round(strength, 1)
    if abs(distance) > 0:
        d.scores["distance_pct"] = round(distance, 2)
    if confidence > 0:
        d.scores["confidence"] = round(confidence, 2)

    # W2S / auction 相关
    confirm_score = _safe_float(alert.get("confirm_score"))
    d2_score = _safe_float(alert.get("d2_score"))
    intraday_score = _safe_float(alert.get("intraday_score"))
    relative_strength = _safe_float(alert.get("relative_strength"))

    if confirm_score > 0:
        d.scores["confirm_score"] = round(confirm_score, 1)
    if d2_score > 0:
        d.scores["d2_score"] = round(d2_score, 1)
    if intraday_score > 0:
        d.scores["intraday_score"] = round(intraday_score, 1)
    if relative_strength > 0:
        d.scores["relative_strength"] = round(relative_strength, 1)

    # Intel / event 相关
    impact_score = _safe_float(alert.get("impact_score"))
    if impact_score > 0:
        d.scores["impact_score"] = round(impact_score, 1)

    # 综合 final_score：取已提取分数的加权平均
    existing = [v for v in d.scores.values() if v > 0]
    if existing:
        d.scores["final_score"] = round(sum(existing) / len(existing), 1)


def ensure_decision(
    alert: dict,
    decision_type: str = "",
    level: str = ALERT,
    **overrides,
) -> SignalDecision:
    """将现有告警包装为统一 SignalDecision。

    不修改原始 scorer，只做 facade 适配。
    """
    d = SignalDecision(
        decision_type=decision_type or alert.get("item_type", alert.get("alert_type", "")),
        level=level,
        trace_id=str(alert.get("trace_id") or alert.get("item_id", "")),
        stock_code=str(alert.get("stock_id", "")),
        stock_name=str(alert.get("stock_name", "")),
        theme_name=str(alert.get("theme_name", "")),
        title=str(alert.get("title") or f"{alert.get('stock_name', '')} {alert.get('alert_type', '')}"),
        summary=str(alert.get("summary", "")),
        source_type=str(alert.get("source_type", "")),
        source_channel=str(alert.get("source_channel", "")),
        biz_date=str(alert.get("biz_date", alert.get("trade_date", ""))),
        raw=dict(alert),
    )

    # 从现有字段推断 evidence
    if alert.get("support_type"):
        d.evidence.append(Evidence("support",
            f"{alert.get('support_type')} 支撑位 {alert.get('support_level', '?')}，"
            f"距离 {alert.get('distance_pct', '?')}%"))
    if alert.get("confirm_score"):
        d.evidence.append(Evidence("auction",
            f"竞价确认分 {alert.get('confirm_score')}，开盘 {alert.get('auction_open_pct', '?')}%"))

    # 风险标记
    if alert.get("distance_pct"):
        try:
            dist = float(alert["distance_pct"])
            if dist < 1.0:
                d.risk_flags.append("已触及支撑位，需关注是否破位")
            elif dist < 3.0:
                d.risk_flags.append("接近支撑位，若破位信号失效")
        except (ValueError, TypeError):
            pass

    # P1-3.5: 自动提取 scores
    _extract_scores(alert, d)

    for k, v in overrides.items():
        if hasattr(d, k):
            setattr(d, k, v)

    return d
