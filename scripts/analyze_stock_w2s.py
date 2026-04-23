#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一弱转强单票分析（本地映射 + v2主线 + 候选池 + 价格支撑）")
    parser.add_argument("--stock-code", required=True, help="股票代码，如 002361 / 605060")
    parser.add_argument("--trade-date", required=True, help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--support-ref-date", default="", help="支撑参考日（可选），默认使用前一交易日")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser.parse_args()


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _to_float(v: Any) -> float:
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0


async def _connect(config: StockServiceConfig) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        database=config.postgres_database,
        user=config.postgres_user,
        password=config.postgres_password,
    )


async def _fetch_mapping(conn: asyncpg.Connection, trade_date: date, stock_code: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT
          s.subject_key,
          COALESCE(NULLIF(vw.theme_name, ''), s.subject_key) AS theme_name
        FROM subject_stock_daily_snapshot s
        LEFT JOIN vw_subject_theme_binding vw
          ON vw.subject_key = s.subject_key
        WHERE s.trade_date = $1::date
          AND split_part(s.stock_id, '.', 1) = $2
        ORDER BY s.subject_key
        """,
        trade_date,
        stock_code,
    )
    return [dict(r) for r in rows]


async def _fetch_v2_states(conn: asyncpg.Connection, trade_date: date, subject_keys: list[str]) -> list[dict[str, Any]]:
    if not subject_keys:
        return []
    rows = await conn.fetch(
        """
        SELECT
          v2.subject_key,
          COALESCE(NULLIF(v2.theme_name, ''), v2.subject_key) AS theme_name,
          COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
          COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
          COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
          COALESCE(v2.fade_watch, FALSE) AS fade_watch,
          COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed,
          COALESCE(e.event_count_3d, 0) AS event_count_3d,
          COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
          COALESCE(e.limit_up_count, 0) AS limit_up_count
        FROM theme_cycle_judgement_v2 v2
        LEFT JOIN theme_cycle_evidence_daily e
          ON e.trade_date = v2.trade_date
         AND e.subject_key = v2.subject_key
        WHERE v2.trade_date = $1::date
          AND v2.subject_key = ANY($2::varchar[])
        ORDER BY v2.subject_key
        """,
        trade_date,
        subject_keys,
    )
    return [dict(r) for r in rows]


async def _fetch_candidate_rows(conn: asyncpg.Connection, trade_date: date, stock_code: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
          trade_date,
          next_trade_date,
          subject_key,
          COALESCE(theme_name, subject_key) AS theme_name,
          stock_id,
          stock_name,
          pool_entry_type,
          candidate_score,
          support_strength,
          support_type,
          cycle_state,
          mainline_strength_score,
          fade_watch,
          fade_confirmed
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = $1::date
          AND split_part(stock_id, '.', 1) = $2
        ORDER BY candidate_score DESC NULLS LAST
        """,
        trade_date,
        stock_code,
    )
    return [dict(r) for r in rows]


