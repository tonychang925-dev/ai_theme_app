from __future__ import annotations

import asyncio
import json
from argparse import Namespace
from pathlib import Path

from scripts import build_post_market_recap as recap_script
from stock_service.services.stock_abnormal_signal_service import StockAbnormalInput, StockDailySnapshot


class _FakeSignal:
    trade_date = "2026-04-08"
    subject_key = "901"
    theme_name = "测试题材"
    stock_id = "000001"
    stock_name = "平安银行"
    abnormal_composite_score = 66.0
    turnover_rate = 8.5
    volume_ratio_to_ma50 = 1.8
    main_net_inflow_rank_in_theme = 1
    hot_money_buy_names = ["测试游资"]
    institution_seat_count = 2
    abnormal_labels = ["放量", "机构净买"]
    conclusion = "测试结论"
    evidence = ["量比 1.80"]


class _FakeSignalService:
    def __init__(self) -> None:
        self.loaded_paths: list[str] = []

    def load_stock_bars(self, path: Path) -> list[StockDailySnapshot]:
        self.loaded_paths.append(str(path))
        return [
            StockDailySnapshot(
                trade_date=f"2026-03-{day:02d}",
                stock_id="000001",
                stock_name="平安银行",
                open_price=10.0,
                high_price=10.5,
                low_price=9.8,
                close_price=10.2,
                pre_close=10.0,
                pct_chg=2.0,
                volume=1000000.0 + day,
                amount=10000000.0 + day,
                source_name="tushare",
            )
            for day in range(1, 21)
        ]

    def build_signal(self, current, rows):
        assert len(rows) >= 20
        assert current.stock_id == "000001"
        return _FakeSignal()


def test_build_abnormal_fallback_uses_existing_stock_bar_loader(tmp_path: Path, monkeypatch):
    details_root = tmp_path / "details"
    kline_root = tmp_path / "kline"
    details_root.mkdir()
    kline_root.mkdir()
    (kline_root / "000001.SZ.jsonl").write_text('{"stub": true}\n', encoding="utf-8")

    service = _FakeSignalService()
    monkeypatch.setattr(recap_script, "StockAbnormalSignalService", lambda: service)
    monkeypatch.setattr(
        recap_script,
        "load_current_inputs",
        lambda *args, **kwargs: [
            StockAbnormalInput(
                trade_date="2026-04-08",
                subject_key="901",
                theme_name="测试题材",
                stock_id="000001",
                stock_name="平安银行",
                open_price=10.0,
                high_price=10.5,
                low_price=9.8,
                close_price=10.2,
                pre_close=10.0,
                pct_chg=2.0,
                volume=1000000.0,
                amount=10000000.0,
                volume_ratio=1.8,
                turnover_rate=8.5,
            )
        ],
    )
    monkeypatch.setattr(recap_script, "PROJECT_ROOT", tmp_path)

    args = Namespace(
        trade_date="2026-04-08",
        token="",
        force_refresh_tail_auction=False,
        postgres_database="stock_data_test",
        min_turnover_rate=3.0,
        limit=0,
        fallback_top_k=20,
        details_root=str(details_root),
        kline_root=str(kline_root),
    )

    out_path = asyncio.run(recap_script._build_abnormal_fallback(args))

    assert service.loaded_paths == [str(kline_root / "000001.SZ.jsonl")]
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["trade_date"] == "2026-04-08"
    assert payload["rows"][0]["stock_id"] == "000001"
