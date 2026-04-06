from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from stock_service.models import PreMarketAuctionSignal, PreMarketAuctionSnapshot


def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


@dataclass(frozen=True)
class AuctionCandidateInput:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    role_label: str
    is_main_theme: bool
    action_bias: str
    position_label: str = ""
    pattern_labels: tuple[str, ...] = ()
    is_reversal_watch: bool = False


@dataclass(frozen=True)
class AuctionTimelinePoint:
    ts: str
    price: float
    amount: float


@dataclass(frozen=True)
class AuctionSnapshotInput:
    candidate: AuctionCandidateInput
    pre_close: float
    auction_open_price: float
    auction_volume: float
    auction_amount: float
    prev_day_max_intraday_amount: float
    last_minute_amount: float
    points: tuple[AuctionTimelinePoint, ...]


class AuctionSignalService:
    """
    P3.phase3 盘前竞价承接验证最小骨架：
    - 只处理前一晚已筛出的候选池
    - 先生成竞价事实快照
    - 再基于硬规则给出盘前信号
    """

    ALLOWED_ROLES = {"龙头", "龙二", "卡位", "强趋势"}

    def candidate_priority(self, candidate: AuctionCandidateInput) -> str:
        if candidate.role_label in {"龙头", "龙二", "卡位"}:
            return "P1"
        if candidate.role_label == "强趋势" or candidate.is_reversal_watch:
            return "P2"
        return "P3"

    def is_candidate_eligible(self, candidate: AuctionCandidateInput) -> bool:
        if candidate.role_label not in self.ALLOWED_ROLES and not candidate.is_reversal_watch:
            return False
        if candidate.is_main_theme:
            return True
        return candidate.action_bias in {"关注弱转强", "试错"}

    def compute_open_pct(self, pre_close: float, auction_open_price: float) -> float:
        if pre_close <= 0:
            return 0.0
        return round((auction_open_price - pre_close) / pre_close * 100.0, 4)

    def compute_last_minute_ratio(self, auction_amount: float, last_minute_amount: float) -> float:
        if auction_amount <= 0:
            return 0.0
        return round(last_minute_amount / auction_amount, 4)

    def compute_carry_ratio(self, auction_amount: float, prev_day_max_intraday_amount: float) -> float:
        if prev_day_max_intraday_amount <= 0:
            return 0.0
        return round(auction_amount / prev_day_max_intraday_amount, 4)

    def detect_end_drop(self, points: Iterable[AuctionTimelinePoint]) -> bool:
        rows = list(points)
        if len(rows) < 2:
            return False
        return rows[-1].price < rows[-2].price * 0.995

    def detect_end_spike(self, auction_amount: float, last_minute_amount: float, points: Iterable[AuctionTimelinePoint]) -> bool:
        rows = list(points)
        if len(rows) < 2 or auction_amount <= 0:
            return False
        return last_minute_amount / auction_amount >= 0.35 and rows[-1].price >= rows[-2].price

    def compute_price_path_stability_score(self, points: Iterable[AuctionTimelinePoint]) -> float:
        rows = list(points)
        if len(rows) <= 1:
            return 50.0
        prices = [max(row.price, 0.0) for row in rows]
        base = prices[0] if prices[0] > 0 else max(prices)
        if base <= 0:
            return 0.0
        jumps = 0
        max_drawdown = 0.0
        peak = prices[0]
        for prev, cur in zip(prices, prices[1:]):
            change_pct = abs(cur - prev) / base * 100.0
            if change_pct >= 0.8:
                jumps += 1
            peak = max(peak, cur)
            drawdown = (peak - cur) / base * 100.0
            max_drawdown = max(max_drawdown, drawdown)
        score = 100.0 - jumps * 12.0 - max_drawdown * 18.0
        if self.detect_end_drop(rows):
            score -= 18.0
        return _clip(score)

    def derive_shape_features(self, points: Iterable[AuctionTimelinePoint], auction_open_pct: float, has_end_spike: bool) -> list[str]:
        rows = list(points)
        if not rows:
            return []
        prices = [row.price for row in rows]
        features: list[str] = []
        if auction_open_pct > 0:
            features.append("red_zone")
        if len(prices) >= 3 and prices[-1] > prices[0] and sum(1 for a, b in zip(prices, prices[1:]) if b >= a) >= max(2, len(prices) - 2):
            features.append("step_up")
        if len(prices) >= 4:
            trough = min(prices)
            trough_idx = prices.index(trough)
            if 0 < trough_idx < len(prices) - 1 and prices[-1] >= prices[0]:
                features.append("u_recovery")
        if has_end_spike:
            features.append("tail_upturn")
        return features

    def build_snapshot(self, payload: AuctionSnapshotInput) -> PreMarketAuctionSnapshot:
        auction_open_pct = self.compute_open_pct(payload.pre_close, payload.auction_open_price)
        last_minute_ratio = self.compute_last_minute_ratio(payload.auction_amount, payload.last_minute_amount)
        carry_ratio = self.compute_carry_ratio(payload.auction_amount, payload.prev_day_max_intraday_amount)
        stability_score = self.compute_price_path_stability_score(payload.points)
        has_end_drop = self.detect_end_drop(payload.points)
        has_end_spike = self.detect_end_spike(payload.auction_amount, payload.last_minute_amount, payload.points)
        shape_features = self.derive_shape_features(payload.points, auction_open_pct, has_end_spike)
        return PreMarketAuctionSnapshot(
            trade_date=payload.candidate.trade_date,
            stock_id=payload.candidate.stock_id,
            stock_name=payload.candidate.stock_name,
            subject_key=payload.candidate.subject_key,
            theme_name=payload.candidate.theme_name,
            role_label=payload.candidate.role_label,
            auction_open_price=round(payload.auction_open_price, 4),
            pre_close=round(payload.pre_close, 4),
            auction_open_pct=auction_open_pct,
            auction_volume=round(payload.auction_volume, 2),
            auction_amount=round(payload.auction_amount, 2),
            last_minute_amount=round(payload.last_minute_amount, 2),
            last_minute_ratio=last_minute_ratio,
            prev_day_max_intraday_amount=round(payload.prev_day_max_intraday_amount, 2),
            carry_ratio=carry_ratio,
            price_path_stability_score=stability_score,
            is_red_zone=auction_open_pct > 0,
            has_end_spike=has_end_spike,
            has_end_drop=has_end_drop,
            shape_features=shape_features,
        )

    def _stability_score(self, snapshot: PreMarketAuctionSnapshot) -> float:
        return _clip(snapshot.price_path_stability_score)

    def _carry_ratio_score(self, snapshot: PreMarketAuctionSnapshot) -> float:
        if snapshot.carry_ratio >= 0.5:
            return 100.0
        if snapshot.carry_ratio >= 0.3:
            return 60.0
        return 20.0

    def _end_spike_score(self, snapshot: PreMarketAuctionSnapshot) -> float:
        if snapshot.has_end_spike:
            return 100.0
        if snapshot.last_minute_ratio >= 0.2:
            return 55.0
        return 20.0

    def _open_pct_score(self, snapshot: PreMarketAuctionSnapshot) -> float:
        pct = snapshot.auction_open_pct
        if 3.0 <= pct <= 5.0:
            return 100.0
        if 0.0 <= pct < 3.0:
            return 60.0
        if pct > 7.0:
            return 50.0
        return 20.0

    def _red_zone_score(self, snapshot: PreMarketAuctionSnapshot) -> float:
        return 100.0 if snapshot.is_red_zone else 20.0

    def _prior_role_boost(self, snapshot: PreMarketAuctionSnapshot) -> float:
        mapping = {
            "龙头": 100.0,
            "龙二": 85.0,
            "卡位": 75.0,
            "强趋势": 65.0,
        }
        return mapping.get(snapshot.role_label, 30.0)

    def compute_signal_score(self, snapshot: PreMarketAuctionSnapshot) -> float:
        score = (
            0.25 * self._stability_score(snapshot)
            + 0.20 * self._carry_ratio_score(snapshot)
            + 0.20 * self._end_spike_score(snapshot)
            + 0.15 * self._open_pct_score(snapshot)
            + 0.10 * self._red_zone_score(snapshot)
            + 0.10 * self._prior_role_boost(snapshot)
        )
        return _clip(score)

    def detect_hard_reject_reason(self, snapshot: PreMarketAuctionSnapshot, candidate: AuctionCandidateInput) -> str:
        if snapshot.price_path_stability_score < 30.0:
            return "路径不稳"
        if snapshot.has_end_drop:
            return "末端跳水"
        if snapshot.carry_ratio < 0.2:
            return "承接不足"
        if snapshot.auction_open_pct < -1.0:
            return "低开不及预期"
        if not candidate.is_main_theme and candidate.action_bias == "放弃":
            return "非主线降级"
        return ""

    def derive_signal_level(self, score: float, hard_reject_reason: str) -> str:
        if hard_reject_reason:
            return "invalid"
        if score >= 75.0:
            return "strong"
        if score >= 50.0:
            return "watch"
        return "weak"

    def derive_signal_type(self, snapshot: PreMarketAuctionSnapshot, level: str) -> str:
        if level == "invalid":
            return "情绪转弱"
        if snapshot.role_label == "龙头" and level == "strong":
            return "龙头承接强"
        if snapshot.role_label in {"龙二", "卡位"} and level == "strong":
            return "卡位加强"
        if "u_recovery" in snapshot.shape_features and level in {"strong", "watch"}:
            return "弱转强候选"
        return "跟风无承接" if level == "weak" else "弱转强候选"

    def derive_leader_status(self, snapshot: PreMarketAuctionSnapshot, level: str) -> str:
        if level == "invalid":
            return "放弃"
        if snapshot.role_label == "龙头" and level == "strong":
            return "继续成立"
        if snapshot.role_label in {"龙二", "卡位"} and level == "strong":
            return "有上位可能"
        if level == "watch":
            return "观察承接"
        return "放弃"

    def derive_action_today(self, level: str) -> str:
        if level == "strong":
            return "act"
        if level == "watch":
            return "watch"
        return "avoid"

    def build_evidence(self, snapshot: PreMarketAuctionSnapshot, signal_score: float, hard_reject_reason: str) -> list[str]:
        evidence = [
            f"竞价高开 {snapshot.auction_open_pct:.2f}%",
            f"承接比 {snapshot.carry_ratio:.2f}",
            f"最后一分钟占比 {snapshot.last_minute_ratio:.2f}",
            f"稳定性 {snapshot.price_path_stability_score:.2f}",
        ]
        return evidence

    def build_signal_evidence(
        self,
        snapshot: PreMarketAuctionSnapshot,
        candidate: AuctionCandidateInput,
        signal_score: float,
        hard_reject_reason: str,
    ) -> list[str]:
        evidence = self.build_evidence(snapshot, signal_score, hard_reject_reason)
        if candidate.position_label:
            evidence.append(f"K线位置 {candidate.position_label}")
        if candidate.pattern_labels:
            evidence.append(f"K线形态 {'/'.join(candidate.pattern_labels)}")
        if snapshot.shape_features:
            evidence.append("形态特征 " + ", ".join(snapshot.shape_features))
        if hard_reject_reason:
            evidence.append(f"否决原因 {hard_reject_reason}")
        else:
            evidence.append(f"竞价评分 {signal_score:.2f}")
        return evidence

    def build_signal(self, snapshot: PreMarketAuctionSnapshot, candidate: AuctionCandidateInput) -> PreMarketAuctionSignal:
        hard_reject_reason = self.detect_hard_reject_reason(snapshot, candidate)
        signal_score = self.compute_signal_score(snapshot)
        signal_level = self.derive_signal_level(signal_score, hard_reject_reason)
        return PreMarketAuctionSignal(
            trade_date=snapshot.trade_date,
            stock_id=snapshot.stock_id,
            stock_name=snapshot.stock_name,
            subject_key=snapshot.subject_key,
            theme_name=snapshot.theme_name,
            role_label=snapshot.role_label,
            auction_signal_score=signal_score,
            auction_signal_level=signal_level,
            signal_type=self.derive_signal_type(snapshot, signal_level),
            leader_status=self.derive_leader_status(snapshot, signal_level),
            action_today=self.derive_action_today(signal_level),
            hard_reject_reason=hard_reject_reason,
            evidence=self.build_signal_evidence(snapshot, candidate, signal_score, hard_reject_reason),
            source_trace_id=snapshot.source_trace_id,
            source_trace={
                "snapshot_source_type": snapshot.source_type,
                "snapshot_rule_version": snapshot.rule_version,
                "shape_features": snapshot.shape_features,
                "position_label": candidate.position_label,
                "pattern_labels": list(candidate.pattern_labels),
            },
        )
