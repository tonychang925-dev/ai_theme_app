"""P2-4: DecisionEngine — 统一决策层 facade。

组合 MarketState / SupportSignal / W2SSignal，输出 SignalDecision。
不替换现有前端主链路，不落库，不发 SSE。
仅作 facade 闭环验证。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from core.contracts.decision import (
    SignalDecision, Evidence, ALERT, WATCH, OBSERVATION,
    ensure_decision,
)

logger = logging.getLogger("engines.decision")

TZ_CN = timezone(timedelta(hours=8))


class DecisionEngine:
    """统一决策引擎 facade。

    只组合已有 facade 输出，不重写任何 scorer。
    """

    def accept_support_signal(self, signal) -> SignalDecision:
        """接受 SupportSignal，转为统一决策。"""
        try:
            from engines.support_engine.service import SupportSignal as SS
            is_support = isinstance(signal, SS)
        except ImportError:
            is_support = False

        if is_support:
            raw = {
                "stock_code": signal.stock_code,
                "stock_name": signal.stock_name,
                "support_type": signal.support_type,
                "support_price": signal.support_price,
                "current_price": signal.current_price,
                "distance_pct": signal.distance_pct,
                "support_strength": signal.support_strength,
                "alert_type": signal.alert_type,
                "source": "SupportEngine",
            }
        else:
            raw = dict(signal) if isinstance(signal, dict) else {"source": "unknown"}

        return ensure_decision(raw, decision_type="support_alert", level=self._map_level(signal))

    def accept_w2s_signal(self, signal) -> SignalDecision:
        """接受 W2SSignal，转为统一决策。"""
        raw = {
            "stock_id": getattr(signal, "stock_code", ""),
            "stock_name": getattr(signal, "stock_name", ""),
            "theme_name": getattr(signal, "theme_name", ""),
            "w2s_score": getattr(signal, "w2s_score", 0),
            "candidate_level": getattr(signal, "candidate_level", ""),
            "d2_score": getattr(signal, "d2_score", 0),
            "auction_open_pct": getattr(signal, "auction_open_pct", 0),
            "carry_ratio": getattr(signal, "carry_ratio", 0),
            "source": "W2SEngine",
        }

        decision = ensure_decision(raw, decision_type="w2s_alert", level=self._map_level(signal))

        # 添加 evidence
        if getattr(signal, "evidence", None):
            for e in signal.evidence:
                decision.evidence.append(Evidence("w2s", str(e)))
        if getattr(signal, "risk_flags", None):
            for r in signal.risk_flags:
                decision.risk_flags.append(str(r))

        # 添加 scores
        scores = {}
        for field in ("w2s_score", "d2_score", "support_safety_score", "theme_mainline_score", "auction_bonus"):
            val = getattr(signal, field, 0) or 0
            if val > 0:
                scores[field] = float(val)
        if scores:
            decision.scores.update(scores)
            existing = [v for v in decision.scores.values() if v > 0]
            if existing:
                decision.scores["final_score"] = round(sum(existing) / len(existing), 1)

        return decision

    def to_feed_item(self, decision: SignalDecision) -> dict:
        """转为 Intel Feed 兼容格式。"""
        return decision.to_feed_item()

    def _map_level(self, signal) -> str:
        """从信号推断决策级别。"""
        level = getattr(signal, "signal_level", None) or getattr(signal, "candidate_level", "")
        if level in ("alert", "strong_watch"):
            return ALERT
        if level in ("watch",):
            return WATCH
        return OBSERVATION
