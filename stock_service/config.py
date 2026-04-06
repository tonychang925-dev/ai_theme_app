from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StockServiceConfig:
    project_root: Path = Path(__file__).resolve().parents[1]
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_database: str = os.getenv("POSTGRES_DATABASE", "stock_data_test")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
    tushare_token: str = os.getenv("TUSHARE_TOKEN", "")
    notion_report_page_id: str = os.getenv("NOTION_REPORT_PAGE_ID", "")
    report_snapshot_root: Path = Path(
        os.getenv(
            "STOCK_REPORT_SNAPSHOT_ROOT",
            str(Path(__file__).resolve().parents[1] / "theme_data_complete" / "_report_snapshots"),
        )
    )
    raw_snapshot_root: Path = Path(
        os.getenv(
            "STOCK_RAW_SNAPSHOT_ROOT",
            str(Path(__file__).resolve().parents[1] / "theme_data_complete" / "_raw_stock_sources"),
        )
    )
    local_kline_root: Path = Path(
        os.getenv(
            "STOCK_LOCAL_KLINE_ROOT",
            str(Path(__file__).resolve().parents[1] / "theme_data_complete" / "_stock_kline"),
        )
    )


DEFAULT_CONFIG = StockServiceConfig()
