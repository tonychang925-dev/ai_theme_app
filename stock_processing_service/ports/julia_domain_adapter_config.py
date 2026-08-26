"""Deployment configuration for ai-theme-adapter/1.0 HTTP boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


@dataclass(frozen=True)
class JuliaDomainAdapterHTTPConfig:
    workbench_base_dir: Path
    execute_timeout_seconds: float = 5.0
    max_request_bytes: int = 262_144
    max_response_bytes: int = 1_048_576
    redis_required: bool = False
    redis_url: str = ""
    database_required: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "JuliaDomainAdapterHTTPConfig":
        values = env or os.environ
        root = values.get("AI_THEME_APP_ROOT")
        default_root = Path(root) if root else Path(__file__).resolve().parents[2]
        workbench = values.get("JULIA_ADAPTER_WORKBENCH_BASE_DIR")
        return cls(
            workbench_base_dir=Path(workbench) if workbench else default_root / "tmp" / "analyst_workbench",
            execute_timeout_seconds=_float_env(values, "JULIA_ADAPTER_EXECUTE_TIMEOUT_SECONDS", 5.0, minimum=0.1),
            max_request_bytes=_int_env(values, "JULIA_ADAPTER_MAX_REQUEST_BYTES", 262_144, minimum=1024),
            max_response_bytes=_int_env(values, "JULIA_ADAPTER_MAX_RESPONSE_BYTES", 1_048_576, minimum=1024),
            redis_required=_bool_env(values, "JULIA_ADAPTER_REDIS_REQUIRED", False),
            redis_url=str(values.get("REDIS_URL") or "redis://127.0.0.1:6379/0"),
            database_required=_bool_env(values, "JULIA_ADAPTER_DATABASE_REQUIRED", True),
        )

    def redis_url_valid(self) -> bool:
        if not self.redis_url:
            return False
        scheme = urlparse(self.redis_url).scheme
        return scheme in {"redis", "rediss", "unix"}


def _bool_env(values: Mapping[str, str], key: str, default: bool) -> bool:
    raw = str(values.get(key, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(values: Mapping[str, str], key: str, default: int, *, minimum: int) -> int:
    try:
        value = int(str(values.get(key, default)))
    except Exception:
        return default
    return max(minimum, value)


def _float_env(values: Mapping[str, str], key: str, default: float, *, minimum: float) -> float:
    try:
        value = float(str(values.get(key, default)))
    except Exception:
        return default
    return max(minimum, value)


__all__ = ["JuliaDomainAdapterHTTPConfig"]
