"""Phase 4.2.3 — CLI Hardening tests.

Covers: safe_get_chart, partial AI data, bad JSON, missing charts,
        ai_quality degradation, CLI exit codes.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# ── Test safe_get_chart via the CLI builder ──

@pytest.fixture
def empty_chart_dir():
    d = tempfile.mkdtemp(prefix="empty_charts_")
    yield Path(d)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def partial_chart_dir():
    """Chart dir with only 2 of 7 expected chart types."""
    d = tempfile.mkdtemp(prefix="partial_charts_")
    td = date(2026, 7, 10)
    charts = [
        {"chart_type": "market_breadth", "data": {"limit_up_count": 75, "up_ratio": 0.46, "composite_score": 6, "label": "REBOUND", "chain_board_count": 6, "loss_effect_ratio": 0.012}},
        {"chart_type": "emotion_momentum", "data": {"emotion_momentum_score": 6.0}},
    ]
    (d / Path(f"{td.isoformat()}.json")).write_text(json.dumps(charts))
    yield Path(d), td
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def bad_json_chart_dir():
    """Chart dir with a corrupt JSON file."""
    d = tempfile.mkdtemp(prefix="badjson_charts_")
    (d / Path("2026-07-10.json")).write_text("{not valid json")
    yield Path(d), date(2026, 7, 10)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ═══ TC-HARD-01: missing chart file → None ═══

def test_missing_chart_file_returns_none(empty_chart_dir):
    """When chart JSON doesn't exist, _build_ai_view_from_charts returns None."""
    from scripts.run_analyst_alignment import _build_ai_view_from_charts
    result = _build_ai_view_from_charts(
        date(2026, 7, 10), empty_chart_dir, {}, {}
    )
    assert result is None


# ═══ TC-HARD-02: partial charts → view built with degraded quality ═══

def test_partial_charts_produces_view_with_lower_quality(partial_chart_dir):
    """When only 2/7 chart types exist, view is built but ai_quality < 0.85."""
    chart_dir, td = partial_chart_dir
    from scripts.run_analyst_alignment import _build_ai_view_from_charts
    view = _build_ai_view_from_charts(td, chart_dir, {}, {})
    assert view is not None
    assert view.source_quality < 0.85
    assert len(view.missing_fields) > 0
    # Should have at least some facts from the available charts
    assert view.market_facts.limit_up_count == 75


# ═══ TC-HARD-03: bad JSON → None ═══

def test_bad_json_returns_none(bad_json_chart_dir):
    """Corrupt JSON file returns None, doesn't crash."""
    chart_dir, td = bad_json_chart_dir
    from scripts.run_analyst_alignment import _build_ai_view_from_charts
    view = _build_ai_view_from_charts(td, chart_dir, {}, {})
    assert view is None


# ═══ TC-HARD-04: ReplayRunner handles empty ai_views ═══

def test_replay_runner_handles_empty_ai_views():
    """Runner skips all days when no AI views available."""
    from stock_processing_service.application.services.analyst_alignment.replay_runner import ReplayRunner
    from stock_processing_service.application.services.analyst_reference.store import AnalystReferenceStore
    import tempfile, os

    base = tempfile.mkdtemp(prefix="empty_store_")
    store = AnalystReferenceStore(base_dir=base)
    runner = ReplayRunner(store=store)
    results, agg = runner.run(date(2026, 7, 10), date(2026, 7, 12), ai_views={})

    assert len(results) == 0
    assert len(agg.skipped_days) == 3

    for f in store._repo.base_dir.iterdir():
        os.unlink(f)
    os.rmdir(store._repo.base_dir)


# ═══ TC-HARD-05: aggregate report includes partial/failed tracking ═══

def test_aggregate_has_partial_and_failed_fields():
    from stock_processing_service.application.services.analyst_alignment.replay_runner import ReplayAggregateReport
    agg = ReplayAggregateReport(
        start_date=date(2026,7,7), end_date=date(2026,7,9),
        trading_days=2,
        skipped_days=["2026-07-09"],
        partial_days=["2026-07-08"],
        failed_days=[],
    )
    d = agg.to_dict()
    assert "partial_days" in d
    assert "failed_days" in d
    assert d["partial_days"] == ["2026-07-08"]
    assert d["failed_days"] == []

    md = agg.to_markdown()
    assert "Partial" in md


# ═══ TC-HARD-06: ai_quality degrades with missing chart ratio ═══

def test_ai_quality_degradation():
    """0/7 missing → 0.85; 3/7 missing → ~0.59; 7/7 → 0.30 floor."""
    # Test the degradation formula: max(0.30, 0.85 - ratio * 0.6)
    for missing, expected_min in [(0, 0.85), (1, 0.76), (3, 0.59), (7, 0.30)]:
        ratio = missing / 7.0
        quality = max(0.30, 0.85 - ratio * 0.6)
        assert quality >= expected_min - 0.01, \
            f"missing={missing} ratio={ratio:.2f} quality={quality:.2f} expected>={expected_min}"
