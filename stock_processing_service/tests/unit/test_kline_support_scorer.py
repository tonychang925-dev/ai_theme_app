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


def test_scorer_end_to_end() -> None:
    scorer = KlineSupportScorer()
    history_bars = [
        _bar(
            d=date(2026, 3, 30),
            stock_id="002361.SZ",
            stock_name="神剑股份",
            open_price="13.37",
            high_price="15.00",
            low_price="13.21",
            close_price="15.00",
            pre_close="13.64",
            pct_chg="9.97",
        ),
        _bar(
            d=date(2026, 3, 31),
            stock_id="002361.SZ",
            stock_name="神剑股份",
            open_price="16.15",
            high_price="16.50",
            low_price="15.83",
            close_price="16.50",
            pre_close="15.00",
            pct_chg="10.00",
        ),
    ]
    current_bar = _bar(
        d=date(2026, 4, 7),
        stock_id="002361.SZ",
        stock_name="神剑股份",
        open_price="15.85",
        high_price="16.47",
        low_price="14.80",
        close_price="15.25",
        pre_close="15.74",
        pct_chg="-3.11",
    )

    result = scorer.score(
        stock_id="002361.SZ",
        current_bar=current_bar,
        prior_rows=[],
        history_bars=history_bars,
    )

    assert result.support_type in {"gap_support", "prev_low_support", "ma_support", "none"}
    assert isinstance(result.support_score, Decimal)
    assert isinstance(result.support_level, Decimal)
    assert len(result.support_refs) > 0

