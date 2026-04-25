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


async def _fetch_old_ids(conn: asyncpg.Connection, anchor: date) -> set[str]:
    sql = """
    WITH w AS (
      SELECT DISTINCT trade_date
      FROM public.stock_daily_snapshot
      WHERE trade_date <= $1::date
      ORDER BY trade_date DESC
      LIMIT 7
    )
    SELECT DISTINCT h.stock_id
    FROM public.strong_stock_watch_history h
    JOIN w ON w.trade_date = h.trade_date
    WHERE h.watch_status IN ('active', 'weakening')
      AND h.pool_entry_type IN ('formal', 'observe_only')
    """
    rows = await conn.fetch(sql, anchor)
    return {str(r["stock_id"]) for r in rows if r["stock_id"]}


async def _fetch_new_payload(conn: asyncpg.Connection, anchor: date) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT payload
        FROM public.post_market_recap_snapshot
        WHERE trade_date = $1::date
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        anchor,
    )
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    # 兼容 payload.recap_doc 与 payload 直存两种写法
    recap_doc = payload.get("recap_doc")
    if isinstance(recap_doc, dict):
        return recap_doc
    return payload


async def _debug_recap_presence(conn: asyncpg.Connection, anchor: date) -> dict[str, Any]:
    count_row = await conn.fetchrow("SELECT COUNT(*) AS c FROM public.post_market_recap_snapshot")
    hit_row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS c
        FROM public.post_market_recap_snapshot
        WHERE trade_date = $1::date
        """,
        anchor,
    )
    sample_rows = await conn.fetch(
        """
        SELECT trade_date::text AS trade_date, snapshot_version
        FROM public.post_market_recap_snapshot
        ORDER BY trade_date DESC
        LIMIT 5
        """
    )
    return {
        "table_total": int((count_row or {}).get("c") or 0),
        "anchor_hit": int((hit_row or {}).get("c") or 0),
        "latest_dates": [dict(r) for r in sample_rows],
    }


def _fetch_new_ids(payload: dict[str, Any]) -> set[str]:
    raw = payload.get("strong_watch_input_7d_stock_ids") or []
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x)}


def _preview_by_stock(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    preview = payload.get("strong_watch_input_7d_preview") or []
    if not isinstance(preview, list):
        return out
    for item in preview:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        out[sid] = item
    return out


def _sample_preview(preview_map: dict[str, dict[str, Any]], ids: set[str], limit: int = 30) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for sid in sorted(ids)[:limit]:
        p = preview_map.get(sid, {})
        result.append(
            {
                "stock_id": sid,
                "stock_name": str(p.get("stock_name") or ""),
                "subject_key": str(p.get("subject_key") or ""),
                "subject_name": str(p.get("subject_name") or ""),
                "watch_score": str(p.get("watch_score") or ""),
                "support_type": str(p.get("support_type") or ""),
                "final_cycle_state": str(p.get("final_cycle_state") or ""),
                "transition_type": str(p.get("transition_type") or ""),
                "transition_confidence": str(p.get("transition_confidence") or ""),
            }
        )
    return result


async def _compare_one(conn: asyncpg.Connection, anchor: date) -> dict[str, Any]:
    old_ids = await _fetch_old_ids(conn, anchor)
    payload = await _fetch_new_payload(conn, anchor)
    if payload is None:
        return {
            "trade_date": anchor.isoformat(),
            "ok": False,
            "reason": "post_market_recap_snapshot_missing",
            "debug": await _debug_recap_presence(conn, anchor),
        }
    new_ids = _fetch_new_ids(payload)
    preview_map = _preview_by_stock(payload)

    overlap = old_ids & new_ids
    old_only = old_ids - new_ids
    new_only = new_ids - old_ids

    # Key anchors explicitly required by user.
    shenjian = "002361.SZ" in new_ids if anchor == date(2026, 4, 7) else None
    liande = "605060.SH" in new_ids if anchor == date(2026, 4, 15) else None

    return {
        "trade_date": anchor.isoformat(),
        "ok": True,
        "counts": {
            "old_7d_union_count": len(old_ids),
            "new_7d_input_count": len(new_ids),
            "overlap_count": len(overlap),
            "old_only_count": len(old_only),
            "new_only_count": len(new_only),
        },
        "key_samples": {
            "shenjian_002361_SZ_in_new_7d": shenjian,
            "liande_605060_SH_in_new_7d": liande,
        },
        "old_only_sample": sorted(old_only)[:50],
        "new_only_sample": _sample_preview(preview_map, new_only, limit=50),
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
        dates = [_parse_date(x.strip()) for x in args.trade_dates.split(",") if x.strip()]
        out = {"ok": True, "results": []}
        for d in dates:
            out["results"].append(await _compare_one(conn, d))
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare old vs new 7-trading-day strong-watch input pools.")
    p.add_argument("--trade-dates", required=True, help="Comma separated dates, e.g. 2026-04-07,2026-04-15")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--database", default="stock_data_test")
    p.add_argument("--user", default="postgres")
    p.add_argument("--password", default="")
    return p


def main() -> int:
    return asyncio.run(_run(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
