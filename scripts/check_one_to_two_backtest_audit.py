#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from stock_processing_service.application.services.backtest.one_to_two_backtest_validation_summary_service import (
    OneToTwoBacktestValidationSummaryService,
)

try:
    import asyncpg
except Exception:  # pragma: no cover
    asyncpg = None


BUY_TOKENS = ("recommend_buy", "must_buy", "buy")
EXPECTED_SOURCE_TABLE = "w2s_backtest_feature_snapshot"
EXPECTED_SIGNAL_SESSION = "post_market"
EXPECTED_SIGNAL_DIRECTION = "long_watch"
EXPECTED_SIGNAL_AVAILABLE_TIME = time(15, 30)
EXPECTED_SIGNAL_TRADABLE_TIME = time(9, 30)


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


async def _require_backtest_schema_contract(conn: Any) -> None:
    if not await _table_has_column(conn, "w2s_backtest_feature_snapshot", "strategy_id"):
        raise RuntimeError("BACKTEST_SNAPSHOT_STRATEGY_ID_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "strategy_id"):
        raise RuntimeError("BACKTEST_SIGNAL_STRATEGY_ID_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "signal_session"):
        raise RuntimeError("BACKTEST_SIGNAL_SESSION_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "direction"):
        raise RuntimeError("BACKTEST_SIGNAL_DIRECTION_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "tradable"):
        raise RuntimeError("BACKTEST_SIGNAL_TRADABLE_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "available_at"):
        raise RuntimeError("BACKTEST_SIGNAL_AVAILABLE_AT_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "tradable_at"):
        raise RuntimeError("BACKTEST_SIGNAL_TRADABLE_AT_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "source_table"):
        raise RuntimeError("BACKTEST_SIGNAL_SOURCE_TABLE_MISSING")
    if not await _table_has_column(conn, "strategy_signal_daily", "source_snapshot_version"):
        raise RuntimeError("BACKTEST_SIGNAL_SOURCE_SNAPSHOT_VERSION_MISSING")
    if not await _table_has_column(conn, "strategy_signal_validation", "outcome_source"):
        raise RuntimeError("BACKTEST_VALIDATION_OUTCOME_SOURCE_MISSING")


async def _fetch_rows(conn: Any, sql: str, *params: Any) -> list[dict[str, Any]]:
    rows = await conn.fetch(sql, *params)
    return [dict(row) for row in rows]


def _row_has_buy_token(row: dict[str, Any]) -> bool:
    text = json.dumps(row, ensure_ascii=False, default=str).lower()
    return any(token in text for token in BUY_TOKENS)


class _AuditConnClient:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def execute_query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = await self._conn.fetch(sql, *params)
        return [dict(row) for row in rows]


class _AuditGateway:
    def __init__(self, conn: Any) -> None:
        self._client = _AuditConnClient(conn)


def _to_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _validate_exact_strategy_ids(rows: list[dict[str, Any]], strategy_id: str) -> tuple[bool, dict[str, int]]:
    counter = Counter(str(row.get("strategy_id") or "") for row in rows)
    return set(counter) == {strategy_id}, dict(counter)


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

    snapshot_strategy_ok, snapshot_strategy_ids = _validate_exact_strategy_ids(snapshot_rows, strategy_id)
    signal_strategy_ok, signal_strategy_ids = _validate_exact_strategy_ids(signal_rows, strategy_id)
    validation_strategy_ok, validation_strategy_ids = _validate_exact_strategy_ids(validation_rows, strategy_id)

    snapshot_source_tables = Counter(str(row.get("source_table") or "") for row in signal_rows)
    snapshot_buy_hits = [row for row in snapshot_rows if _row_has_buy_token(row)]
    signal_buy_hits = [row for row in signal_rows if _row_has_buy_token(row)]
    validation_buy_hits = [row for row in validation_rows if _row_has_buy_token(row)]
    summary_buy_hits = [row for row in summary_rows if _row_has_buy_token(row)]
    summary_strategy_ids = Counter(str(row.get("strategy_id") or "") for row in summary_rows if "strategy_id" in row)
    summary_strategy_versions = Counter(str(row.get("strategy_version") or "") for row in summary_rows if "strategy_version" in row)

    signal_ids = [str(row.get("signal_id") or "") for row in signal_rows]
    validation_ids = [str(row.get("signal_id") or "") for row in validation_rows]
    signal_id_set = {sid for sid in signal_ids if sid}
    validation_id_set = {sid for sid in validation_ids if sid}
    missing_validation_for_signal = sorted(signal_id_set - validation_id_set)
    orphan_validation_rows = sorted(validation_id_set - signal_id_set)
    duplicate_signal_ids = sorted(sid for sid, count in Counter(signal_ids).items() if sid and count > 1)
    duplicate_validation_ids = sorted(sid for sid, count in Counter(validation_ids).items() if sid and count > 1)

    signal_session_mismatches = [
        row for row in signal_rows if str(row.get("signal_session") or "") != EXPECTED_SIGNAL_SESSION
    ]
    direction_mismatches = [
        row for row in signal_rows if str(row.get("direction") or "") != EXPECTED_SIGNAL_DIRECTION
    ]
    tradable_true_forbidden = [row for row in signal_rows if bool(row.get("tradable")) is True]
    source_table_mismatches = [
        row for row in signal_rows if str(row.get("source_table") or "") != EXPECTED_SOURCE_TABLE
    ]
    available_at_invalid = []
    tradable_at_invalid = []
    for row in signal_rows:
        trade_date_text = str(row.get("trade_date") or "")
        trade_date = None
        if trade_date_text:
            try:
                trade_date = datetime.strptime(trade_date_text[:10], "%Y-%m-%d").date()
            except ValueError:
                trade_date = None
        available_at = _to_datetime(row.get("available_at"))
        tradable_at = _to_datetime(row.get("tradable_at"))
        if trade_date is None or available_at is None or tradable_at is None:
            available_at_invalid.append(row)
            tradable_at_invalid.append(row)
            continue
        expected_available = datetime.combine(trade_date, EXPECTED_SIGNAL_AVAILABLE_TIME)
        expected_tradable = datetime.combine(trade_date + timedelta(days=1), EXPECTED_SIGNAL_TRADABLE_TIME)
        if available_at != expected_available:
            available_at_invalid.append(row)
        if tradable_at != expected_tradable:
            tradable_at_invalid.append(row)

    outcome_label_missing = [row for row in validation_rows if not str(row.get("outcome_label") or "").strip()]
    outcome_source_missing = [row for row in validation_rows if not str(row.get("outcome_source") or "").strip()]

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
    if not snapshot_strategy_ok:
        errors.append(f"snapshot_strategy_ids={dict(snapshot_strategy_ids)}")
    if not signal_strategy_ok:
        errors.append(f"signal_strategy_ids={dict(signal_strategy_ids)}")
    if not validation_strategy_ok:
        errors.append(f"validation_strategy_ids={dict(validation_strategy_ids)}")
    if snapshot_source_tables and set(snapshot_source_tables) != {EXPECTED_SOURCE_TABLE}:
        errors.append(f"unexpected_signal_source_table={dict(snapshot_source_tables)}")
    if snapshot_buy_hits or signal_buy_hits or validation_buy_hits or summary_buy_hits:
        errors.append("buy_tokens_present")
    if missing_validation_for_signal:
        errors.append(f"validation_missing_for_signal={missing_validation_for_signal}")
    if orphan_validation_rows:
        errors.append(f"orphan_validation_rows={orphan_validation_rows}")
    if duplicate_signal_ids:
        errors.append(f"duplicate_signal_ids={duplicate_signal_ids}")
    if duplicate_validation_ids:
        errors.append(f"duplicate_validation_ids={duplicate_validation_ids}")
    if len(signal_rows) != len(validation_rows):
        errors.append(f"signal_validation_count_mismatch={len(signal_rows)}:{len(validation_rows)}")
    if signal_session_mismatches:
        errors.append("signal_session_mismatch")
    if direction_mismatches:
        errors.append("direction_mismatch")
    if tradable_true_forbidden:
        errors.append("tradable_true_forbidden")
    if available_at_invalid:
        errors.append("available_at_invalid")
    if tradable_at_invalid:
        errors.append("tradable_at_invalid")
    if outcome_label_missing:
        errors.append("outcome_label_missing")
    if outcome_source_missing:
        errors.append("outcome_source_missing")
    if summary_strategy_ids and any(key not in {"", strategy_id} for key in summary_strategy_ids):
        errors.append(f"summary_strategy_ids={dict(summary_strategy_ids)}")
    if summary_strategy_versions and expected_version and any(key not in {"", expected_version} for key in summary_strategy_versions):
        errors.append(f"summary_strategy_versions={dict(summary_strategy_versions)}")

    contract = {
        "run_present": run_row is not None,
        "run_strategy_match": run_strategy_id == strategy_id,
        "run_version_match": not expected_version or run_strategy_version == expected_version,
        "snapshot_strategy_match": snapshot_strategy_ok,
        "signal_strategy_match": signal_strategy_ok,
        "validation_strategy_match": validation_strategy_ok,
        "summary_present": bool(summary_rows),
        "no_buy_signal": not (snapshot_buy_hits or signal_buy_hits or validation_buy_hits or summary_buy_hits),
        "signal_session_post_market": not signal_session_mismatches,
        "direction_long_watch": not direction_mismatches,
        "tradable_false_only": not tradable_true_forbidden,
        "signal_source_table_consistent": not source_table_mismatches,
        "signal_validation_mapped": not (missing_validation_for_signal or orphan_validation_rows),
        "validation_outcome_present": not (outcome_label_missing or outcome_source_missing),
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
            "signal_session_mismatches": len(signal_session_mismatches),
            "direction_mismatches": len(direction_mismatches),
            "tradable_true_forbidden": len(tradable_true_forbidden),
            "available_at_invalid": len(available_at_invalid),
            "tradable_at_invalid": len(tradable_at_invalid),
        },
        "validation": {
            "total_rows": len(validation_rows),
            "strategy_id_counts": dict(validation_strategy_ids),
            "missing_validation_for_signal": len(missing_validation_for_signal),
            "orphan_validation_rows": len(orphan_validation_rows),
            "outcome_label_missing": len(outcome_label_missing),
            "outcome_source_missing": len(outcome_source_missing),
        },
        "summary": {
            "total_rows": len(summary_rows),
            "sample_count_total": sum(int(row.get("sample_count") or 0) for row in summary_rows),
            "strategy_id_counts": dict(summary_strategy_ids),
            "strategy_version_counts": dict(summary_strategy_versions),
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
    summary_report: dict[str, Any] = {}
    try:
        run_table = await _resolve_table_name(conn, "w2s_backtest_run")
        snapshot_table = await _resolve_table_name(conn, "w2s_backtest_feature_snapshot")
        signal_table = await _resolve_table_name(conn, "strategy_signal_daily")
        validation_table = await _resolve_table_name(conn, "strategy_signal_validation")
        await _require_backtest_schema_contract(conn)

        run_rows = await _fetch_rows(
            conn,
            f"SELECT * FROM {run_table} WHERE run_id = $1::text LIMIT 1",
            run_id,
        )
        snapshot_rows = await _fetch_rows(
            conn,
            f"SELECT * FROM {snapshot_table} WHERE run_id = $1::text AND strategy_id = $2::text",
            run_id,
            strategy_id,
        )
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
        summary_service = OneToTwoBacktestValidationSummaryService(gateway=_AuditGateway(conn))
        summary_report = await summary_service.build(
            run_id,
            strategy_id=strategy_id,
            strategy_version=(run_rows[0].get("strategy_version") if run_rows else None) or "one_to_two_v1.0_post_market_plan",
        )
        summary_rows = list(summary_report.get("summary_rows") or [])
    finally:
        await conn.close()

    report = build_backtest_audit_report(
        run_row=run_rows[0] if run_rows else None,
        snapshot_rows=snapshot_rows,
        signal_rows=signal_rows,
        validation_rows=validation_rows,
        summary_rows=summary_rows,
        strategy_id=strategy_id,
        strategy_version=(run_rows[0].get("strategy_version") if run_rows else None),
    )
    report["summary_report"] = summary_report
    return report


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
