from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.replay.legacy_layer_c_output_report import (
    LegacyLayerCOutputReportBuilder,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import (
    _ReplayDatabaseStockFacade,
    _get_replay_gateway,
)


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    source = report.get("source") or {}
    raw = report.get("raw") or {}
    effective = report.get("effective") or {}
    dist = report.get("distributions") or {}
    target = report.get("target") or {}
    consistency = report.get("consistency") or {}
    lines = [
        f"# Legacy Layer C Output Report - {report.get('trade_date')}",
        "",
        "## Source",
        "",
        f"- source_used: `{source.get('source_used')}`",
        f"- reason: `{source.get('reason')}`",
        f"- latest_pool_trade_date: `{source.get('latest_pool_trade_date')}`",
        "",
        "## Raw Output",
        "",
        f"- raw_row_count: `{raw.get('raw_row_count')}`",
        f"- stock_distinct_count: `{raw.get('stock_distinct_count')}`",
        f"- subject_distinct_count: `{raw.get('subject_distinct_count')}`",
        f"- duplicate_stock_count: `{raw.get('duplicate_stock_count')}`",
        f"- max_rows_per_stock: `{raw.get('max_rows_per_stock')}`",
        "",
        "## Effective Output",
        "",
        f"- effective_stock_count: `{effective.get('effective_stock_count')}`",
        f"- effective_subject_count: `{effective.get('effective_subject_count')}`",
        "",
        "## Distributions",
        "",
        f"- watch_status_counts: `{dist.get('watch_status_counts')}`",
        f"- pool_entry_type_counts: `{dist.get('pool_entry_type_counts')}`",
        f"- watch_source_tag_counts: `{dist.get('watch_source_tag_counts')}`",
        f"- watch_score: `{dist.get('watch_score')}`",
        f"- watch_priority: `{dist.get('watch_priority')}`",
        "",
        "## Target",
        "",
        f"- stock_id: `{target.get('stock_id')}`",
        f"- raw_rows: `{target.get('raw_rows')}`",
        f"- effective_selected: `{target.get('effective_selected')}`",
        f"- selected_subject_key: `{target.get('selected_subject_key')}`",
        f"- selected_theme_name: `{target.get('selected_theme_name')}`",
        f"- watch_status: `{target.get('watch_status')}`",
        f"- pool_entry_type: `{target.get('pool_entry_type')}`",
        f"- watch_score: `{target.get('watch_score')}`",
        f"- watch_priority: `{target.get('watch_priority')}`",
        f"- prior7_limitup_days: `{target.get('prior7_limitup_days')}`",
        f"- prior7_strong_days: `{target.get('prior7_strong_days')}`",
        f"- recent_limit_up_count: `{target.get('recent_limit_up_count')}`",
        f"- support_type: `{target.get('support_type')}`",
        f"- support_score: `{target.get('support_score')}`",
        f"- rank_in_effective_c_pool: `{target.get('rank_in_effective_c_pool')}`",
        f"- legacy_raw_row_count: `{target.get('legacy_raw_row_count')}`",
        "",
        "## Recap Consistency",
        "",
        f"- recap_available: `{consistency.get('recap_available')}`",
        f"- recap_layer_c_input_mode: `{consistency.get('recap_layer_c_input_mode')}`",
        f"- recap_legacy_watch_input_count: `{consistency.get('recap_legacy_watch_input_count')}`",
        f"- recap_strong_watch_input_7d_count: `{consistency.get('recap_strong_watch_input_7d_count')}`",
        f"- recap_candidate_count_all: `{consistency.get('recap_candidate_count_all')}`",
        f"- recap_candidate_count_observe: `{consistency.get('recap_candidate_count_observe')}`",
        f"- recap_observe_candidates_count: `{consistency.get('recap_observe_candidates_count')}`",
        f"- effective_equals_legacy_watch_input_count: `{consistency.get('effective_equals_legacy_watch_input_count')}`",
        f"- effective_equals_strong_watch_input_7d_count: `{consistency.get('effective_equals_strong_watch_input_7d_count')}`",
        "",
        "## Effective Top Preview",
        "",
        "| rank | stock_id | subject | type | status | priority | score | prior7_limitup | prior7_strong | support | support_score |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in effective.get("top_preview") or []:
        lines.append(
            f"| {row.get('rank')} | {row.get('stock_id')} | {row.get('subject_key')} | {row.get('pool_entry_type')} | {row.get('watch_status')} | {row.get('watch_priority')} | {row.get('watch_score')} | {row.get('prior7_limitup_days')} | {row.get('prior7_strong_days')} | {row.get('support_type')} | {row.get('support_score')} |"
        )
    notes = report.get("notes") or []
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- `{note}`" for note in notes)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    trade_date = date.fromisoformat(args.trade_date)
    gateway = await _get_replay_gateway()
    try:
        facade = _ReplayDatabaseStockFacade(gateway)
        read = StockReadGatewayAdapter(db_gateway=facade)
        raw_rows = await facade.get_legacy_strong_watch_candidate_inputs(
            trade_date=trade_date,
            lookback_days=args.lookback_days,
        )
        effective_rows = await read.get_legacy_strong_watch_candidate_inputs(
            trade_date=trade_date,
            lookback_days=args.lookback_days,
        )
        recap_doc: dict[str, Any] = {}
        if args.include_recap:
            snapshot = await read.get_existing_post_market_recap_snapshot(trade_date)
            recap_doc = dict(getattr(snapshot, "recap_doc", {}) or {}) if snapshot else {}
        return LegacyLayerCOutputReportBuilder().build(
            trade_date=trade_date.isoformat(),
            raw_rows=raw_rows,
            effective_rows=effective_rows,
            target_stock_id=args.stock_id,
            recap_doc=recap_doc,
        ).to_dict()
    finally:
        close = getattr(gateway, "close", None)
        if callable(close):
            await close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate read-only legacy Layer C output report.")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--stock-id", required=True)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--include-recap", action="store_true")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    out_dir = Path(args.output_dir) if args.output_dir else Path("reports/replay") / args.trade_date.replace("-", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "legacy_layer_c_output.json"
    md_path = out_dir / "legacy_layer_c_output.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    _write_markdown(report, md_path)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(md_path),
                "raw": report.get("raw"),
                "effective": {k: v for k, v in (report.get("effective") or {}).items() if k != "top_preview"},
                "target": {k: v for k, v in (report.get("target") or {}).items() if k != "duplicate_subjects"},
                "consistency": report.get("consistency"),
            },
            ensure_ascii=False,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
