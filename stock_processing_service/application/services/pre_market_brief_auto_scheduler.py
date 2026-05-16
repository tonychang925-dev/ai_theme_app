from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx


ScheduleAction = Literal["rebuild", "finalize", "idle"]
CN_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class PreMarketBriefScheduleDecision:
    action: ScheduleAction
    next_sleep_seconds: int
    reason: str


def _seconds_until(now: datetime, target: time) -> int:
    local = now.astimezone(CN_TZ)
    target_dt = local.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
    if target_dt <= local:
        target_dt += timedelta(days=1)
    return max(1, int((target_dt - local).total_seconds()))


def decide_pre_market_brief_schedule(
    now: datetime,
    *,
    finalized: bool = False,
) -> PreMarketBriefScheduleDecision:
    """Return scheduler action only; no report business logic lives here."""
    local = now.astimezone(CN_TZ)
    current = local.time()

    if time(15, 30) <= current < time(22, 0):
        return PreMarketBriefScheduleDecision("rebuild", 10 * 60, "after_close_rebuild")
    if current >= time(22, 0) or current < time(7, 0):
        return PreMarketBriefScheduleDecision("rebuild", 15 * 60, "overnight_rebuild")
    if time(7, 0) <= current < time(8, 20):
        return PreMarketBriefScheduleDecision("rebuild", 5 * 60, "pre_open_rebuild")
    if time(8, 20) <= current < time(8, 30):
        return PreMarketBriefScheduleDecision("rebuild", 5 * 60, "last_rebuild_before_finalize")
    if time(8, 30) <= current < time(15, 30):
        if finalized:
            return PreMarketBriefScheduleDecision("idle", _seconds_until(local, time(15, 30)), "final_already_frozen")
        return PreMarketBriefScheduleDecision("finalize", 60 * 60, "finalize_at_or_after_0830")
    return PreMarketBriefScheduleDecision("idle", _seconds_until(local, time(15, 30)), "outside_rebuild_window")


class PreMarketBriefSpsClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 30.0) -> None:
        self._base_url = (base_url or os.getenv("STOCK_PROCESSING_READ_BASE_URL") or "http://127.0.0.1:8090").rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def rebuild(self, *, trade_date: date, source: str = "db_first", limit: int = 200, force: bool = False) -> dict[str, Any]:
        payload = {
            "trade_date": trade_date.isoformat(),
            "source": source,
            "limit": limit,
            "dry_run": False,
            "force": force,
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            resp = await client.post(f"{self._base_url}/api/v1/pre_market_brief/rebuild", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def finalize(self, *, trade_date: date, force: bool = False) -> dict[str, Any]:
        payload = {"trade_date": trade_date.isoformat(), "force": force}
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            resp = await client.post(f"{self._base_url}/api/v1/pre_market_brief/finalize", json=payload)
            resp.raise_for_status()
            return resp.json()


class PreMarketBriefAutoScheduler:
    def __init__(
        self,
        client: Any,
        *,
        source: str = "db_first",
        limit: int = 200,
        force_rebuild: bool = False,
        force_finalize: bool = False,
    ) -> None:
        self._client = client
        self._source = source
        self._limit = max(1, int(limit))
        self._force_rebuild = force_rebuild
        self._force_finalize = force_finalize
        self._finalized_dates: set[str] = set()

    async def run_once(self, *, trade_date: date, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(CN_TZ)
        finalized = trade_date.isoformat() in self._finalized_dates
        decision = decide_pre_market_brief_schedule(now, finalized=finalized)
        result: dict[str, Any] = {
            "action": decision.action,
            "reason": decision.reason,
            "trade_date": trade_date.isoformat(),
            "next_sleep_seconds": decision.next_sleep_seconds,
        }
        if decision.action == "rebuild":
            result["response"] = await self._client.rebuild(
                trade_date=trade_date,
                source=self._source,
                limit=self._limit,
                force=self._force_rebuild,
            )
        elif decision.action == "finalize":
            response = await self._client.finalize(
                trade_date=trade_date,
                force=self._force_finalize,
            )
            result["response"] = response
            if bool(response.get("ok")) or response.get("status") == "final" or int(response.get("affected_rows") or 0) > 0:
                self._finalized_dates.add(trade_date.isoformat())
        return result

    async def run_forever(self, *, trade_date_provider, poll_now=None) -> None:
        while True:
            now = poll_now() if poll_now else datetime.now(CN_TZ)
            trade_date = trade_date_provider(now)
            result = await self.run_once(trade_date=trade_date, now=now)
            await asyncio.sleep(max(1, int(result["next_sleep_seconds"])))
