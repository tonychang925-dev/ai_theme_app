from __future__ import annotations

import pytest

from database_service.streams.services.semantic_event_deduper import SemanticEventDeduper


class _FakeQwenPrefilter:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.preload_calls = 0
        self.check_calls = 0

    def preload_model(self) -> bool:
        self.preload_calls += 1
        return True

    def check_semantic_duplicate(self, title_a: str, title_b: str) -> bool | None:
        self.check_calls += 1
        return self.result


@pytest.mark.asyncio
async def test_semantic_deduper_routes_high_similarity_near_duplicate_to_qwen() -> None:
    prefilter = _FakeQwenPrefilter(result=True)
    deduper = SemanticEventDeduper(prefilter=prefilter)

    assert await deduper.warmup() is True

    row_a = {"source_channel": "seed_original", "title": "长安汽车5月交付20.91万辆，海外5月交付70700辆，同比增长38%，新能源汽车5月交付92400辆...", "content": "x"}
    row_b = {"source_channel": "injected_test", "title": "据长安汽车消息，长安汽车5月交付209100辆，海外5月交付70700辆，同比增长38%，新能源汽车5月交付92400辆...", "content": "y"}

    result = await deduper._judge_pair(row_a["title"], row_b["title"], row_a, row_b)

    assert result["is_dup"] is True
    assert result["method"] == "qwen"
    assert prefilter.check_calls == 1


@pytest.mark.asyncio
async def test_semantic_deduper_still_auto_merges_extreme_similarity() -> None:
    prefilter = _FakeQwenPrefilter(result=False)
    deduper = SemanticEventDeduper(prefilter=prefilter)

    assert await deduper.warmup() is True

    row_a = {"source_channel": "seed_original", "title": "上汽集团公告，2026年5月整车产量33.46万辆，同比下降18.61%", "content": "x"}
    row_b = {"source_channel": "injected_test", "title": "上汽集团公告，2026年5月整车产量33.46万辆，同比下降18.61%", "content": "y"}

    result = await deduper._judge_pair(row_a["title"], row_b["title"], row_a, row_b)

    assert result["is_dup"] is True
    assert result["method"] == "ratio"
    assert prefilter.check_calls == 0
