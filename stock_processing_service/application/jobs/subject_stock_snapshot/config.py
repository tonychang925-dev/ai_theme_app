"""题材股票日快照 — 可插拔数据源配置."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


ProviderMode = Literal["jyhf", "tushare_join"]
OnExistingMode = Literal["skip", "upsert", "replace"]


@dataclass(frozen=True)
class SubjectStockSnapshotConfig:
    """可通过环境变量 STOCK_SNAPSHOT_PROVIDER / STOCK_SNAPSHOT_ON_EXISTING 覆盖."""

    provider: ProviderMode = "jyhf"
    on_existing: OnExistingMode = "skip"
    enable_quality_check: bool = True

    # ── JYHF ──
    jyhf_enabled: bool = True
    jyhf_sync_theme_list: bool = False        # 题材列表低频同步，日常默认关闭
    jyhf_load_staging: bool = False           # 同上
    jyhf_import_stock_daily: bool = True

    # ── Tushare Join ──
    tushare_join_enabled: bool = True
    tushare_join_require_daily_bar: bool = True
    tushare_join_auto_run_daily_bar: bool = False
    tushare_join_rank_method: str = "pct_chg_desc"
    tushare_join_stock_id_format: str = "local_6digit"
    tushare_join_limit_up_rule: str = "pct_chg_9_8"

    @classmethod
    def from_env(cls) -> SubjectStockSnapshotConfig:
        provider_raw = os.getenv("STOCK_SNAPSHOT_PROVIDER", "jyhf").strip().lower()
        if provider_raw not in ("jyhf", "tushare_join"):
            provider_raw = "jyhf"
        on_existing_raw = os.getenv("STOCK_SNAPSHOT_ON_EXISTING", "skip").strip().lower()
        if on_existing_raw not in ("skip", "upsert", "replace"):
            on_existing_raw = "skip"
        return cls(
            provider=provider_raw,  # type: ignore[arg-type]
            on_existing=on_existing_raw,  # type: ignore[arg-type]
        )


def load_config() -> SubjectStockSnapshotConfig:
    return SubjectStockSnapshotConfig.from_env()
