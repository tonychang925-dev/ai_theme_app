#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mainline hard gate: legacy入口 + 身份/周期冲突 + 迁移分布")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--skip-legacy-entrypoint-gate", action="store_true")
    parser.add_argument("--skip-consistency-gate", action="store_true")
    parser.add_argument("--skip-transition-gate", action="store_true")
    parser.add_argument("--max-hidden-conflicts", type=int, default=0, help="hidden_conflicts 允许上限")
    parser.add_argument("--max-dropped-conflicts", type=int, default=0, help="dropped_conflicts 允许上限")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--min-total", type=int, default=8)
    parser.add_argument("--single-type-dominance-threshold", type=float, default=0.95)
    parser.add_argument("--downgrade-jump-threshold", type=float, default=0.35)
    parser.add_argument("--fade-jump-threshold", type=float, default=0.15)
    parser.add_argument("--min-history-days", type=int, default=3)
    parser.add_argument("--disable-transition-auto-tune", action="store_true")
    parser.add_argument(
        "--fail-on-transition-alert",
        action="store_true",
        help="When set, transition distribution alert will fail the hard gate (strict mode).",
    )
    return parser.parse_args()


async def _fetch_conflicts(trade_date: date) -> tuple[int, int]:
    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        sql = """
        WITH j AS (
            SELECT
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') AS identity_status,
                COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive
            FROM theme_cycle_judgement_v2 v2
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = v2.subject_key
            WHERE v2.trade_date = $1::date
        )
        SELECT
            COUNT(*) FILTER (
                WHERE (is_main_theme = FALSE OR identity_status <> 'confirmed')
                  AND final_mainline_alive = TRUE
            ) AS hidden_conflicts,
            COUNT(*) FILTER (
                WHERE is_main_theme = TRUE
                  AND identity_status = 'confirmed'
                  AND final_mainline_alive = FALSE
            ) AS dropped_conflicts
        FROM j
        """
        row = await conn.fetchrow(sql, trade_date)
        return int(row["hidden_conflicts"] or 0), int(row["dropped_conflicts"] or 0)
    finally:
        await conn.close()


def _run_step(name: str, cmd: list[str]) -> None:
    print(f"[STEP] {name}")
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    python = sys.executable

    if not args.skip_legacy_entrypoint_gate:
        _run_step(
            "legacy_cycle_entrypoint_gate",
            [python, str(PROJECT_ROOT / "stock_service" / "scripts" / "check_legacy_cycle_entrypoints.py")],
        )
    else:
        print("[SKIP] legacy_cycle_entrypoint_gate")

    if not args.skip_consistency_gate:
        hidden, dropped = await _fetch_conflicts(trade_date)
        print(
            f"[CHECK] consistency trade_date={trade_date.isoformat()} "
            f"hidden={hidden} dropped={dropped} "
            f"max_hidden={int(args.max_hidden_conflicts)} max_dropped={int(args.max_dropped_conflicts)}"
        )
        if hidden > int(args.max_hidden_conflicts) or dropped > int(args.max_dropped_conflicts):
            print("[FAIL] consistency_gate_exceeded_threshold")
            return 2
        print("[OK] consistency_gate_passed")
    else:
        print("[SKIP] consistency_gate")

    if not args.skip_transition_gate:
        transition_cmd = [
            python,
            str(PROJECT_ROOT / "stock_service" / "scripts" / "check_mainline_transition_distribution.py"),
            "--trade-date",
            trade_date.isoformat(),
            "--lookback-days",
            str(max(1, int(args.lookback_days))),
            "--min-total",
            str(max(1, int(args.min_total))),
            "--single-type-dominance-threshold",
            str(args.single_type_dominance_threshold),
            "--downgrade-jump-threshold",
            str(args.downgrade_jump_threshold),
            "--fade-jump-threshold",
            str(args.fade_jump_threshold),
            "--min-history-days",
            str(max(1, int(args.min_history_days))),
        ]
        if args.fail_on_transition_alert:
            transition_cmd.append("--fail-on-alert")
        if args.disable_transition_auto_tune:
            transition_cmd.append("--disable-auto-tune")
        _run_step("transition_distribution_gate", transition_cmd)
    else:
        print("[SKIP] transition_distribution_gate")

    print("[OK] mainline_hard_gate_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
