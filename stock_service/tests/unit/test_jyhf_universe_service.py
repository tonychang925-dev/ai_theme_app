from __future__ import annotations

from pathlib import Path

from stock_service.services.jyhf_universe_service import JyhfUniverseService


def test_collect_stock_ids_from_jyhf_files(tmp_path: Path):
    stock_daily_dir = tmp_path / "theme_data_complete" / "stock_daily"
    stock_details_dir = tmp_path / "theme_data_complete" / "stock_details"
    stock_daily_dir.mkdir(parents=True)
    stock_details_dir.mkdir(parents=True)

    (stock_daily_dir / "901_2026-04-03_stocks.jsonl").write_text(
        '["2026-04-03 00:00:00", "1", "601872", "招商轮船"]\n'
        '["2026-04-03 00:00:00", "2", "301048", "金鹰重工"]\n',
        encoding="utf-8",
    )
    (stock_details_dir / "901_2026-04_stocks.jsonl").write_text(
        '["2026-04-02 00:00:00", "1", "000001", "平安银行"]\n'
        '["2026-04-02 00:00:00", "2", "601872", "招商轮船"]\n',
        encoding="utf-8",
    )

    service = JyhfUniverseService(tmp_path)
    assert service.collect_stock_ids() == ["000001.SZ", "301048.SZ", "601872.SH"]
