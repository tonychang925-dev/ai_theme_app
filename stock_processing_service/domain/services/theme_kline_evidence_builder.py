from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO


@dataclass(frozen=True)
class ThemeKlineEvidence:
    subject_key: str
    theme_ret_3d: Decimal
    theme_ret_5d: Decimal
    theme_ret_10d: Decimal
    above_ma5: bool
    above_ma10: bool
    above_ma20: bool
    volume_breakdown_flag: bool
    break_start_pivot: bool
    theme_support_score: Decimal
    composite_last: Decimal
    ma5: Decimal
    ma10: Decimal
    ma20: Decimal
    avg_volume_ratio: Decimal


class ThemeKlineEvidenceBuilder:
    """Build theme-level K-line evidence from component stock bars.

    Constructs an equal-weighted composite index from component stocks'
    historical daily bars, then computes MA/return/volume/support signals.
    Pure domain service — no DB access.
    """

    LOOKBACK_BARS = 25

    @staticmethod
    def _d(val: object) -> Decimal:
        if val is None:
            return Decimal("0")
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except Exception:
            return Decimal("0")

    def build_one(
        self,
        *,
        subject_key: str,
        stock_ids: list[str],
        bars_by_date: dict[str, list[StockBarDTO]],
        trade_dates: list[str],
    ) -> ThemeKlineEvidence:
        """Build K-line evidence for one subject_key.

        Args:
            stock_ids: Component stock IDs for this subject.
            bars_by_date: {trade_date_iso: [StockBarDTO, ...]} for all stocks.
            trade_dates: Sorted ascending trading dates (most recent last).
        """
        if not stock_ids or len(trade_dates) < 5:
            return self._empty(subject_key)

        # Build equal-weighted composite index.
        composite = self._build_composite(stock_ids, bars_by_date, trade_dates)
        if len(composite) < 5:
            return self._empty(subject_key)

        closes = [c for _, c in composite]
        volumes = [v for _, _, v in composite]
        last_close = closes[-1]

        # MA computations
        ma5 = self._sma(closes, 5)
        ma10 = self._sma(closes, 10)
        ma20 = self._sma(closes, 20)

        above_ma5 = last_close >= ma5 if ma5 > 0 else False
        above_ma10 = last_close >= ma10 if ma10 > 0 else False
        above_ma20 = last_close >= ma20 if ma20 > 0 else False

        # Theme returns
        theme_ret_3d = self._ret(closes, 3)
        theme_ret_5d = self._ret(closes, 5)
        theme_ret_10d = self._ret(closes, 10)

        # Volume breakdown: recent volume surge + price decline
        avg_vol_10d = sum(volumes[-10:]) / max(len(volumes[-10:]), 1) if volumes else Decimal("0")
        recent_vol = volumes[-1]
        avg_volume_ratio = recent_vol / avg_vol_10d if avg_vol_10d > 0 else Decimal("1")
        volume_breakdown_flag = bool(
            avg_volume_ratio > Decimal("1.5") and theme_ret_3d < Decimal("-3")
        )

        # Break start pivot: price below key MAs + recent decline
        break_start_pivot = bool(
            (not above_ma10 or not above_ma20)
            and theme_ret_5d < Decimal("-2")
        )

        # Support score: based on MA proximity and retracement
        support_score = Decimal("50")
        if above_ma20:
            support_score += Decimal("20")
        if above_ma10:
            support_score += Decimal("15")
        if above_ma5:
            support_score += Decimal("10")
        if theme_ret_5d >= Decimal("-3"):
            support_score += Decimal("5")
        support_score = min(Decimal("100"), max(Decimal("0"), support_score))

        return ThemeKlineEvidence(
            subject_key=subject_key,
            theme_ret_3d=theme_ret_3d,
            theme_ret_5d=theme_ret_5d,
            theme_ret_10d=theme_ret_10d,
            above_ma5=above_ma5,
            above_ma10=above_ma10,
            above_ma20=above_ma20,
            volume_breakdown_flag=volume_breakdown_flag,
            break_start_pivot=break_start_pivot,
            theme_support_score=support_score,
            composite_last=last_close,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            avg_volume_ratio=avg_volume_ratio,
        )

    def _build_composite(
        self,
        stock_ids: list[str],
        bars_by_date: dict[str, list[StockBarDTO]],
        trade_dates: list[str],
    ) -> list[tuple[str, Decimal, Decimal]]:
        """Build equal-weighted composite: [(date, close, volume), ...]."""
        result: list[tuple[str, Decimal, Decimal]] = []
        for td in trade_dates:
            day_bars = bars_by_date.get(td, [])
            stock_bars = {b.stock_id: b for b in day_bars if b.stock_id in set(stock_ids)}
            if not stock_bars:
                continue
            # Equal-weighted pct_chg
            pcts = [b.pct_chg for b in stock_bars.values()]
            avg_pct = sum(pcts, start=Decimal("0")) / Decimal(str(len(pcts)))
            result.append((td, avg_pct, sum(
                (b.volume for b in stock_bars.values()), start=Decimal("0")
            )))
        return result

    @staticmethod
    def _sma(values: list[Decimal], window: int) -> Decimal:
        if len(values) < window:
            return Decimal("0")
        return sum(values[-window:]) / Decimal(str(window))

    @staticmethod
    def _ret(values: list[Decimal], window: int) -> Decimal:
        if len(values) < window + 1:
            return Decimal("0")
        return values[-1] - values[-window - 1]

    @staticmethod
    def _empty(subject_key: str) -> ThemeKlineEvidence:
        return ThemeKlineEvidence(
            subject_key=subject_key,
            theme_ret_3d=Decimal("0"),
            theme_ret_5d=Decimal("0"),
            theme_ret_10d=Decimal("0"),
            above_ma5=False,
            above_ma10=False,
            above_ma20=False,
            volume_breakdown_flag=False,
            break_start_pivot=False,
            theme_support_score=Decimal("0"),
            composite_last=Decimal("0"),
            ma5=Decimal("0"),
            ma10=Decimal("0"),
            ma20=Decimal("0"),
            avg_volume_ratio=Decimal("0"),
        )
