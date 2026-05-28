"""P2-3: W2SEngine — 弱转强候选识别 facade。

包装现有 W2SUnifiedAlertService，不重写 scorer，不改评分权重。
等接口稳定后，逐步内聚核心逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))
logger = logging.getLogger("engines.w2s")

# ── candidate levels ──
STRONG_WATCH = "strong_watch"
WATCH = "watch"
OBSERVE = "observe"


@dataclass
class W2SSignal:
    """统一弱转强信号结构。"""
    stock_code: str = ""
    stock_name: str = ""
    theme_id: str = ""
    theme_name: str = ""
    w2s_score: float = 0.0
    candidate_level: str = OBSERVE
    candidate_type: str = ""
    weak_type: str = ""

    # 分项评分
    d2_score: float = 0.0
    above_vwap: bool = False
    relative_strength_score: float = 0.0
    platform_break_score: float = 0.0
    amount_accel_score: float = 0.0
    support_safety_score: float = 0.0
    theme_mainline_score: float = 0.0
    auction_bonus: float = 0.0

    # 竞价
    auction_open_pct: float = 0.0
    carry_ratio: float = 0.0

    evidence: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(TZ_CN).isoformat())
    raw: dict[str, Any] = field(default_factory=dict)


class W2SEngine:
    """弱转强引擎 facade。

    第一阶段只做 facade 封装，内部委托给现有的 W2SUnifiedAlertService。
    不重写 scorer，不改评分权重。
    """

    def __init__(self, dsn: str | None = None, redis_url: str = "redis://localhost:6379/0"):
        self._dsn = dsn
        self._redis_url = redis_url

    async def evaluate_auction(self, candidate_date: str, confirm_date: str) -> list[W2SSignal]:
        """竞价确认阶段弱转强评估。"""
        try:
            from stock_processing_service.domain.services.w2s_unified_alert_service import (
                W2SUnifiedAlertService,
            )
            svc = W2SUnifiedAlertService(
                self._dsn or "postgresql://localhost:5432/stock_data_test",
                redis_url=self._redis_url,
            )
            alerts = await svc.build_auction_alerts(candidate_date, confirm_date)
            return [self._to_signal(a, phase="auction") for a in alerts]
        except ImportError:
            logger.warning("W2SUnifiedAlertService not available")
            return []
        except Exception as exc:
            logger.warning("W2SEngine.evaluate_auction failed: %s", exc)
            return []

    def _to_signal(self, alert: Any, phase: str = "auction") -> W2SSignal:
        """将 UnifiedW2SAlert 转为标准 W2SSignal。"""
        d2_score = float(getattr(alert, "d2_score", 0) or 0)
        intraday_score = float(getattr(alert, "intraday_score", 0) or 0)
        confirm_level = str(getattr(alert, "d2_level", "") or "")

        # 综合评分
        if phase == "auction":
            w2s_score = d2_score
        else:
            w2s_score = max(d2_score, intraday_score)

        # candidate_level 推断
        if confirm_level in ("A",):
            level = STRONG_WATCH
        elif confirm_level in ("B",):
            level = WATCH
        else:
            level = OBSERVE

        sig = W2SSignal(
            stock_code=str(getattr(alert, "stock_id", "")),
            stock_name=str(getattr(alert, "stock_name", "")),
            theme_name=str(getattr(alert, "theme_name", "")),
            w2s_score=round(w2s_score, 1),
            candidate_level=level,
            candidate_type=str(getattr(alert, "candidate_type", "")),
            weak_type=str(getattr(alert, "weak_type", "")),
            d2_score=round(d2_score, 1),
            auction_open_pct=float(getattr(alert, "auction_open_pct", 0) or 0),
            carry_ratio=float(getattr(alert, "carry_ratio", 0) or 0),
            raw={"source": "W2SUnifiedAlertService", "phase": phase},
        )

        # evidence
        if sig.candidate_type:
            sig.evidence.append(f"候选类型: {sig.candidate_type}")
        if sig.d2_score > 0:
            sig.evidence.append(f"D2 竞价确认分: {sig.d2_score}")
        if sig.carry_ratio > 0:
            sig.evidence.append(f"延续比率: {sig.carry_ratio:.2f}")

        # risk_flags
        if confirm_level == "C":
            sig.risk_flags.append("C 级确认偏弱，需盘中验证")
        if float(getattr(alert, "auction_open_pct", 0) or 0) < 0:
            sig.risk_flags.append("竞价低开，注意开盘方向")

        return sig
