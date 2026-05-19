"""v2.2 Auction Confirmation Service — New-Chain Domain Service.

Migrated from old-chain WeakToStrongAuctionScorer (stock_service/services/weak_to_strong_auction_scorer.py).
Pure business logic: NO SQL, NO I/O, NO asyncpg, NO production table writes.

Four-dimension scoring (100-point scale):
  - price_strength       0–30
  - pattern_stability    0–25
  - last_minute_grab     0–25
  - plate_follow         0–20
  - risk_penalty         0–30  (subtracted)
  ─────────────────────────────────
  - confirmation_score   0–100

Levels:
  A: >= 75  → confirmed
  B: >= 55  → watch
  C: <  55  → reject
  X: hard_reject (cannot trade)

data_status is the PRIMARY classifier:
  - real_auction:      full scoring, can output A/B/C/X
  - daily_open_proxy:  reduced scoring, outputs proxy_A/proxy_B/proxy_C/proxy_X
  - missing:           hard reject → X, reason=auction_data_missing
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

RULE_VERSION = "auction_confirmation.v2"


# ── Input DTOs ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CandidateAuctionContext:
    """D1 candidate context for D2 auction confirmation."""
    trade_date: date
    stock_id: str
    stock_name: str = ""
    subject_key: str = ""
    theme_name: str = ""
    candidate_score: float = 0.0
    candidate_type: str = "generic_repair"
    support_type: str = ""
    support_strength: float = 0.0
    support_level: float = 0.0
    weak_type: str = ""
    pool_entry_type: str = "formal"
    cycle_state: str = ""
    mainline_strength_score: float = 0.0
    fade_watch: bool = False
    fade_confirmed: bool = False
    expected_open_low: float = 0.0
    expected_open_high: float = 0.0
    need_last_minute_grab: bool = False
    need_plate_follow: bool = False


@dataclass(frozen=True)
class AuctionSnapshotData:
    """T+1 auction snapshot for a single stock (from pre_market_auction_snapshot)."""
    trade_date: date
    stock_id: str
    auction_open_pct: float = 0.0
    auction_amount: float = 0.0
    auction_volume: float = 0.0
    pre_close: float = 0.0
    # Stability & pattern
    price_path_stability_score: float = 0.0
    last_minute_ratio: float = 0.0
    has_end_spike: bool = False
    has_end_drop: bool = False
    is_red_zone: bool = False
    # Data provenance
    data_status: str = "missing"  # real_auction | daily_open_proxy | missing
    source_version: str = ""
    source_trace: dict[str, Any] = field(default_factory=dict)
    # Derived
    auction_close_pct: float = 0.0
    auction_high_pct: float = 0.0
    auction_low_pct: float = 0.0


@dataclass(frozen=True)
class BoardAuctionData:
    """Subject-level auction board context for plate follow scoring."""
    subject_key: str = ""
    plate_red_ratio: float = 0.0
    plate_leader_strength: float = 0.0


# ── Output DTO ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AuctionConfirmationResult:
    """Output of auction confirmation for a single candidate."""
    trade_date: date
    confirm_trade_date: date
    stock_id: str
    stock_name: str = ""
    subject_key: str = ""
    theme_name: str = ""

    # Scores
    auction_confirm_score: float = 0.0
    auction_confirm_level: str = "X"  # A | B | C | X | proxy_A | proxy_B | proxy_C | proxy_X
    auction_confirm_source: str = "missing"  # real_auction | daily_open_proxy | missing

    price_strength_score: float = 0.0
    pattern_stability_score: float = 0.0
    last_minute_grab_score: float = 0.0
    plate_follow_score: float = 0.0
    risk_penalty: float = 0.0

    # Decision
    decision: str = "no_decision"  # confirmed | watch | reject | observe_only | no_decision
    approved: bool = False

    # Rejection
    hard_reject_reasons: list[str] = field(default_factory=list)
    reject_reason: str = ""

    # Data provenance
    data_status: str = "missing"
    rule_version: str = RULE_VERSION

    # Evidence
    evidence_json: str = ""


# ── Service ─────────────────────────────────────────────────────────────────

class AuctionConfirmationService:
    """Confirm D1 candidates using T+1 auction data.

    Pure domain service: no SQL, no I/O, no external dependencies.
    Migrated from old-chain WeakToStrongAuctionScorer.

    Usage::

        service = AuctionConfirmationService()
        result = service.confirm(candidate, auction, board)
    """

    A_THRESHOLD: float = 75.0
    B_THRESHOLD: float = 55.0

    # ── Public API ──────────────────────────────────────────────────────

    def confirm(
        self,
        candidate: CandidateAuctionContext,
        auction: AuctionSnapshotData | None,
        board: BoardAuctionData | None = None,
    ) -> AuctionConfirmationResult:
        """Confirm a single D1 candidate with T+1 auction data."""
        board = board or BoardAuctionData()
        confirm_date = auction.trade_date if auction else candidate.trade_date

        # ── data_status is the PRIMARY classifier ──
        data_status = auction.data_status if auction else "missing"

        # Missing → hard reject immediately
        if data_status == "missing" or auction is None:
            return AuctionConfirmationResult(
                trade_date=candidate.trade_date,
                confirm_trade_date=confirm_date,
                stock_id=candidate.stock_id,
                stock_name=candidate.stock_name,
                subject_key=candidate.subject_key,
                theme_name=candidate.theme_name,
                auction_confirm_source="missing",
                auction_confirm_level="X",
                data_status="missing",
                decision="no_decision",
                hard_reject_reasons=["data_status=missing", "auction_data_missing"],
                reject_reason="auction_data_missing",
                evidence_json=self._build_evidence(
                    candidate, None, board,
                    price_strength=0.0, pattern_stability=0.0,
                    last_minute_grab=0.0, plate_follow=0.0,
                    risk_penalty=0.0, confirm_score=0.0,
                    level="X", decision="no_decision",
                    hard_rejects=["data_status=missing", "auction_data_missing"],
                ),
            )

        # ── Run hard rules ──
        hard_rejects = self._hard_rules(candidate, auction, board)

        # Hard reject with observe_only handling
        if hard_rejects:
            if "pool_entry_not_formal" in hard_rejects:
                return self._make_result(
                    candidate, confirm_date, auction, board,
                    price_strength=0.0, pattern_stability=0.0,
                    last_minute_grab=0.0, plate_follow=0.0,
                    risk_penalty=0.0, confirm_score=0.0,
                    level="X", decision="observe_only",
                    hard_rejects=hard_rejects,
                )
            # data_status issues → X
            if data_status in {"missing", "delayed"}:
                return self._make_result(
                    candidate, confirm_date, auction, board,
                    price_strength=0.0, pattern_stability=0.0,
                    last_minute_grab=0.0, plate_follow=0.0,
                    risk_penalty=0.0, confirm_score=0.0,
                    level="X", decision="no_decision",
                    hard_rejects=hard_rejects,
                )
            return self._make_result(
                candidate, confirm_date, auction, board,
                price_strength=0.0, pattern_stability=0.0,
                last_minute_grab=0.0, plate_follow=0.0,
                risk_penalty=0.0, confirm_score=0.0,
                level="C", decision="reject",
                hard_rejects=hard_rejects,
            )

        # ── 4-dim scoring ──
        price_strength = self._price_strength(candidate, auction)
        pattern_stability = self._pattern_stability(auction)
        last_minute_grab = self._last_minute_grab(auction)
        plate_follow = self._plate_follow(board)
        risk_penalty = self._risk_penalty(candidate, auction, board)

        confirm_score = max(
            0.0,
            min(price_strength + pattern_stability + last_minute_grab + plate_follow - risk_penalty, 100.0),
        )

        # ── Level classification ──
        if data_status == "real_auction":
            # Full A/B/C/X
            if confirm_score >= self.A_THRESHOLD:
                level, decision = "A", "confirmed"
            elif confirm_score >= self.B_THRESHOLD:
                level, decision = "B", "watch"
            else:
                level, decision = "C", "reject"
        else:
            # Proxy → prefixed levels, cannot produce formal A/B/C
            if confirm_score >= self.A_THRESHOLD:
                level, decision = "proxy_A", "confirmed"
            elif confirm_score >= self.B_THRESHOLD:
                level, decision = "proxy_B", "watch"
            else:
                level, decision = "proxy_C", "reject"

        return self._make_result(
            candidate, confirm_date, auction, board,
            price_strength=round(price_strength, 2),
            pattern_stability=round(pattern_stability, 2),
            last_minute_grab=round(last_minute_grab, 2),
            plate_follow=round(plate_follow, 2),
            risk_penalty=round(risk_penalty, 2),
            confirm_score=round(confirm_score, 2),
            level=level, decision=decision,
            hard_rejects=[],
        )

    # ── Hard Rules (migrated from old-chain _hard_rule_check) ────────────

    def _hard_rules(
        self,
        candidate: CandidateAuctionContext,
        auction: AuctionSnapshotData,
        board: BoardAuctionData,
    ) -> list[str]:
        reasons: list[str] = []

        # 1) Data status gate: missing/delayed → hard reject
        if auction.data_status in {"missing", "delayed"}:
            reasons.append(f"data_status={auction.data_status}")

        # 2) Must come from candidate pool
        if not candidate.stock_id:
            reasons.append("not_in_candidate_pool")

        # 3) Fade confirmed → reject
        if candidate.fade_confirmed:
            reasons.append("fade_confirmed")

        # 4) Pool entry type gate: only formal gets full auction confirm
        if candidate.pool_entry_type != "formal":
            reasons.append("pool_entry_not_formal")

        # 5) Auction path volatility too high (9:20–9:25 unstable)
        volatility = max(0.0, 100.0 - auction.price_path_stability_score)
        if volatility > 70.0:
            reasons.append("volatility_too_high")

        # 6) Need last-minute grab but not present
        if candidate.need_last_minute_grab and not (
            auction.last_minute_ratio >= 0.20 or auction.has_end_spike
        ):
            reasons.append("no_last_minute_grab")

        # 7) Close not red AND support weak
        if auction.auction_close_pct < -1.0 and candidate.support_strength < 30.0:
            reasons.append("close_not_red_and_support_weak")

        # 8) Tail drop
        if auction.has_end_drop:
            reasons.append("tail_drop")

        # 9) Plate retreat
        if candidate.need_plate_follow and board.plate_red_ratio < 0.20 and not candidate.fade_watch:
            reasons.append("plate_retreat")

        return reasons

    # ── Price Strength (0–30) ───────────────────────────────────────────

    @staticmethod
    def _price_strength(
        candidate: CandidateAuctionContext,
        auction: AuctionSnapshotData,
    ) -> float:
        score = 0.0

        # Expected open range match
        if candidate.expected_open_low <= auction.auction_open_pct <= candidate.expected_open_high:
            score += 10.0
        elif auction.auction_open_pct > candidate.expected_open_high:
            score += 6.0
        elif auction.auction_open_pct >= -0.5:
            score += 4.0

        # Red zone / support-based acceptance
        if auction.auction_close_pct >= 0:
            score += 10.0
        elif candidate.support_strength >= 70:
            score += 7.0
        elif candidate.support_strength >= 55:
            score += 4.0

        # Tail lift
        if auction.has_end_spike:
            score += 10.0
        elif auction.last_minute_ratio >= 0.2:
            score += 6.0

        # Mild low-open with stable path — recovery bonus
        if (
            -1.0 <= auction.auction_close_pct < 0
            and not auction.has_end_drop
            and (100.0 - auction.price_path_stability_score) <= 55
        ):
            score += 8.0

        return min(score, 30.0)

    # ── Pattern Stability (0–25) ────────────────────────────────────────

    @staticmethod
    def _pattern_stability(auction: AuctionSnapshotData) -> float:
        score = 0.0
        volatility = max(0.0, 100.0 - auction.price_path_stability_score)

        # Lower volatility = better
        if volatility <= 15:
            score += 10.0
        elif volatility <= 30:
            score += 8.0
        elif volatility <= 50:
            score += 5.0

        # Tail pattern
        if auction.has_end_spike:
            score += 10.0
        elif not auction.has_end_drop:
            score += 5.0

        # No sharp reversal
        if not auction.has_end_drop:
            score += 5.0

        return min(score, 25.0)

    # ── Last Minute Grab (0–25) ─────────────────────────────────────────

    @staticmethod
    def _last_minute_grab(auction: AuctionSnapshotData) -> float:
        score = 0.0

        # Volume surge in last minute
        if auction.last_minute_ratio >= 0.35:
            score += 10.0
        elif auction.last_minute_ratio >= 0.20:
            score += 7.0
        elif auction.last_minute_ratio >= 0.10:
            score += 4.0

        # Price lift in last minute
        if auction.has_end_spike:
            score += 10.0
        elif auction.auction_close_pct >= auction.auction_open_pct:
            score += 6.0

        # Resonance: volume + price together
        if auction.last_minute_ratio >= 0.20 and auction.has_end_spike:
            score += 5.0

        return min(score, 25.0)

    # ── Plate Follow (0–20) ─────────────────────────────────────────────

    @staticmethod
    def _plate_follow(board: BoardAuctionData) -> float:
        score = 0.0
        red = board.plate_red_ratio
        lead = board.plate_leader_strength

        # Red ratio
        if red >= 0.65:
            score += 8.0
        elif red >= 0.45:
            score += 6.0
        elif red >= 0.30:
            score += 4.0

        # Leader strength
        if lead >= 0.50:
            score += 6.0
        elif lead >= 0.30:
            score += 4.0
        elif lead >= 0.15:
            score += 2.0

        # Resonance: red + leader both strong
        if red >= 0.45 and lead >= 0.30:
            score += 6.0

        return min(score, 20.0)

    # ── Risk Penalty (0–30) ─────────────────────────────────────────────

    @staticmethod
    def _risk_penalty(
        candidate: CandidateAuctionContext,
        auction: AuctionSnapshotData,
        board: BoardAuctionData,
    ) -> float:
        penalty = 0.0

        # Tail drop = strongest risk signal
        if auction.has_end_drop:
            penalty += 12.0

        # Fade watch
        if candidate.fade_watch:
            penalty += 3.0

        # Close negative
        if auction.auction_close_pct < 0:
            if auction.auction_close_pct >= -1.0 and not auction.has_end_drop:
                penalty += 4.0  # mild
            else:
                penalty += 6.0  # significant

        # Open too high (chasing risk)
        if auction.auction_open_pct > max(candidate.expected_open_high + 3.0, 7.0):
            penalty += 6.0

        # Weak plate
        if board.plate_red_ratio < 0.30:
            penalty += 4.0

        return min(penalty, 30.0)

    # ── Evidence Builder ─────────────────────────────────────────────────

    def _build_evidence(
        self,
        candidate: CandidateAuctionContext,
        auction: AuctionSnapshotData | None,
        board: BoardAuctionData,
        *,
        price_strength: float,
        pattern_stability: float,
        last_minute_grab: float,
        plate_follow: float,
        risk_penalty: float,
        confirm_score: float,
        level: str,
        decision: str,
        hard_rejects: list[str],
    ) -> str:
        evidence: dict[str, Any] = {
            "schema_version": "auction_confirmation_evidence.v1",
            "rule_version": RULE_VERSION,
            "trace": {
                "trade_date": candidate.trade_date.isoformat(),
                "confirm_trade_date": auction.trade_date.isoformat() if auction else "",
                "stock_id": candidate.stock_id,
            },
            "inputs": {
                "candidate_type": candidate.candidate_type,
                "support_type": candidate.support_type,
                "support_strength": candidate.support_strength,
                "pool_entry_type": candidate.pool_entry_type,
                "expected_open_low": candidate.expected_open_low,
                "expected_open_high": candidate.expected_open_high,
                "need_last_minute_grab": candidate.need_last_minute_grab,
                "need_plate_follow": candidate.need_plate_follow,
                "fade_watch": candidate.fade_watch,
                "fade_confirmed": candidate.fade_confirmed,
            },
            "scores": {
                "price_strength": price_strength,
                "pattern_stability": pattern_stability,
                "last_minute_grab": last_minute_grab,
                "plate_follow": plate_follow,
                "risk_penalty": risk_penalty,
                "confirmation_score": confirm_score,
                "breakdown": {
                    "auction_open_pct": auction.auction_open_pct if auction else None,
                    "auction_close_pct": auction.auction_close_pct if auction else None,
                    "price_path_stability_score": auction.price_path_stability_score if auction else None,
                    "last_minute_ratio": auction.last_minute_ratio if auction else None,
                    "has_end_spike": auction.has_end_spike if auction else None,
                    "has_end_drop": auction.has_end_drop if auction else None,
                    "plate_red_ratio": board.plate_red_ratio,
                    "plate_leader_strength": board.plate_leader_strength,
                    "data_status": auction.data_status if auction else "missing",
                },
            },
            "rules": {
                "hard_rule_results": [
                    {
                        "rule": "v2.2_hard_rules",
                        "passed": len(hard_rejects) == 0,
                        "reason": ";".join(hard_rejects) if hard_rejects else "all_passed",
                    }
                ],
                "mapping_warnings": [],
            },
            "decision": {
                "signal_level": level,
                "decision": decision,
                "data_status": auction.data_status if auction else "missing",
            },
        }
        return json.dumps(evidence, ensure_ascii=False)

    # ── Result Factory ───────────────────────────────────────────────────

    def _make_result(
        self,
        candidate: CandidateAuctionContext,
        confirm_date: date,
        auction: AuctionSnapshotData,
        board: BoardAuctionData,
        *,
        price_strength: float,
        pattern_stability: float,
        last_minute_grab: float,
        plate_follow: float,
        risk_penalty: float,
        confirm_score: float,
        level: str,
        decision: str,
        hard_rejects: list[str],
    ) -> AuctionConfirmationResult:
        # Determine source
        if auction.data_status == "real_auction":
            source = "real_auction"
        elif auction.data_status == "daily_open_proxy":
            source = "daily_open_proxy"
        else:
            source = "missing"

        # Determine approved
        approved = (
            hard_rejects == []
            and decision in {"confirmed", "watch"}
        )

        # Reject reason
        if hard_rejects:
            reject_reason = ";".join(hard_rejects)
        elif decision == "reject":
            reject_reason = "score_below_threshold"
        else:
            reject_reason = ""

        evidence_json = self._build_evidence(
            candidate, auction, board,
            price_strength=price_strength,
            pattern_stability=pattern_stability,
            last_minute_grab=last_minute_grab,
            plate_follow=plate_follow,
            risk_penalty=risk_penalty,
            confirm_score=confirm_score,
            level=level, decision=decision,
            hard_rejects=hard_rejects,
        )

        return AuctionConfirmationResult(
            trade_date=candidate.trade_date,
            confirm_trade_date=confirm_date,
            stock_id=candidate.stock_id,
            stock_name=candidate.stock_name,
            subject_key=candidate.subject_key,
            theme_name=candidate.theme_name,
            auction_confirm_score=confirm_score,
            auction_confirm_level=level,
            auction_confirm_source=source,
            price_strength_score=price_strength,
            pattern_stability_score=pattern_stability,
            last_minute_grab_score=last_minute_grab,
            plate_follow_score=plate_follow,
            risk_penalty=risk_penalty,
            decision=decision,
            approved=approved,
            hard_reject_reasons=hard_rejects,
            reject_reason=reject_reason,
            data_status=auction.data_status,
            rule_version=RULE_VERSION,
            evidence_json=evidence_json,
        )
