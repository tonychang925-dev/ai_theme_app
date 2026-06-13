"""题材热度排名 — 可插拔数据源配置."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


ProviderMode = Literal["jyhf", "snapshot_agg"]
OnExistingMode = Literal["skip", "upsert", "replace"]


@dataclass(frozen=True)
class SubjectRankConfig:
    """可通过环境变量 SUBJECT_RANK_PROVIDER / SUBJECT_RANK_ON_EXISTING 覆盖."""

    provider: ProviderMode = "jyhf"
    on_existing: OnExistingMode = "skip"
    enable_quality_check: bool = True

    jyhf_enabled: bool = True

    snapshot_agg_enabled: bool = True
    snapshot_agg_require_subject_stock_snapshot: bool = True
    snapshot_agg_heat_formula_version: str = "v1"
    snapshot_agg_rank_method: str = "heat_desc"
    snapshot_agg_min_stock_count: int = 3

    @classmethod
    def from_env(cls) -> SubjectRankConfig:
        provider_raw = os.getenv("SUBJECT_RANK_PROVIDER", "jyhf").strip().lower()
        if provider_raw not in ("jyhf", "snapshot_agg"):
            provider_raw = "jyhf"
        on_existing_raw = os.getenv("SUBJECT_RANK_ON_EXISTING", "skip").strip().lower()
        if on_existing_raw not in ("skip", "upsert", "replace"):
            on_existing_raw = "skip"
        return cls(
            provider=provider_raw,  # type: ignore[arg-type]
            on_existing=on_existing_raw,  # type: ignore[arg-type]
        )


def load_config() -> SubjectRankConfig:
    return SubjectRankConfig.from_env()
