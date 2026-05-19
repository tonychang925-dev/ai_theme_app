"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.2b — AuctionConfirmationService Contract Tests                        ║
║  Date: 2026-05-19                                                          ║
║  Purpose: Verify domain service contract, data_status handling, hard rules ║
╚══════════════════════════════════════════════════════════════════════════════╝

Validates:
  1. Domain service has NO SQL / NO I/O
  2. missing data_status → X, reject_reason=auction_data_missing
  3. daily_open_proxy → proxy_* levels, not formal A/B/C
  4. real_auction → formal A/B/C/X
  5. Hard reject rules fire correctly
  6. evidence_json is complete and parseable
  7. All required output fields are present
"""

from __future__ import annotations

import json, sys
from datetime import date, datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ── Imports ─────────────────────────────────────────────────────────────────

from stock_processing_service.domain.services.auction_confirmation_service import (
    AuctionConfirmationResult,
    AuctionConfirmationService,
    AuctionSnapshotData,
    BoardAuctionData,
    CandidateAuctionContext,
)

SVC = AuctionConfirmationService()
TODAY = date.today()
NEXT_DAY = TODAY + timedelta(days=1)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_candidate(**overrides) -> CandidateAuctionContext:
    kwargs = dict(
        trade_date=TODAY,
        stock_id="000001.SZ",
        stock_name="Test Stock",
        subject_key="test_subject",
        theme_name="Test Theme",
        candidate_score=75.0,
        candidate_type="dragon_repair",
        support_type="previous_low",
        support_strength=80.0,
        support_level=10.5,
        weak_type="bad_limit_up",
        pool_entry_type="formal",
        cycle_state="fermentation",
        mainline_strength_score=70.0,
        fade_watch=False,
        fade_confirmed=False,
        expected_open_low=-1.0,
        expected_open_high=5.0,
        need_last_minute_grab=False,
        need_plate_follow=False,
    )
    kwargs.update(overrides)
    return CandidateAuctionContext(**kwargs)


def _make_auction(**overrides) -> AuctionSnapshotData:
    kwargs = dict(
        trade_date=NEXT_DAY,
        stock_id="000001.SZ",
        auction_open_pct=2.5,
        auction_amount=50_000_000.0,
        auction_volume=500_000.0,
        pre_close=10.0,
        price_path_stability_score=85.0,  # low volatility
        last_minute_ratio=0.25,
        has_end_spike=True,
        has_end_drop=False,
        is_red_zone=True,
        data_status="real_auction",
        source_version="auction_snapshot.v1.timeline",
        source_trace={"record_mode": "timeline_enhanced"},
        auction_close_pct=3.0,
        auction_high_pct=3.5,
        auction_low_pct=2.0,
    )
    kwargs.update(overrides)
    return AuctionSnapshotData(**kwargs)


def _make_board(**overrides) -> BoardAuctionData:
    kwargs = dict(
        subject_key="test_subject",
        plate_red_ratio=0.60,
        plate_leader_strength=0.45,
    )
    kwargs.update(overrides)
    return BoardAuctionData(**kwargs)


def _assert_fields_present(result: AuctionConfirmationResult):
    """All required output fields must be present and non-None."""
    fields = [
        "auction_confirm_score", "auction_confirm_level", "auction_confirm_source",
        "price_strength_score", "pattern_stability_score", "last_minute_grab_score",
        "plate_follow_score", "risk_penalty", "decision", "approved",
        "hard_reject_reasons", "reject_reason", "data_status", "rule_version",
        "evidence_json",
    ]
    for f in fields:
        val = getattr(result, f)
        assert val is not None, f"Field {f} is None"


def _parse_evidence(result: AuctionConfirmationResult) -> dict:
    """Evidence JSON must be valid and complete."""
    ev = json.loads(result.evidence_json)
    assert ev["schema_version"] == "auction_confirmation_evidence.v1"
    assert "trace" in ev
    assert "inputs" in ev
    assert "scores" in ev
    assert "rules" in ev
    assert "decision" in ev
    return ev


# ── Tests ───────────────────────────────────────────────────────────────────


def test_missing_auction_data():
    """data_status=missing → X, reject_reason=auction_data_missing"""
    candidate = _make_candidate()
    result = SVC.confirm(candidate, auction=None)
    assert result.auction_confirm_level == "X"
    assert result.auction_confirm_source == "missing"
    assert result.data_status == "missing"
    assert result.decision == "no_decision"
    assert result.approved is False
    assert "auction_data_missing" in result.hard_reject_reasons
    assert result.reject_reason == "auction_data_missing"
    _assert_fields_present(result)
    _parse_evidence(result)
    print(f"  PASS test_missing_auction_data")


def test_missing_data_status_in_auction():
    """Auction with data_status='missing' → X"""
    candidate = _make_candidate()
    auction = _make_auction(data_status="missing")
    result = SVC.confirm(candidate, auction)
    assert result.auction_confirm_level == "X"
    assert result.data_status == "missing"
    assert "data_status=missing" in result.hard_reject_reasons
    print(f"  PASS test_missing_data_status_in_auction")


def test_daily_open_proxy_produces_proxy_levels():
    """daily_open_proxy → proxy_A/proxy_B/proxy_C (NOT formal A/B/C)"""
    candidate = _make_candidate()
    auction = _make_auction(
        data_status="daily_open_proxy",
        source_version="auction_snapshot.v1",
        source_trace={"record_mode": "single_point"},
        # Strong signal
        auction_open_pct=2.0,
        auction_close_pct=2.5,
        price_path_stability_score=90.0,
        has_end_spike=True,
        has_end_drop=False,
        last_minute_ratio=0.30,
    )
    board = _make_board(plate_red_ratio=0.70, plate_leader_strength=0.55)
    result = SVC.confirm(candidate, auction, board)

    # Must be proxy_* level, not A/B/C
    assert result.auction_confirm_source == "daily_open_proxy"
    assert result.auction_confirm_level.startswith("proxy_"), (
        f"Expected proxy_* level, got {result.auction_confirm_level}"
    )
    assert result.auction_confirm_level in {"proxy_A", "proxy_B", "proxy_C"}
    assert result.data_status == "daily_open_proxy"
    print(f"  PASS test_daily_open_proxy_produces_proxy_levels (level={result.auction_confirm_level})")


def test_real_auction_produces_formal_levels():
    """real_auction → A/B/C/X (NOT proxy_*)"""
    candidate = _make_candidate()
    auction = _make_auction(
        data_status="real_auction",
        auction_open_pct=2.0,
        auction_close_pct=2.5,
        price_path_stability_score=90.0,
        has_end_spike=True,
        last_minute_ratio=0.30,
    )
    board = _make_board(plate_red_ratio=0.70, plate_leader_strength=0.55)
    result = SVC.confirm(candidate, auction, board)

    assert result.auction_confirm_source == "real_auction"
    assert result.auction_confirm_level in {"A", "B", "C", "X"}
    assert not result.auction_confirm_level.startswith("proxy_")
    print(f"  PASS test_real_auction_produces_formal_levels (level={result.auction_confirm_level})")


def test_fade_confirmed_hard_reject():
    """fade_confirmed=True → hard reject"""
    candidate = _make_candidate(fade_confirmed=True)
    auction = _make_auction()
    result = SVC.confirm(candidate, auction)
    assert "fade_confirmed" in result.hard_reject_reasons
    assert result.decision in {"reject", "observe_only", "no_decision"}
    print(f"  PASS test_fade_confirmed_hard_reject")


def test_pool_entry_not_formal_hard_reject():
    """pool_entry_type != formal → hard reject with observe_only"""
    candidate = _make_candidate(pool_entry_type="observe_only")
    auction = _make_auction()
    result = SVC.confirm(candidate, auction)
    assert "pool_entry_not_formal" in result.hard_reject_reasons
    assert result.decision == "observe_only"
    assert result.auction_confirm_level == "X"
    print(f"  PASS test_pool_entry_not_formal_hard_reject")


def test_tail_drop_hard_reject():
    """has_end_drop=True → hard reject"""
    candidate = _make_candidate()
    auction = _make_auction(has_end_drop=True, has_end_spike=False)
    result = SVC.confirm(candidate, auction)
    assert "tail_drop" in result.hard_reject_reasons
    print(f"  PASS test_tail_drop_hard_reject")


def test_volatility_too_high_hard_reject():
    """price_path_stability_score=20 → volatility=80 > 70"""
    candidate = _make_candidate()
    auction = _make_auction(price_path_stability_score=20.0)
    result = SVC.confirm(candidate, auction)
    assert "volatility_too_high" in result.hard_reject_reasons
    print(f"  PASS test_volatility_too_high_hard_reject")


def test_need_last_minute_grab_not_present():
    """need_last_minute_grab=True but no grab → hard reject"""
    candidate = _make_candidate(need_last_minute_grab=True)
    auction = _make_auction(last_minute_ratio=0.05, has_end_spike=False)
    result = SVC.confirm(candidate, auction)
    assert "no_last_minute_grab" in result.hard_reject_reasons
    print(f"  PASS test_need_last_minute_grab_not_present")


def test_close_not_red_and_support_weak():
    """auction_close_pct < -1% and support_strength < 30 → hard reject"""
    candidate = _make_candidate(support_strength=20.0)
    auction = _make_auction(auction_close_pct=-2.0)
    result = SVC.confirm(candidate, auction)
    assert "close_not_red_and_support_weak" in result.hard_reject_reasons
    print(f"  PASS test_close_not_red_and_support_weak")


def test_plate_retreat_hard_reject():
    """need_plate_follow + plate_red_ratio < 0.20 + not fade_watch → hard reject"""
    candidate = _make_candidate(need_plate_follow=True, fade_watch=False)
    auction = _make_auction()
    board = _make_board(plate_red_ratio=0.10)
    result = SVC.confirm(candidate, auction, board)
    assert "plate_retreat" in result.hard_reject_reasons
    print(f"  PASS test_plate_retreat_hard_reject")


def test_strong_signal_scores_high():
    """Optimal auction data → score >= A threshold (>=75)"""
    candidate = _make_candidate(
        expected_open_low=-1.0,
        expected_open_high=5.0,
    )
    auction = _make_auction(
        auction_open_pct=3.0,       # in expected range
        auction_close_pct=3.5,      # red
        price_path_stability_score=92.0,  # very stable
        has_end_spike=True,
        last_minute_ratio=0.40,
    )
    board = _make_board(plate_red_ratio=0.75, plate_leader_strength=0.60)
    result = SVC.confirm(candidate, auction, board)

    assert result.auction_confirm_score >= SVC.A_THRESHOLD, f"Expected >= {SVC.A_THRESHOLD}, got {result.auction_confirm_score}"
    assert result.auction_confirm_level in {"A", "proxy_A"}
    assert result.approved is True
    print(f"  PASS test_strong_signal_scores_high (score={result.auction_confirm_score}, level={result.auction_confirm_level})")


def test_weak_signal_scores_low():
    """Weak auction data → score < B threshold (<55)"""
    candidate = _make_candidate()
    auction = _make_auction(
        auction_open_pct=-1.5,
        auction_close_pct=-1.0,
        price_path_stability_score=50.0,  # volatile
        has_end_spike=False,
        has_end_drop=False,
        last_minute_ratio=0.05,
    )
    board = _make_board(plate_red_ratio=0.25, plate_leader_strength=0.10)
    result = SVC.confirm(candidate, auction, board)

    assert result.auction_confirm_score < SVC.B_THRESHOLD, f"Expected < {SVC.B_THRESHOLD}, got {result.auction_confirm_score}"
    assert result.auction_confirm_level in {"C", "proxy_C"}
    assert result.approved is False
    print(f"  PASS test_weak_signal_scores_low (score={result.auction_confirm_score}, level={result.auction_confirm_level})")


def test_evidence_json_complete():
    """Evidence JSON must be complete and parseable"""
    candidate = _make_candidate()
    auction = _make_auction()
    board = _make_board()
    result = SVC.confirm(candidate, auction, board)

    ev = json.loads(result.evidence_json)
    # Check structure
    assert ev["rule_version"] == "auction_confirmation.v2"
    assert ev["trace"]["stock_id"] == "000001.SZ"
    assert ev["inputs"]["support_type"] == "previous_low"
    assert ev["inputs"]["support_strength"] == 80.0
    assert ev["scores"]["price_strength"] > 0
    assert isinstance(ev["scores"]["breakdown"]["auction_open_pct"], (int, float))
    assert len(ev["rules"]["hard_rule_results"]) >= 1
    assert ev["decision"]["signal_level"] in {"A", "B", "C", "X", "proxy_A", "proxy_B", "proxy_C", "proxy_X"}
    assert ev["decision"]["data_status"] == "real_auction"
    print(f"  PASS test_evidence_json_complete")


def test_no_sql_no_io():
    """Domain service must not import or use any IO/SQL modules."""
    import inspect
    src = inspect.getsource(AuctionConfirmationService)
    forbidden = ["asyncpg", "execute(", "fetch(", "INSERT", "UPDATE", "DELETE", "SELECT"]
    for token in forbidden:
        assert token not in src, f"Forbidden token '{token}' found in AuctionConfirmationService"
    print(f"  PASS test_no_sql_no_io")


def test_scoring_bounds():
    """All score components must be within their defined bounds."""
    candidate = _make_candidate()
    auction = _make_auction()
    board = _make_board()
    result = SVC.confirm(candidate, auction, board)

    assert 0 <= result.price_strength_score <= 30, f"price_strength: {result.price_strength_score}"
    assert 0 <= result.pattern_stability_score <= 25, f"pattern_stability: {result.pattern_stability_score}"
    assert 0 <= result.last_minute_grab_score <= 25, f"last_minute_grab: {result.last_minute_grab_score}"
    assert 0 <= result.plate_follow_score <= 20, f"plate_follow: {result.plate_follow_score}"
    assert 0 <= result.risk_penalty <= 30, f"risk_penalty: {result.risk_penalty}"
    assert 0 <= result.auction_confirm_score <= 100, f"confirm_score: {result.auction_confirm_score}"
    print(f"  PASS test_scoring_bounds")


def test_edge_case_support_strength_zero():
    """Edge case: support_strength=0 should work without error"""
    candidate = _make_candidate(support_strength=0.0)
    auction = _make_auction()
    result = SVC.confirm(candidate, auction)
    assert result.auction_confirm_level is not None
    print(f"  PASS test_edge_case_support_strength_zero")


def test_edge_case_extreme_open():
    """Edge case: extreme open >7% should trigger risk penalty"""
    candidate = _make_candidate(expected_open_high=5.0)
    auction = _make_auction(auction_open_pct=9.0, auction_close_pct=9.5)
    result = SVC.confirm(candidate, auction)
    assert result.risk_penalty >= 6.0, f"Expected risk_penalty >= 6 for extreme open, got {result.risk_penalty}"
    print(f"  PASS test_edge_case_extreme_open (risk_penalty={result.risk_penalty})")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*70}")
    print(f"  v2.2b AuctionConfirmationService — CONTRACT TESTS")
    print(f"{'='*70}\n")

    passed = 0
    failed = 0
    tests = [
        test_missing_auction_data,
        test_missing_data_status_in_auction,
        test_daily_open_proxy_produces_proxy_levels,
        test_real_auction_produces_formal_levels,
        test_fade_confirmed_hard_reject,
        test_pool_entry_not_formal_hard_reject,
        test_tail_drop_hard_reject,
        test_volatility_too_high_hard_reject,
        test_need_last_minute_grab_not_present,
        test_close_not_red_and_support_weak,
        test_plate_retreat_hard_reject,
        test_strong_signal_scores_high,
        test_weak_signal_scores_low,
        test_evidence_json_complete,
        test_no_sql_no_io,
        test_scoring_bounds,
        test_edge_case_support_strength_zero,
        test_edge_case_extreme_open,
    ]

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL {test_fn.__name__}: {e}")

    print(f"\n{'─'*70}")
    print(f"  Results: {passed}/{passed+failed} passed, {failed} failed")
    print(f"{'─'*70}")

    if failed > 0:
        print(f"\n  ❌ CONTRACT TESTS FAILED")
        return 1
    else:
        print(f"\n  ✅ ALL CONTRACT TESTS PASSED")
        return 0


if __name__ == "__main__":
    exit(main())
