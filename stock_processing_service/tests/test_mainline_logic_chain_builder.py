"""Tests for MainlineLogicChainBuilder — Phase 1 PR-2."""
import pytest
from datetime import date
from stock_processing_service.domain.services.mainline_discovery.mainline_logic_chain_builder import (
    MainlineLogicChainBuilder,
    MainlineLogicEvidence,
)


class TestMainlineLogicChainBuilder:

    def test_empty_events_returns_none_score(self):
        builder = MainlineLogicChainBuilder(pool=None)
        result = builder._build_for_subject("test_sk", [])
        assert result.logic_score is None
        assert result.event_chain == []
        assert "event_context" in result.diagnostics["missing_fields"]

    def test_single_event_low_score(self):
        builder = MainlineLogicChainBuilder(pool=None)
        events = [
            {"event_id": "e1", "title": "某公司公告", "event_type": "company",
             "occurred_at": "2026-05-28", "confidence": 0.5, "source_channel": "test"},
        ]
        result = builder._build_for_subject("test_sk", events)
        assert result.logic_score is not None
        assert result.logic_score < 65.0  # single event should be below threshold
        assert result.event_impact_score is not None

    def test_consecutive_policy_events_high_score(self):
        builder = MainlineLogicChainBuilder(pool=None)
        events = [
            {"event_id": "e1", "title": "政策支持卫星互联网", "event_type": "policy",
             "occurred_at": "2026-05-28", "confidence": 0.9, "source_channel": "news"},
            {"event_id": "e2", "title": "产业规划出台", "event_type": "policy",
             "occurred_at": "2026-05-27", "confidence": 0.85, "source_channel": "news"},
            {"event_id": "e3", "title": "地方政府跟进", "event_type": "policy",
             "occurred_at": "2026-05-26", "confidence": 0.8, "source_channel": "gov"},
            {"event_id": "e4", "title": "政策推进细则", "event_type": "policy",
             "occurred_at": "2026-05-25", "confidence": 0.85, "source_channel": "news"},
        ]
        result = builder._build_for_subject("test_sk", events)
        assert result.logic_score is not None
        assert result.logic_score >= 65.0  # 4 policy events over 4 days should pass
        assert result.event_continuity_score == 90.0  # active_days_7d >= 4
        assert len(result.event_chain) == 3  # top 3
        assert len(result.event_series) >= 1  # at least 1 series

    def test_mixed_events_lower_narrative(self):
        builder = MainlineLogicChainBuilder(pool=None)
        events = [
            {"event_id": "e1", "title": "政策", "event_type": "policy",
             "occurred_at": "2026-05-28", "confidence": 0.8, "source_channel": "n1"},
            {"event_id": "e2", "title": "公司公告", "event_type": "company",
             "occurred_at": "2026-05-27", "confidence": 0.5, "source_channel": "n2"},
            {"event_id": "e3", "title": "媒体报道", "event_type": "media",
             "occurred_at": "2026-05-26", "confidence": 0.3, "source_channel": "n3"},
        ]
        result = builder._build_for_subject("test_sk", events)
        # Mixed events should have lower narrative consistency
        assert result.narrative_consistency_score is not None
        # Should be less than 70 because no single type dominates
        assert result.narrative_consistency_score <= 70

    def test_deduplication_by_event_id(self):
        builder = MainlineLogicChainBuilder(pool=None)
        events = [
            {"event_id": "e1", "title": "A", "event_type": "policy",
             "occurred_at": "2026-05-28", "confidence": 0.8, "source_channel": "n"},
            {"event_id": "e1", "title": "A duplicate", "event_type": "policy",
             "occurred_at": "2026-05-28", "confidence": 0.8, "source_channel": "n"},
            {"event_id": "e2", "title": "B", "event_type": "policy",
             "occurred_at": "2026-05-27", "confidence": 0.8, "source_channel": "n"},
        ]
        result = builder._build_for_subject("test_sk", events)
        assert result.diagnostics["event_count"] == 2  # deduplicated

    def test_event_chain_limited_to_3(self):
        builder = MainlineLogicChainBuilder(pool=None)
        events = [
            {"event_id": f"e{i}", "title": f"事件{i}", "event_type": "policy",
             "occurred_at": f"2026-05-{28-i:02d}", "confidence": 0.8, "source_channel": "n"}
            for i in range(1, 8)
        ]
        result = builder._build_for_subject("test_sk", events)
        assert len(result.event_chain) == 3

    def test_subject_key_aliases(self):
        builder = MainlineLogicChainBuilder(pool=None)
        row = {"theme_subject_key": "sk_001", "title": "test", "confidence": 0.5}
        assert builder._resolve_subject_key(row) == "sk_001"

        row2 = {"bizKey": "biz_002", "title": "test"}
        assert builder._resolve_subject_key(row2) == "biz_002"

        row3 = {"unknown_field": "xxx"}
        assert builder._resolve_subject_key(row3) == ""

    def test_report_context_extraction(self):
        builder = MainlineLogicChainBuilder(pool=None)
        out: dict[str, list[dict]] = {}
        ctx = {
            "event_theme_map": {
                "9019807": [
                    {"event_id": "e1", "title": "政策A", "event_type": "policy",
                     "occurred_at": "2026-05-28", "confidence": 0.8, "source_channel": "etm"},
                ]
            }
        }
        builder._extract_from_report_context(ctx, out)
        assert "9019807" in out
        assert len(out["9019807"]) == 1
        assert out["9019807"][0]["event_type"] == "policy"

    def test_report_context_list_format(self):
        builder = MainlineLogicChainBuilder(pool=None)
        out: dict[str, list[dict]] = {}
        ctx = {
            "news_event": [
                {"subject_key": "sk_x", "event_id": 123, "title": "新闻",
                 "event_type": "media", "confidence": 0.6, "occurred_at": "2026-05-28",
                 "source_channel": "news"},
            ]
        }
        builder._extract_from_report_context(ctx, out)
        assert "sk_x" in out
        assert len(out["sk_x"]) == 1

    def test_event_series_building(self):
        builder = MainlineLogicChainBuilder(pool=None)
        events = [
            {"event_id": "e1", "title": "政策A", "event_type": "policy",
             "occurred_at": "2026-05-28", "confidence": 0.9, "source_channel": "n"},
            {"event_id": "e2", "title": "政策B", "event_type": "policy",
             "occurred_at": "2026-05-27", "confidence": 0.85, "source_channel": "n"},
            {"event_id": "e3", "title": "政策C", "event_type": "policy",
             "occurred_at": "2026-05-26", "confidence": 0.8, "source_channel": "n"},
        ]
        series = builder._build_event_series("test_sk", events)
        assert len(series) == 1
        assert series[0]["series_type"] == "policy_chain"
        assert series[0]["event_count"] == 3
        assert series[0]["consistency_score"] >= 75

    def test_build_with_candidate_filter(self):
        import asyncio
        builder = MainlineLogicChainBuilder(pool=None)
        ctx = {
            "event_theme_map": {
                "sk_a": [{"event_id": "e1", "title": "A事件", "event_type": "policy",
                          "occurred_at": "2026-05-28", "confidence": 0.9, "source_channel": "etm"}],
                "sk_b": [{"event_id": "e2", "title": "B事件", "event_type": "media",
                          "occurred_at": "2026-05-28", "confidence": 0.4, "source_channel": "etm"}],
            }
        }
        result = asyncio.run(builder.build(
            trade_date=date(2026,5,28),
            candidate_subjects=["sk_a"],
            report_context=ctx,
        ))
        assert "sk_a" in result
        assert result["sk_a"].logic_score is not None
        # sk_b should NOT be in result because it's not a candidate
        assert "sk_b" not in result
        # But if no candidates given, both should be included
        result2 = asyncio.run(builder.build(
            trade_date=date(2026,5,28),
            report_context=ctx,
        ))
        assert "sk_a" in result2
        assert "sk_b" in result2
