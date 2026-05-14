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
        """

        count = 0
        async with pool.acquire() as conn:
            for row in rows:
                try:
                    await conn.execute(sql, *row)
                    count += 1
                except Exception:
                    pass  # duplicate — 忽略

        self._logger.info("db_sink wrote %s/%s events to subject_history_staging", count, len(events))
        return count

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


def _event_to_row(event: RawJyhfCdpEvent, batch_id: str) -> tuple:
    subject_key = _derive_subject_key(event.subject_name)
    trade_date = _parse_date(event.trade_date, event.subject_name)
    description = _build_description(event)
    pct_chg = event.pct_chg
    raw_json = json.dumps(event.model_dump(), ensure_ascii=False)

    # CDP 事件用 event_id hash 作为 subject_rank_id 用于 DB 去重
    import hashlib
    rank_id = int(hashlib.md5(event.event_id.encode()).hexdigest()[:12], 16) % (10 ** 9)
    return (
        subject_key,        # subject_key
        rank_id,             # subject_rank_id (hash of event_id for dedup)
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


def _parse_date(trade_date: str, subject_name: str = "") -> date | None:
    # 1. 优先用 DOM 提取的 trade_date
    if trade_date:
        try:
            return date.fromisoformat(trade_date)
        except ValueError:
            pass
    # 2. 从 subject_name 中提取日期（如 "5月12日龙虎榜" → 2026-05-12）
    import re
    m = re.search(r'(\d{1,2})月(\d{1,2})日', subject_name)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            return date(datetime.now().year, month, day)
        except ValueError:
            pass
    return None


def _build_description(event: RawJyhfCdpEvent) -> str:
    parts: list[str] = []
    if event.driver_title:
        prefix = "【新题材更新：" if event.event_type == "新题材更新" else "【驱动事件："
        parts.append(f"{prefix}{event.driver_title}】")
    if event.driver_desc:
        parts.append(event.driver_desc)
    if event.news_source:
        parts.append(f"（新闻来源：{event.news_source}）")
    return "\n".join(parts) if parts else event.subject_name
