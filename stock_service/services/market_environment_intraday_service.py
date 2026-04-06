from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class IntradayMinutePoint:
    ts: str
    pct_chg: float


class MarketEnvironmentIntradayService:
    """
    分钟级环境指标服务。
    只负责把单票分钟路径映射成：
    - 早盘冲高回落
    - 日内回落
    不参与大环境总分。
    """

    def parse_points(self, raw_points: Iterable[dict] | None) -> list[IntradayMinutePoint]:
        points: list[IntradayMinutePoint] = []
        for row in raw_points or []:
            ts = str(row.get("ts") or "").strip()
            if not ts:
                continue
            points.append(
                IntradayMinutePoint(
                    ts=ts,
                    pct_chg=float(row.get("pct_chg") or 0.0),
                )
            )
        return sorted(points, key=lambda item: item.ts)

    def is_morning_high_then_fall(self, points: list[IntradayMinutePoint]) -> bool:
        morning = [point for point in points if point.ts <= "10:00:00"]
        later = [point for point in points if point.ts >= "10:30:00"]
        if not morning or not later:
            return False
        morning_high = max(point.pct_chg for point in morning)
        later_anchor = later[0].pct_chg
        return morning_high >= 3.0 and (morning_high - later_anchor) >= 2.0

    def is_intraday_fade(self, points: list[IntradayMinutePoint]) -> bool:
        if not points:
            return False
        early = [point for point in points if point.ts <= "10:00:00"]
        if not early:
            return False
        early_high = max(point.pct_chg for point in early)
        close_like = points[-1].pct_chg
        return early_high >= 2.0 and (early_high - close_like) >= 1.5
