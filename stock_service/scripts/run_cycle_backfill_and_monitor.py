#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
import sys
from typing import List

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig
from stock_service.services.theme_cycle_judgement_service import ThemeCycleJudgementService
from stock_service.scripts.check_cycle_state_distribution import CycleStateDistributionChecker


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填 theme_cycle_judgement_v2 并执行分布告警检查")
    parser.add_argument("--trade-date", help="单日模式：回填并监控此交易日")
    parser.add_argument("--start-date", help="区间模式：起始交易日")
    parser.add_argument("--end-date", help="区间模式：结束交易日")
    parser.add_argument("--skip-backfill", action="store_true", help="仅执行分布监控，不做回填")
    parser.add_argument("--quiet-backfill", action="store_true", default=True, help="隐藏回填明细输出（默认开启）")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--min-total", type=int, default=80)
    parser.add_argument("--dominance-threshold", type=float, default=0.78)
    parser.add_argument("--fade-confirmed-jump-threshold", type=float, default=0.08)
    parser.add_argument("--mainline-alive-drop-threshold", type=float, default=0.15)
    parser.add_argument("--fail-on-alert", action="store_true", help="兼容参数，等价于 --fail-on-distribution-alert")
    parser.add_argument("--fail-on-distribution-alert", action="store_true", help="分布告警存在时返回失败")
    parser.add_argument("--fail-on-mainline-conflict", action="store_true", help="若主线口径分裂(冲突>0)则返回失败")
    parser.add_argument(
        "--enforce-identity-prior",
        action="store_true",
        help="在回填后对 v2.final_mainline_alive 应用身份先验门禁（identity confirmed 优先）",
    )
    parser.add_argument(
        "--identity-prior-dry-run-only",
        action="store_true",
        help="仅预览身份先验门禁影响，不执行写入",
    )
    parser.add_argument(
        "--promote-confirmed-nonfade",
        action="store_true",
        help="配合 --enforce-identity-prior：将 confirmed 且非 fade_confirmed 的 v2_alive=false 回补为 true",
    )
    parser.add_argument(
        "--identity-prior-auto-manage",
        action="store_true",
        help="日终自动治理：先 dry-run，再按阈值决定是否 apply identity-prior",
    )
    parser.add_argument(
        "--identity-prior-hidden-threshold",
        type=int,
        default=0,
        help="auto-manage 下 hidden 冲突触发 apply 的阈值（>阈值触发）",
    )
    parser.add_argument(
        "--identity-prior-dropped-threshold",
        type=int,
        default=0,
        help="auto-manage 下 dropped 冲突触发 promote apply 的阈值（>阈值触发）",
    )
    parser.add_argument(
        "--allow-legacy-cycle-backfill",
        action="store_true",
        help="显式允许旧 ThemeCycleJudgementService 回填入口（默认禁用，避免口径回退）",
    )
    return parser.parse_args()


