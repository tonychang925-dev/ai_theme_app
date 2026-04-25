#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from typing import Any

import asyncpg


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


async def _fetch_diff_rows(conn: asyncpg.Connection, trade_date: date) -> list[dict[str, Any]]:
    sql = """
    WITH old_identity AS (
      SELECT
        subject_key,
        COALESCE(LOWER(identity_status), '') AS old_identity_status,
        COALESCE(is_main_theme, FALSE) AS old_is_main_theme,
        COALESCE(rule_version, '') AS old_rule_version
      FROM theme_mainline_identity_registry
    ),
    old_cycle AS (
      SELECT
        subject_key,
        COALESCE(final_cycle_state, '') AS old_final_cycle_state,
        COALESCE(final_mainline_alive, FALSE) AS old_final_mainline_alive,
        COALESCE(previous_cycle_state, '') AS old_previous_cycle_state,
        COALESCE(confidence_score, 0)::numeric AS old_confidence_score,
        COALESCE(risk_flags, '[]'::jsonb) AS old_risk_flags
      FROM theme_cycle_judgement_v2
      WHERE trade_date = $1::date
    ),
    new_view AS (
      SELECT
        c.subject_key,
        COALESCE(i.old_identity_status, '') AS new_identity_status,
        COALESCE(i.old_is_main_theme, FALSE) AS new_is_main_theme,
        COALESCE(c.old_final_cycle_state, '') AS new_final_cycle_state,
        COALESCE(c.old_final_mainline_alive, FALSE) AS new_final_mainline_alive,
        CASE
          WHEN COALESCE(c.old_final_cycle_state, '') = 'fade_confirmed' THEN 'fade'
          WHEN COALESCE(c.old_previous_cycle_state, '') IN ('', 'unknown') THEN 'flat'
          WHEN COALESCE(c.old_previous_cycle_state, '') = COALESCE(c.old_final_cycle_state, '') THEN 'flat'
          ELSE CASE
            WHEN (
              CASE COALESCE(c.old_final_cycle_state, '')
                WHEN 'fade_confirmed' THEN 0
                WHEN 'fade_watch' THEN 1
                WHEN 'start' THEN 2
                WHEN 'fermentation' THEN 3
                WHEN 'divergence' THEN 4
                WHEN 'repair' THEN 5
                WHEN 'acceleration' THEN 6
                ELSE -1
              END
            ) > (
              CASE COALESCE(c.old_previous_cycle_state, '')
                WHEN 'fade_confirmed' THEN 0
                WHEN 'fade_watch' THEN 1
                WHEN 'start' THEN 2
                WHEN 'fermentation' THEN 3
                WHEN 'divergence' THEN 4
                WHEN 'repair' THEN 5
                WHEN 'acceleration' THEN 6
                ELSE -1
              END
            ) THEN 'upgrade'
            WHEN (
              CASE COALESCE(c.old_final_cycle_state, '')
                WHEN 'fade_confirmed' THEN 0
                WHEN 'fade_watch' THEN 1
                WHEN 'start' THEN 2
                WHEN 'fermentation' THEN 3
                WHEN 'divergence' THEN 4
                WHEN 'repair' THEN 5
                WHEN 'acceleration' THEN 6
                ELSE -1
              END
            ) < (
              CASE COALESCE(c.old_previous_cycle_state, '')
                WHEN 'fade_confirmed' THEN 0
                WHEN 'fade_watch' THEN 1
                WHEN 'start' THEN 2
                WHEN 'fermentation' THEN 3
                WHEN 'divergence' THEN 4
                WHEN 'repair' THEN 5
                WHEN 'acceleration' THEN 6
                ELSE -1
              END
            ) THEN 'downgrade'
            ELSE 'flat'
          END
        END AS new_transition_type,
        CASE
          WHEN COALESCE(c.old_confidence_score, 0) > 0 THEN COALESCE(c.old_confidence_score, 0)
          WHEN COALESCE(c.old_previous_cycle_state, '') IN ('', 'unknown') THEN 0.65
          WHEN COALESCE(c.old_previous_cycle_state, '') = COALESCE(c.old_final_cycle_state, '') THEN 0.75
          ELSE 0.80
        END::numeric AS new_transition_confidence,
        CASE
          WHEN jsonb_array_length(COALESCE(c.old_risk_flags, '[]'::jsonb)) > 0 THEN COALESCE(c.old_risk_flags, '[]'::jsonb)
          ELSE jsonb_build_array(
            CONCAT('from=', COALESCE(NULLIF(c.old_previous_cycle_state, ''), 'unknown')),
            CONCAT('to=', COALESCE(NULLIF(c.old_final_cycle_state, ''), 'unknown'))
          )
        END AS new_trigger_flags
      FROM old_cycle c
      LEFT JOIN old_identity i ON i.subject_key = c.subject_key
    )
    SELECT
      n.subject_key,
      i.old_identity_status,
      n.new_identity_status,
      i.old_is_main_theme,
      n.new_is_main_theme,
      c.old_final_cycle_state,
      n.new_final_cycle_state,
      c.old_final_mainline_alive,
      n.new_final_mainline_alive,
      c.old_previous_cycle_state,
      n.new_transition_type,
      c.old_confidence_score,
      n.new_transition_confidence,
      c.old_risk_flags,
      n.new_trigger_flags
    FROM new_view n
    LEFT JOIN old_identity i ON i.subject_key = n.subject_key
    LEFT JOIN old_cycle c ON c.subject_key = n.subject_key
    ORDER BY n.subject_key
    """
    rows = await conn.fetch(sql, trade_date)
    return [dict(r) for r in rows]


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    identity_diff = 0
    main_theme_diff = 0
    cycle_state_diff = 0
    alive_diff = 0
    trans_type_dist: dict[str, int] = {}
    diff_rows: list[dict[str, Any]] = []

    for r in rows:
        t = str(r.get("new_transition_type") or "")
        trans_type_dist[t] = trans_type_dist.get(t, 0) + 1
        changed = False
        if str(r.get("old_identity_status") or "") != str(r.get("new_identity_status") or ""):
            identity_diff += 1
            changed = True
        if bool(r.get("old_is_main_theme") or False) != bool(r.get("new_is_main_theme") or False):
            main_theme_diff += 1
            changed = True
        if str(r.get("old_final_cycle_state") or "") != str(r.get("new_final_cycle_state") or ""):
            cycle_state_diff += 1
            changed = True
        if bool(r.get("old_final_mainline_alive") or False) != bool(r.get("new_final_mainline_alive") or False):
            alive_diff += 1
            changed = True
        if changed:
            diff_rows.append(r)

    return {
        "total_subjects": total,
        "identity_diff_count": identity_diff,
        "is_main_theme_diff_count": main_theme_diff,
        "cycle_state_diff_count": cycle_state_diff,
        "alive_diff_count": alive_diff,
        "new_transition_type_dist": trans_type_dist,
        "diff_preview": diff_rows[:50],
    }


async def _run(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
    )
    try:
        trade_date = _parse_date(args.trade_date)
        rows = await _fetch_diff_rows(conn, trade_date)
        summary = _summarize(rows)
        out = {
            "ok": True,
            "trade_date": trade_date.isoformat(),
            "summary": summary,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A/B compare old mainline/cycle raw vs new-chain consumed view.")
    parser.add_argument("--trade-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="stock_data_test")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

