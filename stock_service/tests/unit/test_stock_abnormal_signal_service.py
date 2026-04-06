from __future__ import annotations

from stock_service.models import StockDailySnapshot
from stock_service.services.stock_abnormal_signal_service import (
    StockAbnormalInput,
    StockAbnormalSignalService,
)
from database_service.scripts.build_stock_abnormal_signal import dedupe_by_stock, load_current_inputs


def _row(day: int, close_price: float, volume: float, amount: float | None = None):
    return StockDailySnapshot(
        trade_date=f"2026-03-{day:02d}",
        stock_id="600000.SH",
        stock_name="测试股",
        open_price=close_price * 0.98,
        high_price=close_price * 1.02,
        low_price=close_price * 0.97,
        close_price=close_price,
        pre_close=close_price * 0.99,
        pct_chg=1.0,
        volume=volume,
        amount=amount if amount is not None else volume * close_price,
    )


def _input(**overrides):
    payload = {
        "trade_date": "2026-04-03",
        "subject_key": "129",
        "theme_name": "测试题材",
        "stock_id": "600000",
        "stock_name": "测试股",
        "open_price": 12.0,
        "high_price": 12.5,
        "low_price": 11.8,
        "close_price": 12.4,
        "pre_close": 11.2,
        "pct_chg": 10.0,
        "volume": 6000.0,
        "amount": 74400.0,
        "volume_ratio": 3.5,
        "turnover_rate": 18.0,
        "turnover_rank_in_theme": 1,
    }
    payload.update(overrides)
    return StockAbnormalInput(**payload)


def test_build_signal_detects_high_turnover_and_double_volume():
    service = StockAbnormalSignalService()
    rows = [_row(i + 1, 10 + i * 0.05, 1000.0, 10000.0) for i in range(55)]
    item = service.build_signal(_input(), rows)
    assert item is not None
    assert item.is_high_turnover is True
    assert item.is_double_volume is True
    assert "高换手" in item.abnormal_labels
    assert "倍量" in item.abnormal_labels
    assert item.turnover_abnormal_score >= 80
    assert item.volume_abnormal_score == 100.0


def test_build_signal_detects_tail_rush_buy_proxy():
    service = StockAbnormalSignalService()
    rows = [_row(i + 1, 10 + i * 0.05, 1000.0, 10000.0) for i in range(40)]
    current = _input(
        high_price=12.4,
        close_price=12.35,
        low_price=11.7,
        pct_chg=6.5,
        amount=30000.0,
        volume=2500.0,
        turnover_rate=9.0,
        volume_ratio=2.0,
    )
    item = service.build_signal(current, rows)
    assert item is not None
    assert item.has_tail_rush_buy is True
    assert "尾盘抢筹(日频代理)" in item.abnormal_labels
    assert item.tail_abnormal_score == 75.0


def test_build_signal_prefers_tail_auction_push_when_close_auction_present():
    service = StockAbnormalSignalService()
    rows = [_row(i + 1, 10 + i * 0.05, 1000.0, 10000.0) for i in range(40)]
    current = _input(
        high_price=12.4,
        close_price=12.35,
        low_price=11.7,
        pct_chg=6.5,
        amount=30000.0,
        volume=2500.0,
        turnover_rate=9.0,
        volume_ratio=2.0,
        tail_auction_amount=3000.0,
        tail_auction_vwap=12.34,
    )
    item = service.build_signal(current, rows)
    assert item is not None
    assert item.has_tail_rush_buy is True
    assert "尾盘竞价抢筹" in item.abnormal_labels
    assert item.tail_abnormal_score == 85.0


def test_load_current_inputs_filters_low_turnover(tmp_path):
    path = tmp_path / "129_2026-04_stocks.jsonl"
    rows = [
        ["2026-04-03 00:00:00", "", "600000", "低换手股", 10, 10.5, 9.8, 10.2, 9.9, 0, 3.0, 0, 1000, 10000, 0, 0, [["129", "测试题材"]], 1.5, 2.5],
        ["2026-04-03 00:00:00", "", "600001", "高换手股", 10, 10.5, 9.8, 10.2, 9.9, 0, 3.0, 0, 1000, 10000, 0, 0, [["129", "测试题材"]], 1.5, 5.5],
    ]
    path.write_text("".join(f"{__import__('json').dumps(row, ensure_ascii=False)}\n" for row in rows), encoding="utf-8")
    items = load_current_inputs("2026-04-03", tmp_path, min_turnover_rate=3.0)
    assert len(items) == 1
    assert items[0].stock_id == "600001"


def test_load_current_inputs_filters_st_stock(tmp_path):
    path = tmp_path / "129_2026-04_stocks.jsonl"
    rows = [
        ["2026-04-03 00:00:00", "", "600002", "ST测试", 10, 10.5, 9.8, 10.2, 9.9, 0, 3.0, 0, 1000, 10000, 0, 0, [["129", "测试题材"]], 1.5, 8.0],
        ["2026-04-03 00:00:00", "", "600003", "*ST测试", 10, 10.5, 9.8, 10.2, 9.9, 0, 3.0, 0, 1000, 10000, 0, 0, [["129", "测试题材"]], 1.5, 8.0],
        ["2026-04-03 00:00:00", "", "600004", "正常股", 10, 10.5, 9.8, 10.2, 9.9, 0, 3.0, 0, 1000, 10000, 0, 0, [["129", "测试题材"]], 1.5, 8.0],
    ]
    path.write_text("".join(f"{__import__('json').dumps(row, ensure_ascii=False)}\n" for row in rows), encoding="utf-8")
    items = load_current_inputs("2026-04-03", tmp_path, min_turnover_rate=3.0)
    assert len(items) == 1
    assert items[0].stock_id == "600004"


def test_dedupe_by_stock_keeps_best_theme_rank():
    rows = [
        _input(stock_id="600010", stock_name="测试股A", subject_key="129", theme_name="题材A", turnover_rank_in_theme=3, turnover_rate=8.0, volume_ratio=2.0),
        _input(stock_id="600010", stock_name="测试股A", subject_key="130", theme_name="题材B", turnover_rank_in_theme=1, turnover_rate=6.0, volume_ratio=1.0),
    ]
    deduped = dedupe_by_stock(rows)
    assert len(deduped) == 1
    assert deduped[0].theme_name == "题材B"


def test_build_signal_composite_score_can_be_used_as_filter_threshold():
    service = StockAbnormalSignalService()
    rows = [_row(i + 1, 10 + i * 0.05, 1000.0, 10000.0) for i in range(55)]
    weak = service.build_signal(
        _input(
            turnover_rate=3.2,
            turnover_rank_in_theme=5,
            volume=1200.0,
            amount=12000.0,
            volume_ratio=1.1,
            pct_chg=1.0,
            high_price=12.0,
            close_price=11.8,
            low_price=11.5,
        ),
        rows,
    )
    assert weak is not None
    assert weak.abnormal_composite_score < 40.0
