from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REQUIRED_MODULES = (
    "theme_reviews",
    "theme_capital_reviews",
    "strong_stock_reviews",
    "watchlist_reviews",
    "stock_capital_reviews",
    "abnormal_reviews",
    "money_flow_reviews",
)

EMPTY_ALLOWED_MODULES = ("dragon_tiger_reviews",)
ALL_MODULES = (*REQUIRED_MODULES, *EMPTY_ALLOWED_MODULES)
MODULE_SECTION_HEADINGS = {
    "theme_reviews": "主线与支线",
    "theme_capital_reviews": "主线资金流入前10",
    "strong_stock_reviews": "强势股分层",
    "watchlist_reviews": "次日观察清单",
    "stock_capital_reviews": "主线股票资金流入前20",
    "abnormal_reviews": "当日异动股与资金行为",
    "money_flow_reviews": "资金行为增强",
    "dragon_tiger_reviews": "龙虎榜",
}
P5_GATE_SECTION_MODULES = tuple(REQUIRED_MODULES)

ROW_COUNT_EXPECTATIONS = {
    "stock_capital_reviews": 20,
    "abnormal_reviews": 30,
    "money_flow_reviews": 20,
}


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return payload


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8")
    result = json.loads(text)
    if not isinstance(result, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return result


def _preview_keys(value: Any, limit: int = 3) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    result: list[list[str]] = []
    for row in value[:limit]:
        result.append(sorted(row.keys()) if isinstance(row, dict) else [type(row).__name__])
    return result


def _module_line(module: str, coverage: dict[str, Any]) -> str:
    status = coverage.get("status")
    source = coverage.get("source")
    row_count = coverage.get("row_count")
    legacy_count = coverage.get("legacy_row_count", 0)
    missing = coverage.get("missing_fields") or []
    return (
        f"{module}: {status} / {source} / rows={row_count} / "
        f"legacy={legacy_count} / missing_fields={missing}"
    )


def _coverage_record(trade_date: str, module: str, coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": trade_date,
        "module": module,
        "status": coverage.get("status"),
        "source": coverage.get("source"),
        "rows": int(coverage.get("row_count") or 0),
        "legacy": int(coverage.get("legacy_row_count") or 0),
        "missing": coverage.get("missing_fields") or [],
        "message": coverage.get("message") or "",
    }


def _snapshot_recap_doc(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = snapshot.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    recap_doc = payload.get("recap_doc") or payload
    return recap_doc if isinstance(recap_doc, dict) else {}


def _section_counts(recap_doc: dict[str, Any]) -> dict[str, int]:
    counts = {heading: 0 for heading in MODULE_SECTION_HEADINGS.values()}
    report = recap_doc.get("report")
    sections = report.get("sections") if isinstance(report, dict) else []
    if not isinstance(sections, list):
        return counts
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or section.get("title") or "")
        items = section.get("items")
        if heading in counts and isinstance(items, list):
            counts[heading] = len(items)
    return counts


def _sample_class(snapshot: dict[str, Any], payload: dict[str, Any] | None, fetch_error: str | None = None) -> dict[str, Any]:
    if fetch_error:
        return {
            "sample_class": "failed_precondition",
            "p5_gate": False,
            "reason": fetch_error,
        }
    recap_doc = _snapshot_recap_doc(snapshot)
    if not recap_doc:
        return {
            "sample_class": "failed_precondition",
            "p5_gate": False,
            "reason": "post_market_recap_snapshot_missing",
        }

    diagnostics = recap_doc.get("diagnostics")
    readiness = diagnostics.get("readiness") if isinstance(diagnostics, dict) else None
    readiness = readiness if isinstance(readiness, dict) else {}
    readiness_status = str(readiness.get("status") or "").lower()
    if readiness_status in {"failed", "failed_precondition"}:
        return {
            "sample_class": "failed_precondition",
            "p5_gate": False,
            "reason": f"readiness.status={readiness_status}",
        }

    counts = _section_counts(recap_doc)
    missing_sections = [
        heading for module, heading in MODULE_SECTION_HEADINGS.items()
        if module in P5_GATE_SECTION_MODULES and counts.get(heading, 0) <= 0
    ]
    snapshot_version = str(recap_doc.get("snapshot_version") or snapshot.get("snapshot_version") or "")
    if missing_sections:
        return {
            "sample_class": "legacy_snapshot",
            "p5_gate": False,
            "reason": f"missing_core_sections={missing_sections}",
        }
    if "replay_" in snapshot_version or readiness_status != "ready":
        return {
            "sample_class": "compatibility_observation",
            "p5_gate": False,
            "reason": f"snapshot_version={snapshot_version or '<unknown>'}, readiness.status={readiness_status or '<unknown>'}",
        }
    if payload is None or payload.get("schema_version") != "daily_review_v2":
        return {
            "sample_class": "failed_precondition",
            "p5_gate": False,
            "reason": "daily_review_v2_unavailable",
        }
    return {
        "sample_class": "p5_gate_candidate",
        "p5_gate": True,
        "reason": "ready snapshot with complete core sections",
    }


def _dragon_tiger_empty_allowed(payload: dict[str, Any], coverage: dict[str, Any]) -> bool:
    legacy_count = int(coverage.get("legacy_row_count") or 0)
    if legacy_count == 0:
        return True
    diagnostics = payload.get("diagnostics")
    warnings = diagnostics.get("warnings") if isinstance(diagnostics, dict) else []
    source = payload.get("source")
    source_status = source.get("derived_data_status") if isinstance(source, dict) else ""
    text = json.dumps(
        {
            "warnings": warnings,
            "source_status": source_status,
            "coverage_message": coverage.get("message"),
        },
        ensure_ascii=False,
    )
    return "no_dragon_tiger_day" in text


def _dragon_tiger_legacy_allowed(coverage: dict[str, Any]) -> bool:
    return (
        coverage.get("status") == "empty"
        and coverage.get("source") == "legacy_sections"
        and int(coverage.get("legacy_row_count") or 0) > 0
    )


def _row_count_errors(module: str, coverage: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    row_count = int(coverage.get("row_count") or 0)
    legacy_count = int(coverage.get("legacy_row_count") or 0)
    if module in ROW_COUNT_EXPECTATIONS:
        expected = ROW_COUNT_EXPECTATIONS[module]
        if legacy_count > 0:
            floor = max(1, min(expected, legacy_count) // 2)
            if row_count < floor:
                errors.append(f"{module}: row_count {row_count} is too low for legacy_count={legacy_count}")
        elif row_count == 0:
            errors.append(f"{module}: row_count expected > 0")
    if module == "theme_reviews" and legacy_count > 0:
        floor = max(1, legacy_count // 2)
        if row_count < floor:
            errors.append(f"{module}: row_count {row_count} is below 50% of legacy_count={legacy_count}")
    if module == "theme_capital_reviews" and legacy_count > 0:
        floor = max(1, legacy_count // 2)
        if row_count < floor:
            errors.append(f"{module}: row_count {row_count} is below 50% of legacy_count={legacy_count}")
    if module == "watchlist_reviews" and legacy_count > 0:
        floor = max(1, legacy_count // 2)
        if row_count < floor:
            errors.append(f"{module}: row_count {row_count} is below 50% of legacy_count={legacy_count}")
    if module == "dragon_tiger_reviews" and coverage.get("status") == "ready":
        if legacy_count > 0 and row_count != legacy_count:
            errors.append(f"{module}: ready row_count {row_count} must match legacy_count={legacy_count}")
    return errors


def validate(payload: dict[str, Any], *, quiet: bool = False) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    p5_blockers: list[str] = []
    trade_date = str(payload.get("trade_date") or "")
    if payload.get("schema_version") != "daily_review_v2":
        errors.append(f"schema_version expected daily_review_v2, got {payload.get('schema_version')!r}")
    if payload.get("data_mode") != "daily_review_v2_first":
        errors.append(f"data_mode expected daily_review_v2_first, got {payload.get('data_mode')!r}")

    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return records, [*errors, "diagnostics missing or not an object"], p5_blockers
    module_coverage = diagnostics.get("module_coverage")
    if not isinstance(module_coverage, dict):
        return records, [*errors, "diagnostics.module_coverage missing or not an object"], p5_blockers

    for module in ALL_MODULES:
        coverage = module_coverage.get(module)
        if not isinstance(coverage, dict):
            errors.append(f"{module}: coverage missing")
            continue

        records.append(_coverage_record(trade_date, module, coverage))
        if not quiet:
            print(_module_line(module, coverage))
        status = coverage.get("status")
        source = coverage.get("source")
        missing = coverage.get("missing_fields") or []

        if module in REQUIRED_MODULES:
            if status != "ready" or source != "structured" or missing:
                errors.append(
                    f"{module}: expected ready/structured with no missing fields; "
                    f"got status={status!r}, source={source!r}, missing_fields={missing!r}"
                )
            else:
                errors.extend(_row_count_errors(module, coverage))
            continue

        if module == "dragon_tiger_reviews":
            if status == "ready" and source == "structured" and not missing:
                errors.extend(_row_count_errors(module, coverage))
                continue
            if _dragon_tiger_legacy_allowed(coverage):
                p5_blockers.append("dragon_tiger_reviews: structured unavailable; fallback to legacy section")
                continue
            if status == "empty" and _dragon_tiger_empty_allowed(payload, coverage):
                continue
            if status == "empty":
                errors.append(
                    "dragon_tiger_reviews: empty is allowed only when no_dragon_tiger_day is explicit "
                    "or legacy_row_count is 0"
                )
            else:
                errors.append(
                    f"dragon_tiger_reviews: expected ready/structured or allowed empty; "
                    f"got status={status!r}, source={source!r}, missing_fields={missing!r}"
                )

    return records, errors, p5_blockers


def debug_dragon_tiger(snapshot: dict[str, Any], v2_payload: dict[str, Any]) -> None:
    recap_doc = _snapshot_recap_doc(snapshot)
    report_context = recap_doc.get("report_context")
    report_context = report_context if isinstance(report_context, dict) else {}
    source_rows = None
    source_key = ""
    for key, value in (
        ("recap_doc.dragon_tiger_reviews", recap_doc.get("dragon_tiger_reviews")),
        ("recap_doc.report_context.dragon_tiger", report_context.get("dragon_tiger")),
        ("recap_doc.report_context.dragon_tiger_object", report_context.get("dragon_tiger_object")),
        ("recap_doc.dragon_tiger_object", recap_doc.get("dragon_tiger_object")),
        ("recap_doc.capital_reviews", recap_doc.get("capital_reviews")),
    ):
        if isinstance(value, list):
            source_key = key
            source_rows = value
            break

    legacy_count = 0
    report = recap_doc.get("report")
    sections = report.get("sections") if isinstance(report, dict) else []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("heading") or section.get("title") or "") == "龙虎榜":
                items = section.get("items")
                legacy_count = len(items) if isinstance(items, list) else 0
                break

    v2_rows = v2_payload.get("dragon_tiger_reviews")
    normalized_sources = []
    if isinstance(v2_rows, list):
        for row in v2_rows[:3]:
            diagnostics = row.get("diagnostics") if isinstance(row, dict) else None
            normalized_sources.append(diagnostics.get("source") if isinstance(diagnostics, dict) else None)

    print("\nDEBUG dragon_tiger_reviews:")
    print(f"recap_doc keys: {sorted(recap_doc.keys())}")
    print(f"report_context keys: {sorted(report_context.keys())}")
    print(f"dragon_tiger source_key: {source_key or '<none>'}")
    print(f"source_rows.length: {len(source_rows) if isinstance(source_rows, list) else 0}")
    print(f"raw source keys preview: {_preview_keys(source_rows)}")
    print(f"normalized diagnostics.source preview: {normalized_sources}")
    print(f"legacy_sections[`龙虎榜`] count: {legacy_count}")


def _debug_module_source(snapshot: dict[str, Any], v2_payload: dict[str, Any], module: str) -> None:
    if module == "dragon_tiger_reviews":
        debug_dragon_tiger(snapshot, v2_payload)
        return

    recap_doc = _snapshot_recap_doc(snapshot)
    report_context = recap_doc.get("report_context")
    report_context = report_context if isinstance(report_context, dict) else {}
    source_candidates: dict[str, tuple[tuple[str, Any], ...]] = {
        "strong_stock_reviews": (
            ("recap_doc.strong_stock_reviews", recap_doc.get("strong_stock_reviews")),
            ("recap_doc.report_context.strong_stock_reviews", report_context.get("strong_stock_reviews")),
            ("recap_doc.report_context.strong_stock_watch_history", report_context.get("strong_stock_watch_history")),
            ("recap_doc.strong_watch_history", recap_doc.get("strong_watch_history")),
        ),
        "watchlist_reviews": (
            ("recap_doc.watchlist_reviews", recap_doc.get("watchlist_reviews")),
            ("recap_doc.next_day_watchlist", recap_doc.get("next_day_watchlist")),
            ("recap_doc.watchlist", recap_doc.get("watchlist")),
            ("recap_doc.tomorrow_watchlist", recap_doc.get("tomorrow_watchlist")),
            ("recap_doc.post_market_watchlist", recap_doc.get("post_market_watchlist")),
            ("recap_doc.observe_candidates", recap_doc.get("observe_candidates")),
            ("recap_doc.report_context.watchlist", report_context.get("watchlist")),
            ("recap_doc.report_context.observe_candidates", report_context.get("observe_candidates")),
            ("recap_doc.report_context.strong_stock_watch", report_context.get("strong_stock_watch")),
            ("recap_doc.strong_stock_reviews", recap_doc.get("strong_stock_reviews")),
        ),
    }
    source_key = ""
    source_rows = None
    for key, value in source_candidates.get(module, ()):
        if isinstance(value, list):
            if value:
                source_key = key
                source_rows = value
                break
            if source_rows is None:
                source_key = key
                source_rows = value

    heading = MODULE_SECTION_HEADINGS.get(module, "")
    legacy_count = _section_counts(recap_doc).get(heading, 0)
    v2_rows = v2_payload.get(module)
    normalized_sources = []
    if isinstance(v2_rows, list):
        for row in v2_rows[:3]:
            diagnostics = row.get("diagnostics") if isinstance(row, dict) else None
            normalized_sources.append(diagnostics.get("source") if isinstance(diagnostics, dict) else None)
    coverage = {}
    diagnostics = v2_payload.get("diagnostics")
    if isinstance(diagnostics, dict):
        module_coverage = diagnostics.get("module_coverage")
        if isinstance(module_coverage, dict):
            coverage = module_coverage.get(module) or {}

    print(f"\nDEBUG {module}:")
    print(f"recap_doc keys: {sorted(recap_doc.keys())}")
    print(f"report_context keys: {sorted(report_context.keys())}")
    print(f"{module} source_key: {source_key or '<none>'}")
    print(f"source_rows.length: {len(source_rows) if isinstance(source_rows, list) else 0}")
    print(f"raw source keys preview: {_preview_keys(source_rows)}")
    print(f"normalized diagnostics.source preview: {normalized_sources}")
    print(f"coverage.missing_fields: {coverage.get('missing_fields') or []}")
    print(f"legacy_sections[`{heading}`] count: {legacy_count}")


def _parse_dates(args: argparse.Namespace) -> list[str]:
    dates: list[str] = []
    if args.date:
        dates.append(args.date)
    if args.dates:
        dates.extend(part.strip() for part in args.dates.split(",") if part.strip())
    if args.dates_file:
        with open(args.dates_file, encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if text and not text.startswith("#"):
                    dates.append(text)
    seen: set[str] = set()
    result: list[str] = []
    for item in dates:
        if item not in seen:
            seen.add(item)
            result.append(item)
    if not result:
        raise ValueError("one of --date, --dates, or --dates-file is required")
    return result


def _print_records(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    print(
        f"{'date':<12} {'class':<27} {'p5':<3} {'module':<28} {'status':<9} {'source':<16} "
        f"{'rows':>5} {'legacy':>6} missing_fields"
    )
    for record in records:
        missing = json.dumps(record["missing"], ensure_ascii=False)
        print(
            f"{record['date']:<12} {str(record.get('sample_class', '')):<27} "
            f"{'yes' if record.get('p5_gate') else 'no':<3} "
            f"{record['module']:<28} {str(record['status']):<9} "
            f"{str(record['source']):<16} {record['rows']:>5} {record['legacy']:>6} {missing}"
        )


def _check_one_date(
    *,
    trade_date: str,
    base_url: str,
    generate_first: bool,
    debug_module: str | None,
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
    snapshot_url = f"{base_url}/api/v1/post_market_snapshot?{urlencode({'trade_date': trade_date})}"
    snapshot = _fetch_json(snapshot_url)
    if generate_first:
        generate_url = f"{base_url}/api/v2/post-market/daily-review-v2/generate"
        _post_json(generate_url, {"trade_date": trade_date, "force": True})

    url = f"{base_url}/api/v2/daily-review-v2?{urlencode({'date': trade_date})}"
    payload = _fetch_json(url)
    sample = _sample_class(snapshot, payload)
    if debug_module:
        try:
            _debug_module_source(snapshot, payload, debug_module)
        except Exception as exc:  # noqa: BLE001 - debug mode should not hide coverage validation.
            print(f"failed to fetch debug snapshot for {trade_date}: {exc}", file=sys.stderr)
    records, errors, blockers = validate(payload, quiet=True)
    for record in records:
        record["sample_class"] = sample["sample_class"]
        record["p5_gate"] = sample["p5_gate"]
        record["sample_reason"] = sample["reason"]
    if not sample["p5_gate"]:
        return records, [], [], sample
    return records, errors, blockers, sample


def main() -> int:
    parser = argparse.ArgumentParser(description="Check DailyReview V2 module coverage for a trade date.")
    parser.add_argument("--date", help="Trade date in YYYY-MM-DD format.")
    parser.add_argument("--dates", help="Comma-separated trade dates in YYYY-MM-DD format.")
    parser.add_argument("--dates-file", help="File containing one trade date per line.")
    parser.add_argument("--api", default="http://127.0.0.1:8090", help="API base URL.")
    parser.add_argument("--generate-first", action="store_true", help="POST generate before checking each date.")
    parser.add_argument(
        "--debug-module",
        choices=["dragon_tiger_reviews", "strong_stock_reviews", "watchlist_reviews"],
        help="Print raw source audit for a module.",
    )
    args = parser.parse_args()

    base_url = args.api.rstrip("/")
    try:
        dates = _parse_dates(args)
    except Exception as exc:  # noqa: BLE001 - CLI should print concrete input failure.
        print(f"invalid date arguments: {exc}", file=sys.stderr)
        return 2

    print(f"DailyReview V2 coverage check: dates={','.join(dates)} api={base_url}")
    all_records: list[dict[str, Any]] = []
    failed: dict[str, list[str]] = {}
    p5_blocked: dict[str, list[str]] = {}
    observed: dict[str, str] = {}
    for trade_date in dates:
        try:
            records, errors, blockers, sample = _check_one_date(
                trade_date=trade_date,
                base_url=base_url,
                generate_first=args.generate_first,
                debug_module=args.debug_module,
            )
        except Exception as exc:  # noqa: BLE001 - CLI should continue through multi-date smoke.
            records, errors, blockers = [], [f"fetch_or_generate_failed: {exc}"], []
            sample = {
                "sample_class": "failed_precondition",
                "p5_gate": False,
                "reason": str(exc),
            }
        all_records.extend(records)
        if not sample["p5_gate"]:
            observed[trade_date] = f"{sample['sample_class']}: {sample['reason']}"
            continue
        if errors:
            failed[trade_date] = errors
        if blockers:
            p5_blocked[trade_date] = blockers

    _print_records(all_records)
    pass_dates = [
        trade_date for trade_date in dates
        if trade_date not in failed and trade_date not in p5_blocked and trade_date not in observed
    ]
    failed_dates = sorted(failed)
    p5_blocked_dates = sorted(p5_blocked)
    observe_dates = sorted(observed)

    print("\nSUMMARY:")
    print(f"p5_pass_dates: {pass_dates}")
    print(f"p5_failed_dates: {failed_dates}")
    print(f"p5_blocked_dates: {p5_blocked_dates}")
    print(f"observe_dates: {observe_dates}")
    if failed:
        print("\nFAILED MODULES:")
        for trade_date, errors in failed.items():
            for error in errors:
                print(f"- {trade_date}: {error}")
    if p5_blocked:
        print("\nP5 BLOCKERS:")
        for trade_date, blockers in p5_blocked.items():
            for blocker in blockers:
                print(f"- {trade_date}: {blocker}")
    if observed:
        print("\nOBSERVE DATES:")
        for trade_date, reason in observed.items():
            print(f"- {trade_date}: {reason}")

    if failed or p5_blocked:
        return 1
    print("\nPASSED: DailyReview V2 coverage is ready for required modules across all dates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
