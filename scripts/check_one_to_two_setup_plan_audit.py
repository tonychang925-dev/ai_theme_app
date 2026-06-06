#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import asyncpg
except Exception:  # pragma: no cover
    asyncpg = None


BUY_TOKENS = ("recommend_buy", "must_buy", "buy")


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _dsn_from_args_or_env(dsn: str | None) -> str:
    if dsn:
        return dsn
    return os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL") or ""


def _as_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"{field_name} payload must be a JSON object")
    raise ValueError(f"{field_name} payload must be a JSON object")


def _row_text(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, default=str).lower()


def _row_has_buy_token(row: dict[str, Any]) -> bool:
    text = _row_text(row)
    return any(token in text for token in BUY_TOKENS)


def _safe_schema_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError(f"Unsafe schema name: {value!r}")
    return value


async def _resolve_table_name(conn: Any, table_name: str) -> str:
    rows = await conn.fetch(
        """
        SELECT table_schema
        FROM information_schema.tables
        WHERE table_name = $1
        ORDER BY CASE WHEN table_schema = 'public' THEN 0 ELSE 1 END, table_schema ASC
        LIMIT 1
        """,
        table_name,
    )
    if not rows:
        raise RuntimeError(f"relation '{table_name}' does not exist")
    schema = _safe_schema_name(str(rows[0]["table_schema"]))
    return f"{schema}.{table_name}"


def build_audit_report(
    plan_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    *,
    trade_date: str,
    setup_type: str = "one_to_two",
) -> dict[str, Any]:
    summary_rows = [row for row in plan_rows if str(row.get("stock_id") or "") == "__SUMMARY__"]
    item_rows = [row for row in plan_rows if str(row.get("stock_id") or "") != "__SUMMARY__"]
    candidate_summary_rows = [row for row in feature_rows if str(row.get("stock_id") or "") == "__SUMMARY__"]
    candidate_item_rows = [row for row in feature_rows if str(row.get("stock_id") or "") != "__SUMMARY__"]

    summary = _as_dict(summary_rows[0].get("summary"), "summary") if len(summary_rows) == 1 else {}
    diagnostics = _as_dict(summary_rows[0].get("diagnostics"), "diagnostics") if len(summary_rows) == 1 else {}

    summary_counts = {
        "focus_count": int(summary.get("focus_count") or 0),
        "observe_only_count": int(summary.get("observe_only_count") or 0),
        "pending_review_only_count": int(summary.get("pending_review_only_count") or 0),
        "reject_count": int(summary.get("reject_count") or 0),
    }
    summary_counts_total = (
        summary_counts["focus_count"]
        + summary_counts["observe_only_count"]
        + summary_counts["pending_review_only_count"]
    )

    plan_item_decisions = Counter(str(row.get("decision") or "") for row in item_rows)
    candidate_decisions = Counter(str(row.get("decision") or "") for row in candidate_item_rows)
    reject_rows = [row for row in candidate_item_rows if str(row.get("decision") or "") == "reject"]
    reject_missing_veto_reasons = [
        row for row in reject_rows if not row.get("veto_reasons")
    ]

    plan_item_keys = {
        (
            str(row.get("trade_date") or trade_date),
            str(row.get("setup_type") or setup_type),
            str(row.get("stock_id") or ""),
            str(row.get("subject_key") or ""),
        )
        for row in item_rows
    }
    candidate_item_keys = {
        (
            str(row.get("trade_date") or trade_date),
            str(row.get("setup_type") or setup_type),
            str(row.get("stock_id") or ""),
            str(row.get("subject_key") or ""),
        )
        for row in candidate_item_rows
    }
    missing_candidate_coverage = sorted(plan_item_keys - candidate_item_keys)

    plan_buy_hits = [row for row in plan_rows if _row_has_buy_token(row)]
    feature_buy_hits = [row for row in feature_rows if _row_has_buy_token(row)]

    errors: list[str] = []
    if len(summary_rows) != 1:
        errors.append(f"summary_row_count={len(summary_rows)}")
    if len(candidate_summary_rows) > 0:
        errors.append(f"candidate_summary_row_count={len(candidate_summary_rows)}")
    if len(item_rows) != summary_counts_total:
        errors.append(
            "plan_item_count_mismatch="
            f"items={len(item_rows)} summary_total={summary_counts_total}"
        )
    if missing_candidate_coverage:
        errors.append(f"candidate_coverage_missing={missing_candidate_coverage}")
    if reject_missing_veto_reasons:
        errors.append(f"reject_missing_veto_reasons={len(reject_missing_veto_reasons)}")
    if not all(str(row.get("setup_type") or "") == setup_type for row in plan_rows):
        errors.append("plan_setup_type_mismatch")
    if not all(str(row.get("setup_type") or "") == setup_type for row in feature_rows):
        errors.append("candidate_setup_type_mismatch")
    if plan_buy_hits or feature_buy_hits:
        errors.append("buy_tokens_present")

    contract = {
        "summary_unique": len(summary_rows) == 1,
        "summary_payload_valid": bool(summary) and isinstance(summary, dict),
        "diagnostics_payload_valid": bool(diagnostics) and isinstance(diagnostics, dict),
        "plan_item_count_matches_summary": len(item_rows) == summary_counts_total,
        "candidate_feature_covers_plan_items": not missing_candidate_coverage,
        "candidate_feature_no_summary": len(candidate_summary_rows) == 0,
        "candidate_feature_setup_type_consistent": all(
            str(row.get("setup_type") or "") == setup_type for row in feature_rows
        ),
        "reject_audit_complete": len(reject_rows) > 0 and len(reject_missing_veto_reasons) == 0,
        "no_buy_signal": not (plan_buy_hits or feature_buy_hits),
    }

    ok = not errors and all(contract.values())
    return {
        "trade_date": trade_date,
        "setup_type": setup_type,
        "setup_plan": {
            "total_rows": len(plan_rows),
            "summary_rows": len(summary_rows),
            "item_rows": len(item_rows),
            "summary_counts": summary_counts,
            "summary_counts_total": summary_counts_total,
            "decision_counts": dict(plan_item_decisions),
        },
        "candidate_feature": {
            "total_rows": len(feature_rows),
            "summary_rows": len(candidate_summary_rows),
            "reject_rows": len(reject_rows),
            "reject_missing_veto_reasons": len(reject_missing_veto_reasons),
            "decision_counts": dict(candidate_decisions),
            "missing_candidate_coverage": missing_candidate_coverage,
        },
        "contract": contract,
        "errors": errors,
        "ok": ok,
    }


