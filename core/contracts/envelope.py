"""P1-2: 统一事件 Envelope — 兼容包装，不强制重写上游。

设计原则：
- ensure_envelope() 对已有 envelope 的消息透传
- 旧消息自动包装，补齐 trace_id / run_id / source_type
- 下游统一读 envelope["payload"] 获取业务数据
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Any

CST = timezone(timedelta(hours=8))

ENVELOPE_VERSION = "1.0"

SOURCE_TYPE_MAP: dict[str, str] = {
    "news": "news",
    "akshare": "news",
    "cls": "news",
    "jyhf_cdp": "dom",
    "jyhf_cdp_dom": "dom",
    "jyhf": "market",
    "tdx": "market",
    "kline_break_detector": "signal",
    "w2s": "signal",
    "decision_executor_feed": "alert",
    "manual": "manual",
    "replay": "replay",
}


def _current_run_id() -> str:
    env_run_id = os.environ.get("REALTIME_RUN_ID") or os.environ.get("RUN_ID") or ""
    if env_run_id:
        return env_run_id
    return f"realtime-{datetime.now(CST).strftime('%Y%m%d-%H%M%S')}"


def _infer_source_type(message: dict) -> str:
    """从消息内容推测 source_type。"""
    channel = str(message.get("source_channel") or message.get("source") or "").lower()
    for key, stype in SOURCE_TYPE_MAP.items():
        if key in channel:
            return stype
    return "unknown"


def _infer_market_session() -> str:
    now = datetime.now(CST)
    h, m = now.hour, now.minute
    if h < 9 or (h == 9 and m < 15):
        return "premarket"
    if h == 9 and 15 <= m <= 25:
        return "auction"
    if h < 11 or (h == 11 and m <= 30):
        return "morning"
    if h < 15 or (h == 15 and m <= 5):
        return "intraday"
    return "postmarket"


def ensure_envelope(message: dict, default_schema_type: str = "UnknownEvent") -> dict:
    """对消息做 envelope 兼容包装。

    已有 envelope_version 的消息直接透传。
    旧消息补齐 trace_id / run_id / source_type 等追踪字段。
    """
    if message.get("envelope_version"):
        return message

    event_id = str(
        message.get("event_id")
        or message.get("news_id")
        or message.get("item_id")
        or f"evt_{uuid.uuid4().hex[:12]}"
    )

    return {
        "envelope_version": ENVELOPE_VERSION,
        "event_id": event_id,
        "trace_id": str(message.get("trace_id") or uuid.uuid4().hex),
        "run_id": _current_run_id(),
        "source_type": _infer_source_type(message),
        "source_name": str(message.get("source") or message.get("source_name") or "legacy"),
        "source_channel": str(message.get("source_channel") or ""),
        "biz_date": str(message.get("biz_date") or date.today().isoformat()),
        "market_session": _infer_market_session(),
        "event_time": str(
            message.get("event_time")
            or message.get("created_at")
            or message.get("occurred_at")
            or datetime.now(CST).isoformat()
        ),
        "ingest_time": datetime.now(CST).isoformat(),
        "schema_type": default_schema_type,
        "schema_version": "legacy-adapted",
        "payload": dict(message),
        "quality": {},
        "routing": {},
    }


def get_payload(message: dict) -> dict:
    """从 envelope 消息中提取业务 payload。

    兼容旧消息（无 envelope）和新消息（有 envelope）。
    """
    if message.get("envelope_version"):
        return message.get("payload", message)
    return message
