from __future__ import annotations

from stock_service.models import StockDailySnapshot
from stock_service.services.stock_kline_judgement_service import StockKlineJudgementService


def _row(day: int, close_price: float, volume: float, high_price: float | None = None, low_price: float | None = None):
    return StockDailySnapshot(
        trade_date=f"2026-04-{day:02d}",
        stock_id="600000.SH",
        stock_name="测试股",
        open_price=close_price * 0.98,
        high_price=high_price if high_price is not None else close_price * 1.02,
        low_price=low_price if low_price is not None else close_price * 0.97,
        close_price=close_price,
        pre_close=close_price * 0.99,
        pct_chg=1.0,
        volume=volume,
        amount=volume * close_price,
    )


def test_build_position_judgement_breakout():
    service = StockKlineJudgementService()
    rows = [_row(i + 1, 10 + i * 0.1, 1000 + i * 10) for i in range(25)]
    item = service.build_position_judgement(rows)
    assert item is not None
    assert item.position_label in {"突破前高", "接近前高", "低位启动", "平台整理", "高位分歧"}


def test_build_pattern_judgement_detects_ma_and_breakout():
    service = StockKlineJudgementService()
    rows = [_row(i + 1, 10 + i * 0.2, 1000 + i * 20) for i in range(24)]
    rows.append(_row(25, 20.0, 5000.0, high_price=20.0))
    item = service.build_pattern_judgement(rows)
    assert item is not None
    assert "均线多头" in item.pattern_labels
