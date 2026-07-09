"""Phase 4.2 — AnalystReferenceStore tests.

Covers: append, get_by_date, list_dates, validate_manifest,
        duplicate handling, rebuild_manifest, empty store edge cases.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_reference.contracts import (
    ExtractionStatus,
)
from stock_processing_service.application.services.analyst_reference.markdown_ingestion import (
    MarkdownReferenceParser,
)
from stock_processing_service.application.services.analyst_reference.store import (
    AnalystReferenceStore,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def parser():
    return MarkdownReferenceParser()


@pytest.fixture
def tmp_store():
    """Create a temp store that self-cleans."""
    import os
    base = tempfile.mkdtemp(prefix="test_store_")
    store = AnalystReferenceStore(base_dir=base)
    yield store
    # Cleanup
    for f in [store._repo.jsonl_path, store._repo.manifest_path]:
        if f.exists():
            os.unlink(f)
    if store._repo.base_dir.exists():
        os.rmdir(store._repo.base_dir)


@pytest.fixture
def rec_0707(parser):
    return parser.parse_file(FIXTURES / "analyst_recap_0707.md", trade_date=date(2026, 7, 7))


@pytest.fixture
def rec_0708(parser):
    return parser.parse_file(FIXTURES / "analyst_recap_0708.md", trade_date=date(2026, 7, 8))


# ═══ TC-4.2-STORE-01: Append + get round-trip ═══

def test_append_and_get_round_trip(tmp_store, rec_0707):
    h = tmp_store.append(rec_0707)
    assert len(h) == 64  # SHA-256 hex

    loaded = tmp_store.get_by_date(date(2026, 7, 7))
    assert loaded is not None
    assert loaded.market_facts.limit_up_count == 33
    assert loaded.market_facts.max_board_height == 5
    assert loaded.emotion_label.market_phase == "PANIC"
    assert loaded.emotion_label.risk_level == "HIGH"
    assert loaded.emotion_label.emotion_momentum == -12.0
    assert loaded.relay_label.promotion_1_to_2 == 0.051
    assert loaded.quality.extraction_status == ExtractionStatus.FULL_COMPLETE


# ═══ TC-4.2-STORE-02: Same date, same hash → skip ═══

def test_append_same_hash_skipped(tmp_store, rec_0707):
    h1 = tmp_store.append(rec_0707)
    # Append the exact same record again
    h2 = tmp_store.append(rec_0707)
    assert h1 == h2  # should return same hash, no-op

    dates = tmp_store.list_dates()
    assert len(dates) == 1

    # Manifest should have one version
    manifest = tmp_store._repo.read_manifest()
    entry = manifest.records["2026-07-07"]
    assert len(entry.versions) == 1


# ═══ TC-4.2-STORE-02b: Same date, diff hash → new version ═══

def test_append_same_date_diff_hash_adds_version(tmp_store, rec_0707, parser):
    tmp_store.append(rec_0707)

    # Append a record with different content under same date
    rec2 = parser.parse_file(FIXTURES / "analyst_recap_0708.md", trade_date=date(2026, 7, 7))
    h2 = tmp_store.append(rec2)

    dates = tmp_store.list_dates()
    assert len(dates) == 1

    # Manifest should have 2 versions
    manifest = tmp_store._repo.read_manifest()
    entry = manifest.records["2026-07-07"]
    assert len(entry.versions) == 2
    assert entry.latest_hash == h2

    # Latest record should be the new one
    loaded = tmp_store.get_by_date(date(2026, 7, 7))
    assert loaded.market_facts.limit_up_count == 47  # from 7/8 data


# ═══ TC-4.2-STORE-03: Multiple dates ═══

def test_multiple_dates(tmp_store, rec_0707, rec_0708):
    tmp_store.append(rec_0707)
    tmp_store.append(rec_0708)

    dates = tmp_store.list_dates()
    assert len(dates) == 2
    assert date(2026, 7, 7) in dates
    assert date(2026, 7, 8) in dates

    # Load all
    all_recs = tmp_store.load_all()
    assert len(all_recs) == 2
    assert all_recs[date(2026, 7, 7)].emotion_label.market_phase == "PANIC"
    assert all_recs[date(2026, 7, 8)].emotion_label.market_phase == "REPAIR_WATCH"


# ═══ TC-4.2-STORE-04: Missing date returns None ═══

def test_get_nonexistent_date(tmp_store):
    assert tmp_store.get_by_date(date(2026, 7, 10)) is None


# ═══ TC-4.2-STORE-05: Empty store ═══

def test_empty_store(tmp_store):
    assert tmp_store.list_dates() == []
    assert tmp_store.load_all() == {}
    report = tmp_store.validate_manifest()
    assert report.valid  # Empty store is valid


# ═══ TC-4.2-STORE-06: Manifest validation ═══

def test_validate_manifest_passes(tmp_store, rec_0707):
    tmp_store.append(rec_0707)
    report = tmp_store.validate_manifest()
    assert report.valid
    assert report.total_records == 1
    assert len(report.errors) == 0


# ═══ TC-4.2-STORE-07: Rebuild manifest ═══

def test_rebuild_manifest_restores(tmp_store, rec_0707):
    tmp_store.append(rec_0707)

    # Corrupt manifest — delete it
    import os
    os.unlink(tmp_store._repo.manifest_path)

    # Rebuild
    manifest = tmp_store.rebuild_manifest()
    assert manifest.record_count == 1
    assert "2026-07-07" in manifest.records

    # Write it back
    tmp_store._repo.write_manifest(manifest)

    # Validate should now pass
    report = tmp_store.validate_manifest()
    assert report.valid


# ═══ TC-4.2-STORE-08: Theme and leader data preserved ═══

def test_theme_and_leader_round_trip(tmp_store, rec_0708):
    tmp_store.append(rec_0708)
    loaded = tmp_store.get_by_date(date(2026, 7, 8))

    # Themes preserved
    assert len(loaded.theme_lifecycle) > 0
    theme_names = [t.theme_name for t in loaded.theme_lifecycle]
    assert any("服务器" in tn for tn in theme_names)

    # Leaders preserved
    assert len(loaded.leader_state) > 0
    roles = [l.role for l in loaded.leader_state]
    assert "market_leader" in roles

    # Strategy preserved
    assert len(loaded.strategy_label.allowed) >= 1


# ═══ TC-4.2-STORE-09: Quality fields preserved ═══

def test_quality_preserved(tmp_store, rec_0708):
    tmp_store.append(rec_0708)
    loaded = tmp_store.get_by_date(date(2026, 7, 8))

    assert loaded.quality.extraction_status == ExtractionStatus.FULL_COMPLETE
    assert loaded.quality.required_field_coverage >= 0.9
    assert loaded.quality.optional_field_coverage >= 0.5
