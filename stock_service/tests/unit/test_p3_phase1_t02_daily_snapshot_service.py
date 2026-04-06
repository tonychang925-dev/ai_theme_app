from __future__ import annotations

import json
from pathlib import Path

from stock_service.adapters.jyhf_adapter import JyhfAdapter
from stock_service.services.daily_snapshot_service import DailySnapshotService


def test_normalize_tushare_daily_rows():
    service = DailySnapshotService()
    rows = [
        {
            "ts_code": "000001.SZ",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.3,
            "pre_close": 9.9,
            "pct_chg": 4.04,
            "vol": 12345,
            "amount": 98765,
        }
    ]
    snapshots = service.normalize_tushare_daily_rows(rows, "2026-04-02")
    assert len(snapshots) == 1
    assert snapshots[0].stock_id == "000001.SZ"
    assert snapshots[0].close_price == 10.3
    assert snapshots[0].pct_chg == 4.04


def test_jyhf_adapter_iter_stock_daily_rows(tmp_path: Path):
    project_root = tmp_path
    stock_daily_dir = project_root / "theme_data_complete" / "stock_daily"
    stock_daily_dir.mkdir(parents=True)
    row = [
        "2026-04-02 00:00:00",
        "153143",
        "601872",
        "招商轮船",
        16.68,
        18,
        16.68,
        18,
        16.36,
        1.64,
        10.02,
        0,
        1968440.26,
        3523412682,
        18,
        [[129, "交通运输", 1]],
    ]
    file_path = stock_daily_dir / "129_2026-04-02_stocks.jsonl"
    file_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    adapter = JyhfAdapter(project_root)
    items = list(adapter.iter_stock_daily_rows("2026-04-02"))
    assert len(items) == 1
    assert items[0]["subject_key"] == "129"
    assert items[0]["subject_name"] == "交通运输"
    assert items[0]["stock_id"] == "601872.SH"
    assert items[0]["is_leader"] is True


def test_jyhf_adapter_iter_stock_daily_rows_real_layout_with_theme_tags_at_index_16(tmp_path: Path):
    project_root = tmp_path
    stock_daily_dir = project_root / "theme_data_complete" / "stock_daily"
    stock_daily_dir.mkdir(parents=True)
    row = [
        "2026-04-01 00:00:00",
        "153143",
        "688488",
        "艾迪药业",
        15.14,
        17.82,
        15.07,
        17.82,
        14.85,
        2.97,
        20,
        0,
        286168.99,
        484695870,
        17.82,
        9.33,
        [[9025631, "创新药", 1], [9065775, "4月1日热门题材复盘", 1]],
    ]
    file_path = stock_daily_dir / "9025631_2026-04-01_stocks.jsonl"
    file_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    adapter = JyhfAdapter(project_root)
    items = list(adapter.iter_stock_daily_rows("2026-04-01"))
    assert len(items) == 1
    assert items[0]["subject_key"] == "9025631"
    assert items[0]["subject_name"] == "创新药"
    assert items[0]["stock_id"] == "688488.SH"


def test_build_subject_stock_daily_snapshots():
    service = DailySnapshotService()
    stock_snapshots = service.normalize_tushare_daily_rows(
        [
            {
                "ts_code": "601872.SH",
                "close": 16.68,
                "pre_close": 15.16,
                "pct_chg": 10.02,
                "vol": 1968440.26,
                "amount": 3523412682,
            }
        ],
        "2026-04-02",
    )
    jyhf_rows = [
        {
            "subject_key": "129",
            "subject_name": "交通运输",
            "stock_id": "601872.SH",
            "stock_name": "招商轮船",
            "rank_order": 1,
            "pct_chg": 10.02,
            "close_price": 16.68,
            "is_leader": True,
        }
    ]
    subject_rows = service.build_subject_stock_daily_snapshots("2026-04-02", stock_snapshots, jyhf_rows)
    assert len(subject_rows) == 1
    assert subject_rows[0].subject_key == "129"
    assert subject_rows[0].stock_id == "601872.SH"
    assert subject_rows[0].is_leader is True
    assert subject_rows[0].close_price == 16.68
