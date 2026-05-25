"""P1-A JYHF 行情集成配置 — frozen."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class JyhfMarketConfig:
    # ── 久赢恒丰 API ──
    api_base_url: str = "https://app.txcfgl.com"
    api_timeout_seconds: float = float(os.getenv("JYHF_MARKET_API_TIMEOUT", "10.0"))
    api_max_retries: int = int(os.getenv("JYHF_MARKET_API_MAX_RETRIES", "1"))

    # ── Token ──
    token_path: str = os.getenv("JYHF_AUTH_TOKEN_PATH", "/tmp/jyhf_auth_token.json")
    token_validation_endpoint: str = "/api/app/realtime/index"

    # ── Redis ──
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_stream_market: str = os.getenv("JYHF_MARKET_REDIS_STREAM", "stream:market:jyhf")
    redis_stream_maxlen: int = int(os.getenv("JYHF_MARKET_REDIS_MAXLEN", "10000"))

    # ── PostgreSQL ──
    pg_dsn: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/stock_data_test",
    )

    # ── 采集调度 ──
    interval_quote_seconds: float = float(os.getenv("JYHF_MARKET_QUOTE_INTERVAL", "10.0"))
    interval_subject_seconds: float = float(os.getenv("JYHF_MARKET_SUBJECT_INTERVAL", "30.0"))

    # ── Watchlist ──
    watchlist_path: str = os.getenv(
        "JYHF_MARKET_WATCHLIST_PATH",
        str(Path(__file__).resolve().parents[3] / "tmp" / "realtime" / "jyhf_market" / "watchlist.json"),
    )

    # ── 运行时目录 ──
    @property
    def runtime_dir(self) -> Path:
        return Path(__file__).resolve().parents[3] / "tmp" / "realtime" / "jyhf_market"

    @property
    def status_path(self) -> Path:
        return self.runtime_dir / "market_collector.status.json"

    @property
    def log_path(self) -> Path:
        return self.runtime_dir / "market_collector.log"

    # ── 推送开关 ──
    allow_push_redis: bool = os.getenv("JYHF_MARKET_PUSH_REDIS", "1") == "1"
    allow_push_db: bool = os.getenv("JYHF_MARKET_PUSH_DB", "1") == "1"


def load_config() -> JyhfMarketConfig:
    return JyhfMarketConfig()
