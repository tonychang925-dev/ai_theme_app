"""
Apply W2S backtest DDL migration.
Usage: python database_service/scripts/apply_w2s_backtest_tables.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [

    # ── w2s_backtest_run ──
    """
    CREATE TABLE IF NOT EXISTS w2s_backtest_run (
        run_id TEXT PRIMARY KEY,
        strategy_id TEXT NOT NULL DEFAULT 'weak_to_strong',
        strategy_version TEXT NOT NULL,
        run_type VARCHAR(32) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,

        config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        data_quality_json JSONB NOT NULL DEFAULT '{}'::jsonb,

        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        error_message TEXT,

        signal_count INTEGER DEFAULT 0,
        validated_count INTEGER DEFAULT 0,

        created_at TIMESTAMP DEFAULT now(),
        started_at TIMESTAMP,
        completed_at TIMESTAMP
    );
    """,

    # ── w2s_backtest_feature_snapshot ──
    """
    CREATE TABLE IF NOT EXISTS w2s_backtest_feature_snapshot (
        snapshot_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES w2s_backtest_run(run_id),
        strategy_id TEXT NOT NULL DEFAULT 'weak_to_strong',
        strategy_version TEXT NOT NULL,

        candidate_trade_date DATE NOT NULL,
        confirm_trade_date DATE,

        stock_id VARCHAR(32) NOT NULL,
        stock_name VARCHAR(64),

        subject_key VARCHAR(64),
        theme_name VARCHAR(128),

        candidate_id BIGINT,
        pool_entry_type VARCHAR(32),
        candidate_score NUMERIC(8,2),
        candidate_type VARCHAR(64),
        weak_type VARCHAR(64),

        support_type VARCHAR(64),
        support_strength NUMERIC(8,2),

        is_leader BOOLEAN,
        rank_order INTEGER,
        recent_limit_up_count INTEGER,
        prior7_limitup_days INTEGER,
        prior7_strong_days INTEGER,

        leader_role_proxy VARCHAR(32),
        leader_score_proxy NUMERIC(8,2),
        two_board_quality_score NUMERIC(8,2),
        board_type VARCHAR(32),
        is_20cm BOOLEAN DEFAULT false,

        mainline_strength_score NUMERIC(8,2),
        fade_watch BOOLEAN,
        fade_confirmed BOOLEAN,
        cycle_state VARCHAR(64),

        auction_feature_mode VARCHAR(32),
        auction_open_pct NUMERIC(8,4),
        auction_amount NUMERIC(18,2),
        auction_score NUMERIC(8,2),
        confirm_level VARCHAR(16),
        confirmation_score NUMERIC(8,2),
        auction_feature_quality VARCHAR(32),
        missing_features JSONB NOT NULL DEFAULT '[]'::jsonb,

        bull_stock_score NUMERIC(8,2),

        raw_feature_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        derived_feature_json JSONB NOT NULL DEFAULT '{}'::jsonb,

        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT now(),

        UNIQUE(run_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id)
    );
    """,

    # ── strategy_signal_daily (update: add run_id, confirm_source etc.) ──
    """
    CREATE TABLE IF NOT EXISTS strategy_signal_daily (
        signal_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        strategy_id TEXT NOT NULL DEFAULT 'weak_to_strong',
        strategy_version TEXT NOT NULL,
        trade_date DATE NOT NULL,
        signal_session TEXT NOT NULL,
        available_at TIMESTAMP NOT NULL,
        tradable_at TIMESTAMP NOT NULL,

        stock_id TEXT NOT NULL,
        stock_name TEXT,
        subject_key TEXT,
        theme_name TEXT,

        direction TEXT NOT NULL DEFAULT 'watch',
        tradable BOOLEAN DEFAULT false,
        signal_level TEXT,
        score NUMERIC(8,2),
        confidence NUMERIC(8,4),

        confirm_level VARCHAR(16),
        confirm_source VARCHAR(32),
        reject_reason_code VARCHAR(64),

        entry_plan JSONB DEFAULT '{}'::jsonb,
        exit_plan JSONB DEFAULT '{}'::jsonb,
        risk_plan JSONB DEFAULT '{}'::jsonb,
        evidence_json JSONB DEFAULT '{}'::jsonb,

        source_chain TEXT NOT NULL DEFAULT 'stock_processing_service',
        source_table TEXT,
        source_id TEXT,
        source_snapshot_version TEXT,
        rule_version TEXT,

        created_at TIMESTAMP DEFAULT now(),

        UNIQUE(run_id, strategy_id, strategy_version, trade_date, signal_session, stock_id, source_id)
    );
    """,

    # ── strategy_signal_validation ──
    """
    CREATE TABLE IF NOT EXISTS strategy_signal_validation (
        signal_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        strategy_id TEXT NOT NULL DEFAULT 'weak_to_strong',
        strategy_version TEXT NOT NULL,
        trade_date DATE NOT NULL,
        stock_id TEXT NOT NULL,
        signal_level TEXT,
        score NUMERIC(8,2),

        buy_ref_date DATE,
        buy_ref_price NUMERIC(18,4),

        next_day_touch_limit_up BOOLEAN,
        next_day_sealed_limit_up BOOLEAN,
        next_day_open_pct NUMERIC(12,6),
        next_day_high_pct NUMERIC(12,6),
        next_day_close_pct NUMERIC(12,6),
        next_day_open_board_count INTEGER,
        next_day_max_drawdown NUMERIC(12,6),
        outcome_label TEXT,

        next_1d_return NUMERIC(12,6),
        next_2d_return NUMERIC(12,6),
        next_3d_return NUMERIC(12,6),
        next_5d_return NUMERIC(12,6),

        max_return_3d NUMERIC(12,6),
        max_return_5d NUMERIC(12,6),
        max_drawdown_3d NUMERIC(12,6),
        max_drawdown_5d NUMERIC(12,6),

        hit_limit_up_3d BOOLEAN,
        hit_limit_up_5d BOOLEAN,

        is_win_1d BOOLEAN,
        is_win_3d BOOLEAN,
        is_win_5d BOOLEAN,

        loss_over_5pct BOOLEAN,

        validation_status TEXT DEFAULT 'ok',
        validation_error TEXT,

        validated_at TIMESTAMP DEFAULT now()
    );
    """,

    # ── w2s_validation_summary ──
    """
    CREATE TABLE IF NOT EXISTS w2s_validation_summary (
        run_id TEXT NOT NULL,
        experiment_id VARCHAR(32) NOT NULL,
        confirm_source_group VARCHAR(32),
        confirm_level VARCHAR(16),

        sample_count INTEGER,
        win_rate_1d NUMERIC(8,4),
        win_rate_3d NUMERIC(8,4),
        win_rate_5d NUMERIC(8,4),
        avg_return_3d NUMERIC(12,6),
        avg_return_5d NUMERIC(12,6),
        max_drawdown_5d NUMERIC(12,6),
        hit_limit_up_pct NUMERIC(8,4),
        loss_over_5pct_pct NUMERIC(8,4),

        PRIMARY KEY(run_id, experiment_id, confirm_source_group, confirm_level)
    );
    """,

    # ── Indexes ──
    """
    CREATE INDEX IF NOT EXISTS idx_w2s_br_status ON w2s_backtest_run(status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_w2s_br_strategy ON w2s_backtest_run(strategy_id, strategy_version);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_w2s_bfs_run ON w2s_backtest_feature_snapshot(run_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_w2s_bfs_stock ON w2s_backtest_feature_snapshot(stock_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_w2s_bfs_date ON w2s_backtest_feature_snapshot(candidate_trade_date);
    """,
    """
    ALTER TABLE w2s_backtest_feature_snapshot
    ADD COLUMN IF NOT EXISTS strategy_id TEXT NOT NULL DEFAULT 'weak_to_strong';
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ssd_run ON strategy_signal_daily(run_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ssd_date ON strategy_signal_daily(trade_date);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ssv_run ON strategy_signal_validation(run_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_w2s_vs_run ON w2s_validation_summary(run_id);
    """,
]


async def _apply_ddl(gateway: DatabaseGateway) -> list[str]:
    applied: list[str] = []
    client = gateway._client
    for idx, sql in enumerate(DDL_STATEMENTS):
        try:
            await client.execute_query(sql)
            applied.append(f"DDL #{idx+1} OK")
            logger.info("DDL #%d applied successfully", idx + 1)
        except Exception as exc:
            logger.error("DDL #%d failed: %s", idx + 1, exc)
            applied.append(f"DDL #{idx+1} FAILED: {exc}")
    return applied


async def main() -> None:
    db_name = str(os.getenv("DB_NAME") or "stock_data_test")
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=db_name)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    try:
        results = await _apply_ddl(gw)
        for r in results:
            print(r)
    finally:
        close_fn = getattr(gw, "close", None)
        if callable(close_fn):
            await close_fn()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
