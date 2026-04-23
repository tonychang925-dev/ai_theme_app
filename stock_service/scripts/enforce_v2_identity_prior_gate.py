#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path
import sys

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对 theme_cycle_judgement_v2 应用身份先验门禁（可 dry-run）")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument(
        "--promote-confirmed-nonfade",
        action="store_true",
        help="对 identity confirmed 且非 fade_confirmed 的题材，将 final_mainline_alive 回补为 TRUE（可与 identity-prior 一起用）",
    )
    parser.add_argument("--apply", action="store_true", help="执行写入；默认仅 dry-run")
    return parser.parse_args()


async def _connect() -> asyncpg.Connection:
    c = StockServiceConfig()
    return await asyncpg.connect(
        host=c.postgres_host,
        port=c.postgres_port,
        database=c.postgres_database,
        user=c.postgres_user,
        password=c.postgres_password,
    )


async def _count_targets(conn: asyncpg.Connection, trade_date: date) -> asyncpg.Record:
    sql = """
    WITH j AS (
      SELECT
        v2.subject_key,
        COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
        COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed,
        COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
        COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
        COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') AS identity_status
      FROM theme_cycle_judgement_v2 v2
      LEFT JOIN theme_mainline_identity_registry mr
        ON mr.subject_key = v2.subject_key
      WHERE v2.trade_date = $1::date
    )
    SELECT
      COUNT(*) FILTER (
        WHERE final_mainline_alive = TRUE
          AND (is_main_theme = FALSE OR identity_status <> 'confirmed')
      ) AS target_rows,
      COUNT(*) FILTER (
        WHERE final_mainline_alive = FALSE
          AND is_main_theme = TRUE
          AND identity_status = 'confirmed'
          AND fade_confirmed = FALSE
          AND final_cycle_state IN ('start', 'fermentation', 'acceleration', 'divergence', 'repair', '启动', '发酵', '分歧', '修复')
      ) AS promote_rows,
      COUNT(*) FILTER (
        WHERE final_mainline_alive = TRUE
      ) AS alive_rows_before
    FROM j
    """
    return await conn.fetchrow(sql, trade_date)


async def _apply_gate(conn: asyncpg.Connection, trade_date: date) -> str:
    sql = """
    UPDATE theme_cycle_judgement_v2 v2
    SET
      final_mainline_alive = FALSE,
      state_transition_reason = CASE
        WHEN COALESCE(NULLIF(BTRIM(v2.state_transition_reason), ''), '') = '' THEN 'identity_prior_gate'
        WHEN POSITION('identity_prior_gate' IN v2.state_transition_reason) > 0 THEN v2.state_transition_reason
        ELSE v2.state_transition_reason || ';identity_prior_gate'
      END
    FROM theme_mainline_identity_registry mr
    WHERE v2.trade_date = $1::date
      AND mr.subject_key = v2.subject_key
      AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
      AND (
        COALESCE(mr.is_main_theme, FALSE) = FALSE
        OR COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') <> 'confirmed'
      )
    """
    return await conn.execute(sql, trade_date)


async def _apply_promote_confirmed_nonfade(conn: asyncpg.Connection, trade_date: date) -> str:
    sql = """
    UPDATE theme_cycle_judgement_v2 v2
    SET
      final_mainline_alive = TRUE,
      state_transition_reason = CASE
        WHEN COALESCE(NULLIF(BTRIM(v2.state_transition_reason), ''), '') = '' THEN 'identity_confirmed_nonfade_bridge'
        WHEN POSITION('identity_confirmed_nonfade_bridge' IN v2.state_transition_reason) > 0 THEN v2.state_transition_reason
        ELSE v2.state_transition_reason || ';identity_confirmed_nonfade_bridge'
      END
    FROM theme_mainline_identity_registry mr
    WHERE v2.trade_date = $1::date
      AND mr.subject_key = v2.subject_key
      AND COALESCE(v2.final_mainline_alive, FALSE) = FALSE
      AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
      AND COALESCE(mr.is_main_theme, FALSE) = TRUE
      AND COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') = 'confirmed'
      AND COALESCE(v2.final_cycle_state, '') IN ('start', 'fermentation', 'acceleration', 'divergence', 'repair', '启动', '发酵', '分歧', '修复')
    """
    return await conn.execute(sql, trade_date)


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    conn = await _connect()
    try:
        before = await _count_targets(conn, trade_date)
        target_rows = int(before["target_rows"] or 0)
        promote_rows = int(before["promote_rows"] or 0)
        alive_rows_before = int(before["alive_rows_before"] or 0)
        print(
            f"[PREVIEW] trade_date={trade_date.isoformat()} "
            f"target_rows={target_rows} promote_rows={promote_rows} alive_rows_before={alive_rows_before}"
        )
        if not args.apply:
            print("[DRY_RUN] set --apply to execute update")
            return 0

        update_result = await _apply_gate(conn, trade_date)
        promote_result = "UPDATE 0"
        if args.promote_confirmed_nonfade:
            promote_result = await _apply_promote_confirmed_nonfade(conn, trade_date)
        after = await _count_targets(conn, trade_date)
        target_rows_after = int(after["target_rows"] or 0)
        promote_rows_after = int(after["promote_rows"] or 0)
        alive_rows_after = int(after["alive_rows_before"] or 0)
        print(
            f"[APPLY] result={update_result} promote_result={promote_result} "
            f"target_rows_after={target_rows_after} promote_rows_after={promote_rows_after} "
            f"alive_rows_after={alive_rows_after}"
        )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