async def _list_trade_dates(config: StockServiceConfig, start_date: date, end_date: date) -> List[date]:
    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
    )
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT trade_date
            FROM theme_cycle_judgement_v2
            WHERE trade_date BETWEEN $1::date AND $2::date
            ORDER BY trade_date
            """,
            start_date,
            end_date,
        )
        return [row["trade_date"] for row in rows]
    finally:
        await conn.close()


async def _run_backfill(dates: List[date], quiet: bool) -> int:
    if not dates:
        print("[BACKFILL] no_trade_dates")
        return 0
    service = ThemeCycleJudgementService()
    failures = 0
    try:
        for d in dates:
            print(f"[BACKFILL] run {d.isoformat()}")
            try:
                if quiet:
                    with open("/dev/null", "w", encoding="utf-8") as sink, redirect_stdout(sink):
                        out = await service.judge_all_themes_for_date(d)
                else:
                    out = await service.judge_all_themes_for_date(d)
                print(f"[BACKFILL] ok {d.isoformat()} count={len(out)}")
            except Exception as e:
                failures += 1
                print(f"[BACKFILL] fail {d.isoformat()} err={e}")
    finally:
        await service.close()
    return failures


async def _sync_mainline_with_v2(config: StockServiceConfig, dates: List[date]) -> int:
    """仅做兼容占位：禁止再把 v2 周期存活回写到主线身份字段。

    说明：
    - `theme_mainline_identity_registry.is_main_theme` 表示“主线身份”；
    - `theme_cycle_judgement_v2.final_mainline_alive` 表示“主线周期是否存活”。
    二者语义不同，不允许互相覆盖。
    """
    if not dates:
        return 0
    for d in dates:
        print(
            f"[SYNC] mainline_with_v2 {d.isoformat()} skipped=1 "
            f"reason=identity_cycle_semantics_separated"
        )
    return 0


async def _run_monitor(args: argparse.Namespace, trade_date: date) -> tuple[int, bool]:
    checker = CycleStateDistributionChecker()
    await checker.connect()
    try:
        result = await checker.run(
            trade_date=trade_date,
            lookback_days=args.lookback_days,
            min_total=args.min_total,
            dominance_threshold=args.dominance_threshold,
            fade_confirmed_jump_threshold=args.fade_confirmed_jump_threshold,
            mainline_alive_drop_threshold=args.mainline_alive_drop_threshold,
        )
    finally:
        await checker.close()

    current = result.get("current")
    print(f"[MONITOR] date={trade_date.isoformat()}")
    if current:
        print(
            f"[MONITOR] source={current.source_table} total={current.total} "
            f"mainline_alive_ratio={current.mainline_alive_ratio:.3f} "
            f"fade_confirmed_ratio={current.fade_confirmed_ratio:.3f}"
        )
    print(f"[MONITOR] history_days={result.get('history_days', 0)}")
    alerts = result.get("alerts") or []
    if alerts:
        print("[MONITOR] alerts:")
        for item in alerts:
            print(f"  - {item}")
    else:
        print("[MONITOR] alerts: none")
    fail_on_distribution = bool(args.fail_on_alert or args.fail_on_distribution_alert)
    if fail_on_distribution and alerts:
        return 3, True
    return 0, bool(alerts)


async def _check_mainline_conflicts(config: StockServiceConfig, dates: List[date]) -> int:
    if not dates:
        print("[CONSISTENCY] no_dates")
        return 0
    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
    )
    total_conflicts = 0
    try:
        sql = """
        WITH j AS (
            SELECT
                v2.trade_date AS trade_date,
                v2.subject_key AS subject_key,
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
        for d in dates:
            row = await conn.fetchrow(sql, d)
            hidden = int(row["hidden_conflicts"] or 0)
            dropped = int(row["dropped_conflicts"] or 0)
            conflicts = hidden + dropped
            total_conflicts += conflicts
            print(
                f"[CONSISTENCY] date={d.isoformat()} hidden={hidden} dropped={dropped} total={conflicts}"
            )
    finally:
        await conn.close()
    print(f"[CONSISTENCY] total_conflicts={total_conflicts}")
    return total_conflicts


async def _fetch_conflict_counts_for_date(config: StockServiceConfig, d: date) -> tuple[int, int]:
    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
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
        row = await conn.fetchrow(sql, d)
        return int(row["hidden_conflicts"] or 0), int(row["dropped_conflicts"] or 0)
    finally:
        await conn.close()


async def _enforce_identity_prior_gate(
    config: StockServiceConfig,
    dates: List[date],
    *,
    dry_run_only: bool,
    promote_confirmed_nonfade: bool,
) -> int:
    if not dates:
        print("[IDENTITY_PRIOR] no_dates")
        return 0
    conn = await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
    )
    total_updated = 0
    try:
        preview_sql = """
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
          COUNT(*) FILTER (WHERE final_mainline_alive = TRUE) AS alive_rows_before
        FROM j
        """
        update_sql = """
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
        promote_sql = """
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
        for d in dates:
            preview = await conn.fetchrow(preview_sql, d)
            target_rows = int(preview["target_rows"] or 0)
            promote_rows = int(preview["promote_rows"] or 0)
            alive_rows_before = int(preview["alive_rows_before"] or 0)
            print(
                f"[IDENTITY_PRIOR] date={d.isoformat()} target_rows={target_rows} "
                f"promote_rows={promote_rows} "
                f"alive_rows_before={alive_rows_before} dry_run={dry_run_only}"
            )
            if dry_run_only:
                continue
            result = await conn.execute(update_sql, d)
            promote_result = "UPDATE 0"
            if promote_confirmed_nonfade:
                promote_result = await conn.execute(promote_sql, d)
            try:
                updated = int(str(result).split()[-1])
            except Exception:
                updated = 0
            try:
                promoted = int(str(promote_result).split()[-1])
            except Exception:
                promoted = 0
            total_updated += updated
            total_updated += promoted
            print(
                f"[IDENTITY_PRIOR] date={d.isoformat()} apply_result={result} "
                f"promote_result={promote_result}"
            )
    finally:
        await conn.close()
    print(f"[IDENTITY_PRIOR] total_updated={total_updated}")
    return total_updated


