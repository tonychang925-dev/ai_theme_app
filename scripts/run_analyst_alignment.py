#!/usr/bin/env python3
"""Phase 4.2 T05 — Analyst Alignment Replay CLI (v2).

Usage:
    PYTHONPATH=. python3 scripts/run_analyst_alignment.py \\
        --start 2026-07-07 \\
        --end 2026-07-09 \\
        --reference-dir data/analyst_reports \\
        --ai-source charts \\
        --ai-chart-dir frontend/public/api/analyst-charts \\
        --emotion-dir frontend/public/api \\
        --output tmp/analyst_alignment
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _get_ai_strategy_text(td, chart_dir, breadth, hm, capital) -> str:
    """Get AI strategy text: prefer emotion JSON strategy_bias."""
    emotion_path = chart_dir.parent / f"emotion-{td.isoformat()}.json"
    if emotion_path.exists():
        try:
            emo = json.loads(emotion_path.read_text())
            text = emo.get("strategy_bias", "")
            if text:
                return text
        except (json.JSONDecodeError, OSError):
            pass
    return f"{breadth.get('label', '')}, {hm.get('label', '')}, {capital.get('label', '')}"


def _build_ai_view_from_charts(
    td: date,
    chart_dir: Path,
    prev_refs: dict[date, object],
    all_refs: dict[date, object],
) -> object:
    """Build AIDiagnosisReferenceView from real chart/emotion JSONs with PhaseOntology."""
    from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
        AIDiagnosisReferenceView,
    )
    from stock_processing_service.application.services.analyst_reference.contracts import (
        EmotionLabel, MarketFacts, RelayLabel, StrategyLabel, ThemeLifecycleEntry,
    )
    from stock_processing_service.application.services.analyst_alignment.phase_ontology import (
        PhaseContext, normalize_phase_label, adjust_risk_by_confirmation,
    )

    chart_path = chart_dir / f"{td.isoformat()}.json"
    if not chart_path.exists():
        return None

    charts = json.loads(chart_path.read_text())
    breadth = next(c for c in charts if c['chart_type'] == 'market_breadth')['data']
    emotion_c = next(c for c in charts if c['chart_type'] == 'emotion_momentum')['data']
    capital = next(c for c in charts if c['chart_type'] == 'active_capital')['data']
    relay = next(c for c in charts if c['chart_type'] == 'relay_ecology')['data']
    inst = next(c for c in charts if c['chart_type'] == 'institution_style')['data']
    hm = next(c for c in charts if c['chart_type'] == 'hot_money_style')['data']

    # ── PhaseContext from cross-date data ──
    prev_ref = prev_refs.get(td)
    prev_phase = getattr(getattr(prev_ref, 'emotion_label', None), 'market_phase', '') if prev_ref else ''
    prev_risk = getattr(getattr(prev_ref, 'emotion_label', None), 'risk_level', '') if prev_ref else ''
    prev_lu = getattr(getattr(prev_ref, 'market_facts', None), 'limit_up_count', 0) or 0

    lu_count = breadth.get('limit_up_count', 0)
    lu_delta = lu_count - prev_lu if prev_lu > 0 else 0
    composite = breadth.get('composite_score', 0)
    raw_risk = (
        'HIGH' if composite <= -8 else
        'MEDIUM_HIGH' if composite <= -3 else
        'MEDIUM' if composite <= 3 else
        'LOW'
    )

    # Days since panic
    days_since_panic = 99
    d = td - timedelta(days=1)
    while d >= date(2026, 6, 1):
        if d in all_refs:
            ph = getattr(getattr(all_refs[d], 'emotion_label', None), 'market_phase', '')
            if ph in ('PANIC', 'FREEZE'):
                days_since_panic = (td - d).days
                break
        d -= timedelta(days=1)

    feedback_label = relay.get('feedback_label', '')
    relay_health = 0.5 if feedback_label == '负反馈' else 0.7 if feedback_label == '中性' else 0.85

    ctx = PhaseContext(
        trade_date=td.isoformat(),
        prev_phase=prev_phase, prev_risk=prev_risk,
        limit_up_count=lu_count, limit_up_delta=lu_delta,
        max_board_height=relay.get('max_board_height', 0),
        emotion_momentum=emotion_c.get('emotion_momentum_score', 0),
        risk_level=raw_risk,
        days_since_panic=days_since_panic,
        promotion_1_to_2=relay.get('promotion_1_to_2', 0),
        promotion_2_to_3=relay.get('promotion_2_to_3', 0),
        relay_score=relay_health,
        up_ratio=breadth.get('up_ratio', 0),
        has_index_confirmation=lu_delta > 20,
    )

    ai_phase = normalize_phase_label(breadth.get('label', ''), ctx)
    ai_risk = adjust_risk_by_confirmation(ai_phase, raw_risk, ctx)

    themes = tuple(
        ThemeLifecycleEntry(
            theme_name=d.get('name', ''),
            state='调整' if '调整' in str(d.get('state', ''))
            else '启动' if '启动' in str(d.get('state', ''))
            else str(d.get('state', ''))
        ) for d in inst.get('directions', [])
    )

    return AIDiagnosisReferenceView(
        trade_date=td,
        market_facts=MarketFacts(
            limit_up_count=lu_count,
            chain_board_count=breadth.get('chain_board_count'),
            max_board_height=relay.get('max_board_height'),
            active_capital_yi=capital.get('active_amount_yi'),
            market_up_ratio=breadth.get('up_ratio'),
            loss_effect_ratio=breadth.get('loss_effect_ratio'),
        ),
        emotion_label=EmotionLabel(
            market_phase=ai_phase, risk_level=ai_risk,
            emotion_momentum=emotion_c.get('emotion_momentum_score'),
        ),
        relay_label=RelayLabel(
            max_board_height=relay.get('max_board_height'),
            promotion_1_to_2=relay.get('promotion_1_to_2'),
            promotion_2_to_3=relay.get('promotion_2_to_3'),
        ),
        theme_lifecycle=themes,
        # AI strategy text: prefer emotion JSON strategy_bias over label concatenation
        strategy_label=StrategyLabel(
            summary=_get_ai_strategy_text(td, chart_dir, breadth, hm, capital)
        ),
        source_quality=0.85,
    )


def main():
    parser = argparse.ArgumentParser(description="Analyst Alignment Replay CLI v2")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--reference-dir", default="tmp/analyst_reference",
                        help="AnalystReferenceStore directory (parsed markdown references)")
    parser.add_argument("--ai-source", choices=["mock", "charts"], default="charts",
                        help="AI view source: mock (test) or charts (real chart JSON)")
    parser.add_argument("--ai-chart-dir", default="frontend/public/api/analyst-charts",
                        help="Directory of AI chart JSON files (ai-source=charts)")
    parser.add_argument("--output", default="tmp/analyst_alignment",
                        help="Output directory for reports")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load Store ──
    from stock_processing_service.application.services.analyst_reference.store import AnalystReferenceStore
    store = AnalystReferenceStore(base_dir=args.reference_dir)

    # Pre-load all reference records for cross-date context
    all_refs = store.load_all()

    # ── 2. Build AI views ──
    ai_views: dict[date, object] = {}
    if args.ai_source == "mock":
        from stock_processing_service.application.services.analyst_alignment.ai_adapter import AIDiagnosisReferenceView
        from stock_processing_service.application.services.analyst_reference.contracts import EmotionLabel, MarketFacts, RelayLabel
        d = start
        while d <= end:
            ai_views[d] = AIDiagnosisReferenceView(
                trade_date=d,
                market_facts=MarketFacts(limit_up_count=0, max_board_height=0),
                emotion_label=EmotionLabel(),
                relay_label=RelayLabel(),
                source_quality=0.5,
            )
            d += timedelta(days=1)
    elif args.ai_source == "charts":
        chart_dir = Path(args.ai_chart_dir)
        # Build prev_refs map (yesterday's reference for each date)
        prev_refs: dict[date, object] = {}
        d = start
        while d <= end:
            prev_d = d - timedelta(days=1)
            if prev_d in all_refs:
                prev_refs[d] = all_refs[prev_d]
            d += timedelta(days=1)

        d = start
        while d <= end:
            view = _build_ai_view_from_charts(d, chart_dir, prev_refs, all_refs)
            if view is not None:
                ai_views[d] = view
            d += timedelta(days=1)

    # ── 3. Run Replay ──
    from stock_processing_service.application.services.analyst_alignment.replay_runner import ReplayRunner
    runner = ReplayRunner(store=store)
    daily_results, aggregate = runner.run(start, end, ai_views=ai_views)

    # ── 4. Write Output ──
    daily_dir = output_dir / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    for dr in daily_results:
        ds = dr.trade_date.isoformat()
        (daily_dir / f"{ds}.alignment.json").write_text(
            json.dumps(dr.alignment_report.to_dict(), ensure_ascii=False, indent=2))
        (daily_dir / f"{ds}.turing.json").write_text(
            json.dumps(dr.turing_score.to_dict(), ensure_ascii=False, indent=2))

    (output_dir / "aggregate_report.json").write_text(
        json.dumps(aggregate.to_dict(), ensure_ascii=False, indent=2))
    (output_dir / "drift_summary.md").write_text(aggregate.to_markdown())

    # ── 5. Summary ──
    print(f"Phase 4.2 Replay: {aggregate.trading_days} days | "
          f"Avg ATS={aggregate.average_score:.3f} | Median={aggregate.median_score:.3f}")
    print(f"Grades: {aggregate.grade_distribution}")
    print(f"Skipped: {aggregate.skipped_days}")
    if aggregate.weak_days:
        print(f"Weak: {aggregate.weak_days}")
    print(f"Output: {output_dir}/")
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(output_dir)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
