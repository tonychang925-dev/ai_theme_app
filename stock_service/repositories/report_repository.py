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
            subject_key,
            theme_name,
            event_chain_score,
            event_chain_continuity_score,
            market_recognition_score,
            mainline_stability_score,
            is_main_theme,
            theme_tier,
            limit_up_count,
            conclusion,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM theme_mainline_judgement
        WHERE trade_date = $1::date
        ORDER BY
            CASE theme_tier
                WHEN 'main' THEN 0
                WHEN 'strong_branch' THEN 1
                ELSE 2
            END,
            (event_chain_score + market_recognition_score + mainline_stability_score) DESC,
            subject_key
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
            subject_key,
            theme_name,
            is_main_theme,
            primary_cycle_stage,
            limit_up_count,
            leader_status,
            board_effect_status,
            action_bias,
            confidence,
            conclusion,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM theme_cycle_judgement
        WHERE trade_date = $1::date
        ORDER BY
            CASE
                WHEN is_main_theme THEN 0
                ELSE 1
            END,
            confidence DESC,
            subject_key
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
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
            s.amount AS day_amount
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

    async def fetch_stock_abnormal_signals(self, trade_date: str, limit: int = 120):
        sql = """
        SELECT
            trade_date,
            subject_key,
            theme_name,
            stock_id,
            stock_name,
            turnover_rate,
            turnover_rank_in_theme,
            main_net_inflow,
            main_net_inflow_rank_in_theme,
            turnover_abnormal_score,
            capital_focus_score,
            is_high_turnover,
            is_extreme_turnover,
            volume_ratio_to_ma50,
            volume_abnormal_score,
            is_volume_breakout,
            is_double_volume,
            is_high_volume_bar,
            tail_amount,
            tail_amount_ratio,
            tail_unmatched_buy_order,
            tail_abnormal_score,
            has_tail_rush_buy,
            has_tail_large_unmatched_bid,
            hot_money_buy_names,
            institution_net_buy,
            institution_seat_count,
            has_hot_money_buy,
            has_institution_buy,
            abnormal_labels,
            abnormal_composite_score,
            conclusion,
            evidence,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM stock_abnormal_signal
        WHERE trade_date = $1::date
        ORDER BY abnormal_composite_score DESC, theme_name ASC, stock_id ASC
        LIMIT $2
        """
        assert self.pool is not None
        trade_date_value = _coerce_trade_date(trade_date)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date_value, limit)
        results = []
        for row in rows:
            item = dict(row)
            item["hot_money_buy_names"] = _coerce_json_list(item.get("hot_money_buy_names"))
            item["abnormal_labels"] = _coerce_json_list(item.get("abnormal_labels"))
            item["evidence"] = _coerce_json_list(item.get("evidence"))
            results.append(item)
        return results

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
