#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from datetime import date, datetime

import asyncpg


def parse_args():
    parser = argparse.ArgumentParser(description="P3.phase2 跨交易日一致性检查")
    parser.add_argument(
        "--dates",
        nargs="+",
        required=True,
        help="交易日列表，格式 YYYY-MM-DD",
    )
    return parser.parse_args()


async def connect_db() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )


def _coerce_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def fetch_table_summary(conn: asyncpg.Connection, table_name: str, trade_date: str) -> dict:
    if table_name == "theme_mainline_judgement":
        key_expr = "subject_key || '|' || theme_tier || '|' || coalesce(source_trace_id,'')"
    elif table_name == "theme_cycle_judgement":
        key_expr = "subject_key || '|' || primary_cycle_stage || '|' || coalesce(source_trace_id,'')"
    elif table_name == "theme_leader_candidate":
        key_expr = "subject_key || '|' || stock_id || '|' || role_label || '|' || coalesce(source_trace_id,'')"
    elif table_name == "money_flow_enhanced":
        key_expr = "subject_key || '|' || stock_id || '|' || role_enhanced || '|' || coalesce(source_trace_id,'')"
    else:
        raise ValueError(f"unsupported table: {table_name}")

    sql = f"""
    SELECT
      count(*) AS total_rows,
      count(*) FILTER (WHERE coalesce(source_type, '') = '') AS missing_source_type,
      count(*) FILTER (WHERE coalesce(source_trace_id, '') = '') AS missing_trace_id,
      count(*) FILTER (WHERE source_trace IS NULL OR source_trace = '{{}}'::jsonb) AS missing_trace_payload,
      count(*) FILTER (WHERE coalesce(source_version, '') = '') AS missing_source_version,
      count(*) FILTER (WHERE coalesce(rule_version, '') = '') AS missing_rule_version,
      md5(string_agg(({key_expr})::text, '||' ORDER BY {key_expr})) AS digest
    FROM {table_name}
    WHERE trade_date = $1::date
    """
    row = await conn.fetchrow(sql, trade_date)
    return dict(row)


async def main_async() -> int:
    args = parse_args()
    dates = [_coerce_date(item) for item in args.dates]
    tables = [
        "theme_mainline_judgement",
        "theme_cycle_judgement",
        "theme_leader_candidate",
        "money_flow_enhanced",
    ]

    conn = await connect_db()
    try:
        print("[CHECK] P3.phase2 consistency")
        for trade_date in dates:
            print(f"[DATE] {trade_date.isoformat()}")
            for table_name in tables:
                summary = await fetch_table_summary(conn, table_name, trade_date)
                digest = summary.get("digest") or ""
                short_digest = hashlib.md5(digest.encode("utf-8")).hexdigest()[:12] if digest else ""
                print(
                    f"  - {table_name}: rows={summary['total_rows']} "
                    f"missing_source_type={summary['missing_source_type']} "
                    f"missing_trace_id={summary['missing_trace_id']} "
                    f"missing_trace_payload={summary['missing_trace_payload']} "
                    f"missing_source_version={summary['missing_source_version']} "
                    f"missing_rule_version={summary['missing_rule_version']} "
                    f"digest={short_digest}"
                )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
