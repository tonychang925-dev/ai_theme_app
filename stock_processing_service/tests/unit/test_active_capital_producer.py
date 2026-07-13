"""PR4.2.28f ActiveCapitalProducer v1 contract."""

from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.market_metrics.active_capital_producer import (
    ActiveCapitalProducer,
)
from stock_processing_service.application.services.market_metrics.board_pool_snapshot import (
    BoardPoolAmount,
    BoardPoolSnapshot,
)


def _snapshot(*, zt: float | None, zb: float | None, yzt: float | None = None) -> BoardPoolSnapshot:
    missing = []
    if zt is None:
        missing.append("board_pool.zt.amount_yi")
    if zb is None:
        missing.append("board_pool.zb.amount_yi")
    if yzt is None:
        missing.append("board_pool.yzt.amount_yi")
    return BoardPoolSnapshot(
        trade_date=date(2026, 7, 9),
        zt=BoardPoolAmount("ZT", 75, zt, "eastmoney_board_pool_daily.amount" if zt else None, "OK" if zt else "MISSING"),
        zb=BoardPoolAmount("ZB", 17, zb, "eastmoney_board_pool_daily.amount" if zb else None, "OK" if zb else "MISSING"),
        yzt=BoardPoolAmount("YZT", 47, yzt, "eastmoney_board_pool_daily.amount" if yzt else None, "OK" if yzt else "MISSING"),
        diagnostics={"missing": tuple(missing)},
    )


def test_active_capital_uses_zt_plus_zb_and_marks_partial_without_yzt() -> None:
    """TC-ID: PR4.2.28f-active-capital-zb-v1."""
    active = ActiveCapitalProducer().produce(_snapshot(zt=2479.55, zb=185.29))

    assert active.value_yi == 2664.84
    assert active.method == "board_pool_zt_zb_v1"
    assert active.quality == "PARTIAL"
    assert active.confidence == 0.85
    assert [(c.type, c.amount_yi) for c in active.components] == [
        ("ZT", 2479.55),
        ("ZB", 185.29),
    ]
    assert [c.source for c in active.components] == [
        "eastmoney_board_pool_daily.amount",
        "eastmoney_board_pool_daily.amount",
    ]
    assert "board_pool.yzt.amount_yi" in active.missing


def test_active_capital_does_not_emit_value_when_zb_missing() -> None:
    """TC-ID: PR4.2.28f-active-capital-zb-required."""
    active = ActiveCapitalProducer().produce(_snapshot(zt=2479.55, zb=None))

    assert active.value_yi is None
    assert active.quality == "DEGRADED"
    assert active.confidence == 0.60
    assert "board_pool.zb.amount_yi" in active.missing


def test_active_capital_marks_full_only_when_yzt_is_available() -> None:
    """TC-ID: PR4.2.28f-active-capital-full-requires-yzt."""
    active = ActiveCapitalProducer().produce(_snapshot(zt=2479.55, zb=185.29, yzt=969.0))

    assert active.value_yi == 2664.84
    assert active.quality == "FULL"
    assert active.confidence == 0.95
    assert active.missing == ()
