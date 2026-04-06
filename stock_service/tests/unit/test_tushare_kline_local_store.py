from __future__ import annotations

import json
from pathlib import Path

from stock_service.models import StockDailySnapshot
from stock_service.services.tushare_kline_local_store import TushareKlineLocalStore


def test_upsert_stock_bars_merges_and_sorts(tmp_path: Path):
    store = TushareKlineLocalStore(tmp_path)
    stock_id = "601872.SH"
    store.upsert_stock_bars(
        stock_id,
        [
            StockDailySnapshot(
                trade_date="2026-04-02",
                stock_id=stock_id,
                stock_name="招商轮船",
                open_price=18.0,
                high_price=19.0,
                low_price=17.8,
                close_price=18.5,
                pre_close=17.5,
                pct_chg=5.7,
                volume=100.0,
                amount=200.0,
            )
        ],
    )
    path = store.upsert_stock_bars(
        stock_id,
        [
            StockDailySnapshot(
                trade_date="2026-04-01",
                stock_id=stock_id,
                stock_name="招商轮船",
                open_price=17.0,
                high_price=17.8,
                low_price=16.8,
                close_price=17.5,
                pre_close=16.9,
                pct_chg=3.5,
                volume=90.0,
                amount=180.0,
            )
        ],
    )

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    rows = [json.loads(line) for line in lines]
    assert [row["trade_date"] for row in rows] == ["2026-04-01", "2026-04-02"]
