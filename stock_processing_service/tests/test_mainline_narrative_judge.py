"""Tests for MainlineNarrativeJudge — PR-4B.

All tests use mock parsers — no real LLM calls.
"""
import json
import pytest
import asyncio
from stock_processing_service.domain.services.mainline_discovery.mainline_narrative_judge import (
    MainlineNarrativeJudge,
    NarrativeJudgeResult,
)


# ── mock parser helpers ──

def _mock_parser_factory(return_value: dict | str | None, delay: float = 0.0):
    """Create a parser factory that returns the given value."""
    class MockParser:
        async def parse_content(self, prompt, system_prompt, model, timeout):
            if isinstance(return_value, str):
                return return_value
            if isinstance(return_value, dict):
                return json.dumps(return_value)
            if return_value is None:
                raise RuntimeError("mock parser error")
            return str(return_value)
    return lambda: MockParser()


def _build_strong_narrative_response():
    return {
        "is_mainline_logic": True,
        "narrative_score": 82.0,
        "narrative_level": "strong",
        "logic_type": "policy_industry_chain",
        "impact_scope": "industry_chain",
        "time_horizon": "multi_week",
        "narrative_consistency_score": 86.0,
        "novelty_score": 72.0,
        "event_continuity_assessment": "continuous",
        "supporting_event_ids": ["e1", "e2", "e3"],
        "negative_reasons": [],
        "logic_summary": "多条事件共同指向产业链级催化",
        "confidence": 0.84,
    }


def _build_events():
    return [
        {"event_id": "e1", "event_date": "2026-04-29", "title": "国务院发布卫星互联网产业规划",
         "summary": "重大政策", "event_type": "policy", "impact_score": 0.9, "confidence": 0.85,
         "source_table": "theme_history_event"},
        {"event_id": "e2", "event_date": "2026-04-28", "title": "发改委配套实施细则",
         "summary": "政策跟进", "event_type": "policy", "impact_score": 0.85, "confidence": 0.8,
         "source_table": "theme_history_event"},
        {"event_id": "e3", "event_date": "2026-04-27", "title": "地方产业基金落地",
         "summary": "产业支持", "event_type": "industry", "impact_score": 0.75, "confidence": 0.7,
         "source_table": "theme_history_event"},
    ]


# ── tests ──

class TestMainlineNarrativeJudge:

    def test_empty_event_chain_skips_llm(self):
        """Precheck: empty events → insufficient without LLM call."""
        judge = MainlineNarrativeJudge(parser_factory=None)
        result = asyncio.run(judge.judge(event_chain=[]))
        assert result.is_mainline_logic is False
        assert result.narrative_level == "insufficient"
        assert result.narrative_score is None
        assert "事件链为空" in str(result.negative_reasons)

    def test_single_non_major_event_skips_llm(self):
        """Precheck: single non-major event → insufficient."""
        judge = MainlineNarrativeJudge(parser_factory=None)
        events = [{"event_id": "e1", "title": "某公司公告", "impact_score": 0.3}]
        result = asyncio.run(judge.judge(event_chain=events))
        assert result.is_mainline_logic is False
        assert result.narrative_level == "insufficient"
        assert result.diagnostics["skip_reason"] == "single_non_major_event"

    def test_strong_narrative_from_llm(self):
        """Normal strong narrative returned by LLM."""
        judge = MainlineNarrativeJudge(parser_factory=_mock_parser_factory(_build_strong_narrative_response()))
        events = _build_events()
        result = asyncio.run(judge.judge(event_chain=events, subject_key="test", theme_name="测试"))
        assert result.is_mainline_logic is True
        assert result.narrative_score == 82.0
        assert result.narrative_level == "strong"
        assert result.supporting_event_ids == ["e1", "e2", "e3"]
        assert result.method == "llm_narrative_judge_v1"

    def test_empty_supporting_ids_downgraded(self):
        """Forced downgrade: empty supporting_event_ids → not strong."""
        raw = _build_strong_narrative_response()
        raw["supporting_event_ids"] = []
        raw["narrative_level"] = "strong"
        judge = MainlineNarrativeJudge(parser_factory=_mock_parser_factory(raw))
        events = _build_events()
        result = asyncio.run(judge.judge(event_chain=events))
        assert result.is_mainline_logic is False
        assert result.narrative_level == "insufficient"
        assert result.narrative_score <= 49.0
        assert "forced_downgrade" in result.diagnostics

    def test_invalid_event_ids_removed(self):
        """Validation: event IDs not in input → removed."""
        raw = _build_strong_narrative_response()
        raw["supporting_event_ids"] = ["e999", "e888"]  # not in input
        judge = MainlineNarrativeJudge(parser_factory=_mock_parser_factory(raw))
        events = _build_events()
        result = asyncio.run(judge.judge(event_chain=events))
        assert result.supporting_event_ids == []
        assert result.is_mainline_logic is False
        assert result.diagnostics["invalid_event_ids_removed"] == 2

    def test_invalid_json_fallback(self):
        """LLM returns non-JSON → fallback insufficient."""
        judge = MainlineNarrativeJudge(parser_factory=_mock_parser_factory("not valid json {{{"))
        events = _build_events()
        result = asyncio.run(judge.judge(event_chain=events))
        assert result.narrative_level == "unavailable"
        assert result.is_mainline_logic is False

    def test_parser_exception_fallback(self):
        """LLM parser throws → fallback without crashing."""
        judge = MainlineNarrativeJudge(parser_factory=_mock_parser_factory(None))  # None triggers RuntimeError
        events = _build_events()
        result = asyncio.run(judge.judge(event_chain=events))
        assert result.narrative_level == "unavailable"
        assert result.is_mainline_logic is False

    def test_score_clamp(self):
        """Score outside 0-100 → clamped."""
        raw = _build_strong_narrative_response()
        raw["narrative_score"] = 150.0
        raw["confidence"] = 2.5
        judge = MainlineNarrativeJudge(parser_factory=_mock_parser_factory(raw))
        events = _build_events()
        result = asyncio.run(judge.judge(event_chain=events))
        assert result.narrative_score == 100.0  # clamped
        assert result.confidence == 1.0  # clamped

    def test_to_dict_output(self):
        """Verify to_dict() works on result."""
        r = NarrativeJudgeResult(
            is_mainline_logic=True,
            narrative_score=80.0,
            narrative_level="strong",
            supporting_event_ids=["e1"],
            logic_summary="test",
        )
        d = r.to_dict()
        assert d["narrative_score"] == 80.0
        assert d["is_mainline_logic"] is True
        assert d["method"] == "llm_narrative_judge_v1"
