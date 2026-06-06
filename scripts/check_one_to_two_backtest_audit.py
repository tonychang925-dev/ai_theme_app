#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import asyncpg
except Exception:  # pragma: no cover
    asyncpg = None


BUY_TOKENS = ("recommend_buy", "must_buy", "buy")
EXPECTED_SOURCE_TABLE = "w2s_backtest_feature_snapshot"


def _dsn_from_args_or_env(dsn: str | None) -> str:
    if dsn:
        return dsn
    return os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL") or ""


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
    return f"{_safe_schema_name(str(rows[0]['table_schema']))}.{table_name}"


async def _table_has_column(conn: Any, table_name: str, column_name: str) -> bool:
    rows = await conn.fetch(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = $1 AND column_name = $2
        LIMIT 1
        """,
        table_name,
        column_name,
    )
    return bool(rows)


async def _fetch_rows(conn: Any, sql: str, *params: Any) -> list[dict[str, Any]]:
    rows = await conn.fetch(sql, *params)
    return [dict(row) for row in rows]


def _row_has_buy_token(row: dict[str, Any]) -> bool:
    text = json.dumps(row, ensure_ascii=False, default=str).lower()
    return any(token in text for token in BUY_TOKENS)


def build_backtest_audit_report(
    *,
    run_row: dict[str, Any] | None,
    snapshot_rows: list[dict[str, Any]],
    signal_rows: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    strategy_id: str,
    strategy_version: str | None = None,
) -> dict[str, Any]:
    run_strategy_id = str((run_row or {}).get("strategy_id") or "")
    run_strategy_version = str((run_row or {}).get("strategy_version") or "")
    expected_version = str(strategy_version or run_strategy_version or "")

    snapshot_strategy_ids = Counter(str(row.get("strategy_id") or "") for row in snapshot_rows)
    signal_strategy_ids = Counter(str(row.get("strategy_id") or "") for row in signal_rows)
    validation_strategy_ids = Counter(str(row.get("strategy_id") or "") for row in validation_rows)

    snapshot_source_tables = Counter(str(row.get("source_table") or "") for row in signal_rows)
    snapshot_buy_hits = [row for row in snapshot_rows if _row_has_buy_token(row)]
    signal_buy_hits = [row for row in signal_rows if _row_has_buy_token(row)]
    validation_buy_hits = [row for row in validation_rows if _row_has_buy_token(row)]
    summary_buy_hits = [row for row in summary_rows if _row_has_buy_token(row)]

    errors: list[str] = []
    if run_row is None:
        errors.append("missing_run_row")
    if run_strategy_id != strategy_id:
        errors.append(f"run_strategy_id_mismatch={run_strategy_id or '<empty>'}")
    if expected_version and run_strategy_version and run_strategy_version != expected_version:
        errors.append(f"run_strategy_version_mismatch={run_strategy_version}")
    if not snapshot_rows:
        errors.append("missing_snapshot_rows")
    if not signal_rows:
        errors.append("missing_signal_rows")
    if not validation_rows:
        errors.append("missing_validation_rows")
    if not summary_rows:
        errors.append("missing_summary_rows")
    if any(key not in {"", strategy_id} for key in snapshot_strategy_ids):
        errors.append(f"snapshot_strategy_ids={dict(snapshot_strategy_ids)}")
    if any(key not in {"", strategy_id} for key in signal_strategy_ids):
        errors.append(f"signal_strategy_ids={dict(signal_strategy_ids)}")
    if any(key not in {"", strategy_id} for key in validation_strategy_ids):
        errors.append(f"validation_strategy_ids={dict(validation_strategy_ids)}")
    if snapshot_source_tables and set(snapshot_source_tables) - {EXPECTED_SOURCE_TABLE, ""}:
        errors.append(f"unexpected_signal_source_table={dict(snapshot_source_tables)}")
    if snapshot_buy_hits or signal_buy_hits or validation_buy_hits or summary_buy_hits:
        errors.append("buy_tokens_present")

    contract = {
        "run_present": run_row is not None,
        "run_strategy_match": run_strategy_id == strategy_id,
        "run_version_match": not expected_version or run_strategy_version == expected_version,
        "snapshot_strategy_match": not any(key not in {"", strategy_id} for key in snapshot_strategy_ids),
        "signal_strategy_match": not any(key not in {"", strategy_id} for key in signal_strategy_ids),
        "validation_strategy_match": not any(key not in {"", strategy_id} for key in validation_strategy_ids),
        "summary_present": bool(summary_rows),
        "no_buy_signal": not (snapshot_buy_hits or signal_buy_hits or validation_buy_hits or summary_buy_hits),
    }

    return {
        "run_id": (run_row or {}).get("run_id"),
        "strategy_id": strategy_id,
        "strategy_version": expected_version or None,
        "snapshot": {
            "total_rows": len(snapshot_rows),
            "strategy_id_counts": dict(snapshot_strategy_ids),
        },
        "signal": {
            "total_rows": len(signal_rows),
            "strategy_id_counts": dict(signal_strategy_ids),
            "source_table_counts": dict(snapshot_source_tables),
        },
        "validation": {
            "total_rows": len(validation_rows),
            "strategy_id_counts": dict(validation_strategy_ids),
        },
        "summary": {
            "total_rows": len(summary_rows),
            "sample_count_total": sum(int(row.get("sample_count") or 0) for row in summary_rows),
        },
        "contract": contract,
        "errors": errors,
        "ok": not errors and all(contract.values()),
    }


async def run_audit(run_id: str, dsn: str, strategy_id: str = "one_to_two") -> dict[str, Any]:
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed. Please run with the project virtualenv.")
    if not dsn:
        raise RuntimeError("Missing DSN. Please set --dsn or POSTGRES_DSN/DATABASE_URL.")

    conn = await asyncpg.connect(dsn=dsn)
    try:
        run_table = await _resolve_table_name(conn, "w2s_backtest_run")
        snapshot_table = await _resolve_table_name(conn, "w2s_backtest_feature_snapshot")
        signal_table = await _resolve_table_name(conn, "strategy_signal_daily")
        validation_table = await _resolve_table_name(conn, "strategy_signal_validation")
        summary_table = await _resolve_table_name(conn, "w2s_validation_summary")

        run_rows = await _fetch_rows(
            conn,
            f"SELECT * FROM {run_table} WHERE run_id = $1::text LIMIT 1",
            run_id,
        )
        has_snapshot_strategy_id = await _table_has_column(conn, "w2s_backtest_feature_snapshot", "strategy_id")
        snapshot_sql = f"SELECT * FROM {snapshot_table} WHERE run_id = $1::text"
        snapshot_params: list[Any] = [run_id]
        if has_snapshot_strategy_id:
            snapshot_sql += " AND strategy_id = $2::text"
            snapshot_params.append(strategy_id)

        snapshot_rows = await _fetch_rows(conn, snapshot_sql, *snapshot_params)
        signal_rows = await _fetch_rows(
            conn,
            f"SELECT * FROM {signal_table} WHERE run_id = $1::text AND strategy_id = $2::text",
            run_id,
            strategy_id,
        )
        validation_rows = await _fetch_rows(
            conn,
            f"SELECT * FROM {validation_table} WHERE run_id = $1::text AND strategy_id = $2::text",
            run_id,
            strategy_id,
        )
        summary_rows = await _fetch_rows(
            conn,
            f"SELECT * FROM {summary_table} WHERE run_id = $1::text",
            run_id,
        )
    finally:
        await conn.close()

    return build_backtest_audit_report(
        run_row=run_rows[0] if run_rows else None,
        snapshot_rows=snapshot_rows,
        signal_rows=signal_rows,
        validation_rows=validation_rows,
        summary_rows=summary_rows,
        strategy_id=strategy_id,
        strategy_version=(run_rows[0].get("strategy_version") if run_rows else None),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit OneToTwo unified backtest run.")
    parser.add_argument("--run-id", required=True, help="Backtest run id")
    parser.add_argument("--strategy-id", default="one_to_two", help="Strategy id, default: one_to_two")
    parser.add_argument("--dsn", default="", help="Postgres DSN, default from POSTGRES_DSN/DATABASE_URL")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dsn = _dsn_from_args_or_env(args.dsn)
    report = asyncio.run(run_audit(args.run_id, dsn, strategy_id=args.strategy_id))

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
