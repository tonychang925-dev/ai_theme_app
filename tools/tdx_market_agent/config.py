"""TDX Market Agent 配置 — 环境变量驱动，无外部依赖."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    host: str = os.getenv("TDX_AGENT_HOST", "127.0.0.1")
    port: int = int(os.getenv("TDX_AGENT_PORT", "8766"))
    timeout_seconds: float = float(os.getenv("TDX_AGENT_TIMEOUT", "15.0"))
    log_level: str = os.getenv("TDX_AGENT_LOG_LEVEL", "info")


def load_config() -> AgentConfig:
    return AgentConfig()
