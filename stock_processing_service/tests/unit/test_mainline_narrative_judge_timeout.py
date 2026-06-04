from __future__ import annotations

import asyncio

import pytest

from stock_processing_service.domain.services.mainline_discovery.mainline_narrative_judge import (
    MainlineNarrativeJudge,
)


class _SlowParser:
    async def parse_content(self, content: str):
        await asyncio.sleep(0.05)
        return '{"is_mainline_logic": true, "narrative_level": "strong", "supporting_event_ids": ["e1"]}'


@pytest.mark.asyncio
async def test_mainline_narrative_judge_times_out_and_degrades() -> None:
    judge = MainlineNarrativeJudge(parser_factory=lambda: _SlowParser(), timeout_sec=0.01)

    result = await judge.judge(
        subject_key="ai_chip",
        theme_name="AI Chip",
        event_chain=[
            {"event_id": "e1", "title": "event 1", "summary": "s1"},
            {"event_id": "e2", "title": "event 2", "summary": "s2"},
        ],
        event_series=[],
        event_stats={"recent_event_count": 2},
        major_event_classification={"is_fast_line_trigger": False, "major_event_score": 0},
    )

    assert result.narrative_level == "unavailable"
    assert result.diagnostics["skip_reason"] == "llm_failure"
