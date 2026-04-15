from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from stock_service.services.weak_to_strong_auction_data_adapter import AuctionFeatureRow


@dataclass
class AuctionScoreBreakdown:
    price_strength: float
    pattern_stability: float
    last_minute_grab: float
    plate_follow: float
    risk_penalty: float
    confirmation_score: float
    hard_reject_reasons: List[str]
    signal_level: str
    decision: str


class WeakToStrongAuctionScorer:
    """按 v1.1 文档执行盘前竞价评分与分级。"""
    A_THRESHOLD = 65.0
    B_THRESHOLD = 52.0

    def score(self, row: AuctionFeatureRow) -> AuctionScoreBreakdown:
        hard_rejects = self._hard_rule_check(row)
        if row.data_status in {"missing", "delayed"}:
            hard_rejects.append(f"data_status={row.data_status}")

        if hard_rejects:
            return AuctionScoreBreakdown(
                price_strength=0.0,
                pattern_stability=0.0,
                last_minute_grab=0.0,
                plate_follow=0.0,
                risk_penalty=0.0,
                confirmation_score=0.0,
                hard_reject_reasons=hard_rejects,
                signal_level="X" if row.data_status in {"missing", "delayed"} else "C",
                decision="no_decision" if row.data_status in {"missing", "delayed"} else "reject",
            )

        price_strength = self._price_strength(row)
        pattern_stability = self._pattern_stability(row)
        last_minute_grab = self._last_minute_grab(row)
        plate_follow = self._plate_follow(row)
        risk_penalty = self._risk_penalty(row)
        confirmation_score = max(
            0.0, min(price_strength + pattern_stability + last_minute_grab + plate_follow - risk_penalty, 100.0)
        )

        if confirmation_score >= self.A_THRESHOLD:
            level, decision = "A", "confirmed"
        elif confirmation_score >= self.B_THRESHOLD:
            level, decision = "B", "watch"
        else:
            level, decision = "C", "reject"

        return AuctionScoreBreakdown(
            price_strength=round(price_strength, 2),
            pattern_stability=round(pattern_stability, 2),
            last_minute_grab=round(last_minute_grab, 2),
            plate_follow=round(plate_follow, 2),
            risk_penalty=round(risk_penalty, 2),
            confirmation_score=round(confirmation_score, 2),
            hard_reject_reasons=[],
            signal_level=level,
            decision=decision,
        )

    def _hard_rule_check(self, row: AuctionFeatureRow) -> List[str]:
        reasons: List[str] = []
        # 1) 必须来自候选池（当前输入已满足，保留检查）
        if row.candidate_id <= 0:
            reasons.append("not_in_candidate_pool")
        # 2) 9:20-9:25 不可大起大落（用波动代理）
        if row.auction_path_volatility > 70.0:
            reasons.append("volatility_too_high")
        # 3) 最后一分钟抢筹/承接
        if row.need_last_minute_grab and not (row.last_minute_volume_ratio >= 0.20 or row.price_lift_last_minute):
            reasons.append("no_last_minute_grab")
        # 4) 竞价结束需红盘或接近强承接位：
        # 轻微低开（>-1%）不做硬否决，交由扣分项处理；
        # 明显低开且承接弱，才判定为硬否决。
        if row.auction_close_pct < -1.0 and row.support_strength < 30:
            reasons.append("close_not_red_and_support_weak")
        # 5) 不可尾段急跌
        if row.tail_drop_flag:
            reasons.append("tail_drop")
        # 6) 板块不可明显退潮
        if row.need_plate_follow and row.plate_red_ratio < 0.20:
            reasons.append("plate_retreat")
        return reasons

    def _price_strength(self, row: AuctionFeatureRow) -> float:
        score = 0.0
        # 预期开盘区间
        if row.expected_open_low <= row.auction_open_pct <= row.expected_open_high:
            score += 10.0
        elif row.auction_open_pct > row.expected_open_high:
            score += 6.0
        elif row.auction_open_pct >= -0.5:
            score += 4.0
        # 红盘/承接
        if row.auction_close_pct >= 0:
            score += 10.0
        elif row.support_strength >= 70:
            score += 7.0
        elif row.support_strength >= 55:
            score += 4.0
        # 尾值偏强（用尾段抬升代理）
        if row.price_lift_last_minute:
            score += 10.0
        elif row.last_minute_volume_ratio >= 0.2:
            score += 6.0
        # 轻微低开但稳定承接，给恢复补偿分（避免全部被负分压死）
        if -1.0 <= row.auction_close_pct < 0 and not row.tail_drop_flag and row.auction_path_volatility <= 55:
            score += 8.0
        return min(score, 30.0)

    def _pattern_stability(self, row: AuctionFeatureRow) -> float:
        score = 0.0
        # 波动越小越好
        if row.auction_path_volatility <= 15:
            score += 10.0
        elif row.auction_path_volatility <= 30:
            score += 8.0
        elif row.auction_path_volatility <= 50:
            score += 5.0
        # 尾段形态
        if row.price_lift_last_minute:
            score += 10.0
        elif not row.tail_drop_flag:
            score += 5.0
        # 急拉急砸控制
        if not row.tail_drop_flag:
            score += 5.0
        return min(score, 25.0)

    def _last_minute_grab(self, row: AuctionFeatureRow) -> float:
        score = 0.0
        if row.last_minute_volume_ratio >= 0.35:
            score += 10.0
        elif row.last_minute_volume_ratio >= 0.20:
            score += 7.0
        elif row.last_minute_volume_ratio >= 0.10:
            score += 4.0

        if row.price_lift_last_minute:
            score += 10.0
        elif row.auction_close_pct >= row.auction_open_pct:
            score += 6.0

        if row.last_minute_volume_ratio >= 0.20 and row.price_lift_last_minute:
            score += 5.0
        return min(score, 25.0)

    def _plate_follow(self, row: AuctionFeatureRow) -> float:
        score = 0.0
        red = row.plate_red_ratio
        lead = row.plate_leader_strength
        if red >= 0.65:
            score += 8.0
        elif red >= 0.45:
            score += 6.0
        elif red >= 0.30:
            score += 4.0

        if lead >= 0.50:
            score += 6.0
        elif lead >= 0.30:
            score += 4.0
        elif lead >= 0.15:
            score += 2.0

        if red >= 0.45 and lead >= 0.30:
            score += 6.0
        return min(score, 20.0)

    def _risk_penalty(self, row: AuctionFeatureRow) -> float:
        penalty = 0.0
        if row.tail_drop_flag:
            penalty += 12.0
        if row.auction_close_pct < 0:
            if row.auction_close_pct >= -1.0 and not row.tail_drop_flag:
                penalty += 4.0
            else:
                penalty += 6.0
        if row.auction_open_pct > max(row.expected_open_high + 3.0, 7.0):
            penalty += 6.0
        if row.plate_red_ratio < 0.30:
            penalty += 4.0
        return min(penalty, 30.0)

    def to_evidence(self, row: AuctionFeatureRow, breakdown: AuctionScoreBreakdown) -> Dict[str, object]:
        return {
            "schema_version": "evidence_schema.v1",
            "trace": {
                "trade_date": row.trade_date.isoformat(),
                "stock_id": row.stock_id,
                "candidate_id": row.candidate_id,
                "source_snapshot_id": row.source_snapshot_id,
            },
            "inputs": {
                "candidate_type": row.candidate_type,
                "rule_version": "weak_to_strong_auction.v1",
                "weak_type": "",
                "support_type": "",
                "expected_auction_pattern": "",
            },
            "scores": {
                "price_strength": breakdown.price_strength,
                "pattern_stability": breakdown.pattern_stability,
                "last_minute_grab": breakdown.last_minute_grab,
                "plate_follow": breakdown.plate_follow,
                "risk_penalty": breakdown.risk_penalty,
                "confirmation_score": breakdown.confirmation_score,
                "breakdown": {
                    "auction_open_pct": row.auction_open_pct,
                    "auction_path_volatility": row.auction_path_volatility,
                    "last_minute_volume_ratio": row.last_minute_volume_ratio,
                    "tail_drop_flag": row.tail_drop_flag,
                    "price_lift_last_minute": row.price_lift_last_minute,
                    "plate_red_ratio": row.plate_red_ratio,
                    "plate_leader_strength": row.plate_leader_strength,
                },
            },
            "rules": {
                "hard_rule_results": [
                    {"rule": "mvp_hard_rules", "passed": len(breakdown.hard_reject_reasons) == 0, "reason": ";".join(breakdown.hard_reject_reasons)},
                ],
                "mapping_warnings": [],
            },
            "decision": {
                "signal_level": breakdown.signal_level,
                "decision": breakdown.decision,
                "data_status": row.data_status,
                "data_latency_ms": row.data_latency_ms,
            },
        }
