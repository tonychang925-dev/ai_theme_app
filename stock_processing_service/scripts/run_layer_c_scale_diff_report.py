from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.replay.layer_c_scale_diff_report import (
    LayerCScaleDiffReportBuilder,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import (
    _ReplayDatabaseStockFacade,
    _get_replay_gateway,
)


def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if is_dataclass(row):
        return asdict(row)
    return dict(getattr(row, "__dict__", {}) or {})


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    counts = report.get("pipeline_counts") or {}
    d_counts = report.get("d_layer_counts") or {}
    target = report.get("target") or {}
    lines = [
        f"# Layer C Scale Diff Report - {report.get('trade_date')}",
        "",
        f"- target: `{report.get('target_stock_id')}`",
        f"- subject_pool_rows: `{counts.get('subject_pool_rows')}`",
        f"- universe: formal `{counts.get('universe_formal')}`, observe `{counts.get('universe_observe')}`, blocked `{counts.get('universe_blocked')}`",
        f"- seeded: `{counts.get('seeded')}`, rolled `{counts.get('rolled')}`, carried_from_prior `{counts.get('carried_from_prior')}`",
        f"- refreshed: `{counts.get('refreshed')}`, admission_kept `{counts.get('admission_kept')}`, admission_pruned `{counts.get('admission_pruned')}`",
        f"- prune: kept `{counts.get('prune_kept')}`, removed `{counts.get('prune_removed')}`",
        f"- promoted: `{counts.get('promoted')}`",
        f"- strong_watch_input_7d_count: `{counts.get('strong_watch_input_7d_count')}`",
        f"- D: all `{d_counts.get('all_candidates')}`, formal `{d_counts.get('formal_candidates')}`, observe `{d_counts.get('observe_candidates')}`, observe_top_n `{d_counts.get('observe_top_n')}`",
        "",
        "## Target",
        "",
        f"- candidate_level: `{target.get('candidate_level')}`",
        f"- candidate_rank: `{target.get('candidate_rank')}`",
        f"- observe_rank: `{target.get('observe_rank')}`",
        f"- promoted_rank: `{target.get('promoted_rank')}`",
        f"- candidate_input_rank: `{target.get('candidate_input_rank')}`",
        f"- promote_bucket: `{target.get('promote_bucket')}`",
        f"- support_type: `{target.get('support_type')}`",
        f"- support_score: `{target.get('support_score')}`",
        "",
        "## Seven Day History",
        "",
        "| trade_date | active | weakening | formal | observe_only | removed | total_kept | total_rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.get("seven_day_history_counts") or []:
        lines.append(
            "| {trade_date} | {active} | {weakening} | {formal} | {observe_only} | {removed} | {total_kept} | {total_rows} |".format(
                **row
            )
        )
    lines.extend(["", "## Top Observe Candidates", ""])
    lines.append("| rank | stock_id | name | level | score | support | support_score | subject |")
    lines.append("|---:|---|---|---|---:|---|---:|---|")
    for row in report.get("top_observe_candidates") or []:
        lines.append(
            f"| {row.get('rank')} | {row.get('stock_id')} | {row.get('stock_name')} | {row.get('candidate_level')} | {row.get('candidate_score')} | {row.get('support_type')} | {row.get('support_score')} | {row.get('subject_key')} |"
        )
    notes = report.get("notes") or []
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- `{note}`" for note in notes)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("SPS_IDENTITY_GATE_MODE", "legacy_anytime")
    trade_date = date.fromisoformat(args.trade_date)
    gateway = await _get_replay_gateway()
    try:
        read = StockReadGatewayAdapter(db_gateway=_ReplayDatabaseStockFacade(gateway))
        pool_rows = await read.get_subject_stock_pool_by_trade_date(trade_date)
        stock_ids = sorted({r.stock_id for r in pool_rows if r.stock_id})
        subject_keys = sorted({r.subject_key for r in pool_rows if r.subject_key})
        prior_watch_rows = await read.get_prior_strong_watch_pool_rows(trade_date, lookback_days=args.lookback_days)
        stock_ids = sorted(
            {
                row.stock_id
                for row in [*pool_rows, *prior_watch_rows]
                if str(getattr(row, "stock_id", "") or "")
            }
        )
        subject_keys = sorted(
            {
                row.subject_key
                for row in [*pool_rows, *prior_watch_rows]
                if str(getattr(row, "subject_key", "") or "")
            }
        )
        bars = await read.get_stock_daily_bars(trade_date)
        prior_rows = await read.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=args.lookback_days,
            stock_ids=stock_ids or None,
        )
        history_bars = await read.get_stock_daily_bars_range(
            start_date=trade_date - timedelta(days=args.history_days),
            end_date=trade_date,
            stock_ids=stock_ids or None,
        )
        identities_raw = await read.get_mainline_identity_by_subject_keys(subject_keys, trade_date)
        cycles_raw = await read.get_mainline_cycle_by_subject_keys(subject_keys, trade_date)
        identities = {str(_as_dict(row).get("subject_key")): _as_dict(row) for row in identities_raw}
        cycles = {str(_as_dict(row).get("subject_key")): _as_dict(row) for row in cycles_raw}
        report = LayerCScaleDiffReportBuilder().build(
            trade_date=trade_date,
            target_stock_id=args.stock_id,
            pool_rows=pool_rows,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
            prior_watch_rows=prior_watch_rows,
            identities_by_subject=identities,
            cycles_by_subject=cycles,
        )
        return report.to_dict()
    finally:
        close = getattr(gateway, "close", None)
        if callable(close):
            await close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate read-only Layer C scale diagnostics.")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--stock-id", required=True)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--history-days", type=int, default=90)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = Path("reports/replay") / args.trade_date.replace("-", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "layer_c_scale_diff.json"
    md_path = out_dir / "layer_c_scale_diff.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    _write_markdown(report, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "target": report.get("target"), "pipeline_counts": report.get("pipeline_counts"), "d_layer_counts": report.get("d_layer_counts")}, ensure_ascii=False, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
