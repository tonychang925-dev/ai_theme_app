"""Tests for MainlineDiscovery DTO models — Phase 1 PR-1."""
import pytest
from stock_processing_service.domain.services.mainline_discovery.models import (
    MainlineDiscoveryReview,
    MainlineDiscoveryDiagnostics,
    MainlineEvent,
    MainlineEventSeries,
    MainlineLogicEvidence,
    MainlineMarketAcceptance,
    MainlineSubjectBinding,
)


class TestMainlineEvent:
    def test_to_dict(self):
        ev = MainlineEvent(event_id="evt_001", title="政策利好", event_type="policy",
                           impact_score=0.86, confidence=0.90, source_channel="jyhf")
        d = ev.to_dict()
        assert d["event_id"] == "evt_001"
        assert d["impact_score"] == 0.86
        assert d["event_type"] == "policy"

    def test_defaults(self):
        ev = MainlineEvent(event_id="evt_x")
        d = ev.to_dict()
        assert d["event_type"] == "unknown"
        assert d["title"] == ""
        assert d["impact_score"] is None


class TestMainlineEventSeries:
    def test_to_dict_with_events(self):
        s = MainlineEventSeries(
            series_id="ml_001_policy",
            series_type="policy_chain",
            event_count=4,
            active_days_7d=3,
            first_seen="2026-05-18",
            last_seen="2026-05-22",
            logic_summary="持续政策催化",
            consistency_score=72.0,
        )
        d = s.to_dict()
        assert d["event_count"] == 4
        assert d["consistency_score"] == 72.0

    def test_empty_series(self):
        s = MainlineEventSeries(series_id="empty")
        d = s.to_dict()
        assert d["event_count"] == 0


class TestMainlineLogicEvidence:
    def test_with_score(self):
        ev = MainlineLogicEvidence(logic_score=82.5, event_impact_score=80.0)
        d = ev.to_dict()
        assert d["logic_score"] == 82.5
        assert d["event_impact_score"] == 80.0

    def test_null_score(self):
        ev = MainlineLogicEvidence()
        d = ev.to_dict()
        assert d["logic_score"] is None
        assert d["event_chain"] == []


class TestMainlineMarketAcceptance:
    def test_leader_alive(self):
        ma = MainlineMarketAcceptance(market_acceptance_score=78.0, leader_alive=True)
        d = ma.to_dict()
        assert d["leader_alive"] is True
        assert d["market_acceptance_score"] == 78.0

    def test_empty(self):
        ma = MainlineMarketAcceptance()
        d = ma.to_dict()
        assert d["leader_alive"] is False
        assert d["market_acceptance_score"] is None


class TestMainlineSubjectBinding:
    def test_binding(self):
        b = MainlineSubjectBinding(subject_key="9019807", theme_name="卫星互联网", role="core", confidence=0.85)
        d = b.to_dict()
        assert d["role"] == "core"
        assert d["confidence"] == 0.85


class TestMainlineDiscoveryReview:
    def test_confirmed_mainline(self):
        r = MainlineDiscoveryReview(
            trade_date="2026-05-28",
            mainline_id="ml_9019807_202605",
            mainline_name="卫星互联网",
            confirmation_state="confirmed_mainline",
            logic_score=82.0,
            market_acceptance_score=78.0,
            mainline_score=80.0,
            core_subject_keys=["9019807"],
            diagnostics={"reject_reason": None},
        )
        d = r.to_dict()
        assert d["confirmation_state"] == "confirmed_mainline"
        assert d["mainline_id"] == "ml_9019807_202605"
        assert d["mainline_name"] == "卫星互联网"

    def test_rejected(self):
        r = MainlineDiscoveryReview(
            trade_date="2026-05-28",
            mainline_id="ml_reject",
            mainline_name="弱题材",
            confirmation_state="rejected",
            diagnostics={"reject_reason": "logic_and_market_below_threshold"},
        )
        d = r.to_dict()
        assert d["confirmation_state"] == "rejected"
        assert d["diagnostics"]["reject_reason"] is not None


class TestMainlineDiscoveryDiagnostics:
    def test_diagnostics(self):
        diag = MainlineDiscoveryDiagnostics(
            candidate_subject_count=48,
            confirmed_mainline_count=2,
            logic_only_count=4,
            market_noise_count=8,
            rejected_count=34,
            data_quality="ready",
        )
        d = diag.to_dict()
        assert d["confirmed_mainline_count"] == 2
        assert d["data_quality"] == "ready"

    def test_empty(self):
        diag = MainlineDiscoveryDiagnostics()
        d = diag.to_dict()
        assert d["candidate_subject_count"] == 0