async def _fetch_rows(conn: Any, sql: str, *params: Any) -> list[dict[str, Any]]:
    rows = await conn.fetch(sql, *params)
    return [dict(row) for row in rows]


async def run_audit(trade_date: date, dsn: str, setup_type: str = "one_to_two") -> dict[str, Any]:
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed. Please run with the project virtualenv.")
    if not dsn:
        raise RuntimeError("Missing DSN. Please set --dsn or POSTGRES_DSN/DATABASE_URL.")

    conn = await asyncpg.connect(dsn=dsn)
    try:
        plan_table = await _resolve_table_name(conn, "post_market_setup_plan")
        feature_table = await _resolve_table_name(conn, "one_to_two_candidate_feature")
        plan_rows = await _fetch_rows(
            conn,
            f"""
            SELECT *
            FROM {plan_table}
            WHERE trade_date = $1::date
              AND setup_type = $2::text
            ORDER BY CASE WHEN stock_id = '__SUMMARY__' THEN 0 ELSE 1 END,
                     COALESCE(final_score, -1) DESC,
                     stock_id ASC,
                     subject_key ASC
            """,
            trade_date,
            setup_type,
        )
        feature_rows = await _fetch_rows(
            conn,
            f"""
            SELECT *
            FROM {feature_table}
            WHERE trade_date = $1::date
              AND setup_type = $2::text
            ORDER BY COALESCE(final_score, -1) DESC,
                     stock_id ASC,
                     subject_key ASC
            """,
            trade_date,
            setup_type,
        )
    finally:
        await conn.close()

    return build_audit_report(plan_rows, feature_rows, trade_date=trade_date.isoformat(), setup_type=setup_type)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit OneToTwo setup plan persistence contract.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--setup-type", default="one_to_two", help="Setup type, default: one_to_two")
    parser.add_argument("--dsn", default="", help="Postgres DSN, default from POSTGRES_DSN/DATABASE_URL")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trade_date = _parse_trade_date(args.trade_date)
    dsn = _dsn_from_args_or_env(args.dsn)
    report = asyncio.run(run_audit(trade_date, dsn, setup_type=args.setup_type))

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
