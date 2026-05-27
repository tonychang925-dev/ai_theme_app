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


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return payload


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


def validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "daily_review_v2":
        errors.append(f"schema_version expected daily_review_v2, got {payload.get('schema_version')!r}")
    if payload.get("data_mode") != "daily_review_v2_first":
        errors.append(f"data_mode expected daily_review_v2_first, got {payload.get('data_mode')!r}")

    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return [*errors, "diagnostics missing or not an object"]
    module_coverage = diagnostics.get("module_coverage")
    if not isinstance(module_coverage, dict):
        return [*errors, "diagnostics.module_coverage missing or not an object"]

    for module in ALL_MODULES:
        coverage = module_coverage.get(module)
        if not isinstance(coverage, dict):
            errors.append(f"{module}: coverage missing")
            continue

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
            continue

        if module == "dragon_tiger_reviews":
            if status == "ready" and source == "structured" and not missing:
                continue
            if _dragon_tiger_legacy_allowed(coverage):
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

    return errors


def debug_dragon_tiger(snapshot: dict[str, Any], v2_payload: dict[str, Any]) -> None:
    payload = snapshot.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    recap_doc = payload.get("recap_doc") or payload
    recap_doc = recap_doc if isinstance(recap_doc, dict) else {}
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check DailyReview V2 module coverage for a trade date.")
    parser.add_argument("--date", required=True, help="Trade date in YYYY-MM-DD format.")
    parser.add_argument("--api", default="http://127.0.0.1:8090", help="API base URL.")
    parser.add_argument("--debug-module", choices=["dragon_tiger_reviews"], help="Print raw source audit for a module.")
    args = parser.parse_args()

    base_url = args.api.rstrip("/")
    url = f"{base_url}/api/v2/daily-review-v2?{urlencode({'date': args.date})}"
    try:
        payload = _fetch_json(url)
    except Exception as exc:  # noqa: BLE001 - CLI should print the concrete fetch failure.
        print(f"failed to fetch DailyReview V2: {exc}", file=sys.stderr)
        return 2

    print(f"DailyReview V2 coverage check: date={args.date} api={base_url}")
    if args.debug_module == "dragon_tiger_reviews":
        snapshot_url = f"{base_url}/api/v1/post_market_snapshot?{urlencode({'trade_date': args.date})}"
        try:
            snapshot = _fetch_json(snapshot_url)
            debug_dragon_tiger(snapshot, payload)
        except Exception as exc:  # noqa: BLE001 - debug mode should not hide coverage validation.
            print(f"failed to fetch debug snapshot: {exc}", file=sys.stderr)
    errors = validate(payload)
    if errors:
        print("\nFAILED:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nPASSED: DailyReview V2 coverage is ready for required modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
