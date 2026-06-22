#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import asyncpg

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.services.limit_up_theme_matrix_builder import (  # noqa: E402
    LimitUpThemeMatrixBuilder,
)


GOLDEN_DATES = ("2026-06-18", "2026-06-19", "2026-06-20")
DEFAULT_THRESHOLDS = {
    "other_count_max": 20,
    "ths_reason_covered_count_min": 80,
    "top_5_theme_coverage_min": 0.55,
    "single_theme_max_ratio_max": 0.35,
}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class _ReasonMaskedConn:
    """Connection proxy for before/after comparison.

    It keeps all market/mainline/static-subject reads intact and hides the new
    THS reason evidence tables to simulate pre-M2 attribution.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        q = " ".join(query.lower().split())
        if "from stock_theme_reason_evidence" in q or "from ths_hot_reason_snapshot" in q:
            return []
        return await self._conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Any:
        return await self._conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        return await self._conn.fetchval(query, *args)


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _stock_key(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return raw.split(".", 1)[0] if raw else ""


def _safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _column_stock_count(matrix: dict[str, Any], theme_name: str) -> int:
    total = 0
    for column in matrix.get("columns") or []:
        if str(column.get("theme_name") or "") != theme_name:
            continue
        for group in column.get("board_groups") or []:
            total += int(group.get("stock_count") or 0)
    return total


def _limitup_stock_keys(matrix: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for row in matrix.get("diagnostics", {}).get("assignment_audit_rows") or []:
        stock_key = _stock_key(row.get("stock_id"))
        if stock_key:
            result.add(stock_key)
    for row in matrix.get("diagnostics", {}).get("unmapped_stocks") or []:
        stock_key = _stock_key(row.get("stock_id") or row.get("stock_key"))
        if stock_key:
            result.add(stock_key)
    return result


def _theme_counts(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    counts: list[dict[str, Any]] = []
    for column in matrix.get("columns") or []:
        theme_name = str(column.get("theme_name") or "")
        if not theme_name:
            continue
        counts.append(
            {
                "theme_name": theme_name,
                "limitup_count": int(column.get("limit_up_count") or 0),
                "mapping_source": (column.get("diagnostics") or {}).get("mapping_source", ""),
            }
        )
    counts.sort(key=lambda item: (-int(item["limitup_count"]), str(item["theme_name"])))
    return counts


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    value = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
    return bool(value)


async def _fetch_ths_rows(
    conn: asyncpg.Connection,
    trade_date: date,
    stock_keys: set[str],
) -> list[dict[str, Any]]:
    if not stock_keys or not await _table_exists(conn, "ths_hot_reason_snapshot"):
        return []
    rows = await conn.fetch(
        """
        SELECT stock_code, reason_raw, reason_tags
        FROM ths_hot_reason_snapshot
        WHERE trade_date = $1::date
          AND stock_code = ANY($2::text[])
        """,
        trade_date,
        sorted(stock_keys),
    )
    return [dict(row) for row in rows]


async def _fetch_evidence_stock_count(
    conn: asyncpg.Connection,
    trade_date: date,
    stock_keys: set[str],
) -> int:
    if not stock_keys or not await _table_exists(conn, "stock_theme_reason_evidence"):
        return 0
    value = await conn.fetchval(
        """
        SELECT COUNT(DISTINCT stock_code)
        FROM stock_theme_reason_evidence
        WHERE trade_date = $1::date
          AND stock_code = ANY($2::text[])
        """,
        trade_date,
        sorted(stock_keys),
    )
    return int(value or 0)


def _top_reason_tags(ths_rows: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in ths_rows:
        for tag in _safe_list(row.get("reason_tags")):
            text = str(tag or "").strip()
            if text:
                counter[text] += 1
    return [{"tag": tag, "count": count} for tag, count in counter.most_common(limit)]


def _matrix_metrics(
    matrix: dict[str, Any],
    *,
    ths_rows: list[dict[str, Any]],
    evidence_stock_count: int,
) -> dict[str, Any]:
    diagnostics = matrix.get("diagnostics") or {}
    total = int(diagnostics.get("limit_up_stock_count") or 0)
    theme_counts = _theme_counts(matrix)
    real_theme_counts = [row for row in theme_counts if row["theme_name"] != "其他"]
    top5_count = sum(int(row["limitup_count"]) for row in real_theme_counts[:5])
    max_theme_count = max([int(row["limitup_count"]) for row in real_theme_counts] or [0])
    audit_rows = diagnostics.get("assignment_audit_rows") or []
    source_counter = Counter(str(row.get("chosen_reason") or "") for row in audit_rows)
    clustered_count = sum(
        1
        for row in audit_rows
        if str(row.get("chosen_reason") or "") in {"stock_theme_reason_evidence", "ths_hot_reason_snapshot"}
    )
    true_other_count = int(diagnostics.get("true_other_count") or diagnostics.get("unmapped_stock_count") or 0)
    display_other_count = int(diagnostics.get("display_other_count") or _column_stock_count(matrix, "其他"))
    collapsed_other_count = int(diagnostics.get("collapsed_other_count") or max(display_other_count - true_other_count, 0))
    return {
        "limitup_count": total,
        "theme_count": len(theme_counts),
        "other_count": true_other_count,
        "true_other_count": true_other_count,
        "display_other_count": display_other_count,
        "collapsed_other_count": collapsed_other_count,
        "collapsed_other_themes": diagnostics.get("collapsed_other_themes") or [],
        "unmapped_count": int(diagnostics.get("unmapped_stock_count") or 0),
        "ths_reason_covered_count": len({_stock_key(row.get("stock_code")) for row in ths_rows}),
        "evidence_stock_count": evidence_stock_count,
        "ths_reason_clustered_count": clustered_count,
        "top_5_theme_coverage": round(top5_count / total, 4) if total else 0.0,
        "single_theme_max_ratio": round(max_theme_count / total, 4) if total else 0.0,
        "source_breakdown": dict(sorted(source_counter.items())),
        "top_themes": theme_counts[:10],
        "top_reason_tags": _top_reason_tags(ths_rows),
    }


def _diff_metrics(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "other_count",
        "true_other_count",
        "display_other_count",
        "collapsed_other_count",
        "unmapped_count",
        "theme_count",
        "ths_reason_covered_count",
        "ths_reason_clustered_count",
        "top_5_theme_coverage",
        "single_theme_max_ratio",
    ]
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys}


def _gate(metrics: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if metrics["true_other_count"] > thresholds["other_count_max"]:
        failures.append("true_other_count_gt_max")
    if metrics["ths_reason_covered_count"] < thresholds["ths_reason_covered_count_min"]:
        failures.append("ths_reason_covered_count_lt_min")
    if metrics["top_5_theme_coverage"] < thresholds["top_5_theme_coverage_min"]:
        failures.append("top_5_theme_coverage_lt_min")
    if metrics["single_theme_max_ratio"] > thresholds["single_theme_max_ratio_max"]:
        failures.append("single_theme_max_ratio_gt_max")
    return {"passed": not failures, "failures": failures}


async def _validate_date(
    conn: asyncpg.Connection,
    trade_date: date,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    builder = LimitUpThemeMatrixBuilder()
    before = await builder.build(trade_date=trade_date, conn=_ReasonMaskedConn(conn))
    after = await builder.build(trade_date=trade_date, conn=conn)
    stock_keys = _limitup_stock_keys(after)
    ths_rows = await _fetch_ths_rows(conn, trade_date, stock_keys)
    evidence_stock_count = await _fetch_evidence_stock_count(conn, trade_date, stock_keys)
    before_metrics = _matrix_metrics(before, ths_rows=[], evidence_stock_count=0)
    after_metrics = _matrix_metrics(after, ths_rows=ths_rows, evidence_stock_count=evidence_stock_count)
    return {
        "trade_date": trade_date.isoformat(),
        "before": before_metrics,
        "after": after_metrics,
        "diff": _diff_metrics(before_metrics, after_metrics),
        "gate": _gate(after_metrics, thresholds),
    }


def _write_markdown(report: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Limit-Up Theme Matrix M2b Validation",
        "",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- database: `{report.get('database')}`",
        f"- all_passed: `{report.get('all_passed')}`",
        "",
        "| date | limitups | true other before -> after | display other | collapsed other | THS covered | THS clustered | top5 coverage | max theme ratio | gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report.get("dates") or []:
        before = row["before"]
        after = row["after"]
        gate = row["gate"]
        lines.append(
            "| {date} | {limitups} | {before_other} -> {after_other} | {display_other} | {collapsed_other} | {covered} | {clustered} | {top5:.2%} | {max_ratio:.2%} | {gate} |".format(
                date=row["trade_date"],
                limitups=after["limitup_count"],
                before_other=before["true_other_count"],
                after_other=after["true_other_count"],
                display_other=after["display_other_count"],
                collapsed_other=after["collapsed_other_count"],
                covered=after["ths_reason_covered_count"],
                clustered=after["ths_reason_clustered_count"],
                top5=after["top_5_theme_coverage"],
                max_ratio=after["single_theme_max_ratio"],
                gate="pass" if gate["passed"] else ",".join(gate["failures"]),
            )
        )
    lines.extend(["", "## Per-Date Top Themes", ""])
    for row in report.get("dates") or []:
        lines.extend([f"### {row['trade_date']}", ""])
        lines.append("| rank | theme | limitups | source |")
        lines.append("|---:|---|---:|---|")
        for idx, item in enumerate(row["after"].get("top_themes") or [], start=1):
            lines.append(f"| {idx} | {item['theme_name']} | {item['limitup_count']} | {item.get('mapping_source','')} |")
        lines.extend(["", "Top reason tags:"])
        for tag in row["after"].get("top_reason_tags") or []:
            lines.append(f"- {tag['tag']}: {tag['count']}")
        if not row["after"].get("top_reason_tags"):
            lines.append("- none")
        collapsed_themes = row["after"].get("collapsed_other_themes") or []
        if collapsed_themes:
            lines.extend(["", "Collapsed other themes:"])
            for item in collapsed_themes[:20]:
                lines.append(f"- {item['theme_name']}: {item['limit_up_count']} ({item.get('mapping_source','')})")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


async def _run(args: argparse.Namespace) -> int:
    dsn = args.dsn or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required, or pass --dsn")
    conn = await asyncpg.connect(dsn)
    try:
        database = await conn.fetchval("SELECT current_database()")
        thresholds = dict(DEFAULT_THRESHOLDS)
        if args.allow_partial_data:
            thresholds["ths_reason_covered_count_min"] = 0
        rows = [
            await _validate_date(conn, date.fromisoformat(item), thresholds)
            for item in args.dates
        ]
        report = {
            "generated_at": date.today().isoformat(),
            "database": database,
            "dates": rows,
            "thresholds": thresholds,
            "all_passed": all(row["gate"]["passed"] for row in rows),
        }
    finally:
        await conn.close()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    markdown = output.with_suffix(".md")
    _write_markdown(report, markdown)
    print(json.dumps({"ok": True, "output": str(output), "markdown": str(markdown), "all_passed": report["all_passed"]}, ensure_ascii=False))
    return 0 if report["all_passed"] or args.allow_fail else 2


def _parse_args() -> argparse.Namespace:
    _load_env_file(Path.cwd() / ".env.theme")
    parser = argparse.ArgumentParser(description="Run M2b validation for limit-up theme matrix reason evidence.")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dates", nargs="+", default=list(GOLDEN_DATES))
    parser.add_argument("--output", default="reports/golden/limit_up_theme_matrix_m2b/validation.json")
    parser.add_argument("--allow-partial-data", action="store_true", help="Do not fail when THS data is unavailable.")
    parser.add_argument("--allow-fail", action="store_true", help="Always exit 0 after writing the report.")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
