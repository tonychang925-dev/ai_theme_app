"""Market-owned exact-date post-market recap read port."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Any, Dict, Optional

from theme_service.repositories.phase1_read_repository import Phase1ReadRepository


class Phase1MarketStateReadRepository(Phase1ReadRepository):
    """Extend Market's private Phase1 binding with the exact recap read port."""

    async def get_existing_post_market_recap_snapshot(
        self,
        trade_date: str,
    ) -> Optional[Dict[str, Any]]:
        parsed_date = date.fromisoformat(trade_date)
        await self.initialize()
        sql = """
        SELECT trade_date, snapshot_version, batch_id, trace_id, payload
        FROM post_market_recap_snapshot
        WHERE trade_date = $1::date
        LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, parsed_date)
            return dict(row) if row else None

    async def fetch_intel_event_by_item_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        match = re.fullmatch(r"event:(\d+):(.+)", item_id)
        if match:
            event_id, subject_key = int(match.group(1)), match.group(2)
            return await self._fetch_exact_news_event(event_id, subject_key)
        match = re.fullmatch(r"event:jyhf_cdp:(\d+)", item_id)
        if match:
            return await self._fetch_exact_jyhf_cdp_event(int(match.group(1)))
        return None

    async def fetch_intel_event_by_legacy_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        await self.initialize()
        event = await self._fetch_exact_news_event_by_id(event_id)
        if event is not None:
            return event
        return await self._fetch_exact_jyhf_cdp_event(event_id)

    async def _fetch_exact_news_event(
        self,
        event_id: int,
        subject_key: str,
    ) -> Optional[Dict[str, Any]]:
        sql = self._news_event_sql("ne.id = $1::bigint", "$2::text")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, event_id, subject_key, 1)
        return await self._public_event_row(rows[0]) if rows else None

    async def _fetch_exact_news_event_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        sql = self._news_event_sql("ne.id = $1::bigint", "$2::text")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, event_id, None, 1)
        return await self._public_event_row(rows[0]) if rows else None

    async def _fetch_exact_jyhf_cdp_event(self, staging_id: int) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            ('event:jyhf_cdp:' || id::text) AS item_id,
            'event'::text AS item_type,
            CASE
                WHEN (raw_json::jsonb->>'event_time')::text IS NOT NULL AND (raw_json::jsonb->>'event_time')::text <> ''
                THEN (rank_date::text || 'T' || (raw_json::jsonb->>'event_time')::text || ':00')::timestamp
                ELSE COALESCE(rank_date::timestamp, created_at)
            END AS occurred_at,
            COALESCE(NULLIF(subject_name, ''), subject_key) AS title,
            COALESCE(NULLIF(description, ''), subject_name, subject_key) AS summary,
            ARRAY[subject_key]::text[] AS theme_subject_keys,
            ARRAY[COALESCE(NULLIF(subject_name, ''), subject_key)]::text[] AS theme_names,
            ARRAY[]::text[] AS stock_ids,
            ARRAY[]::text[] AS stock_names,
            NULL::numeric AS confidence,
            COALESCE(pct_chg, 0)::numeric AS impact_score,
            'jyhf_cdp_dom'::text AS source_type,
            'jyhf_cdp'::text AS source_channel
        FROM subject_history_staging
        WHERE source_type = 'jyhf_cdp'
          AND id = $1::bigint
        ORDER BY id
        LIMIT 1
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, staging_id)
        return await self._public_event_row(rows[0]) if rows else None

    @staticmethod
    def _news_event_sql(identity_condition: str, subject_condition: str) -> str:
        return f"""
        WITH mapped AS (
            SELECT DISTINCT ON (ne.id, COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text))
                ne.id AS event_id,
                COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) AS subject_key,
                tm.name AS theme_name,
                COALESCE(ne.created_at, etm.created_at, nr.created_at, ne.event_time, nr.publish_date::timestamp) AS occurred_at,
                COALESCE(NULLIF(nr.title, ''), NULLIF(ne.summary, ''), ne.event_type, ('事件#' || ne.id::text)) AS title,
                COALESCE(ne.summary, nr.content, '') AS summary,
                COALESCE(etm.confidence, ne.confidence) AS confidence,
                ne.severity_score AS impact_score
            FROM news_event ne
            LEFT JOIN news_raw nr ON nr.id = ne.news_id
            JOIN event_theme_map etm ON etm.event_id = ne.id
            JOIN theme_master tm ON tm.id = etm.theme_id
            WHERE {identity_condition}
              AND ({subject_condition}::text IS NULL OR COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) = {subject_condition})
            ORDER BY ne.id, COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text), etm.confidence DESC NULLS LAST, etm.created_at DESC NULLS LAST
        )
        SELECT
            ('event:' || event_id::text || ':' || subject_key) AS item_id,
            'event'::text AS item_type,
            occurred_at,
            title,
            summary,
            ARRAY[subject_key]::text[] AS theme_subject_keys,
            ARRAY[theme_name]::text[] AS theme_names,
            ARRAY[]::text[] AS stock_ids,
            ARRAY[]::text[] AS stock_names,
            confidence,
            impact_score,
            'event_theme_map'::text AS source_type,
            'realtime_news'::text AS source_channel
        FROM mapped
        ORDER BY occurred_at DESC NULLS LAST, event_id DESC, subject_key
        LIMIT $3::bigint
        """

    async def _public_event_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        occurred_at = item.get("occurred_at")
        if hasattr(occurred_at, "isoformat"):
            item["occurred_at"] = occurred_at.isoformat()
        for field in ("theme_subject_keys", "theme_names", "stock_ids", "stock_names"):
            item[field] = [str(value) for value in item.get(field) or []]
        if isinstance(item.get("impact_score"), Decimal):
            item["impact_score"] = str(item["impact_score"])
        return item
