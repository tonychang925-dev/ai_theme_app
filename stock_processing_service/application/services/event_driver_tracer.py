"""EventDriverTracer — 盘后复盘事件→题材因果链查询服务。

从 event_subject_map + news_event 查出每个题材当日/近N日的驱动新闻事件，
供复盘报告生成"XX题材因XX事件走强"的因果叙事。

Phase P0: 基础版本，直接查询 DB，不缓存。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from stock_processing_service.integrations.a_stock_data.resolvers.reason_theme_resolver import (
    DEFAULT_THEME_KEYWORDS,
)

logger = logging.getLogger(__name__)

# 单次查询最大题材数
_MAX_SUBJECT_KEYS_PER_QUERY = 50
# 默认回溯天数
_DEFAULT_LOOKBACK_DAYS = 3


class EventDriverTracer:
    """查询题材的驱动新闻事件。"""

    def __init__(self, pool: Any) -> None:
        """
        Args:
            pool: asyncpg connection pool (from DatabaseGateway._client.pool)
        """
        self._pool = pool

    async def trace(
        self,
        subject_keys: List[str],
        trade_date: date,
        *,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        per_theme_limit: int = 3,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """批量查询多个题材的驱动事件。

        Args:
            subject_keys: 题材 subject_key 列表
            trade_date: 复盘日期
            lookback_days: 向前回溯天数（含当日）
            per_theme_limit: 每个题材最多返回几条事件

        Returns:
            {subject_key: [event_dict, ...], ...}
        """
        if not subject_keys:
            return {}

        since = trade_date - timedelta(days=lookback_days)
        until = trade_date + timedelta(days=1)

        results: Dict[str, List[Dict[str, Any]]] = {sk: [] for sk in subject_keys}

        # 分批查询，避免 IN 子句过长
        for batch_start in range(0, len(subject_keys), _MAX_SUBJECT_KEYS_PER_QUERY):
            batch_keys = subject_keys[batch_start:batch_start + _MAX_SUBJECT_KEYS_PER_QUERY]
            batch_results = await self._query_batch(batch_keys, since, until, per_theme_limit)
            for sk, events in batch_results.items():
                results[sk] = events

        return results

    async def _query_batch(
        self,
        subject_keys: List[str],
        since: date,
        until: date,
        per_theme_limit: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """单批查询。"""
        sql = """
        WITH ranked AS (
            SELECT
                esm.subject_key,
                ne.id AS event_id,
                ne.summary,
                ne.event_time,
                esm.confidence,
                esm.match_reason,
                ROW_NUMBER() OVER (
                    PARTITION BY esm.subject_key
                    ORDER BY
                        esm.confidence DESC NULLS LAST,
                        ne.event_time DESC NULLS LAST,
                        ne.id DESC
                ) AS rn
            FROM event_subject_map esm
            JOIN news_event ne ON ne.id = esm.event_id
            WHERE esm.subject_key = ANY($1::varchar[])
              AND ne.event_time >= $2::timestamp
              AND ne.event_time < $3::timestamp
              AND NULLIF(ne.summary, '') IS NOT NULL
        )
        SELECT subject_key, event_id, summary, event_time, confidence, match_reason, rn
        FROM ranked
        WHERE rn <= $4
        ORDER BY subject_key, rn
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, subject_keys, since, until, per_theme_limit)
        except Exception as exc:
            logger.warning("EventDriverTracer query failed: %s", exc)
            return {sk: [] for sk in subject_keys}

        results: Dict[str, List[Dict[str, Any]]] = {sk: [] for sk in subject_keys}
        for row in rows:
            sk = row["subject_key"]
            if sk not in results:
                results[sk] = []
            results[sk].append({
                "event_id": row["event_id"],
                "summary": row["summary"],
                "event_time": row["event_time"].isoformat() if row["event_time"] else None,
                "confidence": float(row["confidence"]) if row["confidence"] else None,
                "match_reason": row["match_reason"],
            })

        return results

    async def trace_top_themes(
        self,
        theme_capital_reviews: List[Dict[str, Any]],
        trade_date: date,
        *,
        top_n: int = 10,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        per_theme_limit: int = 2,
    ) -> List[Dict[str, Any]]:
        """为资金流入前N的题材查询驱动事件，返回可直接注入复盘报告的富化列表。

        Args:
            theme_capital_reviews: 已排序的主题资金流列表
            trade_date: 复盘日期
            top_n: 取前N个题材
            lookback_days: 事件回溯天数
            per_theme_limit: 每个题材最多返回几条事件

        Returns:
            [{subject_key, theme_name, driver_events: [...], ...}, ...]
        """
        # 取前 N 并按 total_inflow 排序（已排好序）
        top_themes = theme_capital_reviews[:top_n]
        subject_keys = [
            str(row.get("subject_key") or "")
            for row in top_themes
        ]
        subject_keys = [sk for sk in subject_keys if sk]

        if not subject_keys:
            return []

        events_by_key = await self.trace(
            subject_keys, trade_date,
            lookback_days=lookback_days,
            per_theme_limit=per_theme_limit,
        )

        enriched: List[Dict[str, Any]] = []
        for row in top_themes:
            sk = str(row.get("subject_key") or "")
            enriched.append({
                "subject_key": sk,
                "theme_name": row.get("theme_name", sk),
                "total_inflow": row.get("total_inflow"),
                "leader_inflow": row.get("leader_inflow"),
                "limit_up_count": row.get("limit_up_count"),
                "cycle_stage": row.get("cycle_stage"),
                "driver_events": events_by_key.get(sk, []),
            })

        return enriched

    async def trace_theme_rows(
        self,
        theme_rows: List[Dict[str, Any]],
        trade_date: date,
        *,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        per_theme_limit: int = 2,
    ) -> List[Dict[str, Any]]:
        """Trace every limit-up matrix theme and map reason buckets to subjects."""
        normalized_rows: List[Dict[str, Any]] = []
        reason_theme_names: List[str] = []
        for row in theme_rows:
            if not isinstance(row, dict):
                continue
            subject_key = str(row.get("subject_key") or "").strip()
            theme_name = str(row.get("theme_name") or "").strip()
            normalized_rows.append(
                {
                    "subject_key": subject_key,
                    "theme_name": theme_name,
                }
            )
            if subject_key.startswith("reason:") and theme_name:
                reason_theme_names.append(theme_name)

        resolved_by_theme = await self._resolve_subject_keys_by_theme_names(
            reason_theme_names
        )
        query_keys: List[str] = []
        source_keys_by_row: Dict[str, List[str]] = {}
        for row in normalized_rows:
            subject_key = row["subject_key"]
            theme_name = row["theme_name"]
            source_keys: List[str] = []
            if (
                subject_key
                and subject_key != "other"
                and not subject_key.startswith("reason:")
            ):
                source_keys.append(subject_key)
            source_keys.extend(resolved_by_theme.get(theme_name, []))
            source_keys = list(dict.fromkeys(source_keys))
            source_keys_by_row[subject_key] = source_keys
            query_keys.extend(source_keys)

        events_by_key = await self.trace(
            list(dict.fromkeys(query_keys)),
            trade_date,
            lookback_days=lookback_days,
            per_theme_limit=per_theme_limit,
        )

        enriched: List[Dict[str, Any]] = []
        for row in normalized_rows:
            subject_key = row["subject_key"]
            events: List[Dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()
            for source_key in source_keys_by_row.get(subject_key, []):
                for event in events_by_key.get(source_key, []):
                    event_id = str(event.get("event_id") or "")
                    summary = str(event.get("summary") or "").strip()
                    dedupe_key = (event_id, summary)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    events.append(event)
            events.sort(
                key=lambda event: (
                    float(event.get("confidence") or 0),
                    str(event.get("event_time") or ""),
                    str(event.get("event_id") or ""),
                ),
                reverse=True,
            )
            enriched.append(
                {
                    **row,
                    "resolved_subject_keys": source_keys_by_row.get(subject_key, []),
                    "driver_events": events[:per_theme_limit],
                }
            )
        return enriched

    async def _resolve_subject_keys_by_theme_names(
        self,
        theme_names: List[str],
    ) -> Dict[str, List[str]]:
        unique_names = list(dict.fromkeys(name for name in theme_names if name))
        if not unique_names:
            return {}

        aliases_by_theme: Dict[str, set[str]] = {}
        all_aliases: set[str] = set()
        for theme_name in unique_names:
            aliases = {
                theme_name,
                *DEFAULT_THEME_KEYWORDS.get(theme_name, ()),
            }
            aliases_by_theme[theme_name] = aliases
            all_aliases.update(aliases)

        sql = """
        SELECT subject_key, concept
        FROM theme_gate_profile
        WHERE concept = ANY($1::text[])
          AND NULLIF(subject_key, '') IS NOT NULL
        ORDER BY concept, subject_key
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, sorted(all_aliases))
        except Exception as exc:
            logger.warning("EventDriverTracer theme resolution failed: %s", exc)
            return {name: [] for name in unique_names}

        result: Dict[str, List[str]] = {name: [] for name in unique_names}
        for row in rows:
            concept = str(row["concept"] or "").strip()
            subject_key = str(row["subject_key"] or "").strip()
            if not concept or not subject_key:
                continue
            for theme_name, aliases in aliases_by_theme.items():
                if concept in aliases and subject_key not in result[theme_name]:
                    result[theme_name].append(subject_key)
        return result


async def create_event_driver_tracer(pool: Any) -> EventDriverTracer:
    """工厂函数：创建 EventDriverTracer 实例。"""
    return EventDriverTracer(pool)
