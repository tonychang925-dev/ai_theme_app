from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO
from stock_processing_service.domain.services.kline_support_scorer import KlineSupportScorer


def _bar(
    *,
    d: date,
    stock_id: str,
    stock_name: str,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    pre_close: str,
    pct_chg: str,
) -> StockBarDTO:
    return StockBarDTO(
        trade_date=d,
        stock_id=stock_id,
        stock_name=stock_name,
        open_price=Decimal(open_price),
        high_price=Decimal(high_price),
        low_price=Decimal(low_price),
        close_price=Decimal(close_price),
        pre_close=Decimal(pre_close),
        pct_chg=Decimal(pct_chg),
        volume=Decimal("1000000"),
        amount=Decimal("10000000"),
        limit_up_price=Decimal("999"),
        limit_down_price=Decimal("0"),
    )


def test_legacy_prev_day_gap_hit_becomes_primary_support() -> None:
    scorer = KlineSupportScorer()
    history_bars = [
        _bar(
            d=date(2026, 4, 6),
            stock_id="002361.SZ",
            stock_name="神剑股份",
            open_price="9.80",
            high_price="10.00",
            low_price="9.70",
            close_price="9.95",
            pre_close="9.60",
            pct_chg="3.65",
        )
    ]
    current_bar = _bar(
        d=date(2026, 4, 7),
        stock_id="002361.SZ",
        stock_name="神剑股份",
        open_price="10.20",
        high_price="10.30",
        low_price="10.05",
        close_price="10.18",
        pre_close="9.95",
        pct_chg="2.31",
    )

    result = scorer.score(
        stock_id="002361.SZ",
        current_bar=current_bar,
        prior_rows=[],
        history_bars=history_bars,
    )

    assert result.gap_hit is True
    assert result.gap_source == "gap_structure"
    assert result.gap_hit_mode in {"strict", "soft"}
    assert result.support_type == "gap_support"
    assert result.gap_level == Decimal("10.00")


def test_legacy_gap_lock_prevents_prev_low_overtake() -> None:
    scorer = KlineSupportScorer()
    history_bars = [
        _bar(
            d=date(2026, 4, 6),
            stock_id="605060.SH",
            stock_name="联德股份",
            open_price="20.10",
            high_price="20.50",
            low_price="19.90",
            close_price="20.30",
            pre_close="19.70",
            pct_chg="3.05",
        )
    ]
    current_bar = _bar(
        d=date(2026, 4, 15),
        stock_id="605060.SH",
        stock_name="联德股份",
        open_price="20.65",
        high_price="20.80",
        low_price="20.55",
        close_price="20.70",
        pre_close="20.30",
        pct_chg="1.97",
    )

    result = scorer.score(
        stock_id="605060.SH",
        current_bar=current_bar,
        prior_rows=[],
        history_bars=history_bars,
    )

    assert result.support_type == "gap_support"
    assert result.gap_hit is True
    assert result.gap_source == "gap_structure"
    assert any("gap_candidate=" in x or "legacy_gap_candidate " in x for x in result.support_refs)


def test_legacy_gap_not_hit_when_outside_1pct_window() -> None:
    scorer = KlineSupportScorer()
    history_bars = [
        _bar(
            d=date(2026, 4, 6),
            stock_id="000001.SZ",
            stock_name="测试股",
            open_price="9.80",
            high_price="10.00",
            low_price="9.70",
            close_price="9.95",
            pre_close="9.60",
            pct_chg="3.00",
        )
    ]
    current_bar = _bar(
        d=date(2026, 4, 7),
        stock_id="000001.SZ",
        stock_name="测试股",
        open_price="10.30",
        high_price="10.50",
        low_price="10.25",
        close_price="10.40",
        pre_close="9.95",
        pct_chg="4.52",
    )

    result = scorer.score(
        stock_id="000001.SZ",
        current_bar=current_bar,
        prior_rows=[],
        history_bars=history_bars,
    )

    assert result.gap_source != "gap_structure" or result.gap_hit is False
    assert result.gap_hit_mode not in {"strict", "soft"}


def test_legacy_gap_not_hit_when_no_gap() -> None:
    scorer = KlineSupportScorer()
    history_bars = [
        _bar(
            d=date(2026, 4, 6),
            stock_id="000002.SZ",
            stock_name="测试股2",
            open_price="10.00",
            high_price="10.20",
            low_price="9.80",
            close_price="10.10",
            pre_close="9.90",
            pct_chg="2.02",
        )
    ]
    # current low does not satisfy up-gap condition vs prev_high*1.001
    current_bar = _bar(
        d=date(2026, 4, 7),
        stock_id="000002.SZ",
        stock_name="测试股2",
        open_price="10.15",
        high_price="10.30",
        low_price="10.19",
        close_price="10.22",
        pre_close="10.10",
        pct_chg="1.19",
    )

    result = scorer.score(
        stock_id="000002.SZ",
        current_bar=current_bar,
        prior_rows=[],
        history_bars=history_bars,
    )

    assert result.gap_source == ""
    assert result.gap_hit is False
    assert result.gap_hit_mode not in {"strict", "soft"}
