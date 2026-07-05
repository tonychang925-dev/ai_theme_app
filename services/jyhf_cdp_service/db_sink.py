from __future__ import annotations

import json
from datetime import date, datetime
from logging import Logger

import asyncpg

from services.jyhf_cdp_service.config import JyhfCdpServiceConfig
from services.jyhf_cdp_service.schemas import RawJyhfCdpEvent


class DatabaseSink:
    """Writes JYHF CDP events to subject_history_staging + news_event tables.

    P0-D: JYHF DOM events now also write to news_event(source_category='jyhf_dom')
    and optionally to event_subject_map(source='jyhf_dom_confirmed') when a
    mappable subject_key is present.
    """

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
        """Write a batch of CDP events to subject_history_staging + news_event."""
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
        news_count = 0
        esm_count = 0
        errors: list[str] = []
        async with pool.acquire() as conn:
            for idx, row in enumerate(rows):
                event = events[idx]
                try:
                    await conn.execute(sql, *row)
                    count += 1
                except Exception as exc:
                    errors.append(str(exc)[:200])

                # P0-D D1: 同步写 news_event（幂等，不触发 LLM，不进 stream:news:raw）
                news_id = await _write_news_event(conn, event, self._logger)
                if news_id:
                    news_count += 1

                # P0-D D2: 若有 subject_key，映射后写 event_subject_map
                if event.subject_key and event.subject_name:
                    written = await _write_event_subject_map(
                        conn, news_id, event, self._logger
                    )
                    if written:
                        esm_count += 1

        if errors:
            unique_errors = list(dict.fromkeys(errors))
            self._logger.warning(
                "db_sink %s/%s rows failed: %s",
                len(errors), len(rows), unique_errors[:3],
            )
        self._logger.info(
            "db_sink wrote %s/%s to subject_history_staging, %s news_event, %s event_subject_map",
            count, len(events), news_count, esm_count,
        )
        return count

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


def _event_to_row(event: RawJyhfCdpEvent, batch_id: str) -> tuple:
    # Prefer numeric JYHF subject_key (from popup extraId) over name-derived key
    if event.subject_key and event.subject_key.strip().isdigit():
        subject_key = event.subject_key.strip()
    else:
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


# ── P0-D: JYHF DOM → news_event + event_subject_map ──────────────────────

async def _write_news_event(
    conn: asyncpg.Connection,
    event: RawJyhfCdpEvent,
    logger: Logger,
) -> int | None:
    """幂等写入 news_event(source_category='jyhf_dom')，返回 news_event id。

    不进入 stream:news:raw，不触发 NewsStreamProcessor / LLM。
    """
    source_trace_id = f"jyhf_cdp:{event.event_id}"
    event_time = _resolve_event_time(event)
    summary = _build_description(event)
    raw_event_json = json.dumps(event.model_dump(), ensure_ascii=False)

    sql = """
    INSERT INTO news_event (
        news_id, event_type, summary, confidence,
        source_category, source_trace_id,
        theme_directive_processed,
        event_time, raw_event_json, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW())
    ON CONFLICT (source_trace_id) WHERE (source_trace_id IS NOT NULL) DO NOTHING
    RETURNING id
    """
    try:
        row = await conn.fetchrow(
            sql,
            0,                           # news_id (0 = no raw news)
            _map_event_type(event.event_type),  # event_type
            summary,                     # summary
            1.0,                         # confidence (JYHF DOM 已结构化)
            "jyhf_dom",                  # source_category
            source_trace_id,             # source_trace_id (幂等键)
            True,                        # theme_directive_processed
            event_time,                  # event_time
            raw_event_json,              # raw_event_json
        )
        if row:
            news_id = int(row["id"])
            logger.debug("jyhf_dom news_event id=%s trace_id=%s", news_id, source_trace_id)
            return news_id
        return None  # ON CONFLICT — already exists
    except Exception as exc:
        logger.warning("jyhf_dom news_event insert failed for %s: %s", source_trace_id, exc)
        return None


