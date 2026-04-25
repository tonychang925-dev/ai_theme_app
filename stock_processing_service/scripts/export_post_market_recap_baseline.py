#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import asyncpg


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"invalid --trade-date: {value}") from exc


async def _fetch_snapshot(
    conn: asyncpg.Connection,
    *,
    trade_date: date,
    snapshot_version: str | None,
) -> dict[str, Any] | None:
    if snapshot_version:
        row = await conn.fetchrow(
            """
            SELECT trade_date, snapshot_version, batch_id, trace_id, created_at, payload
            FROM post_market_recap_snapshot
            WHERE trade_date = $1::date
              AND snapshot_version = $2
            LIMIT 1
            """,
            trade_date,
            snapshot_version,
        )
        return dict(row) if row else None

    row = await conn.fetchrow(
        """
        SELECT trade_date, snapshot_version, batch_id, trace_id, created_at, payload
        FROM post_market_recap_snapshot
        WHERE trade_date = $1::date
        ORDER BY created_at DESC
        LIMIT 1
        """,
        trade_date,
    )
    return dict(row) if row else None


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
        row = await _fetch_snapshot(
            conn,
            trade_date=trade_date,
            snapshot_version=args.snapshot_version,
        )
        if not row:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "snapshot_not_found",
                        "trade_date": trade_date.isoformat(),
                        "snapshot_version": args.snapshot_version or "",
                    },
                    ensure_ascii=False,
                )
            )
            return 2

        payload = row.get("payload") or {}
        recap_doc = payload.get("recap_doc") if isinstance(payload, dict) else {}
        out = {
            "trade_date": str(row.get("trade_date")),
            "snapshot_version": str(row.get("snapshot_version") or ""),
            "batch_id": str(row.get("batch_id") or ""),
            "trace_id": str(row.get("trace_id") or ""),
            "created_at": str(row.get("created_at") or ""),
            "baseline": {
                "candidate_count": recap_doc.get("candidate_count"),
                "strong_watch_input_count": recap_doc.get("strong_watch_input_count"),
                "strong_watch_promoted_count": recap_doc.get("strong_watch_promoted_count"),
                "strong_watch_history_count": recap_doc.get("strong_watch_history_count"),
                "strong_watch_shadow_summary": recap_doc.get("strong_watch_shadow_summary", {}),
                "shadow_layer_c_formal_count": recap_doc.get("shadow_layer_c_formal_count"),
                "shadow_layer_c_observe_count": recap_doc.get("shadow_layer_c_observe_count"),
                "shadow_layer_c_reject_count": recap_doc.get("shadow_layer_c_reject_count"),
                "shadow_layer_c_pass_4of3_fail_count": recap_doc.get("shadow_layer_c_pass_4of3_fail_count"),
                "shadow_layer_c_hard_reject_count": recap_doc.get("shadow_layer_c_hard_reject_count"),
                "layer_a_identity_source": recap_doc.get("layer_a_identity_source"),
                "layer_b_cycle_source": recap_doc.get("layer_b_cycle_source"),
                "layer_a_identity_hit_count": recap_doc.get("layer_a_identity_hit_count"),
                "layer_b_cycle_hit_count": recap_doc.get("layer_b_cycle_hit_count"),
                "layer_ab_subject_key_count": recap_doc.get("layer_ab_subject_key_count"),
                "input_fingerprint": recap_doc.get("input_fingerprint", {}),
                "top_candidates": recap_doc.get("top_candidates", []),
            },
        }

        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(output_path),
                    "trade_date": out["trade_date"],
                    "snapshot_version": out["snapshot_version"],
                    "candidate_count": out["baseline"]["candidate_count"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export immutable post-market recap baseline JSON.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--snapshot-version", default="", help="Optional exact snapshot_version")
    parser.add_argument("--output", required=True, help="Output baseline json path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="stock_data_test")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.snapshot_version:
        args.snapshot_version = None
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
