#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import date, datetime
from pathlib import Path
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


async def _fetch_recap_payload(conn: asyncpg.Connection, anchor: date) -> dict[str, Any]:
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
        return {}
    payload = row["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return {}
    if not isinstance(payload, dict):
        return {}
    recap_doc = payload.get("recap_doc")
    if isinstance(recap_doc, dict):
        return recap_doc
    return payload


def _new_preview_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
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


def _new_ids(payload: dict[str, Any]) -> set[str]:
    raw = payload.get("strong_watch_input_7d_stock_ids") or []
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x)}


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


async def _run(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
    )
    try:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        summary: list[dict[str, Any]] = []
        for raw_date in [x.strip() for x in args.trade_dates.split(",") if x.strip()]:
            d = _parse_date(raw_date)
            old_ids = await _fetch_old_ids(conn, d)
            payload = await _fetch_recap_payload(conn, d)
            new_ids = _new_ids(payload)
            new_preview = _new_preview_map(payload)

            overlap = old_ids & new_ids
            old_only = old_ids - new_ids
            new_only = new_ids - old_ids

            prefix = out_dir / d.isoformat()
            _write_csv(
                prefix.with_suffix(".old_ids.csv"),
                [{"stock_id": sid} for sid in sorted(old_ids)],
                ["stock_id"],
            )
            _write_csv(
                prefix.with_suffix(".new_ids.csv"),
                [{"stock_id": sid} for sid in sorted(new_ids)],
                ["stock_id"],
            )
            _write_csv(
                prefix.with_suffix(".overlap.csv"),
                [{"stock_id": sid} for sid in sorted(overlap)],
                ["stock_id"],
            )
            _write_csv(
                prefix.with_suffix(".old_only.csv"),
                [{"stock_id": sid} for sid in sorted(old_only)],
                ["stock_id"],
            )

            new_only_rows: list[dict[str, Any]] = []
            for sid in sorted(new_only):
                p = new_preview.get(sid, {})
                new_only_rows.append(
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
            _write_csv(
                prefix.with_suffix(".new_only.csv"),
                new_only_rows,
                [
                    "stock_id",
                    "stock_name",
                    "subject_key",
                    "subject_name",
                    "watch_score",
                    "support_type",
                    "final_cycle_state",
                    "transition_type",
                    "transition_confidence",
                ],
            )

            summary.append(
                {
                    "trade_date": d.isoformat(),
                    "old_7d_union_count": len(old_ids),
                    "new_7d_input_count": len(new_ids),
                    "overlap_count": len(overlap),
                    "old_only_count": len(old_only),
                    "new_only_count": len(new_only),
                    "shenjian_in_new_7d": ("002361.SZ" in new_ids) if d == date(2026, 4, 7) else "",
                    "liande_in_new_7d": ("605060.SH" in new_ids) if d == date(2026, 4, 15) else "",
                }
            )

        _write_csv(
            out_dir / "summary.csv",
            summary,
            [
                "trade_date",
                "old_7d_union_count",
                "new_7d_input_count",
                "overlap_count",
                "old_only_count",
                "new_only_count",
                "shenjian_in_new_7d",
                "liande_in_new_7d",
            ],
        )
        print(f"wrote files to: {out_dir}")
        return 0
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Export full old/new 7d strong-watch pool compare")
    p.add_argument("--trade-dates", required=True)
    p.add_argument("--out-dir", default="tmp/layer_c_audit_7d_full")
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
