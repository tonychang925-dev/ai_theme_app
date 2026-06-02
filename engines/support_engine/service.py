"""P2-2: SupportEngine — 支撑状态识别 facade。

包装现有 KlineBreakDetector，不重写检测逻辑。
等接口稳定后，逐步内聚核心逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))
logger = logging.getLogger("engines.support")

# ── signal level ──
OBSERVATION = "observation"
WATCH = "watch"
ALERT = "alert"


@dataclass
class SupportSignal:
    """统一支撑信号结构。"""
    stock_code: str = ""
    stock_name: str = ""
    support_type: str = ""
    support_price: float = 0.0
    current_price: float = 0.0
    distance_pct: float = 0.0
    support_strength: float = 0.0
    support_safety: float = 0.0
    confidence: float = 0.0
    alert_type: str = ""
    signal_level: str = WATCH
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(TZ_CN).isoformat())
    raw: dict[str, Any] = field(default_factory=dict)


class SupportEngine:
    """支撑引擎 facade。

    第一阶段只做 facade 封装，内部委托给现有的 KlineBreakDetector。
    """

    def __init__(self, dsn: str | None = None, redis_url: str = "redis://localhost:6379/0"):
        self._dsn = dsn
        self._redis_url = redis_url

    async def detect(self) -> list[SupportSignal]:
        """执行一轮支撑检测，返回标准化信号列表。

        委托给现有的 KlineBreakDetector.detect()。
        """
        try:
            from stock_processing_service.domain.services.kline_break_detector import (
                KlineBreakDetector,
            )
            detector = KlineBreakDetector(
                self._dsn or "postgresql://localhost:5432/stock_data_test",
                redis_url=self._redis_url,
            )
            result = await detector.detect()

            signals: list[SupportSignal] = []
            for alert in result.alerts:
                sig = SupportSignal(
                    stock_code=str(getattr(alert, "stock_id", "")),
                    stock_name=str(getattr(alert, "stock_name", "")),
                    support_type=str(getattr(alert, "support_type", "")),
                    support_price=float(getattr(alert, "support_level", 0) or 0),
                    current_price=float(getattr(alert, "current", 0) or 0),
                    distance_pct=float(getattr(alert, "distance_pct", 0) or 0),
                    support_strength=float(getattr(alert, "support_strength", 0) or 0),
                    support_safety=self._calc_safety(alert),
                    confidence=float(getattr(alert, "confidence", 0) or 0),
                    alert_type=str(getattr(alert, "alert_type", "")),
                    signal_level=self._infer_level(alert),
                    evidence=self._build_evidence(alert),
                    raw={"source": "KlineBreakDetector", "severity": str(getattr(alert, "severity", ""))},
                )
                signals.append(sig)

            return signals
        except ImportError:
            logger.warning("KlineBreakDetector not available")
            return []
        except Exception as exc:
            logger.warning("SupportEngine.detect failed: %s", exc)
            return []

    def _calc_safety(self, alert: Any) -> float:
        """估算支撑安全性：距离越远越安全。"""
        try:
            dist = abs(float(getattr(alert, "distance_pct", 0) or 0))
            strength = float(getattr(alert, "support_strength", 50) or 50) / 100.0
            # 距离 >5% = 安全 1.0，距离 0% = 0.0，线性插值
            dist_score = min(dist / 5.0, 1.0)
            return round((dist_score * 0.6 + strength * 0.4) * 100, 1)
        except (ValueError, TypeError):
            return 50.0

    def _infer_level(self, alert: Any) -> str:
        severity = str(getattr(alert, "severity", "")).lower()
        if severity in ("critical", "error"):
            return ALERT
        if severity == "warning":
            return WATCH
        return OBSERVATION

    def _build_evidence(self, alert: Any) -> list[str]:
        evidence: list[str] = []
        try:
            stype = str(getattr(alert, "support_type", ""))
            slevel = float(getattr(alert, "support_level", 0) or 0)
            dist = float(getattr(alert, "distance_pct", 0) or 0)
            if stype and slevel > 0:
                sign = "+" if dist > 0 else ""
                evidence.append(f"{stype} 支撑位 {slevel:.2f}，距离 {sign}{dist:.2f}%")
        except (ValueError, TypeError):
            pass
        return evidence
