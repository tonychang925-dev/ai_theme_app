from __future__ import annotations

import json
from datetime import date
from logging import Logger

import asyncpg

from services.jyhf_cdp_service.config import JyhfCdpServiceConfig
from services.jyhf_cdp_service.schemas import RawJyhfCdpEvent


class DatabaseSink:
    """Writes JYHF CDP events to subject_history_staging table."""

    def __init__(self, config: JyhfCdpServiceConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._pool: asyncpg.Pool | None = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self._config.pg_host,
                port=self._config.pg_port,
                database=self._config.pg_database,
                user=self._config.pg_username,
                password=self._config.pg_password,
                min_size=1,
                max_size=3,
            )
            self._logger.info(
                "db_sink connected to %s:%s/%s",
                self._config.pg_host,
                self._config.pg_port,
                self._config.pg_database,
            )
        return self._pool

    async def write_events(self, events: list[RawJyhfCdpEvent], batch_id: str) -> int:
        """Write a batch of CDP events to subject_history_staging."""
        if not events:
            return 0

        pool = await self._ensure_pool()
        rows: list[tuple] = []
        for event in events:
            rows.append(_event_to_row(event, batch_id))

        sql = """
        INSERT INTO subject_history_staging (
            subject_key, subject_rank_id, rank_date, subject_name, description,
            pct_chg, source_type, raw_json, ingest_batch_id
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9
        )
        ON CONFLICT (subject_key, subject_rank_id) DO NOTHING
        """

        count = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    result = await conn.execute(sql, *row)
                    count += int(result.split()[-1]) if result and "INSERT" in result else 0

        self._logger.info("db_sink wrote %s/%s events to subject_history_staging", count, len(events))
        return count

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


def _event_to_row(event: RawJyhfCdpEvent, batch_id: str) -> tuple:
    subject_key = _derive_subject_key(event.subject_name)
    trade_date = _parse_date(event.trade_date)
    description = _build_description(event)
    pct_chg = event.pct_chg
    raw_json = json.dumps(event.model_dump(), ensure_ascii=False)

    return (
        subject_key,        # subject_key
        None,                # subject_rank_id (CDP events have no ranking)
        trade_date,          # rank_date
        event.subject_name,  # subject_name
        description,         # description
        pct_chg,             # pct_chg
        "jyhf_cdp",          # source_type
        raw_json,            # raw_json
        batch_id,            # ingest_batch_id
    )


def _derive_subject_key(subject_name: str) -> str:
    import re
    key = subject_name.strip()
    key = re.sub(r"[（）()\s]+", "_", key)
    key = re.sub(r"[^\w\u4e00-\u9fff_-]", "", key)
    return key or subject_name.strip()


def _parse_date(trade_date: str) -> date | None:
    if not trade_date:
        return None
    try:
        return date.fromisoformat(trade_date)
    except ValueError:
        return None


def _build_description(event: RawJyhfCdpEvent) -> str:
    parts: list[str] = []
    if event.driver_title:
        parts.append(f"【驱动事件：{event.driver_title}】")
    if event.driver_desc:
        parts.append(event.driver_desc)
    if event.news_source:
        parts.append(f"（新闻来源：{event.news_source}）")
    return "\n".join(parts) if parts else event.subject_name