async def _write_event_subject_map(
    conn: asyncpg.Connection,
    news_id: int | None,
    event: RawJyhfCdpEvent,
    logger: Logger,
) -> bool:
    """如果 JYHF DOM 有 subject_key/theme_name，映射后写 event_subject_map。

    返回 True 表示写入成功。
    """
    if not news_id:
        return False

    numeric_key = await _resolve_numeric_subject_key(conn, event.subject_key, event.subject_name, logger)
    if not numeric_key:
        return False

    source_trace_id = f"jyhf_cdp:{event.event_id}"
    confidence = 1.0

    sql = """
    INSERT INTO event_subject_map (
        event_id, news_id, subject_key, subject_name,
        confidence, relation_type, source, source_trace_id,
        created_at, updated_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
    ON CONFLICT (event_id, subject_key, source) DO NOTHING
    """
    try:
        # Use news_id as the event_id in event_subject_map
        # (news_event.id serves as the "event" identifier for JYHF DOM events)
        await conn.execute(
            sql,
            news_id,                     # event_id (= news_event.id)
            news_id,                     # news_id
            numeric_key,                 # subject_key (数字 key)
            event.subject_name,          # subject_name (中文名)
            confidence,                  # confidence
            "primary",                   # relation_type
            "jyhf_dom_confirmed",        # source
            source_trace_id,             # source_trace_id
        )
        logger.debug(
            "jyhf_dom event_subject_map news_id=%s subject_key=%s subject_name=%s",
            news_id, numeric_key, event.subject_name,
        )
        return True
    except Exception as exc:
        logger.warning(
            "jyhf_dom event_subject_map insert failed news_id=%s key=%s: %s",
            news_id, numeric_key, exc,
        )
        return False


async def _resolve_numeric_subject_key(
    conn: asyncpg.Connection,
    subject_key_raw: str | None,
    subject_name: str,
    logger: Logger,
) -> str | None:
    """将 JYHF 的 subject_key 映射为系统内数字 subject_key。

    - 如果已经是纯数字 → 直接返回
    - 如果是中文名 → 通过 vw_subject_theme_binding / theme_gate_profile 映射
    """
    if not subject_key_raw:
        subject_key_raw = subject_name

    # 已经是纯数字
    if subject_key_raw.strip().isdigit():
        return subject_key_raw.strip()

    # 中文名映射：theme_gate_profile.concept 存储中文题材名
    try:
        row = await conn.fetchrow(
            """SELECT subject_key FROM theme_gate_profile
               WHERE TRIM(concept) = $1 LIMIT 1""",
            subject_key_raw.strip(),
        )
        if row:
            return str(row["subject_key"])

        # fallback: 用 subject_name 再试一次
        if subject_name.strip() != subject_key_raw.strip():
            row = await conn.fetchrow(
                """SELECT subject_key FROM theme_gate_profile
                   WHERE TRIM(concept) = $1 LIMIT 1""",
                subject_name.strip(),
            )
            if row:
                return str(row["subject_key"])
    except Exception as exc:
        logger.debug("jyhf_dom subject_key mapping via gate_profile failed: %s", exc)

    logger.info(
        "jyhf_dom subject_key mapping failed for '%s' / '%s' — only news_event written",
        subject_key_raw, subject_name,
    )
    return None


def _resolve_event_time(event: RawJyhfCdpEvent) -> datetime | None:
    """从 JYHF DOM 字段解析 event_time。"""
    # 优先用 event_time 字段
    if event.event_time:
        try:
            return datetime.fromisoformat(event.event_time)
        except ValueError:
            pass
    # fallback: trade_date
    trade_date = _parse_date(event.trade_date, event.subject_name)
    if trade_date:
        return datetime(trade_date.year, trade_date.month, trade_date.day)
    return None


def _map_event_type(event_type: str) -> str:
    """JYHF event_type → news_event.event_type 标准化。"""
    mapping = {
        "驱动事件": "主题驱动",
        "新题材更新": "新题材",
    }
    return mapping.get(event_type, event_type)
