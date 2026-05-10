from __future__ import annotations

from pydantic import BaseModel, Field


class CollectorStatus(BaseModel):
    service: str = "jyhf_cdp_service"
    running: bool = True
    collector_running: bool = False
    collector_state: str = "stopped"
    started_at: str | None = None
    uptime_seconds: float = 0.0
    app_running: bool = False
    cdp_connected: bool = False
    cdp_port: int = 9223
    current_route: str | None = None
    current_tab: str | None = None
    last_capture_at: str | None = None
    last_event_at: str | None = None
    capture_count_total: int = 0
    new_event_count_total: int = 0
    duplicate_count_total: int = 0
    parse_error_count_total: int = 0
    pushed_to_stream_count_total: int = 0
    pushed_to_db_count_total: int = 0
    pushed_to_intel_count_total: int = 0
    review_queue_count_total: int = 0
    last_error: str | None = None


class CommandResult(BaseModel):
    ok: bool
    message: str
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    command: list[str] = Field(default_factory=list)


class LogsResponse(BaseModel):
    log_file: str
    lines: list[str] = Field(default_factory=list)


class RawJyhfCdpEvent(BaseModel):
    event_id: str
    dedup_key: str
    source_system: str = "jyhf"
    source_channel: str = "jyhf_cdp"
    source_type: str = "cdp_dom_new_event"
    capture_time: str
    trade_date: str
    event_time: str
    subject_name: str
    subject_key: str | None = None
    pct_chg: float | None = None
    driver_title: str
    driver_desc: str
    news_source: str | None = None
    raw_text: str
    parse_version: str = "jyhf_cdp_new_event_v1"
