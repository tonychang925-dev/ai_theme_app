#!/usr/bin/env python3
"""Phase 4.2 T05 — Analyst Alignment Replay CLI.

Usage:
    PYTHONPATH=. python3 scripts/run_analyst_alignment.py \
        --start 2026-07-07 \
        --end 2026-07-08 \
        --reference-dir tmp/analyst_reference \
        --ai-source mock \
        --output tmp/analyst_alignment
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Imports (lazy for CLI startup speed) ──


def _import_store():
    from stock_processing_service.application.services.analyst_reference.store import (
        AnalystReferenceStore,
    )
    return AnalystReferenceStore


def _import_builders():
    from stock_processing_service.tests.unit.test_analyst_turing_score import (
        _perfect_ai,
    )  # type: ignore[no-any-unimported]
    return _perfect_ai


def _make_mock_ai_view(td: date):
    """Build a mock AI view for the given date."""
    from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
        AIDiagnosisReferenceView,
    )
    # Use the perfect-AI builder from tests (same module)
    try:
        from stock_processing_service.tests.unit.test_analyst_turing_score import _perfect_ai
        return _perfect_ai(td)
    except ImportError:
        # Fallback: minimal mock
        from stock_processing_service.application.services.analyst_reference.contracts import (
            EmotionLabel, MarketFacts, RelayLabel,
        )
        return AIDiagnosisReferenceView(
            trade_date=td,
            market_facts=MarketFacts(limit_up_count=0, max_board_height=0),
            emotion_label=EmotionLabel(),
            relay_label=RelayLabel(),
            source_quality=0.5,
        )


def main():
    parser = argparse.ArgumentParser(description="Analyst Alignment Replay CLI")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--reference-dir", default="tmp/analyst_reference",
        help="Path to analyst reference store directory"
    )
    parser.add_argument(
        "--ai-source", choices=["mock", "json"], default="mock",
        help="AI view source: mock (test data) or json (file-based)"
    )
    parser.add_argument(
        "--ai-json-dir", default=None,
        help="Directory of AI view JSON files (ai_source=json only)"
    )
    parser.add_argument(
        "--output", default="tmp/analyst_alignment",
        help="Output directory for reports"
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    # ── 1. Load Store ──
    store_cls = _import_store()
    store = store_cls(base_dir=args.reference_dir)

    # ── 2. Build AI views ──
    ai_views: dict[date, object] = {}
    if args.ai_source == "mock":
        from datetime import timedelta
        d = start
        while d <= end:
            ai_views[d] = _make_mock_ai_view(d)
            d += timedelta(days=1)
    elif args.ai_source == "json":
        if not args.ai_json_dir:
            print("ERROR: --ai-json-dir required when --ai-source=json", file=sys.stderr)
            sys.exit(1)
        json_dir = Path(args.ai_json_dir)
        from datetime import timedelta
        d = start
        while d <= end:
            fpath = json_dir / f"{d.isoformat()}.json"
            if fpath.exists():
                import json as json_mod
                data = json_mod.loads(fpath.read_text())
                # Minimal: load as dict and pass through adapter
                ai_views[d] = data
            d += timedelta(days=1)

    # ── 3. Run Replay ──
    from stock_processing_service.application.services.analyst_alignment.replay_runner import (
        ReplayRunner,
    )
    runner = ReplayRunner(store=store)
    daily_results, aggregate = runner.run(start, end, ai_views=ai_views)

    # ── 4. Write Output ──
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_dir = output_dir / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    for dr in daily_results:
        date_str = dr.trade_date.isoformat()

        # Alignment report
        al_path = daily_dir / f"{date_str}.alignment.json"
        al_path.write_text(
            json.dumps(dr.alignment_report.to_dict(), ensure_ascii=False, indent=2)
        )

        # Turing score
        ts_path = daily_dir / f"{date_str}.turing.json"
        ts_path.write_text(
            json.dumps(dr.turing_score.to_dict(), ensure_ascii=False, indent=2)
        )

    # Aggregate
    agg_path = output_dir / "aggregate_report.json"
    agg_path.write_text(
        json.dumps(aggregate.to_dict(), ensure_ascii=False, indent=2)
    )

    # Drift summary markdown
    md_path = output_dir / "drift_summary.md"
    md_path.write_text(aggregate.to_markdown())

    # ── 5. Print Summary ──
    print(f"Replay complete: {aggregate.trading_days} trading days compared")
    print(f"Skipped: {len(aggregate.skipped_days)} days")
    print(f"Average ATS: {aggregate.average_score:.3f}")
    print(f"Grade distribution: {aggregate.grade_distribution}")
    print(f"Output: {output_dir}/")
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(output_dir)}")

    sys.exit(0)


if __name__ == "__main__":
    main()