async def _auto_manage_identity_prior(args: argparse.Namespace, config: StockServiceConfig, dates: List[date]) -> int:
    if not dates:
        print("[AUTO_GATE] no_dates")
        return 0
    total_updated = 0
    for d in dates:
        hidden, dropped = await _fetch_conflict_counts_for_date(config, d)
        print(
            f"[AUTO_GATE] date={d.isoformat()} pre_hidden={hidden} pre_dropped={dropped} "
            f"hidden_threshold={int(args.identity_prior_hidden_threshold)} "
            f"dropped_threshold={int(args.identity_prior_dropped_threshold)}"
        )
        # 默认先 dry-run，超过阈值再 apply。
        await _enforce_identity_prior_gate(
            config,
            [d],
            dry_run_only=True,
            promote_confirmed_nonfade=bool(args.promote_confirmed_nonfade),
        )
        need_hidden_apply = hidden > int(args.identity_prior_hidden_threshold)
        need_dropped_apply = bool(args.promote_confirmed_nonfade) and dropped > int(args.identity_prior_dropped_threshold)
        if not (need_hidden_apply or need_dropped_apply):
            print(f"[AUTO_GATE] date={d.isoformat()} action=dry_run_only")
            continue
        updated = await _enforce_identity_prior_gate(
            config,
            [d],
            dry_run_only=False,
            promote_confirmed_nonfade=need_dropped_apply,
        )
        total_updated += int(updated or 0)
        print(
            f"[AUTO_GATE] date={d.isoformat()} action=apply "
            f"apply_hidden={need_hidden_apply} apply_promote={need_dropped_apply}"
        )
    print(f"[AUTO_GATE] total_updated={total_updated}")
    return total_updated


async def main_async() -> int:
    args = parse_args()
    if not args.allow_legacy_cycle_backfill and not args.skip_backfill:
        print(
            "[BLOCK] legacy_cycle_backfill_disabled: "
            "旧 ThemeCycleJudgementService 回填入口已默认禁用，"
            "请改用盘后主流程(build_post_market_recap.py) + mainline_state_tracking。"
        )
        print(
            "[HINT] 若仅为历史排障临时使用旧入口，可显式追加 "
            "--allow-legacy-cycle-backfill"
        )
        return 4
    if args.trade_date:
        start_date = _parse_date(args.trade_date)
        end_date = start_date
        monitor_date = start_date
    else:
        if not args.start_date or not args.end_date:
            raise ValueError("必须传 --trade-date，或同时传 --start-date/--end-date")
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date)
        if end_date < start_date:
            raise ValueError("--end-date 不能早于 --start-date")
        monitor_date = end_date

    config = StockServiceConfig()
    dates = await _list_trade_dates(config, start_date, end_date)
    print(f"[PLAN] backfill_dates={[d.isoformat() for d in dates]}")

    backfill_failures = 0
    sync_updates = 0
    if not args.skip_backfill:
        backfill_failures = await _run_backfill(dates, quiet=args.quiet_backfill)
        sync_updates = await _sync_mainline_with_v2(config, dates)
    else:
        print("[BACKFILL] skipped")
    if args.identity_prior_auto_manage:
        await _auto_manage_identity_prior(args, config, dates)
    elif args.enforce_identity_prior:
        await _enforce_identity_prior_gate(
            config,
            dates,
            dry_run_only=bool(args.identity_prior_dry_run_only),
            promote_confirmed_nonfade=bool(args.promote_confirmed_nonfade),
        )
    print(f"[SYNC] total_updated={sync_updates}")
    total_conflicts = await _check_mainline_conflicts(config, dates)

    monitor_code, monitor_has_alerts = await _run_monitor(args, monitor_date)
    if backfill_failures > 0:
        return 1
    if args.fail_on_mainline_conflict and total_conflicts > 0:
        return 2
    if monitor_has_alerts and not (args.fail_on_alert or args.fail_on_distribution_alert):
        print("[GATE] distribution_alerts_detected_but_not_failing (set --fail-on-distribution-alert to fail)")
    return monitor_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