async def _fetch_day_bar(conn: asyncpg.Connection, trade_date: date, stock_code: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT
          trade_date,
          stock_id,
          stock_name,
          pct_chg,
          low_price,
          close_price,
          limit_up,
          is_leader,
          rank_order
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND split_part(stock_id, '.', 1) = $2
        ORDER BY amount DESC NULLS LAST, rank_order ASC
        LIMIT 1
        """,
        trade_date,
        stock_code,
    )
    return dict(row) if row else None


async def _fetch_prev_trade_date(conn: asyncpg.Connection, trade_date: date, stock_code: str) -> date | None:
    return await conn.fetchval(
        """
        SELECT MAX(trade_date)
        FROM subject_stock_daily_snapshot
        WHERE split_part(stock_id, '.', 1) = $1
          AND trade_date < $2::date
        """,
        stock_code,
        trade_date,
    )


def _build_summary(payload: dict[str, Any]) -> dict[str, Any]:
    mapping = payload["mapping"]
    v2_states = payload["v2_states"]
    candidates = payload["candidates"]
    day_bar = payload["day_bar"]
    prev_bar = payload["prev_bar"]

    has_alive_mainline = any(bool(x.get("final_mainline_alive")) for x in v2_states)
    has_non_fade_confirmed = any(not bool(x.get("fade_confirmed")) for x in v2_states)
    has_formal = any(str(x.get("pool_entry_type") or "").lower() == "formal" for x in candidates)
    has_any_candidate = bool(candidates)

    pct_chg = _to_float((day_bar or {}).get("pct_chg"))
    prev_pct = _to_float((prev_bar or {}).get("pct_chg"))
    support_ref = _to_float((prev_bar or {}).get("low_price"))
    day_low = _to_float((day_bar or {}).get("low_price"))
    support_distance_pct = 0.0
    if support_ref > 0:
        support_distance_pct = abs(day_low - support_ref) / support_ref * 100.0

    return {
        "mapping_count": len(mapping),
        "v2_state_count": len(v2_states),
        "has_alive_mainline": has_alive_mainline,
        "has_non_fade_confirmed": has_non_fade_confirmed,
        "candidate_count": len(candidates),
        "has_any_candidate": has_any_candidate,
        "has_formal_candidate": has_formal,
        "day_pct_chg": pct_chg,
        "prev_day_pct_chg": prev_pct,
        "support_ref_low": support_ref,
        "day_low": day_low,
        "support_distance_pct": round(support_distance_pct, 2),
    }


def _print_text(payload: dict[str, Any]) -> None:
    print(f"[INPUT] stock={payload['stock_code']} trade_date={payload['trade_date']}")
    print(f"[MAPPING] count={len(payload['mapping'])}")
    for row in payload["mapping"]:
        print(f"  - {row['subject_key']} {row['theme_name']}")

    print(f"[V2] count={len(payload['v2_states'])}")
    for row in payload["v2_states"]:
        print(
            "  - "
            f"{row['subject_key']} {row['theme_name']} "
            f"alive={row['final_mainline_alive']} state={row['final_cycle_state']} "
            f"strength={_to_float(row['mainline_strength_score']):.1f} "
            f"fade_watch={row['fade_watch']} fade_confirmed={row['fade_confirmed']}"
        )

    print(f"[CANDIDATE] count={len(payload['candidates'])}")
    for row in payload["candidates"]:
        print(
            "  - "
            f"{row['stock_id']} {row['theme_name']} entry={row.get('pool_entry_type')} "
            f"score={_to_float(row.get('candidate_score')):.1f} "
            f"support={_to_float(row.get('support_strength')):.1f} "
            f"type={row.get('support_type')} state={row.get('cycle_state')}"
        )

    day_bar = payload.get("day_bar")
    prev_bar = payload.get("prev_bar")
    print("[PRICE]")
    if day_bar:
        print(
            f"  day: {day_bar.get('trade_date')} pct={_to_float(day_bar.get('pct_chg')):.2f}% "
            f"low={_to_float(day_bar.get('low_price')):.2f} close={_to_float(day_bar.get('close_price')):.2f}"
        )
    else:
        print("  day: missing")
    if prev_bar:
        print(
            f"  prev: {prev_bar.get('trade_date')} pct={_to_float(prev_bar.get('pct_chg')):.2f}% "
            f"low={_to_float(prev_bar.get('low_price')):.2f} close={_to_float(prev_bar.get('close_price')):.2f}"
        )
    else:
        print("  prev: missing")

    s = payload["summary"]
    print(
        "[SUMMARY] "
        f"alive_mainline={s['has_alive_mainline']} "
        f"non_fade={s['has_non_fade_confirmed']} "
        f"candidate={s['has_any_candidate']} formal={s['has_formal_candidate']} "
        f"support_distance_pct={s['support_distance_pct']}"
    )


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    stock_code = str(args.stock_code).split(".", 1)[0]
    support_ref_date = _parse_date(args.support_ref_date) if args.support_ref_date else None

    config = StockServiceConfig()
    conn = await _connect(config)
    try:
        mapping = await _fetch_mapping(conn, trade_date, stock_code)
        subject_keys = [str(x["subject_key"]) for x in mapping]
        v2_states = await _fetch_v2_states(conn, trade_date, subject_keys)
        candidates = await _fetch_candidate_rows(conn, trade_date, stock_code)
        day_bar = await _fetch_day_bar(conn, trade_date, stock_code)

        prev_date = support_ref_date or await _fetch_prev_trade_date(conn, trade_date, stock_code)
        prev_bar = await _fetch_day_bar(conn, prev_date, stock_code) if prev_date else None

        payload = {
            "stock_code": stock_code,
            "trade_date": trade_date.isoformat(),
            "support_ref_date": prev_date.isoformat() if prev_date else None,
            "mapping": mapping,
            "v2_states": v2_states,
            "candidates": candidates,
            "day_bar": day_bar,
            "prev_bar": prev_bar,
        }
        payload["summary"] = _build_summary(payload)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_text(payload)
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
