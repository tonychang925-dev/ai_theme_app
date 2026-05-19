"""v2.3 Auction Timeline Feature Builder.

Computes D2-ready features from raw 09:20–09:25 auction timeline points.
Adapted from stock_service/services/auction_signal_service.py.

Pure domain service: NO SQL, NO I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TimelinePoint:
    """Single auction snapshot at a point in time."""
    snapshot_time: str    # '09:20:00' through '09:25:00'
    indicative_price: float
    indicative_open_pct: float
    matched_volume: float
    matched_amount: float


@dataclass
class AuctionTimelineFeature:
    """Computed features from a timeline of auction points."""
    trade_date: date
    stock_id: str
    stock_name: str = ""
    subject_key: str = ""
    theme_name: str = ""

    # Core
    open_pct_0925: float = 0.0
    price_trend_0920_0925: float = 0.0
    price_stability_score: float = 50.0
    last_minute_price_change: float = 0.0
    last_minute_volume_ratio: float = 0.0
    last_minute_grab_score: float = 0.0
    tail_drop_risk: float = 0.0
    auction_volume_ratio: float = 0.0

    # Patterns
    auction_pattern: str = "stable"
    shape_features: list[str] = field(default_factory=list)
    is_red_zone: bool = False
    has_end_spike: bool = False
    has_end_drop: bool = False

    # Quality
    data_status: str = "synthetic_single_point"
    timeline_points_count: int = 0
    timeline_points_snapshot: list[dict[str, Any]] = field(default_factory=list)

    # Source
    rule_version: str = "auction_feature.v2.3"
    source_trace: dict[str, Any] = field(default_factory=dict)


class AuctionTimelineFeatureBuilder:
    """Compute auction features from 09:20–09:25 timeline points.

    Adapted from AuctionSignalService methods:
      - compute_price_path_stability_score()
      - detect_end_drop()
      - detect_end_spike()
      - derive_shape_features()
      - compute_carry_ratio()
      - compute_last_minute_ratio()
    """

    @staticmethod
    def _clip(value: float, upper: float = 100.0) -> float:
        return max(0.0, min(upper, round(value, 2)))

    def build(
        self,
        trade_date: date,
        stock_id: str,
        points: list[TimelinePoint],
        *,
        prev_day_max_intraday_amount: float = 0.0,
        stock_name: str = "",
        subject_key: str = "",
        theme_name: str = "",
        source_trace: dict[str, Any] | None = None,
    ) -> AuctionTimelineFeature:
        """Compute features from auction timeline points."""
        if not points:
            return AuctionTimelineFeature(
                trade_date=trade_date,
                stock_id=stock_id,
                stock_name=stock_name,
                subject_key=subject_key,
                theme_name=theme_name,
                data_status="missing",
                timeline_points_count=0,
                source_trace=source_trace or {},
            )

        # Sort by time
        sorted_pts = sorted(points, key=lambda p: p.snapshot_time)
        n = len(sorted_pts)

        # ── Determine data_status ──
        if n >= 4:
            data_status = "real_auction_timeline"
        elif n >= 2:
            data_status = "partial_timeline"
        else:
            data_status = "synthetic_single_point"

        # ── Open at 09:25 (last point) ──
        last = sorted_pts[-1]
        first = sorted_pts[0]
        open_pct_0925 = last.indicative_open_pct

        # ── Price trend 09:20 → 09:25 ──
        price_trend = last.indicative_open_pct - first.indicative_open_pct

        # ── Price path stability ──
        stability = self._compute_stability(sorted_pts)

        # ── Last minute (09:24-09:25) ──
        last_minute_pts = [p for p in sorted_pts if p.snapshot_time >= "09:24:00"]
        lm_price_change, lm_volume_ratio = self._last_minute_metrics(last_minute_pts, last)

        # ── Last minute grab score ──
        grab_score = self._compute_grab_score(last_minute_pts, last)

        # ── Tail drop risk ──
        tail_drop = self._detect_end_drop(sorted_pts)

        # ── Volume ratio (carry) ──
        total_amount = last.matched_amount
        for pt in sorted_pts:
            if pt.matched_amount > total_amount:
                total_amount = pt.matched_amount
        carry_ratio = total_amount / prev_day_max_intraday_amount if prev_day_max_intraday_amount > 0 else 0.0

        # ── End spike ──
        end_spike = self._detect_end_spike(last_minute_pts, last, total_amount)

        # ── Shape features ──
        shape = self._derive_shapes(sorted_pts, open_pct_0925, end_spike)

        # ── Pattern classification ──
        if tail_drop:
            pattern = "tail_drop"
        elif end_spike:
            pattern = "tail_lift"
        elif "step_up" in shape:
            pattern = "step_up"
        elif "u_recovery" in shape:
            pattern = "u_recovery"
        elif stability < 30:
            pattern = "volatile"
        else:
            pattern = "stable"

        return AuctionTimelineFeature(
            trade_date=trade_date,
            stock_id=stock_id,
            stock_name=stock_name,
            subject_key=subject_key,
            theme_name=theme_name,
            open_pct_0925=round(open_pct_0925, 4),
            price_trend_0920_0925=round(price_trend, 4),
            price_stability_score=round(stability, 2),
            last_minute_price_change=round(lm_price_change, 4),
            last_minute_volume_ratio=round(lm_volume_ratio, 4),
            last_minute_grab_score=round(grab_score, 2),
            tail_drop_risk=round(0.85 if tail_drop else 0.15, 2),
            auction_volume_ratio=round(carry_ratio, 4),
            auction_pattern=pattern,
            shape_features=shape,
            is_red_zone=open_pct_0925 > 0,
            has_end_spike=end_spike,
            has_end_drop=tail_drop,
            data_status=data_status,
            timeline_points_count=n,
            timeline_points_snapshot=[
                {"ts": p.snapshot_time, "price": p.indicative_price, "pct": p.indicative_open_pct,
                 "vol": p.matched_volume, "amt": p.matched_amount}
                for p in sorted_pts
            ],
            source_trace=source_trace or {},
        )

    # ── Internal methods (adapted from AuctionSignalService) ───────────

    def _compute_stability(self, points: list[TimelinePoint]) -> float:
        n = len(points)
        if n <= 1:
            return 50.0
        prices = [max(p.indicative_open_pct, 0.0) for p in points]
        base = prices[0] if prices[0] > 0 else max(prices)
        if base <= 0:
            return 0.0
        jumps = 0
        max_dd = 0.0
        peak = prices[0]
        for prev, cur in zip(prices, prices[1:]):
            change = abs(cur - prev) / base * 100.0
            if change >= 0.8:
                jumps += 1
            peak = max(peak, cur)
            dd = (peak - cur) / base * 100.0
            if dd > max_dd:
                max_dd = dd
        score = 100.0 - jumps * 12.0 - max_dd * 18.0
        if self._detect_end_drop(points):
            score -= 18.0
        return self._clip(score)

    def _detect_end_drop(self, points: list[TimelinePoint]) -> bool:
        if len(points) < 2:
            return False
        return points[-1].indicative_price < points[-2].indicative_price * 0.995

    def _detect_end_spike(
        self, last_minute_pts: list[TimelinePoint], last: TimelinePoint, total_amount: float
    ) -> bool:
        if len(last_minute_pts) < 2 or total_amount <= 0:
            return False
        lm_vol = sum(p.matched_amount for p in last_minute_pts)
        lm_amount = max(p.matched_amount for p in last_minute_pts) if last_minute_pts else last.matched_amount
        ratio = lm_amount / total_amount if total_amount > 0 else 0
        return ratio >= 0.35 and last.indicative_price >= last_minute_pts[0].indicative_price

    def _last_minute_metrics(
        self, last_minute_pts: list[TimelinePoint], last: TimelinePoint
    ) -> tuple[float, float]:
        if not last_minute_pts:
            return 0.0, 0.0
        first_lm = last_minute_pts[0]
        price_change = last.indicative_open_pct - first_lm.indicative_open_pct
        lm_amount = sum(p.matched_amount for p in last_minute_pts)
        vol_ratio = lm_amount / last.matched_amount if last.matched_amount > 0 else 0.0
        return price_change, vol_ratio

    def _compute_grab_score(
        self, last_minute_pts: list[TimelinePoint], last: TimelinePoint
    ) -> float:
        """0-100 grab score based on volume surge + price lift in last minute."""
        if not last_minute_pts:
            return 0.0
        _, vol_ratio = self._last_minute_metrics(last_minute_pts, last)
        price_lift = last.indicative_open_pct > last_minute_pts[0].indicative_open_pct

        score = 0.0
        if vol_ratio >= 0.35:
            score += 50.0
        elif vol_ratio >= 0.20:
            score += 35.0
        elif vol_ratio >= 0.10:
            score += 20.0

        if price_lift:
            score += 35.0
        elif last.indicative_open_pct >= last_minute_pts[0].indicative_open_pct:
            score += 15.0

        if vol_ratio >= 0.20 and price_lift:
            score += 15.0

        return self._clip(score)

    @staticmethod
    def _derive_shapes(
        points: list[TimelinePoint], open_pct: float, has_spike: bool
    ) -> list[str]:
        if not points:
            return []
        shapes: list[str] = []
        if open_pct > 0:
            shapes.append("red_zone")
        prices = [p.indicative_price for p in points]
        if len(prices) >= 3:
            up_count = sum(1 for a, b in zip(prices, prices[1:]) if b >= a)
            if prices[-1] > prices[0] and up_count >= max(2, len(prices) - 2):
                shapes.append("step_up")
        if len(prices) >= 4:
            trough = min(prices)
            t_idx = prices.index(trough)
            if 0 < t_idx < len(prices) - 1 and prices[-1] >= prices[0]:
                shapes.append("u_recovery")
        if has_spike:
            shapes.append("tail_upturn")
        # Synthetic single-point
        if len(points) == 1:
            shapes.append("single_point_snapshot")
        return shapes
