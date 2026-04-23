from __future__ import annotations

import json
from datetime import date, datetime

import asyncpg

from stock_service.config import StockServiceConfig


def _coerce_trade_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _coerce_json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return list(value) if hasattr(value, "__iter__") else []


def _coerce_json_object(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


class ReportRepository:
    def __init__(self, config: StockServiceConfig):
        self.config = config
        self.pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                min_size=1,
                max_size=5,
            )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def fetch_theme_name_map(self, subject_keys: list[str]) -> dict[str, str]:
        keys = sorted({str(key).strip() for key in subject_keys if str(key).strip()})
        if not keys:
            return {}
        sql = """
        WITH keys AS (
            SELECT unnest($1::text[]) AS subject_key
        )
        SELECT
            k.subject_key,
            COALESCE(
                CASE
                    WHEN NULLIF(BTRIM(v.theme_name), '') IS NULL THEN NULL
                    WHEN BTRIM(v.theme_name) ~ '^[0-9]+$' THEN NULL
                    ELSE BTRIM(v.theme_name)
                END,
                CASE
                    WHEN NULLIF(BTRIM(tm.name), '') IS NULL THEN NULL
                    WHEN BTRIM(tm.name) ~ '^[0-9]+$' THEN NULL
                    ELSE BTRIM(tm.name)
                END,
                k.subject_key
            ) AS theme_name
        FROM keys k
        LEFT JOIN vw_subject_theme_binding v
          ON v.subject_key = k.subject_key
        LEFT JOIN theme_master tm
          ON COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) = k.subject_key
        """
        assert self.pool is not None
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, keys)
        except asyncpg.UndefinedTableError:
            return {}
        result: dict[str, str] = {}
        for row in rows:
            item = dict(row)
            theme_name = str(item.get("theme_name") or "").strip()
            if theme_name:
                result[str(item["subject_key"])] = theme_name
        return result

    async def fetch_jyhf_events(self, trade_date: str, limit: int = 50):
        sql = """
        SELECT
            ne.event_time,
            COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) AS subject_key,
            tm.name AS theme_name,
            COALESCE(ne.summary, '') AS summary,
            ne.theme_directive->>'jyhf_source_type' AS source_type
        FROM news_event ne
        JOIN event_theme_map etm
          ON etm.event_id = ne.id
        JOIN theme_master tm
          ON tm.id = etm.theme_id
        WHERE ne.theme_directive->>'jyhf_source_type' = 'jyhf_history'
          AND ne.event_time::date = $1::date
        ORDER BY ne.event_time DESC, ne.id DESC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        return [dict(r) for r in rows]

    async def fetch_market_environment_judgement(self, trade_date: str):
        sql = """
        SELECT
            market_health_score,
            market_bias,
            breadth_status,
            short_term_sentiment_status,
            relay_sentiment_status,
            intraday_fade_status,
            action_bias,
            conclusion,
            evidence,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM market_environment_judgement
        WHERE trade_date = $1::date
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, trade_date_value)
        if not row:
            return None
        item = dict(row)
        item["evidence"] = _coerce_json_list(item.get("evidence"))
        return item

    async def fetch_theme_environment_judgements(self, trade_date: str, limit: int = 30):
        sql = """
        SELECT
            subject_key,
            theme_name,
            board_health_status,
            board_effect_status,
            leader_support_status,
            follow_strength_status,
            action_bias,
            conclusion,
            evidence,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM theme_environment_judgement
        WHERE trade_date = $1::date
        ORDER BY
            CASE action_bias
                WHEN '可主做' THEN 0
                WHEN '可做弱转强' THEN 1
                WHEN '可观察' THEN 2
                WHEN '警惕高潮' THEN 3
                ELSE 4
            END,
            theme_name
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        results = []
        for row in rows:
            item = dict(row)
            item["evidence"] = _coerce_json_list(item.get("evidence"))
            results.append(item)
        return results

    async def fetch_mainline_judgements(self, trade_date: str, limit: int = 30):
        sql = """
        SELECT
            v2.subject_key,
            COALESCE(NULLIF(BTRIM(v2.theme_name), ''), v2.subject_key) AS theme_name,
            COALESCE(msd.state, v2.final_cycle_state) AS final_cycle_state,
            COALESCE(msd.is_mainline, v2.final_mainline_alive, FALSE) AS final_mainline_alive,
            COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score,
            v2.fade_risk_score,
            v2.fade_watch,
            v2.fade_confirmed,
            v2.confidence_score,
            e.event_count_3d,
            e.event_count_7d,
            e.limit_up_count
        FROM theme_cycle_judgement_v2 v2
        JOIN mainline_state_daily msd
          ON msd.trade_date = v2.trade_date
         AND msd.subject_key = v2.subject_key
        LEFT JOIN theme_cycle_evidence_daily e
          ON e.trade_date = v2.trade_date
         AND e.subject_key = v2.subject_key
        WHERE v2.trade_date = $1::date
          AND COALESCE(msd.is_mainline, FALSE) = TRUE
          AND COALESCE(msd.state, '') <> 'fade_confirmed'
        ORDER BY
            COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) DESC,
            COALESCE(v2.confidence_score, 0) DESC,
            v2.subject_key
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        return [dict(r) for r in rows]

    async def fetch_cycle_judgements(self, trade_date: str, limit: int = 30):
        sql = """
        SELECT
            v2.subject_key,
            COALESCE(NULLIF(BTRIM(v2.theme_name), ''), v2.subject_key) AS theme_name,
            (
                COALESCE(msd.is_mainline, FALSE)
                AND COALESCE(msd.state, '') <> 'fade_confirmed'
            ) AS is_main_theme,
            COALESCE(NULLIF(BTRIM(msd.state), ''), NULLIF(BTRIM(v2.final_cycle_state), ''), 'unknown') AS primary_cycle_stage,
            COALESCE(e.limit_up_count, 0) AS limit_up_count,
            ''::text AS leader_status,
            ''::text AS board_effect_status,
            CASE
                WHEN COALESCE(v2.fade_confirmed, FALSE) THEN '观望'
                WHEN COALESCE(v2.final_cycle_state, '') IN ('climax', '高潮') THEN '警惕高潮'
                WHEN COALESCE(v2.final_cycle_state, '') IN ('fermentation', '发酵', 'start', '启动') THEN '可主做'
                WHEN COALESCE(v2.final_cycle_state, '') IN ('repair', '修复', 'divergence', '分歧', 'rebound', '回流') THEN '可做弱转强'
                ELSE '可观察'
            END AS action_bias,
            COALESCE(v2.confidence_score, 0) AS confidence,
            COALESCE(NULLIF(BTRIM(v2.state_transition_reason), ''), '') AS conclusion,
            'theme_cycle_judgement_v2'::text AS source_type,
            ''::text AS source_trace_id,
            '{}'::jsonb AS source_trace,
            COALESCE(NULLIF(BTRIM(v2.source_version), ''), 'theme_cycle_judgement.v2') AS source_version,
            COALESCE(NULLIF(BTRIM(v2.state_machine_version), ''), 'theme_cycle_judgement.v2') AS rule_version
        FROM theme_cycle_judgement_v2 v2
        LEFT JOIN mainline_state_daily msd
          ON msd.trade_date = v2.trade_date
         AND msd.subject_key = v2.subject_key
        LEFT JOIN theme_cycle_evidence_daily e
          ON e.trade_date = v2.trade_date
         AND e.subject_key = v2.subject_key
        WHERE v2.trade_date = $1::date
        ORDER BY
            CASE
                WHEN (
                    COALESCE(msd.is_mainline, FALSE)
                    AND COALESCE(msd.state, '') <> 'fade_confirmed'
                ) THEN 0
                ELSE 1
            END,
            COALESCE(v2.confidence_score, 0) DESC,
            v2.subject_key
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        return [dict(r) for r in rows]

    async def fetch_mainline_state_transitions(self, trade_date: str, limit: int = 40):
        sql = """
        SELECT
            subject_key,
            COALESCE(NULLIF(BTRIM(theme_name), ''), subject_key) AS theme_name,
            COALESCE(NULLIF(BTRIM(from_state), ''), '--') AS from_state,
            COALESCE(NULLIF(BTRIM(to_state), ''), '--') AS to_state,
            COALESCE(NULLIF(BTRIM(transition_type), ''), 'flat') AS transition_type,
            COALESCE(confidence, 0) AS confidence,
            COALESCE(trigger_flags, '[]'::jsonb) AS trigger_flags
        FROM mainline_state_transition
        WHERE trade_date = $1::date
        ORDER BY
            CASE COALESCE(NULLIF(BTRIM(transition_type), ''), 'flat')
                WHEN 'fade' THEN 0
                WHEN 'downgrade' THEN 1
                WHEN 'upgrade' THEN 2
                ELSE 3
            END,
            COALESCE(confidence, 0) DESC,
            subject_key
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)

        results = []
        for row in rows:
            item = dict(row)
            item["trigger_flags"] = _coerce_json_list(item.get("trigger_flags"))
            results.append(item)
        return results

    async def fetch_theme_recent_rank_stats(self, trade_date: str, lookback_days: int = 5):
        sql = """
        WITH recent AS (
            SELECT
                r.subject_key,
                r.rank_date,
                COALESCE(r.pct_chg, 0) AS pct_chg,
                COALESCE(r.his_pct_chg, 0) AS his_pct_chg,
                COALESCE(r.red, FALSE) AS red,
                COALESCE(h.heat_name, '') AS heat_name,
                ROW_NUMBER() OVER (
                    PARTITION BY r.subject_key
                    ORDER BY r.rank_date DESC
                ) AS rn
            FROM subject_rank_daily r
            LEFT JOIN subject_history_staging h
              ON h.source_type = 'jyhf_history'
             AND h.subject_key = r.subject_key
             AND h.rank_date = r.rank_date
            WHERE r.rank_date <= $1::date
              AND r.rank_date >= ($1::date - (($2::int - 1) * INTERVAL '1 day'))
        )
        SELECT
            subject_key,
            COUNT(*) AS recent_days,
            SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END) AS positive_days,
            SUM(CASE WHEN red THEN 1 ELSE 0 END) AS red_days,
            AVG(pct_chg) AS avg_pct_chg,
            MAX(CASE WHEN rn = 1 THEN pct_chg END) AS latest_pct_chg,
            MAX(CASE WHEN rn = 1 THEN his_pct_chg END) AS latest_his_pct_chg,
            MAX(CASE WHEN rn = 1 THEN heat_name END) AS latest_heat_name
        FROM recent
        GROUP BY subject_key
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, lookback_days)
        return [dict(r) for r in rows]

    async def fetch_leader_candidates(self, trade_date: str, limit: int = 80):
        sql = """
        SELECT
            c.subject_key,
            c.theme_name,
            c.stock_id,
            c.stock_name,
            c.purity_score,
            c.leading_score,
            c.capital_score,
            c.structure_score,
            c.resilience_score,
            c.composite_score,
            c.candidate_rank,
            c.role_label,
            c.is_limit_up,
            c.limit_up_type,
            c.turnover_rate,
            c.volume_ratio,
            c.main_net_inflow,
            c.evidence,
            c.source_type,
            c.source_trace_id,
            c.source_trace,
            c.source_version,
            c.rule_version,
            p.position_label,
            p.trend_strength_score,
            p.ma_alignment_status,
            x.pattern_labels,
            s.open_price,
            s.high_price,
            s.low_price,
            s.close_price AS day_close_price,
            s.pre_close,
            s.pct_chg AS day_pct_chg,
            s.amount AS day_amount,
            CASE
                WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 20
                    THEN NULLIF(s.raw_json->>20, '')::integer
                ELSE NULL
            END AS current_flag
        FROM theme_leader_candidate c
        LEFT JOIN stock_position_judgement p
          ON p.trade_date = c.trade_date
         AND split_part(p.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        LEFT JOIN stock_pattern_judgement x
          ON x.trade_date = c.trade_date
         AND split_part(x.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        LEFT JOIN subject_stock_daily_snapshot s
          ON s.trade_date = c.trade_date
         AND s.subject_key = c.subject_key
         AND split_part(s.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        WHERE c.trade_date = $1::date
        ORDER BY c.subject_key, c.candidate_rank ASC, c.composite_score DESC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        results = []
        for row in rows:
            item = dict(row)
            item["evidence"] = _coerce_json_list(item.get("evidence"))
            if isinstance(item.get("pattern_labels"), str):
                try:
                    item["pattern_labels"] = json.loads(item["pattern_labels"])
                except Exception:
                    item["pattern_labels"] = []
            results.append(item)
        return results

    async def fetch_leader_llm_judgements(self, trade_date: str, limit: int = 30):
        sql = """
        SELECT
            trade_date,
            subject_key,
            theme_name,
            leader_stock_id,
            leader_status,
            confirmation_basis,
            runner_up_stock_id,
            card_position_stock_id,
            supplement_stock_id,
            eliminated_stock_id,
            judgement_json,
            reasoning_summary,
            model_name,
            prompt_version,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM theme_leader_llm_judgement
        WHERE trade_date = $1::date
        ORDER BY subject_key
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        results = []
        for row in rows:
            item = dict(row)
            if item.get("judgement_json") is None:
                item["judgement_json"] = {}
            results.append(item)
        return results

    async def fetch_pre_market_execution_plans(self, trade_date: str, limit: int = 30, include_avoid: bool = False):
        sql = """
        SELECT
            source_trade_date,
            subject_key,
            theme_name,
            theme_status,
            leader_stock_id,
            leader_stock_name,
            leader_status,
            action_today,
            action_bias,
            watch_reason,
            auction_focus_stock_id,
            auction_focus_stock_name,
            auction_signal_level,
            auction_signal_type,
            auction_action_today,
            auction_signal_score,
            auction_hard_reject_reason,
            invalid_conditions
        FROM pre_market_execution_plan
        WHERE trade_date = $1::date
          AND ($3::boolean = TRUE OR action_today <> 'avoid')
        ORDER BY
            CASE action_today
                WHEN 'act' THEN 0
                WHEN 'watch' THEN 1
                ELSE 2
            END,
            theme_name
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit, include_avoid)
        results = []
        for row in rows:
            item = dict(row)
            item["invalid_conditions"] = _coerce_json_list(item.get("invalid_conditions"))
            results.append(item)
        return results

    async def fetch_dragon_tiger_objects(self, trade_date: str, limit: int = 120):
        sql = """
        SELECT
            stock_id,
            stock_name,
            reason,
            net_amount,
            institution_seat_count,
            seat_summary,
            source_trace_id
        FROM dragon_tiger_object
        WHERE trade_date = $1::date
        ORDER BY ABS(net_amount) DESC, stock_id ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        results = []
        for row in rows:
            item = dict(row)
            item["seat_summary"] = _coerce_json_list(item.get("seat_summary"))
            results.append(item)
        return results

    async def fetch_subject_theme_links_for_stocks(self, trade_date: str, stock_ids: list[str]):
        if not stock_ids:
            return []
        sql = """
        SELECT DISTINCT
            s.subject_key,
            COALESCE(tm.name, s.subject_key) AS theme_name,
            s.stock_id,
            s.stock_name,
            s.rank_order,
            s.is_leader
        FROM subject_stock_daily_snapshot s
        LEFT JOIN theme_master tm
          ON COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) = s.subject_key
        WHERE trade_date = $1::date
          AND split_part(s.stock_id, '.', 1) = ANY($2::text[])
        ORDER BY theme_name, s.rank_order ASC, s.stock_name
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        normalized_ids = [str(item).split(".")[0] for item in stock_ids if str(item).strip()]
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, normalized_ids)
        return [dict(r) for r in rows]

    async def fetch_money_flow_enhanced(self, trade_date: str, limit: int = 120):
        sql = """
        SELECT
            subject_key,
            theme_name,
            stock_id,
            stock_name,
            role_label,
            role_enhanced,
            candidate_rank,
            money_flow_score,
            money_flow_tier,
            explanation,
            sources,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM money_flow_enhanced
        WHERE trade_date = $1::date
        ORDER BY money_flow_score DESC, subject_key ASC, candidate_rank ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        results = []
        for row in rows:
            item = dict(row)
            item["explanation"] = _coerce_json_list(item.get("explanation"))
            item["sources"] = _coerce_json_list(item.get("sources"))
            results.append(item)
        return results

    async def fetch_stock_abnormal_signals(
        self,
        trade_date: str,
        limit: int = 120,
        min_composite_score: float = 60.0,
        max_main_net_rank: int = 2,
    ):
        sql = """
        SELECT
            a.trade_date,
            a.subject_key,
            a.theme_name,
            a.stock_id,
            a.stock_name,
            a.turnover_rate,
            a.turnover_rank_in_theme,
            a.main_net_inflow,
            a.main_net_inflow_rank_in_theme,
            a.turnover_abnormal_score,
            a.capital_focus_score,
            a.is_high_turnover,
            a.is_extreme_turnover,
            a.volume_ratio_to_ma50,
            a.volume_abnormal_score,
            a.is_volume_breakout,
            a.is_double_volume,
            a.is_high_volume_bar,
            a.tail_amount,
            a.tail_amount_ratio,
            a.tail_unmatched_buy_order,
            a.tail_abnormal_score,
            a.has_tail_rush_buy,
            a.has_tail_large_unmatched_bid,
            a.hot_money_buy_names,
            a.institution_net_buy,
            a.institution_seat_count,
            a.has_hot_money_buy,
            a.has_institution_buy,
            CASE
                WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 20
                    THEN NULLIF(s.raw_json->>20, '')::integer
                ELSE NULL
            END AS current_flag,
            a.abnormal_labels,
            a.abnormal_composite_score,
            a.conclusion,
            a.evidence,
            a.source_type,
            a.source_trace_id,
            a.source_trace,
            a.source_version,
            a.rule_version
        FROM stock_abnormal_signal a
        LEFT JOIN subject_stock_daily_snapshot s
          ON s.trade_date = a.trade_date
         AND s.subject_key = a.subject_key
         AND split_part(s.stock_id, '.', 1) = split_part(a.stock_id, '.', 1)
        WHERE a.trade_date = $1::date
          AND split_part(a.stock_id, '.', 1) NOT LIKE '688%'
          AND UPPER(COALESCE(a.stock_name, '')) NOT LIKE 'ST%'
          AND UPPER(COALESCE(a.stock_name, '')) NOT LIKE '*ST%'
          AND COALESCE(a.abnormal_composite_score, 0) >= $3::numeric
          AND (
            (COALESCE(a.main_net_inflow_rank_in_theme, 0) > 0 AND COALESCE(a.main_net_inflow_rank_in_theme, 0) <= $4::int)
            OR COALESCE(a.has_institution_buy, FALSE)
            OR COALESCE(a.has_hot_money_buy, FALSE)
            OR COALESCE(a.has_tail_rush_buy, FALSE)
          )
        ORDER BY a.abnormal_composite_score DESC, a.theme_name ASC, a.stock_id ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                sql,
                trade_date_value,
                limit,
                float(min_composite_score),
                int(max_main_net_rank),
            )
        results = []
        for row in rows:
            item = dict(row)
            item["hot_money_buy_names"] = _coerce_json_list(item.get("hot_money_buy_names"))
            item["abnormal_labels"] = _coerce_json_list(item.get("abnormal_labels"))
            item["evidence"] = _coerce_json_list(item.get("evidence"))
            results.append(item)
        return results

    async def fetch_strong_stock_watch_history(self, trade_date: str, lookback_days: int = 7, limit: int = 120):
        sql = """
        SELECT
            h.trade_date,
            h.stock_id,
            h.stock_name,
            h.subject_key,
            h.theme_name,
            h.watch_status,
            h.watch_score,
            h.watch_priority,
            h.relay_role,
            h.pool_entry_type,
            h.cycle_state,
            h.mainline_strength_score,
            h.fade_watch,
            h.fade_confirmed,
            h.promoted_to_candidate,
            h.labels_json,
            h.evidence_json,
            a.turnover_rate,
            a.abnormal_composite_score,
            s.pct_chg,
            COALESCE(NULLIF(s.raw_json->>35, ''), '0')::numeric AS main_net_inflow
        FROM strong_stock_watch_history h
        LEFT JOIN stock_abnormal_signal a
          ON a.trade_date = h.trade_date
         AND split_part(a.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
        LEFT JOIN subject_stock_daily_snapshot s
          ON s.trade_date = h.trade_date
         AND split_part(s.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
        WHERE h.trade_date BETWEEN ($1::date - (($2::int - 1) * INTERVAL '1 day')) AND $1::date
        ORDER BY h.trade_date DESC, h.watch_score DESC, h.watch_priority DESC, h.stock_id ASC
        LIMIT $3
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, trade_date_value, lookback_days, limit)
        except asyncpg.UndefinedTableError:
            return []
        results = []
        for row in rows:
            item = dict(row)
            item["labels_json"] = _coerce_json_object(item.get("labels_json"))
            item["evidence_json"] = _coerce_json_object(item.get("evidence_json"))
            results.append(item)
        return results

    async def fetch_recent_dragon_tiger_stats(self, trade_date: str, lookback_days: int = 7):
        sql = """
        SELECT
            stock_id,
            COUNT(DISTINCT trade_date) AS dragon_tiger_days_lookback,
            MAX(trade_date) AS latest_dragon_tiger_date,
            SUM(net_amount) AS dragon_tiger_net_amount_sum
        FROM dragon_tiger_object
        WHERE trade_date BETWEEN ($1::date - (($2::int - 1) * INTERVAL '1 day')) AND $1::date
        GROUP BY stock_id
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, lookback_days)
        return [dict(r) for r in rows]

    async def fetch_theme_capital_flow_top(self, trade_date: str, limit: int = 10):
        sql = """
        WITH mainline AS MATERIALIZED (
            SELECT
                v2.trade_date,
                v2.subject_key,
                COALESCE(NULLIF(BTRIM(v2.theme_name), ''), v2.subject_key) AS theme_name,
                COALESCE(msd.state, v2.final_cycle_state) AS final_cycle_state,
                COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score
            FROM theme_cycle_judgement_v2 v2
            JOIN mainline_state_daily msd
              ON msd.trade_date = v2.trade_date
             AND msd.subject_key = v2.subject_key
            WHERE v2.trade_date = $1::date
              AND COALESCE(msd.is_mainline, FALSE) = TRUE
              AND COALESCE(msd.state, '') <> 'fade_confirmed'
        ),
        snapshot AS MATERIALIZED (
            SELECT
                subject_key,
                rank_order,
                is_leader,
                COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric AS main_net_inflow
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
        ),
        base AS (
            SELECT
                s.subject_key,
                COALESCE(NULLIF(BTRIM(m.theme_name), ''), s.subject_key) AS theme_name,
                m.final_cycle_state,
                m.mainline_strength_score,
                s.main_net_inflow,
                s.rank_order,
                s.is_leader
            FROM mainline m
            JOIN snapshot s
              ON m.subject_key = s.subject_key
        )
        SELECT
            subject_key,
            theme_name,
            final_cycle_state,
            AVG(mainline_strength_score) AS mainline_strength_score,
            SUM(main_net_inflow) AS main_net_inflow_sum,
            AVG(main_net_inflow) AS main_net_inflow_avg,
            SUM(CASE WHEN main_net_inflow > 0 THEN 1 ELSE 0 END) AS positive_inflow_stock_count,
            SUM(CASE WHEN main_net_inflow < 0 THEN 1 ELSE 0 END) AS negative_inflow_stock_count,
            COALESCE(MAX(CASE WHEN is_leader THEN main_net_inflow END), 0) AS leader_main_net_inflow,
            SUM(CASE WHEN rank_order <= 3 THEN main_net_inflow ELSE 0 END) AS top3_main_net_inflow_sum,
            COUNT(*) AS member_count
        FROM base
        GROUP BY subject_key, theme_name, final_cycle_state
        HAVING SUM(main_net_inflow) > 0
        ORDER BY
            AVG(mainline_strength_score) DESC,
            SUM(main_net_inflow) DESC,
            theme_name ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        return [dict(r) for r in rows]

    async def fetch_stock_main_net_inflow_top(self, trade_date: str, limit: int = 20):
        sql = """
        WITH mainline AS MATERIALIZED (
            SELECT
                v2.trade_date,
                v2.subject_key,
                COALESCE(NULLIF(BTRIM(v2.theme_name), ''), v2.subject_key) AS theme_name,
                COALESCE(msd.state, v2.final_cycle_state) AS final_cycle_state,
                COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score
            FROM theme_cycle_judgement_v2 v2
            JOIN mainline_state_daily msd
              ON msd.trade_date = v2.trade_date
             AND msd.subject_key = v2.subject_key
            WHERE v2.trade_date = $1::date
              AND COALESCE(msd.is_mainline, FALSE) = TRUE
              AND COALESCE(msd.state, '') <> 'fade_confirmed'
        ),
        snapshot AS MATERIALIZED (
            SELECT
                split_part(stock_id, '.', 1) AS stock_code,
                stock_id,
                stock_name,
                subject_key,
                rank_order,
                pct_chg,
                is_leader,
                COALESCE(NULLIF(raw_json->>20, ''), '0')::integer AS current_flag,
                COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric AS main_net_inflow
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
        ),
        base AS (
            SELECT
                s.stock_code,
                s.stock_id,
                s.stock_name,
                s.subject_key,
                COALESCE(NULLIF(BTRIM(m.theme_name), ''), s.subject_key) AS theme_name,
                m.final_cycle_state,
                m.mainline_strength_score,
                s.rank_order,
                s.pct_chg,
                s.is_leader,
                s.current_flag,
                s.main_net_inflow
            FROM mainline m
            JOIN snapshot s
              ON m.subject_key = s.subject_key
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY stock_code
                    ORDER BY
                        CASE WHEN is_leader THEN 0 ELSE 1 END,
                        rank_order ASC,
                        main_net_inflow DESC,
                        theme_name ASC
                ) AS rn
            FROM base
            WHERE main_net_inflow > 0
        )
        SELECT
            stock_id,
            stock_name,
            subject_key,
            theme_name,
            final_cycle_state,
            mainline_strength_score,
            rank_order,
            pct_chg,
            is_leader,
            current_flag,
            main_net_inflow
        FROM ranked
        WHERE rn = 1
        ORDER BY main_net_inflow DESC, stock_id ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        return [dict(r) for r in rows]

    async def fetch_hot_money_activities(self, trade_date: str, limit: int = 200):
        sql = """
        SELECT
            trade_date,
            hot_money_name,
            seat_name,
            stock_id,
            stock_name,
            subject_key,
            theme_name,
            side,
            buy_amount,
            sell_amount,
            net_amount,
            reason,
            rank_order,
            is_theme_leader,
            style_tags
        FROM hot_money_trading_activity
        WHERE trade_date = $1::date
        ORDER BY ABS(net_amount) DESC, hot_money_name ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, trade_date_value, limit)
        except asyncpg.UndefinedTableError:
            return []
        results = []
        for row in rows:
            item = dict(row)
            item["style_tags"] = _coerce_json_list(item.get("style_tags"))
            results.append(item)
        return results

    async def fetch_recent_auction_signal_validations(self, trade_date: str, limit: int = 20):
        sql = """
        WITH latest_day AS (
            SELECT MAX(trade_date) AS latest_trade_date
            FROM pre_market_auction_signal_validation
            WHERE trade_date < $1::date
              AND validation_result <> 'pending_daily_result'
        )
        SELECT
            trade_date,
            stock_id,
            stock_name,
            subject_key,
            theme_name,
            role_label,
            auction_signal_level,
            auction_signal_score,
            signal_type,
            action_today,
            close_pct,
            close_price,
            hit_limit_up,
            close_rank_order,
            close_is_leader,
            validation_result,
            signal_validated,
            validation_note
        FROM pre_market_auction_signal_validation
        WHERE trade_date = (SELECT latest_trade_date FROM latest_day)
        ORDER BY
            CASE auction_signal_level
                WHEN 'strong' THEN 0
                WHEN 'watch' THEN 1
                WHEN 'weak' THEN 2
                ELSE 3
            END,
            auction_signal_score DESC,
            stock_id ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        return [dict(r) for r in rows]
