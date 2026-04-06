#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime
from typing import Any

import asyncpg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="多日对账：LLM 龙头 vs JYHF 龙头 vs 规则层龙头")
    parser.add_argument("--dates", nargs="*", help="交易日列表，格式 YYYY-MM-DD；为空时自动读取已有 LLM 裁决日期")
    parser.add_argument("--limit-dates", type=int, default=10, help="自动取日期时的最大日期数")
    parser.add_argument("--output-json", default="", help="可选：将结果落为 json 文件")
    return parser.parse_args()


def connect_kwargs() -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


def _coerce_date(value: str) -> date:
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _canon(stock_id: str | None) -> str:
    raw = str(stock_id or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


async def fetch_benchmark_dates(conn: asyncpg.Connection, limit: int) -> list[date]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT trade_date
        FROM theme_leader_llm_judgement
        WHERE COALESCE(leader_stock_id, '') <> ''
        ORDER BY trade_date DESC
        LIMIT $1
        """,
        limit,
    )
    return [row["trade_date"] for row in rows]


async def fetch_theme_rows(conn: asyncpg.Connection, trade_date: date) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        WITH chosen AS (
            SELECT subject_key, theme_name, theme_tier,
                   (COALESCE(event_chain_score, 0) + COALESCE(market_recognition_score, 0) + COALESCE(mainline_stability_score, 0)) AS total_score
            FROM theme_mainline_judgement
            WHERE trade_date = $1::date
              AND theme_tier IN ('main', 'strong_branch')
        )
        SELECT c.subject_key, c.theme_name, c.theme_tier, c.total_score,
               j.leader_stock_id AS llm_leader_stock_id,
               r.stock_id AS rule_leader_stock_id,
               r.stock_name AS rule_leader_stock_name
        FROM chosen c
        LEFT JOIN theme_leader_llm_judgement j
          ON j.trade_date = $1::date
         AND j.subject_key = c.subject_key
        LEFT JOIN theme_leader_candidate r
          ON r.trade_date = $1::date
         AND r.subject_key = c.subject_key
         AND r.candidate_rank = 1
        WHERE COALESCE(j.leader_stock_id, '') <> ''
        ORDER BY CASE c.theme_tier WHEN 'main' THEN 0 ELSE 1 END,
                 c.total_score DESC,
                 c.subject_key
        """,
        trade_date,
    )
    return [dict(row) for row in rows]


async def fetch_jyhf_leader(conn: asyncpg.Connection, trade_date: date, subject_key: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT stock_id, stock_name, pct_chg, rank_order
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND subject_key = $2
          AND is_leader = TRUE
        ORDER BY rank_order NULLS LAST, pct_chg DESC, stock_id
        LIMIT 1
        """,
        trade_date,
        subject_key,
    )
    if not row:
        return None
    return dict(row)


async def fetch_stock_name_map(conn: asyncpg.Connection, trade_date: date, subject_key: str) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT stock_id, stock_name
        FROM (
            SELECT stock_id, stock_name
            FROM theme_leader_candidate
            WHERE trade_date = $1::date AND subject_key = $2
            UNION ALL
            SELECT stock_id, stock_name
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date AND subject_key = $2
        ) t
        """,
        trade_date,
        subject_key,
    )
    result: dict[str, str] = {}
    for row in rows:
        result[_canon(row["stock_id"])] = str(row["stock_name"] or "")
    return result


def _rate(match_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return round(match_count / total_count, 4)


async def build_report_for_date(conn: asyncpg.Connection, trade_date: date) -> dict[str, Any]:
    rows = await fetch_theme_rows(conn, trade_date)
    details: list[dict[str, Any]] = []
    llm_match = 0
    rule_match = 0
    llm_rule_match = 0

    for row in rows:
        subject_key = row["subject_key"]
        name_map = await fetch_stock_name_map(conn, trade_date, subject_key)
        jyhf = await fetch_jyhf_leader(conn, trade_date, subject_key)

        llm_id = _canon(row.get("llm_leader_stock_id"))
        rule_id = _canon(row.get("rule_leader_stock_id"))
        jyhf_id = _canon((jyhf or {}).get("stock_id"))

        llm_ok = bool(llm_id and jyhf_id and llm_id == jyhf_id)
        rule_ok = bool(rule_id and jyhf_id and rule_id == jyhf_id)
        llm_rule_ok = bool(llm_id and rule_id and llm_id == rule_id)

        llm_match += int(llm_ok)
        rule_match += int(rule_ok)
        llm_rule_match += int(llm_rule_ok)

        details.append(
            {
                "subject_key": subject_key,
                "theme_name": row["theme_name"],
                "theme_tier": row["theme_tier"],
                "llm_leader": {
                    "stock_id": llm_id,
                    "stock_name": name_map.get(llm_id, ""),
                },
                "rule_leader": {
                    "stock_id": rule_id,
                    "stock_name": str(row.get("rule_leader_stock_name") or ""),
                },
                "jyhf_leader": {
                    "stock_id": jyhf_id,
                    "stock_name": str((jyhf or {}).get("stock_name") or ""),
                    "pct_chg": float((jyhf or {}).get("pct_chg") or 0),
                    "rank_order": (jyhf or {}).get("rank_order"),
                },
                "llm_equals_jyhf": llm_ok,
                "rule_equals_jyhf": rule_ok,
                "llm_equals_rule": llm_rule_ok,
            }
        )

    total = len(details)
    mismatches = [item for item in details if not item["llm_equals_jyhf"] or not item["rule_equals_jyhf"]]
    return {
        "trade_date": trade_date.isoformat(),
        "theme_count": total,
        "llm_vs_jyhf": {
            "match_count": llm_match,
            "total_count": total,
            "match_rate": _rate(llm_match, total),
        },
        "rule_vs_jyhf": {
            "match_count": rule_match,
            "total_count": total,
            "match_rate": _rate(rule_match, total),
        },
        "llm_vs_rule": {
            "match_count": llm_rule_match,
            "total_count": total,
            "match_rate": _rate(llm_rule_match, total),
        },
        "details": details,
        "mismatches": mismatches,
    }


def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    total_themes = sum(int(report.get("theme_count") or 0) for report in reports)
    llm_match = sum(int((report.get("llm_vs_jyhf") or {}).get("match_count") or 0) for report in reports)
    rule_match = sum(int((report.get("rule_vs_jyhf") or {}).get("match_count") or 0) for report in reports)
    llm_rule_match = sum(int((report.get("llm_vs_rule") or {}).get("match_count") or 0) for report in reports)
    return {
        "date_count": len(reports),
        "theme_count": total_themes,
        "llm_vs_jyhf": {
            "match_count": llm_match,
            "total_count": total_themes,
            "match_rate": _rate(llm_match, total_themes),
        },
        "rule_vs_jyhf": {
            "match_count": rule_match,
            "total_count": total_themes,
            "match_rate": _rate(rule_match, total_themes),
        },
        "llm_vs_rule": {
            "match_count": llm_rule_match,
            "total_count": total_themes,
            "match_rate": _rate(llm_rule_match, total_themes),
        },
    }


async def main_async() -> int:
    args = parse_args()
    conn = await asyncpg.connect(**connect_kwargs())
    try:
        dates = [_coerce_date(item) for item in (args.dates or [])]
        if not dates:
            dates = await fetch_benchmark_dates(conn, args.limit_dates)
        if not dates:
            raise SystemExit("no benchmark dates found")

        reports = [await build_report_for_date(conn, item) for item in dates]
        result = {
            "summary": aggregate_reports(reports),
            "reports": reports,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
