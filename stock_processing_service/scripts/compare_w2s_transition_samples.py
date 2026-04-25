#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from typing import Any

import asyncpg


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_sample(text: str) -> tuple[date, str]:
    # format: YYYY-MM-DD:STOCK_ID
    if ":" not in text:
        raise ValueError(f"invalid --sample: {text}")
    d, sid = text.split(":", 1)
    return _parse_date(d), sid.strip()


async def _fetch_latest_recap(conn: asyncpg.Connection, trade_date: date) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT trade_date, snapshot_version, created_at, payload
        FROM post_market_recap_snapshot
        WHERE trade_date = $1::date
        ORDER BY created_at DESC
        LIMIT 1
        """,
        trade_date,
    )
    return dict(row) if row else None


def _pick_candidate(top_candidates: list[dict[str, Any]], stock_id: str) -> dict[str, Any] | None:
    for c in top_candidates:
        if str(c.get("stock_id") or "") == stock_id:
            return c
    return None


def _as_json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _row_for_output(
    *,
    sample_date: date,
    stock_id: str,
    snapshot_version: str,
    candidate_count: int,
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "trade_date": sample_date.isoformat(),
        "stock_id": stock_id,
        "snapshot_version": snapshot_version,
        "candidate_count": candidate_count,
        "in_top_candidates": candidate is not None,
        "candidate_level": (candidate or {}).get("candidate_level", ""),
        "candidate_score": (candidate or {}).get("candidate_score", ""),
        "transition_type": (candidate or {}).get("transition_type", ""),
        "transition_confidence": (candidate or {}).get("transition_confidence", ""),
        "trigger_flags": (candidate or {}).get("trigger_flags", []),
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
        sample_specs = [_parse_sample(s) for s in args.sample]
        out_rows: list[dict[str, Any]] = []
        for sample_date, stock_id in sample_specs:
            recap = await _fetch_latest_recap(conn, sample_date)
            if not recap:
                out_rows.append(
                    {
                        "trade_date": sample_date.isoformat(),
                        "stock_id": stock_id,
                        "error": "recap_not_found",
                    }
                )
                continue
            payload = _as_json_obj(recap.get("payload") or {})
            nested = _as_json_obj(payload.get("recap_doc"))
            recap_doc = nested if nested else payload
            top_candidates = recap_doc.get("top_candidates") if isinstance(recap_doc, dict) else []
            if not isinstance(top_candidates, list):
                top_candidates = []
            candidate = _pick_candidate(top_candidates, stock_id)
            out_rows.append(
                _row_for_output(
                    sample_date=sample_date,
                    stock_id=stock_id,
                    snapshot_version=str(recap.get("snapshot_version") or ""),
                    candidate_count=int(recap_doc.get("candidate_count") or 0),
                    candidate=candidate,
                )
            )

        print(json.dumps({"ok": True, "rows": out_rows}, ensure_ascii=False, indent=2))
        return 0
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare weak-to-strong top_candidates transition diagnostics for target sample days."
    )
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        help="Sample in YYYY-MM-DD:STOCK_ID format. Can pass multiple times.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="stock_data_test")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.sample:
        args.sample = ["2026-04-07:002361.SZ", "2026-04-15:605060.SH"]
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
