import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import asyncpg


class Phase1ReadRepository:
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or self._build_database_url()
        self._pool: Optional[asyncpg.Pool] = None
        self._event_review_table_exists: Optional[bool] = None

    def _build_database_url(self) -> str:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        database = os.getenv("POSTGRES_DATABASE", "stock_data_test")
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    async def initialize(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=5,
                command_timeout=60,
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def fetch_rank(
        self,
        limit: int = 50,
        rank_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            subject_key,
            theme_id,
            theme_name,
            rank_date,
            heat,
            heat_name,
            pct_chg,
            his_pct_chg,
            red,
            description,
            source_system
        FROM vw_theme_rank_current
        WHERE ($1::date IS NULL OR rank_date = $1::date)
        ORDER BY rank_date DESC, heat DESC NULLS LAST, pct_chg DESC NULLS LAST, subject_key
        LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, rank_date, limit)
        return [dict(r) for r in rows]

    async def fetch_theme_list(
        self,
        limit: int = 50,
        binding_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            subject_key,
            theme_id,
            theme_name,
            node_level,
            parent_subject_key,
            binding_status,
            last_verified_at
        FROM vw_subject_theme_binding
        WHERE ($1::text IS NULL OR binding_status = $1)
        ORDER BY
            CASE binding_status
                WHEN 'active_binding' THEN 1
                WHEN 'staging_only' THEN 2
                ELSE 3
            END,
            subject_key
        LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, binding_status, limit)
        return [dict(r) for r in rows]

    async def fetch_theme_detail(self, subject_key: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        if subject_key.startswith("theme:"):
            theme_id = subject_key.split(":", 1)[1]
            sql = """
            SELECT
                ('theme:' || tm.id::text) AS subject_key,
                tm.id AS theme_id,
                tm.name AS theme_name,
                'L3'::VARCHAR(10) AS node_level,
                NULL::VARCHAR(80) AS parent_subject_key,
                NULL::TEXT AS ancestors,
                CASE
                    WHEN tm.status = 'active' THEN 'active_binding'
                    ELSE 'inactive_binding'
                END AS binding_status,
                COALESCE(NULLIF(tm.description, ''), NULLIF(tpe.summary, '')) AS summary,
                NULL::TEXT AS detail_html,
                NULL::TEXT AS reason_short,
                NULL::INTEGER AS detail_version,
                TRUE AS is_current,
                tm.updated_at AS detail_updated_at,
                COALESCE(tm.news_count, 0) AS history_count,
                0 AS children_count,
                COALESCE(tm.stock_count, 0) AS stock_count
            FROM theme_master tm
            LEFT JOIN theme_profile_ext tpe
              ON tpe.subject_key = tm.source_id
            WHERE tm.id = $1::int
            LIMIT 1
            """
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(sql, theme_id)
            return dict(row) if row else None

        sql = """
        WITH base AS (
            SELECT
                b.subject_key,
                b.theme_id,
                b.theme_name,
                b.node_level,
                b.parent_subject_key,
                b.ancestors,
                b.binding_status,
                COALESCE(NULLIF(d.reason_short, ''), NULLIF(d.summary, '')) AS summary,
                d.detail_html,
                d.reason_short,
                d.detail_version,
                d.is_current,
                d.detail_updated_at
            FROM vw_subject_theme_binding b
            LEFT JOIN vw_theme_detail_joined d
              ON d.subject_key = b.subject_key
            WHERE b.subject_key = $1
            LIMIT 1
        )
        SELECT
            base.*,
            COALESCE((
                SELECT COUNT(*) FROM vw_theme_history_candidate h
                WHERE h.subject_key = base.subject_key
            ), 0) AS history_count,
            COALESCE((
                SELECT COUNT(*) FROM vw_theme_tree_candidate c
                WHERE c.parent_subject_key = base.subject_key
            ), 0) AS children_count,
            COALESCE((
                SELECT COUNT(*) FROM vw_theme_stock_map_candidate s
                WHERE s.subject_key = base.subject_key
            ), 0) AS stock_count
        FROM base
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, subject_key)
        return dict(row) if row else None

    async def fetch_children(
        self,
        subject_key: str,
        relation_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            parent_subject_key,
            parent_theme_id,
            parent_theme_name,
            child_subject_key,
            child_theme_id,
            child_name,
            relation_type,
            source_type,
            pct_chg,
            stock_count,
            limit_up_count,
            lead_stock_id,
            lead_stock_name,
            depth
        FROM vw_theme_tree_candidate
        WHERE parent_subject_key = $1
          AND ($2::text IS NULL OR relation_type = $2)
        ORDER BY depth NULLS LAST, child_subject_key
        LIMIT $3
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_key, relation_type, limit)
        return [dict(r) for r in rows]

    async def fetch_history(
        self,
        subject_key: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        if subject_key.startswith("theme:"):
            theme_id = subject_key.split(":", 1)[1]
            sql = """
            SELECT
                ('theme:' || tm.id::text) AS subject_key,
                tm.id AS theme_id,
                tm.name AS theme_name,
                NULL::BIGINT AS subject_rank_id,
                COALESCE(ne.event_time::date, ne.created_at::date) AS rank_date,
                COALESCE(ne.summary, '') AS description,
                NULL::INTEGER AS heat,
                NULL::VARCHAR(50) AS heat_name,
                NULL::NUMERIC(8,4) AS pct_chg,
                NULL::NUMERIC(8,4) AS his_pct_chg,
                ne.id AS event_id,
                'event_theme_map' AS source_type,
                ne.id::TEXT AS source_ref
            FROM event_theme_map etm
            JOIN news_event ne
              ON ne.id = etm.event_id
            JOIN theme_master tm
              ON tm.id = etm.theme_id
            WHERE tm.id = $1::int
            ORDER BY COALESCE(ne.event_time, ne.created_at) DESC, ne.id DESC
            LIMIT $2
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, theme_id, limit)
            return [dict(r) for r in rows]

        sql = """
        SELECT
            subject_key,
            theme_id,
            theme_name,
            subject_rank_id,
            rank_date,
            description,
            heat,
            heat_name,
            pct_chg,
            his_pct_chg,
            event_id,
            source_type,
            source_ref
        FROM (
            SELECT
                h.*,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        h.subject_key,
                        h.rank_date,
                        CASE
                            WHEN h.event_id IS NOT NULL THEN h.event_id::text
                            ELSE COALESCE(NULLIF(BTRIM(h.description), ''), h.source_ref)
                        END
                    ORDER BY
                        CASE h.source_type
                            WHEN 'jyhf_history' THEN 0
                            WHEN 'jyhf_rank_daily' THEN 1
                            WHEN 'event_theme_map' THEN 2
                            WHEN 'event_subject_map' THEN 3
                            ELSE 9
                        END,
                        h.source_ref DESC
                ) AS rn
            FROM vw_theme_history_candidate h
            WHERE h.subject_key = $1
        ) ranked
        WHERE rn = 1
        ORDER BY rank_date DESC NULLS LAST, source_ref DESC
        LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_key, limit)
        return [dict(r) for r in rows]

    async def fetch_stocks_by_theme(
        self,
        subject_key: str,
        mapping_scope: str = "pool",
        include_leaders: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            subject_key,
            theme_id,
            theme_name,
            stock_id,
            stock_name,
            relation_type_candidate,
            top,
            sort,
            reason,
            remark,
            confidence,
            source_type,
            mapping_scope,
            detail_html,
            stock_remark,
            price,
            pct_chg
        FROM (
            SELECT
                c.*,
                ROW_NUMBER() OVER (
                    PARTITION BY c.subject_key, c.stock_id
                    ORDER BY
                        CASE c.mapping_scope
                            WHEN 'leader_overlay' THEN 0
                            WHEN 'pool' THEN 1
                            ELSE 2
                        END,
                        CASE c.relation_type_candidate
                            WHEN 'leader' THEN 1
                            WHEN 'core' THEN 2
                            ELSE 3
                        END,
                        c.sort NULLS LAST,
                        c.source_type
                ) AS rn
            FROM vw_theme_stock_map_candidate c
            WHERE c.subject_key = $1
              AND (
                ($2::text = 'pool' AND (c.mapping_scope = 'pool' OR ($3::boolean = TRUE AND c.mapping_scope = 'leader_overlay')))
                OR ($2::text = 'leader_overlay' AND c.mapping_scope = 'leader_overlay')
                OR ($2::text = 'all')
              )
        ) dedup
        WHERE rn = 1
        ORDER BY
            CASE mapping_scope
                WHEN 'leader_overlay' THEN 0
                WHEN 'pool' THEN 1
                ELSE 2
            END,
            CASE relation_type_candidate
                WHEN 'leader' THEN 1
                WHEN 'core' THEN 2
                ELSE 3
            END,
            sort NULLS LAST,
            stock_id
        LIMIT $4
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_key, mapping_scope, include_leaders, limit)
        return [dict(r) for r in rows]

    async def fetch_themes_by_stock(
        self,
        stock_id: str,
        mapping_scope: str = "pool",
        include_leaders: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            subject_key,
            theme_id,
            theme_name,
            stock_id,
            stock_name,
            relation_type_candidate,
            top,
            sort,
            reason,
            remark,
            confidence,
            source_type,
            mapping_scope,
            detail_html,
            stock_remark,
            price,
            pct_chg
        FROM (
            SELECT
                c.*,
                ROW_NUMBER() OVER (
                    PARTITION BY c.subject_key, c.stock_id
                    ORDER BY
                        CASE c.mapping_scope
                            WHEN 'leader_overlay' THEN 0
                            WHEN 'pool' THEN 1
                            ELSE 2
                        END,
                        CASE c.relation_type_candidate
                            WHEN 'leader' THEN 1
                            WHEN 'core' THEN 2
                            ELSE 3
                        END,
                        c.sort NULLS LAST,
                        c.source_type
                ) AS rn
            FROM vw_theme_stock_map_candidate c
            WHERE c.stock_id = $1
              AND (
                ($2::text = 'pool' AND (c.mapping_scope = 'pool' OR ($3::boolean = TRUE AND c.mapping_scope = 'leader_overlay')))
                OR ($2::text = 'leader_overlay' AND c.mapping_scope = 'leader_overlay')
                OR ($2::text = 'all')
              )
        ) dedup
        WHERE rn = 1
        ORDER BY
            CASE mapping_scope
                WHEN 'leader_overlay' THEN 0
                WHEN 'pool' THEN 1
                ELSE 2
            END,
            CASE relation_type_candidate
                WHEN 'leader' THEN 1
                WHEN 'core' THEN 2
                ELSE 3
            END,
            sort NULLS LAST,
            subject_key
        LIMIT $4
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, stock_id, mapping_scope, include_leaders, limit)
        return [dict(r) for r in rows]

    @staticmethod
    def _parse_feed_date(feed_date: Optional[str]) -> date:
        if not feed_date:
            return datetime.now().date()
        return datetime.fromisoformat(feed_date).date()

    @staticmethod
    def _preferred_stock_source_order_sql(alias: str = "tsm") -> str:
        return f"""
            CASE {alias}.source_type
                WHEN 'jyhf_stock_daily' THEN 0
                WHEN 'jyhf_stock_list' THEN 1
                WHEN 'jyhf_children_leader' THEN 2
                ELSE 9
            END
        """

    async def _fetch_stock_tags_by_subjects(self, subject_keys: List[str], per_subject: int = 3) -> Dict[str, Dict[str, List[str]]]:
        if not subject_keys:
            return {}
        sql = """
        SELECT subject_key, stock_id, stock_name
        FROM (
            SELECT
                tsm.subject_key,
                tsm.stock_id,
                tsm.stock_name,
                ROW_NUMBER() OVER (
                    PARTITION BY tsm.subject_key
                    ORDER BY
                        CASE tsm.source_type
                            WHEN 'jyhf_stock_daily' THEN 0
                            WHEN 'jyhf_stock_list' THEN 1
                            WHEN 'jyhf_children_leader' THEN 2
                            ELSE 9
                        END,
                        CASE tsm.relation_type
                            WHEN 'leader' THEN 1
                            WHEN 'core' THEN 2
                            ELSE 3
                        END,
                        tsm.stock_id
                ) AS rn
            FROM theme_stock_map tsm
            WHERE tsm.subject_key = ANY($1::varchar[])
              AND tsm.source_type IN ('jyhf_stock_daily', 'jyhf_stock_list', 'jyhf_children_leader')
        ) ranked
        WHERE rn <= $2
        ORDER BY subject_key, rn
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, subject_keys, per_subject)

        result: Dict[str, Dict[str, List[str]]] = {}
        for row in rows:
            key = str(row["subject_key"])
            bucket = result.setdefault(key, {"stock_ids": [], "stock_names": []})
            bucket["stock_ids"].append(str(row["stock_id"]))
            bucket["stock_names"].append(row["stock_name"])
        return result

    async def _fetch_intel_stock_moves(
        self,
        feed_date: date,
        subject_key: Optional[str],
        stock_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        sql = """
        WITH ranked AS (
            SELECT
                s.trade_date,
                s.subject_key,
                COALESCE(b.theme_name, s.subject_key) AS theme_name,
                s.stock_id,
                s.stock_name,
                s.rank_order,
                s.pct_chg,
                s.limit_up,
                s.is_leader
            FROM subject_stock_daily_snapshot s
            LEFT JOIN vw_subject_theme_binding b
              ON b.subject_key = s.subject_key
            WHERE s.trade_date = $1::date
              AND ($2::text IS NULL OR s.subject_key = $2)
              AND ($3::text IS NULL OR s.stock_id = $3)
        ),
        subject_rollup AS (
            SELECT
                trade_date,
                subject_key,
                theme_name,
                COUNT(*) FILTER (WHERE limit_up) AS limit_up_count,
                MAX(CASE WHEN is_leader THEN stock_name END) AS leader_stock_name,
                MAX(CASE WHEN is_leader THEN stock_id END) AS leader_stock_id,
                MAX(CASE WHEN is_leader THEN pct_chg END) AS leader_pct_chg,
                ARRAY_REMOVE(ARRAY_AGG(CASE WHEN rank_order <= 5 THEN stock_id END ORDER BY rank_order), NULL) AS top_stock_ids,
                ARRAY_REMOVE(ARRAY_AGG(CASE WHEN rank_order <= 5 THEN stock_name END ORDER BY rank_order), NULL) AS top_stock_names
            FROM ranked
            GROUP BY trade_date, subject_key, theme_name
        )
        SELECT
            ('stock_move:' || subject_key || ':' || trade_date::text) AS item_id,
            'stock_move'::text AS item_type,
            trade_date::timestamp AS occurred_at,
            theme_name AS title,
            TRIM(BOTH '；' FROM CONCAT(
                CASE
                    WHEN leader_stock_name IS NOT NULL THEN '龙头股 ' || leader_stock_name ||
                        COALESCE(' (' || ROUND(leader_pct_chg::numeric, 2)::text || '%)', '')
                    ELSE ''
                END,
                CASE
                    WHEN limit_up_count > 0 THEN
                        CASE WHEN leader_stock_name IS NOT NULL THEN '；' ELSE '' END ||
                        '涨停 ' || limit_up_count::text || ' 家'
                    ELSE ''
                END
            )) AS summary,
            ARRAY[subject_key]::text[] AS theme_subject_keys,
            ARRAY[theme_name]::text[] AS theme_names,
            top_stock_ids AS stock_ids,
            top_stock_names AS stock_names,
            NULL::numeric AS confidence,
            GREATEST(COALESCE(limit_up_count, 0)::numeric, COALESCE(ABS(leader_pct_chg), 0)) AS impact_score,
            'jyhf_stock_daily'::text AS source_type,
            'jyhf_manual'::text AS source_channel
        FROM subject_rollup
        WHERE COALESCE(limit_up_count, 0) > 0 OR leader_stock_name IS NOT NULL
        ORDER BY limit_up_count DESC, ABS(leader_pct_chg) DESC NULLS LAST, subject_key
        LIMIT $4
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, feed_date, subject_key, stock_id, limit)
        return [dict(r) for r in rows]

    async def _fetch_intel_events(
        self,
        feed_date: date,
        session: str,
        subject_key: Optional[str],
        stock_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        sql = """
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
            LEFT JOIN news_raw nr
              ON nr.id = ne.news_id
            JOIN event_theme_map etm
              ON etm.event_id = ne.id
            JOIN theme_master tm
              ON tm.id = etm.theme_id
            WHERE (
                ne.event_time::date = $1::date
                OR ne.created_at::date = $1::date
                OR nr.publish_date::date = $1::date
            )
              AND ($2::text IS NULL OR COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) = $2)
              AND (
                $3::text IS NULL
                OR EXISTS (
                    SELECT 1
                    FROM theme_stock_map tsm
                    WHERE tsm.subject_key = tm.source_id
                      AND tsm.stock_id = $3
                      AND tsm.source_type IN ('jyhf_stock_daily', 'jyhf_stock_list', 'jyhf_children_leader')
                )
              )
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
        LIMIT $4
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, feed_date, subject_key, stock_id, limit)

        items: List[Dict[str, Any]] = []
        for row in rows:
            occurred_at = row["occurred_at"]
            if session != "all" and isinstance(occurred_at, datetime):
                hm = occurred_at.hour * 60 + occurred_at.minute
                if session == "pre" and hm >= 9 * 60 + 30:
                    continue
                if session == "intra" and not (9 * 60 + 30 <= hm < 15 * 60):
                    continue
                if session == "post" and hm < 15 * 60:
                    continue
            items.append(dict(row))
        return items

    async def _fetch_intel_jyhf_cdp_events(
        self,
        feed_date: date,
        session: str,
        subject_key: Optional[str],
        stock_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """JYHF CDP DOM 实时采集事件 → 情报台 event 条目。"""
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
          AND rank_date = $1::date
          AND ($2::text IS NULL OR subject_key = $2)
        ORDER BY
            CASE
                WHEN (raw_json::jsonb->>'event_time')::text IS NOT NULL AND (raw_json::jsonb->>'event_time')::text <> ''
                THEN (rank_date::text || 'T' || (raw_json::jsonb->>'event_time')::text || ':00')::timestamp
                ELSE COALESCE(rank_date::timestamp, created_at)
            END DESC NULLS LAST, id DESC
        LIMIT $3
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, feed_date, subject_key, limit)

        items: List[Dict[str, Any]] = []
        for row in rows:
            occurred_at = row["occurred_at"]
            if session != "all" and isinstance(occured_at, datetime):
                hm = occurred_at.hour * 60 + occurred_at.minute
                if session == "pre" and hm >= 9 * 60 + 30:
                    continue
                if session == "intra" and not (9 * 60 + 30 <= hm < 15 * 60):
                    continue
                if session == "post" and hm < 15 * 60:
                    continue
            items.append(dict(row))
        return items

    async def _has_event_review_table(self) -> bool:
        if self._event_review_table_exists is not None:
            return self._event_review_table_exists

        await self.initialize()
        sql = "SELECT to_regclass('public.event_review_queue')::text"
        async with self._pool.acquire() as conn:
            table_name = await conn.fetchval(sql)
        self._event_review_table_exists = bool(table_name)
        return self._event_review_table_exists

    async def _fetch_intel_event_reviews(
        self,
        feed_date: date,
        session: str,
        subject_key: Optional[str],
        stock_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if subject_key or stock_id:
            return []

        if not await self._has_event_review_table():
            return []

        sql = """
        SELECT
            ('event_review:' || q.event_id::text) AS item_id,
            'event_review'::text AS item_type,
            COALESCE(ne.event_time, ne.created_at, q.created_at, nr.publish_date::timestamp) AS occurred_at,
            COALESCE(NULLIF(nr.title, ''), NULLIF(ne.summary, ''), ne.event_type, ('事件#' || q.event_id::text)) AS title,
            COALESCE(q.reason, ne.summary, nr.content, '') AS summary,
            CASE
                WHEN mapped.subject_key IS NULL THEN ARRAY[]::text[]
                ELSE ARRAY[mapped.subject_key]::text[]
            END AS theme_subject_keys,
            ARRAY[
                COALESCE(
                    NULLIF(q.proposed_theme_name, ''),
                    NULLIF(mapped.theme_name, ''),
                    '其他'
                )
            ]::text[] AS theme_names,
            ARRAY[]::text[] AS stock_ids,
            ARRAY[]::text[] AS stock_names,
            ne.confidence AS confidence,
            ne.severity_score AS impact_score,
            'event_review_queue'::text AS source_type,
            COALESCE(NULLIF(q.source_channel, ''), 'realtime_news') AS source_channel
        FROM event_review_queue q
        JOIN news_event ne
          ON ne.id = q.event_id
        LEFT JOIN news_raw nr
          ON nr.id = ne.news_id
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) AS subject_key,
                tm.name AS theme_name
            FROM event_theme_map etm
            JOIN theme_master tm
              ON tm.id = etm.theme_id
            WHERE etm.event_id = q.event_id
            ORDER BY etm.confidence DESC NULLS LAST, etm.created_at DESC NULLS LAST
            LIMIT 1
        ) mapped ON TRUE
        WHERE q.review_status IN ('waiting', 'pending')
          AND COALESCE(NULLIF(q.source_channel, ''), 'realtime_news') = 'event_theme_matcher'
          AND (
            ne.event_time::date = $1::date
            OR ne.created_at::date = $1::date
            OR q.created_at::date = $1::date
            OR nr.publish_date::date = $1::date
          )
        ORDER BY COALESCE(ne.event_time, ne.created_at, q.created_at, nr.publish_date::timestamp) DESC NULLS LAST, q.event_id DESC
        LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, feed_date, limit)

        items: List[Dict[str, Any]] = []
        for row in rows:
            occurred_at = row["occurred_at"]
            if session != "all" and isinstance(occurred_at, datetime):
                hm = occurred_at.hour * 60 + occurred_at.minute
                if session == "pre" and hm >= 9 * 60 + 30:
                    continue
                if session == "intra" and not (9 * 60 + 30 <= hm < 15 * 60):
                    continue
                if session == "post" and hm < 15 * 60:
                    continue
            items.append(dict(row))
        return items

    async def _fetch_intel_theme_moves(
        self,
        feed_date: date,
        subject_key: Optional[str],
        stock_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        sql = """
        WITH ranked AS (
            SELECT
                ('theme_move:' || h.subject_key || ':' || COALESCE(h.source_ref, h.rank_date::text)) AS item_id,
                'theme_move'::text AS item_type,
                h.rank_date::timestamp AS occurred_at,
                COALESCE(h.theme_name, h.subject_key) AS title,
                COALESCE(h.description, '') AS summary,
                ARRAY[h.subject_key]::text[] AS theme_subject_keys,
                ARRAY[COALESCE(h.theme_name, h.subject_key)]::text[] AS theme_names,
                NULL::numeric AS confidence,
                h.heat::numeric AS impact_score,
                h.source_type,
                ROW_NUMBER() OVER (
                    PARTITION BY h.subject_key, COALESCE(h.description, '')
                    ORDER BY
                        CASE h.source_type
                            WHEN 'jyhf_history' THEN 0
                            WHEN 'jyhf_rank_daily' THEN 1
                            ELSE 9
                        END,
                        h.rank_date DESC NULLS LAST,
                        h.source_ref DESC NULLS LAST
                ) AS rn
            FROM vw_theme_history_candidate h
            WHERE h.rank_date = $1::date
              AND h.source_type IN ('jyhf_history', 'jyhf_rank_daily')
              AND ($2::text IS NULL OR h.subject_key = $2)
              AND (
                $3::text IS NULL
                OR EXISTS (
                    SELECT 1
                    FROM theme_stock_map tsm
                    WHERE tsm.subject_key = h.subject_key
                      AND tsm.stock_id = $3
                      AND tsm.source_type IN ('jyhf_stock_daily', 'jyhf_stock_list', 'jyhf_children_leader')
                )
              )
        )
        SELECT
            item_id,
            item_type,
            occurred_at,
            title,
            summary,
            theme_subject_keys,
            theme_names,
            confidence,
            impact_score,
            source_type,
            'jyhf_manual'::text AS source_channel
        FROM ranked
        WHERE rn = 1
        ORDER BY occurred_at DESC NULLS LAST, impact_score DESC NULLS LAST, title
        LIMIT $4
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, feed_date, subject_key, stock_id, limit)
        return [dict(r) for r in rows]

    async def _fetch_intel_new_themes(
        self,
        feed_date: date,
        subject_key: Optional[str],
        stock_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        sql = """
        WITH seen_dates AS (
            SELECT h.subject_key, h.rank_date AS seen_date
            FROM subject_history_staging h
            WHERE h.source_type = 'jyhf_history'
              AND h.rank_date IS NOT NULL
            UNION ALL
            SELECT r.subject_key, r.rank_date AS seen_date
            FROM subject_rank_daily r
            WHERE r.source_system = 'jyhf'
              AND r.rank_date IS NOT NULL
            UNION ALL
            SELECT s.subject_key, s.trade_date AS seen_date
            FROM subject_stock_daily_snapshot s
            WHERE s.trade_date IS NOT NULL
        ),
        first_seen AS (
            SELECT
                subject_key,
                MIN(seen_date) AS first_seen_date
            FROM seen_dates
            GROUP BY subject_key
        ),
        history_today AS (
            SELECT DISTINCT ON (h.subject_key)
                h.subject_key,
                COALESCE(
                    NULLIF(h.raw_json->>'createTime', '')::timestamp,
                    NULLIF(h.raw_json->>'updateTime', '')::timestamp,
                    h.rank_date::timestamp
                ) AS occurred_at,
                h.description,
                h.heat,
                h.source_type,
                COALESCE(h.subject_rank_id::text, h.id::text) AS source_ref
            FROM subject_history_staging h
            WHERE h.rank_date = $1::date
              AND h.source_type = 'jyhf_history'
            ORDER BY
                h.subject_key,
                CASE
                    WHEN h.raw_json->>'type' = '2' OR h.description LIKE '【新题材更新%' THEN 0
                    ELSE 1
                END,
                COALESCE(
                    NULLIF(h.raw_json->>'createTime', '')::timestamp,
                    NULLIF(h.raw_json->>'updateTime', '')::timestamp,
                    h.rank_date::timestamp
                ) DESC NULLS LAST
        )
        SELECT
            ('new_theme:' || fs.subject_key || ':' || fs.first_seen_date::text) AS item_id,
            'new_theme'::text AS item_type,
            COALESCE(
                ht.occurred_at,
                fs.first_seen_date::timestamp
            ) AS occurred_at,
            COALESCE(b.theme_name, sns.subject_name, fs.subject_key) AS title,
            COALESCE(ht.description, sns.reason, '') AS summary,
            ARRAY[fs.subject_key]::text[] AS theme_subject_keys,
            ARRAY[COALESCE(b.theme_name, sns.subject_name, fs.subject_key)]::text[] AS theme_names,
            NULL::numeric AS confidence,
            COALESCE(ht.heat::numeric, sns.importance::numeric, 0::numeric) AS impact_score,
            COALESCE(ht.source_type, sns.source_type, 'jyhf_first_seen') AS source_type,
            'jyhf_manual'::text AS source_channel
        FROM first_seen fs
        LEFT JOIN history_today ht
          ON ht.subject_key = fs.subject_key
        LEFT JOIN vw_subject_theme_binding b
          ON b.subject_key = fs.subject_key
        LEFT JOIN subject_node_staging sns
          ON sns.subject_key = fs.subject_key
        WHERE fs.first_seen_date = $1::date
          AND ($2::text IS NULL OR fs.subject_key = $2)
          AND ($3::text IS NULL OR EXISTS (
                SELECT 1
                FROM theme_stock_map tsm
                WHERE tsm.subject_key = fs.subject_key
                  AND tsm.stock_id = $3
                  AND tsm.source_type IN ('jyhf_stock_daily', 'jyhf_stock_list', 'jyhf_children_leader')
          ))
          AND (
                sns.subject_key IS NOT NULL
                OR b.subject_key IS NOT NULL
                OR EXISTS (
                    SELECT 1
                    FROM subject_stock_daily_snapshot s
                    WHERE s.subject_key = fs.subject_key
                      AND s.trade_date = $1::date
                )
          )
        ORDER BY occurred_at DESC, fs.subject_key
        LIMIT $4
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, feed_date, subject_key, stock_id, limit)
        return [dict(r) for r in rows]

    async def fetch_intel_feed(
        self,
        feed_date: Optional[str] = None,
        session: str = "all",
        item_type: str = "all",
        subject_key: Optional[str] = None,
        stock_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        target_date = self._parse_feed_date(feed_date)
        items: List[Dict[str, Any]] = []

        if item_type in {"all", "event"}:
            items.extend(await self._fetch_intel_events(target_date, session, subject_key, stock_id, limit))
            items.extend(await self._fetch_intel_jyhf_cdp_events(target_date, session, subject_key, stock_id, limit))
        if item_type in {"all", "event_review"}:
            items.extend(await self._fetch_intel_event_reviews(target_date, session, subject_key, stock_id, limit))
        if item_type in {"all", "theme_move"}:
            items.extend(await self._fetch_intel_theme_moves(target_date, subject_key, stock_id, limit))
        if item_type in {"all", "new_theme"}:
            items.extend(await self._fetch_intel_new_themes(target_date, subject_key, stock_id, limit))
        if item_type == "stock_move":
            items.extend(await self._fetch_intel_stock_moves(target_date, subject_key, stock_id, limit))

        subject_keys: List[str] = []
        for item in items:
            subject_keys.extend([str(x) for x in (item.get("theme_subject_keys") or []) if x])
        stock_tags = await self._fetch_stock_tags_by_subjects(sorted(set(subject_keys)))

        for item in items:
            theme_subject_keys = [str(x) for x in (item.get("theme_subject_keys") or []) if x]
            stock_ids: List[str] = [str(x) for x in (item.get("stock_ids") or []) if x]
            stock_names: List[str] = [str(x) for x in (item.get("stock_names") or []) if x]
            for key in theme_subject_keys:
                tags = stock_tags.get(key)
                if not tags:
                    continue
                for sid, sname in zip(tags["stock_ids"], tags["stock_names"]):
                    if sid not in stock_ids:
                        stock_ids.append(sid)
                        stock_names.append(sname)
                    if len(stock_ids) >= 5:
                        break
                if len(stock_ids) >= 5:
                    break
            item["theme_subject_keys"] = theme_subject_keys
            item["theme_names"] = [str(x) for x in (item.get("theme_names") or []) if x]
            item["stock_ids"] = stock_ids
            item["stock_names"] = stock_names
            occurred_at = item.get("occurred_at")
            if isinstance(occurred_at, (datetime, date)):
                item["occurred_at"] = occurred_at.isoformat()

        priority = {
            "new_theme": 0,
            "event_review": 1,
            "event": 2,
            "theme_move": 3,
            "stock_move": 4,
        }

        def _sort_key(item: Dict[str, Any]) -> tuple[int, float]:
            occurred_at = str(item.get("occurred_at") or "")
            try:
                ts = datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = 0.0
            return (priority.get(str(item.get("item_type") or ""), 9), -ts)

        items.sort(key=_sort_key)
        return items[:limit]

    async def fetch_latest_intel_event_date(
        self,
        subject_key: Optional[str] = None,
        stock_id: Optional[str] = None,
    ) -> Optional[str]:
        await self.initialize()
        sql = """
        SELECT MAX(event_date)::text AS latest_date
        FROM (
            SELECT COALESCE(ne.event_time::date, ne.created_at::date, etm.created_at::date, nr.publish_date::date, nr.created_at::date) AS event_date
            FROM news_event ne
            LEFT JOIN news_raw nr
              ON nr.id = ne.news_id
            JOIN event_theme_map etm
              ON etm.event_id = ne.id
            JOIN theme_master tm
              ON tm.id = etm.theme_id
            WHERE ($1::text IS NULL OR COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) = $1)
              AND (
                $2::text IS NULL
                OR EXISTS (
                    SELECT 1
                    FROM theme_stock_map tsm
                    WHERE tsm.subject_key = tm.source_id
                      AND tsm.stock_id = $2
                      AND tsm.source_type IN ('jyhf_stock_daily', 'jyhf_stock_list', 'jyhf_children_leader')
                )
              )
        ) t
        WHERE event_date IS NOT NULL
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, subject_key, stock_id)
