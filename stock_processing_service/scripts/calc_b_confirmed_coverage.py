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


async def _calc_for_date(conn: asyncpg.Connection, d: date) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        WITH confirmed AS (
          SELECT DISTINCT subject_key
          FROM theme_mainline_identity_registry
          WHERE COALESCE(LOWER(identity_status), '') = 'confirmed'
            AND COALESCE(is_main_theme, FALSE) = TRUE
        ),
        covered AS (
          SELECT DISTINCT c.subject_key
          FROM confirmed c
          JOIN theme_cycle_judgement_v2 v2
            ON v2.subject_key = c.subject_key
           AND v2.trade_date = $1::date
        )
        SELECT
          (SELECT COUNT(*) FROM confirmed) AS confirmed_cnt,
          (SELECT COUNT(*) FROM covered) AS covered_cnt
        """,
        d,
    )
    confirmed = int((row or {}).get("confirmed_cnt") or 0)
    covered = int((row or {}).get("covered_cnt") or 0)
    coverage = 1.0 if confirmed == 0 else (covered / confirmed)
    return {
        "trade_date": d.isoformat(),
        "confirmed_cnt": confirmed,
        "covered_cnt": covered,
        "coverage": coverage,
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
        rows = []
        for d in dates:
            rows.append(await _calc_for_date(conn, d))
        avg = sum(float(r["coverage"]) for r in rows) / max(len(rows), 1)
        out = {
            "ok": True,
            "results": rows,
            "b_confirmed_coverage": avg,
            "source": "theme_mainline_identity_registry + theme_cycle_judgement_v2",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Calculate Layer B confirmed coverage for baseline dates.")
    p.add_argument("--trade-dates", required=True, help="Comma separated dates, e.g. 2026-04-07,2026-04-15,2026-04-22")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--database", default="stock_data_test")
    p.add_argument("--user", default="postgres")
    p.add_argument("--password", default="")
    return p


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_build_parser().parse_args())))
