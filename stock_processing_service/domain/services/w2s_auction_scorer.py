"""P2-B-1: W2SAuctionScorer — 6 项竞价信号 + hard reject."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.contracts.dto import StockAuctionDTO


@dataclass(frozen=True)
class AuctionScore:
    stock_id: str
    auction_score: Decimal
    risk_score: Decimal
    final_score: Decimal
    decision: str           # A / B / C / X
    evidence_rules: list[str]


class W2SAuctionScorer:
    """P2-B-1: 接入 carry_ratio / shape / stability / last_minute + hard reject。"""

    # ── shape feature 正向加分 ──
    _SHAPE_BONUS = {
        "inverted_l_uphill": 20,
        "red_staircase": 18,
        "cone_u_shape": 15,
        "upward_hook": 15,
        "inverted_l_u_shape": 12,
        "staircase_up": 12,
        "step_up": 12,
        "u_recovery": 12,
        "tail_upturn": 10,
        "red_zone": 5,
    }

    # ── shape feature 负向惩罚 ──
    _SHAPE_PENALTY = {
        "sharp_drop": 30,
        "volatile": 20,
        "result_only_mode": 10,
        "single_point_snapshot": 10,
    }

    def score_one(self, auction: StockAuctionDTO) -> AuctionScore:
        open_pct = auction.auction_open_pct or Decimal("0")
        auction_amt = auction.auction_amount or Decimal("0")
        carry = auction.carry_ratio or Decimal("0")
        stability = auction.price_path_stability_score or Decimal("50")
        last_min = auction.last_minute_ratio or Decimal("0")
        shapes = auction.shape_features or ()

        evidence: list[str] = [f"open_pct={open_pct}", f"auction_amount={auction_amt}"]

        # ── hard reject (先于打分) ──
        hard = self._check_hard_reject(auction)
        if hard:
            return AuctionScore(
                stock_id=auction.stock_id,
                auction_score=Decimal("0"),
                risk_score=Decimal("100"),
                final_score=Decimal("0"),
                decision="X",
                evidence_rules=evidence + hard,
            )

        # ── 6 项信号 ──
        open_signal = self._score_open_pct(open_pct)
        evidence.append(f"open_signal={open_signal:.1f}")

        carry_signal = self._score_carry_ratio(carry)
        evidence.append(f"carry_ratio={carry} carry_signal={carry_signal:.1f}")

        amount_signal = self._score_amount(auction_amt)
        evidence.append(f"amount_signal={amount_signal:.1f}")

        shape_signal, shape_evidence = self._score_shape(shapes)
        evidence.append(f"shape_features={list(shapes)} shape_signal={shape_signal:.1f}")
        evidence.extend(shape_evidence)

        stability_signal = self._score_stability(stability)
        evidence.append(f"stability={stability} stability_signal={stability_signal:.1f}")

        last_minute_signal = self._score_last_minute(last_min)
        evidence.append(f"last_minute_ratio={last_min} last_minute_signal={last_minute_signal:.1f}")

        # ── 加权 ──
        auction_score = (
            open_signal * Decimal("0.20")
            + carry_signal * Decimal("0.25")
            + amount_signal * Decimal("0.15")
            + shape_signal * Decimal("0.15")
            + stability_signal * Decimal("0.15")
            + last_minute_signal * Decimal("0.10")
        )

        # ── 额外风险 ──
        risk = Decimal("0")
        if auction_amt < Decimal("500000"):
            risk += Decimal("15")
            evidence.append("risk:auction_amount_lt_500k")
        if carry < Decimal("0.3"):
            risk += Decimal("10")
            evidence.append("risk:carry_ratio_lt_0.3")
        if stability < Decimal("40"):
            risk += Decimal("10")
            evidence.append("risk:stability_lt_40")

        final = max(Decimal("0"), auction_score - risk)

        # ── high_open_trap: 降级而非直接 X ──
        force_max_decision = None
        if open_pct > Decimal("7") and carry < Decimal("0.5"):
            force_max_decision = "C"
            evidence.append(f"degrade:high_open_trap→max_C(open={open_pct},carry={carry})")
        if open_pct > Decimal("7") and stability < Decimal("40"):
            force_max_decision = "C"
            evidence.append(f"degrade:high_open_unstable→max_C(open={open_pct},stab={stability})")

        if final >= Decimal("75"):
            decision = "A"
        elif final >= Decimal("65"):
            decision = "B"
        elif final >= Decimal("55"):
            decision = "C"
        else:
            decision = "X"

        _decision_order = {"A": 0, "B": 1, "C": 2, "X": 3}
        if force_max_decision and _decision_order.get(decision, 9) < _decision_order.get(force_max_decision, 9):
            decision = force_max_decision

        return AuctionScore(
            stock_id=auction.stock_id,
            auction_score=auction_score,
            risk_score=risk,
            final_score=final,
            decision=decision,
            evidence_rules=evidence,
        )

    # ── 信号函数 ──

    @staticmethod
    def _score_open_pct(pct: Decimal) -> Decimal:
        if pct >= Decimal("5"):
            return Decimal("90")
        if pct >= Decimal("3"):
            return Decimal("80")
        if pct >= Decimal("1"):
            return Decimal("65")
        if pct >= Decimal("0"):
            return Decimal("50")
        if pct >= Decimal("-1"):
            return Decimal("35")
        return Decimal("20")

    @staticmethod
    def _score_carry_ratio(ratio: Decimal) -> Decimal:
        """PDF 核心规则: 9:25量 vs 昨日最大分时量."""
        if ratio >= Decimal("1.0"):
            return Decimal("100")
        if ratio >= Decimal("0.5"):
            return Decimal("80")
        if ratio >= Decimal("0.3"):
            return Decimal("55")
        return Decimal("30")

    @staticmethod
    def _score_amount(amt: Decimal) -> Decimal:
        return max(Decimal("0"), min(Decimal("100"), amt / Decimal("2000000") * Decimal("100")))

    @classmethod
    def _score_shape(cls, shapes: tuple[str, ...]) -> tuple[Decimal, list[str]]:
        bonus = Decimal("0")
        penalty = Decimal("0")
        evidence: list[str] = []
        for s in shapes:
            if s in cls._SHAPE_BONUS:
                b = cls._SHAPE_BONUS[s]
                bonus += Decimal(str(b))
                evidence.append(f"shape_bonus:{s}=+{b}")
            elif s in cls._SHAPE_PENALTY:
                p = cls._SHAPE_PENALTY[s]
                penalty += Decimal(str(p))
                evidence.append(f"shape_penalty:{s}=-{p}")
        # bonus capped at 40, penalty uncapped
        return max(Decimal("0"), min(Decimal("100"), Decimal("50") + bonus - penalty)), evidence

    @staticmethod
    def _score_stability(score: Decimal) -> Decimal:
        """price_path_stability_score 直接映射."""
        if score >= Decimal("80"):
            return Decimal("90")
        if score >= Decimal("60"):
            return Decimal("70")
        if score >= Decimal("40"):
            return Decimal("50")
        return Decimal("25")

    @staticmethod
    def _score_last_minute(ratio: Decimal) -> Decimal:
        """9:24-9:25 抢筹比例."""
        if ratio >= Decimal("0.4"):
            return Decimal("95")
        if ratio >= Decimal("0.3"):
            return Decimal("80")
        if ratio >= Decimal("0.2"):
            return Decimal("60")
        if ratio >= Decimal("0.1"):
            return Decimal("40")
        return Decimal("20")

    # ── hard reject ──

    def _check_hard_reject(self, auction: StockAuctionDTO) -> list[str] | None:
        reasons: list[str] = []
        open_pct = auction.auction_open_pct or Decimal("0")
        carry = auction.carry_ratio or Decimal("0")
        stability = auction.price_path_stability_score or Decimal("50")

        if auction.has_end_drop:
            reasons.append("hard_reject:has_end_drop")
        if any(s in (auction.shape_features or ()) for s in ("sharp_drop", "volatile")):
            bad = [s for s in auction.shape_features if s in ("sharp_drop", "volatile")]
            reasons.append(f"hard_reject:shape={','.join(bad)}")
        if stability < Decimal("30"):
            reasons.append(f"hard_reject:stability={stability}")
        if carry < Decimal("0.2"):
            reasons.append(f"hard_reject:carry_ratio={carry}")
        if open_pct < Decimal("-1"):
            reasons.append(f"hard_reject:open_pct={open_pct}")
        # high_open_trap 移到加权段做降级（max C），不在此处 X
        if open_pct > Decimal("7") and auction.has_end_drop:
            reasons.append(f"hard_reject:high_open_with_drop(open={open_pct})")

        return reasons if reasons else None
