from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JyhfCdpServiceConfig:
    project_root: Path
    host: str = "127.0.0.1"
    port: int = 8095
    cdp_port: int = 9223
    interval_seconds: float = 20.0
    app_path: str = "/Applications/久赢恒丰.app"
    allow_push_intel: bool = False
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_stream_feed: str = "stream:event:feed"

    @property
    def runtime_dir(self) -> Path:
        return self.project_root / "tmp" / "realtime" / "jyhf_cdp_service"

    @property
    def status_path(self) -> Path:
        return self.runtime_dir / "status.json"

    @property
    def dedup_path(self) -> Path:
        return self.runtime_dir / "seen_keys.json"

    @property
    def log_path(self) -> Path:
        return self.project_root / "logs" / "jyhf_cdp_service.log"

    @property
    def raw_event_dir(self) -> Path:
        return self.project_root / "theme_data_complete" / "cdp_events"

    @property
    def snapshot_dir(self) -> Path:
        return self.runtime_dir / "snapshots"


def load_config() -> JyhfCdpServiceConfig:
    root = Path(os.getenv("AI_THEME_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()
    return JyhfCdpServiceConfig(
        project_root=root,
        host=str(os.getenv("JYHF_CDP_SERVICE_HOST", "127.0.0.1")),
        port=int(os.getenv("JYHF_CDP_SERVICE_PORT", "8095")),
        cdp_port=int(os.getenv("JYHF_CDP_PORT", "9223")),
        interval_seconds=float(os.getenv("JYHF_CDP_INTERVAL_SECONDS", "20")),
        app_path=str(os.getenv("JYHF_APP_PATH", "/Applications/久赢恒丰.app")),
        allow_push_intel=str(os.getenv("JYHF_CDP_PUSH_INTEL", "0")).lower() in {"1", "true", "yes", "on"},
        redis_host=str(os.getenv("REDIS_HOST", "127.0.0.1")),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        redis_db=int(os.getenv("REDIS_DB", "0")),
        redis_stream_feed=str(os.getenv("JYHF_CDP_REDIS_STREAM_FEED", "stream:event:feed")),
    )

