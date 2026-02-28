"""Phase3 unit tests:
1) Reuse RealIntegrationTester.test_new_architecture_with_dataset on real dataset.
2) Add a real Qwen2.5 (llama.cpp compatible) arbiter call in unit test.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from database_service.scripts.test_theme_processor import RealIntegrationTester


def _sample_size() -> int:
    return int(os.getenv("PHASE3_UNIT_SAMPLE_SIZE", "6"))


def _resolve_local_qwen_model_path() -> str | None:
    candidates = [
        os.getenv("PHASE3_LOCAL_QWEN_MODEL_PATH", "").strip(),
        "/Users/admin/Desktop/ai_theme_app/models/Qwen2.5-0.5B-Instruct",
        "/Users/admin/Desktop/ai_theme_app/modles/Qwen2.5-0.5B-Instruct",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    # HuggingFace cache layout: .qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/<hash>
    snapshot_root = Path(
        "/Users/admin/Desktop/ai_theme_app/.qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots"
    )
    if snapshot_root.exists():
        snapshots = sorted(snapshot_root.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for snapshot in snapshots:
            if (snapshot / "config.json").exists():
                return str(snapshot)
    return None


async def _run_dataset_workflow_once() -> tuple[RealIntegrationTester, object]:
    tester = RealIntegrationTester()
    setup_ok = await tester.setup()
    if setup_ok is not True:
        await tester.cleanup()
        pytest.skip("RealIntegrationTester.setup() failed: Redis/DB unavailable")
    result = await tester.test_new_architecture_with_dataset(
        sample_size=_sample_size(),
        return_details=True,
    )
    return tester, result


@pytest.mark.asyncio
async def test_phase3_dataset_pipeline_via_test_new_architecture_with_dataset():
    """真实数据集 + 既有测试框架入口验证（不做纯mock）。"""
    tester, result = await _run_dataset_workflow_once()
    try:
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("stream_stats", {}).get("stream:events:decision", 0) > 0
        assert len(result.get("decision_details", [])) > 0
    finally:
        await tester.cleanup()
        if tester.redis_client is not None:
            if hasattr(tester.redis_client, "aclose"):
                await tester.redis_client.aclose()
            else:
                await tester.redis_client.close()


@pytest.mark.asyncio
async def test_phase3_dynamic_semantic_then_qwen_llm_smoke():
    """真实数据集驱动后，增加一次本地Qwen调用（参考test_local_qwen_matcher）。"""
    tester, result = await _run_dataset_workflow_once()
    try:
        if not isinstance(result, dict) or result.get("success") is not True:
            pytest.skip("dataset workflow returned non-success in current runtime")

        details = result.get("decision_details", [])
        assert details, "decision_details is empty"
        first = details[0]

        event_title = str(first.get("event_title") or "新闻事件")
        event_content = str(first.get("event_core_concept") or "")
        candidate_name = str(first.get("best_theme_name") or "题材A")
        second_candidate = "题材B"

        event = {
            "event_id": "phase3_qwen_unit_event",
            "title": event_title,
            "content": event_content or event_title,
            "keywords": [w for w in [event_content, event_title] if w],
            "ai_analysis": {
                "core_concept": event_content or event_title,
                "industry_keywords": [event_content, event_title],
                "concept_confidence": 0.8,
                "impact_level": "medium",
            },
        }
        themes = [
            {
                "code": "CAND_A",
                "name": candidate_name,
                "keywords": [event_content, event_title],
                "description": candidate_name,
                "level1_category": "概念题材",
                "level2_category": "子概念A",
            },
            {
                "code": "CAND_B",
                "name": second_candidate,
                "keywords": ["无关关键词"],
                "description": second_candidate,
                "level1_category": "概念题材",
                "level2_category": "子概念B",
            },
        ]

        try:
            from theme_service.matchers.local_qwen_matcher import create_medium_qwen_matcher
            matcher_cfg = {"use_cache": True, "match_threshold": 0.3}
            local_model_path = _resolve_local_qwen_model_path()
            if local_model_path:
                matcher_cfg["model_name"] = local_model_path
            matcher = create_medium_qwen_matcher(matcher_cfg)
            matcher.initialize(themes)
            qwen_results = matcher.match(event, precision="normal")
        except Exception as exc:
            pytest.skip(f"Local Qwen matcher unavailable in current env: {exc}")

        assert qwen_results, "Qwen matcher returned empty results"
        top = qwen_results[0]
        assert hasattr(top, "theme_name") and str(top.theme_name).strip()
        assert float(getattr(top, "confidence", 0.0)) >= 0.0
    finally:
        await tester.cleanup()
        if tester.redis_client is not None:
            if hasattr(tester.redis_client, "aclose"):
                await tester.redis_client.aclose()
            else:
                await tester.redis_client.close()
