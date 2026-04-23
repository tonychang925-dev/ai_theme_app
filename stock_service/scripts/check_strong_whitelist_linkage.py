#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig
from stock_service.services.strong_stock_tracking_service import StrongStockTrackingService
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="S/A 白名单联动回归检查")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--rebuild-watch", action="store_true", help="统计前重建强势股观察池")
    parser.add_argument("--rebuild-candidates", action="store_true", help="统计前重建弱转强候选池")
    parser.add_argument("--max-candidates", type=int, default=500, help="候选池重建上限")
    return parser.parse_args()


async def _build_if_needed(args: argparse.Namespace, trade_date: date) -> None:
    if args.rebuild_watch:
        svc = StrongStockTrackingService()
        try:
            seed = await svc.seed_watch_pool(trade_date)
            refresh = await svc.refresh_watch_pool(trade_date)
            promote = await svc.promote_watch_candidates(trade_date)
            prune = await svc.prune_watch_pool(trade_date)
            snapshot = await svc.snapshot_watch_pool(trade_date)
            print(
                f"[REBUILD] watch trade_date={trade_date} "
                f"seed={seed} refresh={refresh} promote={promote} prune={prune} snapshot={snapshot}"
            )
        finally:
            await svc.close()

    if args.rebuild_candidates:
        builder = WeakToStrongCandidateBuilder()
        try:
            result = await builder.build(trade_date, max_candidates=int(args.max_candidates))
            print(
                f"[REBUILD] candidates trade_date={trade_date} next_trade_date={result.next_trade_date} "
                f"inserted={result.total_inserted} scanned={result.total_scanned}"
            )
        finally:
            await builder.close()


async def _fetch_metrics(conn: asyncpg.Connection, trade_date: date) -> Dict[str, Any]:
    grade_rows = await conn.fetch(
        """
        SELECT
            COALESCE(labels_json->>'strong_grade', '') AS strong_grade,
            COUNT(*) AS cnt
        FROM strong_stock_watch_pool
        WHERE last_trade_date = $1::date
          AND watch_status IN ('active', 'weakening')
        GROUP BY 1
        ORDER BY 1
        """,
        trade_date,
    )
    watch_grade_dist = {str(r["strong_grade"] or ""): int(r["cnt"] or 0) for r in grade_rows}
    active_sa_total = int(watch_grade_dist.get("S", 0) + watch_grade_dist.get("A", 0))

    cand_rows = await conn.fetchrow(
        """
        WITH c AS (
            SELECT *
            FROM weak_to_strong_candidate_pool
            WHERE trade_date = $1::date
        ),
        watch_tag AS (
            SELECT
                c.stock_id,
                c.pool_entry_type,
                EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(c.evidence_json->'source_refs', '[]'::jsonb)) ref
                    WHERE ref->>'source_tag' = 'watch_pool'
                ) AS from_watch_pool,
                EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(c.evidence_json->'source_refs', '[]'::jsonb)) ref
                    WHERE ref->>'source_tag' = 'watch_pool'
                      AND UPPER(COALESCE(ref->>'strong_grade', '')) IN ('S', 'A')
                ) AS from_watch_sa
            FROM c
        ),
        sa_watch AS (
            SELECT DISTINCT split_part(stock_id, '.', 1) AS stock_code
            FROM strong_stock_watch_pool
            WHERE last_trade_date = $1::date
              AND watch_status IN ('active', 'weakening')
              AND UPPER(COALESCE(labels_json->>'strong_grade', '')) IN ('S', 'A')
        ),
        cand_stock AS (
            SELECT DISTINCT split_part(stock_id, '.', 1) AS stock_code
            FROM c
        ),
        cand_formal_stock AS (
            SELECT DISTINCT split_part(stock_id, '.', 1) AS stock_code
            FROM c
            WHERE pool_entry_type = 'formal'
        )
        SELECT
            (SELECT COUNT(*) FROM c) AS candidate_total,
            (SELECT COUNT(*) FROM c WHERE pool_entry_type = 'formal') AS formal_total,
            (SELECT COUNT(*) FROM watch_tag WHERE from_watch_pool) AS candidate_from_watch_pool,
            (SELECT COUNT(*) FROM watch_tag WHERE from_watch_sa) AS candidate_from_watch_sa,
            (SELECT COUNT(*) FROM watch_tag WHERE pool_entry_type = 'formal' AND from_watch_pool) AS formal_from_watch_pool,
            (SELECT COUNT(*) FROM watch_tag WHERE pool_entry_type = 'formal' AND from_watch_sa) AS formal_from_watch_sa,
            (SELECT COUNT(*) FROM sa_watch) AS watch_sa_stock_total,
            (SELECT COUNT(*) FROM sa_watch s JOIN cand_stock c ON c.stock_code = s.stock_code) AS watch_sa_to_candidate_stock,
            (SELECT COUNT(*) FROM sa_watch s JOIN cand_formal_stock f ON f.stock_code = s.stock_code) AS watch_sa_to_formal_stock
        """,
        trade_date,
    )

    candidate_total = int(cand_rows["candidate_total"] or 0)
    formal_total = int(cand_rows["formal_total"] or 0)
    watch_sa_stock_total = int(cand_rows["watch_sa_stock_total"] or 0)
    watch_sa_to_candidate_stock = int(cand_rows["watch_sa_to_candidate_stock"] or 0)
    watch_sa_to_formal_stock = int(cand_rows["watch_sa_to_formal_stock"] or 0)
    formal_from_watch_pool = int(cand_rows["formal_from_watch_pool"] or 0)
    formal_from_watch_sa = int(cand_rows["formal_from_watch_sa"] or 0)

    return {
        "watch_grade_distribution": watch_grade_dist,
        "watch_active_sa_total": active_sa_total,
        "candidate_total": candidate_total,
        "formal_total": formal_total,
        "candidate_from_watch_pool": int(cand_rows["candidate_from_watch_pool"] or 0),
        "candidate_from_watch_sa": int(cand_rows["candidate_from_watch_sa"] or 0),
        "formal_from_watch_pool": formal_from_watch_pool,
        "formal_from_watch_sa": formal_from_watch_sa,
        "formal_from_watch_pool_ratio": round(formal_from_watch_pool / formal_total, 4) if formal_total else 0.0,
        "formal_from_watch_sa_ratio": round(formal_from_watch_sa / formal_total, 4) if formal_total else 0.0,
        "watch_sa_to_candidate_stock": watch_sa_to_candidate_stock,
        "watch_sa_to_formal_stock": watch_sa_to_formal_stock,
        "watch_sa_to_candidate_ratio": round(watch_sa_to_candidate_stock / watch_sa_stock_total, 4) if watch_sa_stock_total else 0.0,
        "watch_sa_to_formal_ratio": round(watch_sa_to_formal_stock / watch_sa_stock_total, 4) if watch_sa_stock_total else 0.0,
    }


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)

    await _build_if_needed(args, trade_date)

    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        metrics = await _fetch_metrics(conn, trade_date)
    finally:
        await conn.close()

    print(json.dumps({"trade_date": trade_date.isoformat(), **metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
