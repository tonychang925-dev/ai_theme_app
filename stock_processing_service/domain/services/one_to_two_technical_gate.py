"""OneToTwoTechnicalGate — K-line technical-form focus-cap gate.

Stage 2 Commit 5: standalone service. Not wired into RuleEngine yet.

Rules (v1):
  support_broken=true                     → reject
  is_downtrend=true                       → reject
  near_pressure=true                      → cap_focus  (NOT hard reject)
  kline_data_ready=false                  → cap_focus
  has_golden_spider=false AND score<55    → cap_focus
  has_golden_spider=true  OR  score>=68   → pass
  otherwise                               → unknown (treat as cap_focus)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures

VALID_STATUSES = frozenset({"pass", "cap_focus", "reject", "unknown"})

# -- score thresholds used by both TechnicalGate and Scorer --
TECHNICAL_FOCUS_SCORE_THRESHOLD = Decimal("55")
TECHNICAL_GOLDEN_SCORE_THRESHOLD = Decimal("68")


@dataclass(frozen=True, slots=True)
class TechnicalGateResult:
    status: str  # pass | cap_focus | reject | unknown
    technical_score: Decimal
    veto_reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    focus_cap_reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid technical gate status: {self.status!r}")


class OneToTwoTechnicalGate:
    """Evaluate K-line technical form for OneToTwo focus permission.

    Does NOT read Layer C or D1.
    Does NOT modify features.
    Does NOT upgrade observe_only → focus.
    """

    def evaluate(self, f: OneToTwoFeatures) -> TechnicalGateResult:
        kline = dict(f.kline_pattern_quality or {})

        # --- extract facts ---
        kline_data_ready = bool(kline.get("kline_data_ready"))
        kline_score_raw = kline.get("score")
        kline_score = self._to_decimal(kline_score_raw, None)
        has_golden_spider = bool(kline.get("has_golden_spider"))
        support_broken = bool(kline.get("support_broken"))
        kline_is_downtrend = bool(kline.get("is_downtrend"))

        # --- compute technical score ---
        technical_score = self._compute_technical_score(
            kline_data_ready=kline_data_ready,
            has_golden_spider=has_golden_spider,
            kline_score=kline_score,
            is_downtrend=bool(f.is_downtrend or kline_is_downtrend),
            near_pressure=bool(f.near_pressure),
            support_broken=support_broken,
        )

        # --- gate rules ---
        veto: list[str] = []
        risk: list[str] = []
        cap_reason: str | None = None

        # Hard reject
        if bool(f.is_downtrend or kline_is_downtrend):
            veto.append("下降趋势")
        if support_broken:
            veto.append("支撑破坏")

        if veto:
            return TechnicalGateResult(
                status="reject",
                technical_score=technical_score,
                veto_reasons=veto,
                risk_flags=risk,
                detail={
                    "kline_data_ready": kline_data_ready,
                    "has_golden_spider": has_golden_spider,
                    "kline_score": float(kline_score) if kline_score is not None else None,
                    "support_broken": support_broken,
                    "is_downtrend": bool(f.is_downtrend or kline_is_downtrend),
                    "near_pressure": bool(f.near_pressure),
                },
            )

        # Cap focus (not hard reject)
        if not kline_data_ready:
            cap_reason = "K线数据不足，暂不 focus"
            risk.append(cap_reason)
        elif bool(f.near_pressure):
            cap_reason = "重要压力位附近，暂不 focus"
            risk.append(cap_reason)
        elif not has_golden_spider and (kline_score is None or kline_score < TECHNICAL_FOCUS_SCORE_THRESHOLD):
            cap_reason = "技术形态未确认，暂不 focus"
            risk.append(cap_reason)

        if cap_reason:
            return TechnicalGateResult(
                status="cap_focus",
                technical_score=technical_score,
                veto_reasons=[],
                risk_flags=risk,
                focus_cap_reason=cap_reason,
                detail={
                    "kline_data_ready": kline_data_ready,
                    "has_golden_spider": has_golden_spider,
                    "kline_score": float(kline_score) if kline_score is not None else None,
                    "support_broken": support_broken,
                    "is_downtrend": bool(f.is_downtrend or kline_is_downtrend),
                    "near_pressure": bool(f.near_pressure),
                    "cap_reason": cap_reason,
                },
            )

        # Pass
        return TechnicalGateResult(
            status="pass",
            technical_score=technical_score,
            veto_reasons=[],
            risk_flags=[],
            detail={
                "kline_data_ready": kline_data_ready,
                "has_golden_spider": has_golden_spider,
                "kline_score": float(kline_score) if kline_score is not None else None,
                "support_broken": support_broken,
                "is_downtrend": bool(f.is_downtrend or kline_is_downtrend),
                "near_pressure": bool(f.near_pressure),
            },
        )

    @classmethod
    def _compute_technical_score(
        cls,
        *,
        kline_data_ready: bool,
        has_golden_spider: bool,
        kline_score: Decimal | None,
        is_downtrend: bool,
        near_pressure: bool,
        support_broken: bool,
    ) -> Decimal:
        if is_downtrend:
            return Decimal("0")
        if not kline_data_ready:
            return Decimal("25")
        if near_pressure:
            return Decimal("30")
        if support_broken:
            return Decimal("20")
        if kline_score is not None:
            return Decimal(str(round(float(kline_score), 2)))
        if has_golden_spider:
            return Decimal("90")
        return Decimal("45")

    @staticmethod
    def _to_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
        if value is None or value == "":
            return default
        try:
            return Decimal(str(value))
        except Exception:
            return default
