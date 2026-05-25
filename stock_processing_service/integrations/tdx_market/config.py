"""TDX 行情集成配置 — frozen dataclass，环境变量驱动."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TdxMarketConfig:
    # ── Agent ──
    agent_base_url: str = os.getenv("TDX_AGENT_BASE_URL", "http://127.0.0.1:8766")
    agent_timeout_seconds: float = float(os.getenv("TDX_MARKET_AGENT_TIMEOUT", "10.0"))

    # ── Redis ──
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_stream: str = os.getenv("TDX_MARKET_REDIS_STREAM", "stream:market:tdx")
    redis_stream_maxlen: int = int(os.getenv("TDX_MARKET_REDIS_MAXLEN", "10000"))

    # ── PostgreSQL ──
    pg_dsn: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/stock_data_test",
    )

    # ── 采集调度 ──
    interval_quote_seconds: float = float(os.getenv("TDX_MARKET_QUOTE_INTERVAL", "10.0"))
    interval_bars_seconds: float = float(os.getenv("TDX_MARKET_BARS_INTERVAL", "60.0"))

    # ── Watchlist ──
    watchlist_path: str = os.getenv(
        "TDX_MARKET_WATCHLIST_PATH",
        os.getenv(
            "JYHF_MARKET_WATCHLIST_PATH",
            str(Path(__file__).resolve().parents[3] / "tmp" / "realtime" / "tdx_market" / "watchlist.json"),
        ),
    )

    # ── 运行时目录 ──
    @property
    def runtime_dir(self) -> Path:
        return Path(__file__).resolve().parents[3] / "tmp" / "realtime" / "tdx_market"

    @property
    def status_path(self) -> Path:
        return self.runtime_dir / "market_collector.status.json"

    @property
    def log_path(self) -> Path:
        return self.runtime_dir / "market_collector.log"

    # ── 开关 ──
    allow_push_redis: bool = os.getenv("TDX_MARKET_PUSH_REDIS", "1") == "1"
    allow_push_db: bool = os.getenv("TDX_MARKET_PUSH_DB", "1") == "1"
    enabled: bool = os.getenv("TDX_MARKET_ENABLED", "0") == "1"


def load_config() -> TdxMarketConfig:
    return TdxMarketConfig()
