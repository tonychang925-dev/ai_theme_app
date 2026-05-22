from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")

from stock_processing_service.application.services.pre_market_brief_auto_scheduler import (
    decide_pre_market_brief_schedule,
    resolve_pre_market_brief_trade_date,
    PreMarketBriefSpsClient,
)


def _cn(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 20, hour, minute, 0, tzinfo=CN_TZ)


class _FakeClient:
    def __init__(self, calendar=None):
        self._calendar = calendar or {}

    async def get_trade_calendar(self, *, trade_date):
        return self._calendar


# ── decide_pre_market_brief_schedule ──────────────────────────────────

def test_1459_not_finalized_is_finalize():
    """14:59 in 08:00-15:00 zone — finalize when not yet finalized."""
    d = decide_pre_market_brief_schedule(_cn(14, 59), finalized=False)
    assert d.action == "finalize", f"Expected finalize, got {d.action}"

def test_1459_finalized_is_idle():
    """14:59 in 08:00-15:00 zone — idle when finalized."""
    d = decide_pre_market_brief_schedule(_cn(14, 59), finalized=True)
    assert d.action == "idle", f"Expected idle, got {d.action}"

def test_1500_is_rebuild():
    d = decide_pre_market_brief_schedule(_cn(15, 0))
    assert d.action == "rebuild", f"Expected rebuild, got {d.action}"

def test_2300_is_rebuild():
    d = decide_pre_market_brief_schedule(_cn(23, 0))
    assert d.action == "rebuild", f"Expected rebuild, got {d.action}"

def test_0759_is_rebuild():
    d = decide_pre_market_brief_schedule(_cn(7, 59))
    assert d.action == "rebuild", f"Expected rebuild, got {d.action}"

def test_0800_not_finalized_is_finalize():
    d = decide_pre_market_brief_schedule(_cn(8, 0), finalized=False)
    assert d.action == "finalize", f"Expected finalize, got {d.action}"

def test_0801_finalized_is_idle():
    d = decide_pre_market_brief_schedule(_cn(8, 1), finalized=True)
    assert d.action == "idle", f"Expected idle, got {d.action}"

def test_1200_not_finalized_retries_finalize():
    d = decide_pre_market_brief_schedule(_cn(12, 0), finalized=False)
    assert d.action == "finalize", f"Expected finalize, got {d.action}"


# ── resolve_pre_market_brief_trade_date ──────────────────────────────

async def test_before_1500_uses_current_date():
    now = _cn(14, 59)
    td = await resolve_pre_market_brief_trade_date(PreMarketBriefSpsClient(), now=now)
    assert td.isoformat() == "2026-05-20"

async def test_after_1500_seeks_next_trade_date():
    now = _cn(15, 0)
    client = _FakeClient({"trade_date": "2026-05-20", "prev_trade_date": "2026-05-19", "next_trade_date": "2026-05-21"})
    td = await resolve_pre_market_brief_trade_date(client, now=now)
    assert td.isoformat() == "2026-05-21"

async def test_explicit_trade_date_overrides():
    td = await resolve_pre_market_brief_trade_date(PreMarketBriefSpsClient(), explicit_trade_date="2026-05-19")
    assert td.isoformat() == "2026-05-19"


async def test_after_1500_calendar_null_falls_back_to_next_weekday():
    """When trade calendar returns no next_trade_date, fallback to next weekday."""
    now = _cn(15, 0)
    client = _FakeClient({"trade_date": "2026-05-20", "prev_trade_date": "2026-05-19"})  # no next_trade_date
    td = await resolve_pre_market_brief_trade_date(client, now=now)
    assert td.isoformat() == "2026-05-21"  # Wed→Thu


async def test_after_1500_friday_falls_back_to_monday():
    """Friday after 15:00 → fallback to Monday."""
    now = datetime(2026, 5, 22, 15, 0, 0, tzinfo=CN_TZ)  # Friday
    client = _FakeClient({})  # no data at all
    td = await resolve_pre_market_brief_trade_date(client, now=now)
    assert td.isoformat() == "2026-05-25"  # Friday→Monday
