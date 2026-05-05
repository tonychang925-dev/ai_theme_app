from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


def load_env_file_values(project_root: Path | None = None) -> Dict[str, str]:
    root = project_root or Path(__file__).resolve().parents[1]
    values: Dict[str, str] = {}
    for path in (root / ".env.local", root / ".env.theme", root / ".env"):
        if not path.exists():
            continue
        try:
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'").strip()
                if key and value and key not in values:
                    values[key] = value
        except Exception:
            continue
    return values


def resolve_tushare_token(project_root: Path | None = None) -> str:
    token = str(os.getenv("TUSHARE_TOKEN") or "").strip()
    if token:
        return token
    env_values = load_env_file_values(project_root=project_root)
    return str(env_values.get("TUSHARE_TOKEN") or "").strip()


@dataclass
class StockServiceConfig:
    project_root: Path = Path(__file__).resolve().parents[1]
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_database: str = os.getenv("POSTGRES_DATABASE", "stock_data_test")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
    tushare_token: str = resolve_tushare_token()
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
