"""Phase 4.2 T05 — ReplayRunner tests.

Covers: single day replay, multi-day aggregate, skip missing dates,
        aggregate report serialization, drift summary markdown.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_reference.contracts import (
    AnalystReferenceQuality,
    AnalystReferenceRecord,
    EmotionLabel,
    ExtractionStatus,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
)
from stock_processing_service.application.services.analyst_reference.store import (
    AnalystReferenceStore,
)
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIDiagnosisReferenceView,
)
from stock_processing_service.application.services.analyst_alignment.replay_runner import (
    DailyReplayResult,
    ReplayAggregateReport,
    ReplayRunner,
)
from stock_processing_service.application.services.analyst_alignment.turing_score import (
    AnalystTuringScore,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _store_with_fixtures() -> AnalystReferenceStore:
    """Create a temp store loaded with 7/7 and 7/8 analyst references."""
    import os
    from stock_processing_service.application.services.analyst_reference.markdown_ingestion import MarkdownReferenceParser

    base = tempfile.mkdtemp(prefix="replay_test_")
    store = AnalystReferenceStore(base_dir=base)
    parser = MarkdownReferenceParser()

    for fname, td in [
        ("analyst_recap_0707.md", date(2026, 7, 7)),
        ("analyst_recap_0708.md", date(2026, 7, 8)),
    ]:
        rec = parser.parse_file(FIXTURES / fname, trade_date=td)
        store.append(rec)

    return store


def _perfect_ai_for_date(td: date) -> AIDiagnosisReferenceView:
    """Build a well-matched AI view for testing."""
    return AIDiagnosisReferenceView(
        trade_date=td,
        market_facts=MarketFacts(
            limit_up_count=47 if td.day == 8 else 33,
            chain_board_count=14 if td.day == 8 else 9,
            max_board_height=7 if td.day == 8 else 5,
            active_capital_yi=739.0 if td.day == 8 else 897.0,
            market_up_ratio=0.35 if td.day == 8 else 0.15,
            loss_effect_ratio=None,
        ),
        emotion_label=EmotionLabel(
            market_phase="REPAIR_WATCH" if td.day == 8 else "PANIC",
            risk_level="MEDIUM_HIGH" if td.day == 8 else "HIGH",
            emotion_momentum=-4.0 if td.day == 8 else -12.0,
        ),
        relay_label=RelayLabel(
            max_board_height=7 if td.day == 8 else 5,
            promotion_1_to_2=0.21 if td.day == 8 else 0.051,
            promotion_2_to_3=0.33 if td.day == 8 else 0.0,
        ),
        source_quality=1.0,
    )


# ═══ TC-4.2-RP-01: single day replay produces result ═══

def test_single_day_replay():
    store = _store_with_fixtures()
    runner = ReplayRunner(store=store)
    ai_views = {date(2026, 7, 8): _perfect_ai_for_date(date(2026, 7, 8))}
    results, agg = runner.run(date(2026, 7, 8), date(2026, 7, 8), ai_views=ai_views)

    assert len(results) == 1
    dr = results[0]
    assert dr.trade_date == date(2026, 7, 8)
    assert isinstance(dr.alignment_report, object)
    assert isinstance(dr.turing_score, AnalystTuringScore)
    assert dr.turing_score.grade in ("A", "B")
    assert agg.trading_days == 1
    assert agg.average_score >= 0.8  # strategy+theme_leader=0 without enriched AI view


# ═══ TC-4.2-RP-02: multi-day aggregate ═══

def test_multi_day_replay():
    store = _store_with_fixtures()
    runner = ReplayRunner(store=store)
    ai_views = {
        date(2026, 7, 7): _perfect_ai_for_date(date(2026, 7, 7)),
        date(2026, 7, 8): _perfect_ai_for_date(date(2026, 7, 8)),
    }
    results, agg = runner.run(date(2026, 7, 7), date(2026, 7, 8), ai_views=ai_views)

    assert len(results) == 2
    assert agg.trading_days == 2
    assert agg.average_score > 0.0
    assert agg.min_score <= agg.max_score
    assert 0.0 <= agg.median_score <= 1.0


# ═══ TC-4.2-RP-03: skip missing reference ═══

def test_skip_missing_reference():
    import os
    base = tempfile.mkdtemp(prefix="replay_missing_")
    store = AnalystReferenceStore(base_dir=base)  # empty store

    runner = ReplayRunner(store=store)
    ai_views = {date(2026, 7, 9): _perfect_ai_for_date(date(2026, 7, 9))}
    results, agg = runner.run(date(2026, 7, 9), date(2026, 7, 9), ai_views=ai_views)

    assert len(results) == 0
    assert len(agg.skipped_days) == 1
    assert "2026-07-09" in agg.skipped_days

    # Cleanup
    for f in store._repo.base_dir.iterdir():
        os.unlink(f)
    os.rmdir(store._repo.base_dir)


# ═══ TC-4.2-RP-04: skip missing AI view ═══

def test_skip_missing_ai_view():
    store = _store_with_fixtures()
    runner = ReplayRunner(store=store)
    results, agg = runner.run(date(2026, 7, 7), date(2026, 7, 8), ai_views={})

    assert len(results) == 0
    assert len(agg.skipped_days) == 2


# ═══ TC-4.2-RP-05: aggregate report to_dict ═══

def test_aggregate_to_dict():
    store = _store_with_fixtures()
    runner = ReplayRunner(store=store)
    ai_views = {date(2026, 7, 8): _perfect_ai_for_date(date(2026, 7, 8))}
    _, agg = runner.run(date(2026, 7, 8), date(2026, 7, 8), ai_views=ai_views)

    d = agg.to_dict()
    assert "scores" in d
    assert "average" in d["scores"]
    assert "grade_distribution" in d
    assert "component_averages" in d


# ═══ TC-4.2-RP-06: drift summary markdown ═══

def test_drift_summary_markdown():
    store = _store_with_fixtures()
    runner = ReplayRunner(store=store)
    ai_views = {date(2026, 7, 8): _perfect_ai_for_date(date(2026, 7, 8))}
    _, agg = runner.run(date(2026, 7, 8), date(2026, 7, 8), ai_views=ai_views)

    md = agg.to_markdown()
    assert "Analyst Alignment Replay Summary" in md
    assert "## Overall" in md
    assert "## Component Averages" in md
    assert "## Weak Days" in md
    assert "## Top Calibration Hints" in md


# ═══ TC-4.2-RP-07: DailyReplayResult to_dict ═══

def test_daily_result_to_dict():
    store = _store_with_fixtures()
    runner = ReplayRunner(store=store)
    ai_views = {date(2026, 7, 8): _perfect_ai_for_date(date(2026, 7, 8))}
    results, _ = runner.run(date(2026, 7, 8), date(2026, 7, 8), ai_views=ai_views)

    d = results[0].to_dict()
    assert "trade_date" in d
    assert "alignment" in d
    assert "turing" in d
    assert d["trade_date"] == "2026-07-08"
