from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from stock_processing_service.application.services.pre_market_brief_auto_scheduler import (
    PreMarketBriefAutoScheduler,
    decide_pre_market_brief_schedule,
)


CN_TZ = ZoneInfo("Asia/Shanghai")


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 16, hour, minute, tzinfo=CN_TZ)


def test_pre_market_brief_schedule_windows():
    assert decide_pre_market_brief_schedule(_dt(15, 30)).action == "rebuild"
    assert decide_pre_market_brief_schedule(_dt(15, 30)).next_sleep_seconds == 600
    assert decide_pre_market_brief_schedule(_dt(22, 0)).action == "rebuild"
    assert decide_pre_market_brief_schedule(_dt(22, 0)).next_sleep_seconds == 900
    assert decide_pre_market_brief_schedule(_dt(7, 0)).action == "rebuild"
    assert decide_pre_market_brief_schedule(_dt(7, 0)).next_sleep_seconds == 300
    assert decide_pre_market_brief_schedule(_dt(8, 20)).reason == "last_rebuild_before_finalize"
    assert decide_pre_market_brief_schedule(_dt(8, 30), finalized=False).action == "finalize"
    assert decide_pre_market_brief_schedule(_dt(8, 31), finalized=True).action == "idle"


class _Client:
    def __init__(self, *, finalize_response: dict | None = None):
        self.calls: list[dict] = []
        self.finalize_response = finalize_response or {"ok": True, "status": "final"}

    async def rebuild(self, *, trade_date, source, limit, force):
        self.calls.append(
            {
                "method": "rebuild",
                "trade_date": trade_date,
                "source": source,
                "limit": limit,
                "force": force,
            }
        )
        return {"ok": True}

    async def finalize(self, *, trade_date, force):
        self.calls.append({"method": "finalize", "trade_date": trade_date, "force": force})
        return self.finalize_response


@pytest.mark.asyncio
async def test_pre_market_brief_scheduler_rebuild_calls_sps_without_force_by_default():
    client = _Client()
    scheduler = PreMarketBriefAutoScheduler(client)

    result = await scheduler.run_once(trade_date=date(2026, 5, 16), now=_dt(7, 10))

    assert result["action"] == "rebuild"
    assert client.calls == [
        {
            "method": "rebuild",
            "trade_date": date(2026, 5, 16),
            "source": "db_first",
            "limit": 200,
            "force": False,
        }
    ]


@pytest.mark.asyncio
async def test_pre_market_brief_scheduler_finalizes_once_per_trade_date():
    client = _Client()
    scheduler = PreMarketBriefAutoScheduler(client)

    first = await scheduler.run_once(trade_date=date(2026, 5, 16), now=_dt(8, 30))
    second = await scheduler.run_once(trade_date=date(2026, 5, 16), now=_dt(8, 31))

    assert first["action"] == "finalize"
    assert second["action"] == "idle"
    assert client.calls == [{"method": "finalize", "trade_date": date(2026, 5, 16), "force": False}]


@pytest.mark.asyncio
async def test_pre_market_brief_scheduler_retries_finalize_when_sps_did_not_freeze():
    client = _Client(finalize_response={"ok": False, "affected_rows": 0, "status": "missing"})
    scheduler = PreMarketBriefAutoScheduler(client)

    first = await scheduler.run_once(trade_date=date(2026, 5, 16), now=_dt(8, 30))
    second = await scheduler.run_once(trade_date=date(2026, 5, 16), now=_dt(8, 31))

    assert first["action"] == "finalize"
    assert second["action"] == "finalize"
    assert [call["method"] for call in client.calls] == ["finalize", "finalize"]
