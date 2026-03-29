"""Phase3 embedded-LLM test harness on top of baseline test_theme_processor flow.

Design intent:
- Reuse RealIntegrationTester.test_new_architecture_with_dataset as baseline.
- Inject LLM gates into Stage1/Stage2 via monkeypatch, not by replacing pipeline.
- Enforce FEATURE_SPEC_P1.phase3 §2.5 spirit: LLM participates in both classification
  and theme-matching decisions, not only tail-end post-check.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pytest

from database_service.scripts.test_theme_processor import RealIntegrationTester
from database_service.streams.handlers.theme_processor import ThemeProcessor


def _flatten_text_parts(parts: Iterable[Any]) -> str:
    normalized: List[str] = []
    for item in parts:
        if item is None:
            continue
        if isinstance(item, (list, tuple, set)):
            normalized.append(_flatten_text_parts(item))
            continue
        if isinstance(item, dict):
            normalized.append(_flatten_text_parts(item.values()))
            continue
        normalized.append(str(item))
    return " ".join(p for p in normalized if p).strip()


def _extract_terms(text: str) -> set[str]:
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text or "")
    return set(t.lower() for t in tokens if len(t) >= 2)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


@dataclass
class PairScore:
    candidate: Dict[str, Any]
    score: float
    overlap_count: int
    semantic_confidence: float


class CandidateScopedLLMReviewer:
    """Candidate-scoped LLM reviewer (lightweight, deterministic for tests).

    The reviewer intentionally does not re-search full theme library. It only judges
    candidate set from current stage output, matching the agreed phase3 strategy.
    """

    def __init__(
        self,
        *,
        pair_pass_threshold: float = 0.62,
        high_semantic_threshold: float = 0.86,
    ) -> None:
        self.pair_pass_threshold = pair_pass_threshold
        self.high_semantic_threshold = high_semantic_threshold

    def _request_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def _event_terms(self, event_data: Dict[str, Any]) -> set[str]:
        ai = event_data.get("ai_analysis", {}) or {}
        text = _flatten_text_parts(
            [
                event_data.get("title"),
                event_data.get("content"),
                ai.get("core_concept"),
                ai.get("industry_keywords"),
                ai.get("keywords"),
            ]
        )
        return _extract_terms(text)

    def _candidate_terms(self, candidate: Dict[str, Any]) -> set[str]:
        tags = candidate.get("tags", {})
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = {}
        text = _flatten_text_parts(
            [
                candidate.get("name"),
                candidate.get("description"),
                candidate.get("level1_category"),
                candidate.get("level2_category"),
                candidate.get("level3_category"),
                candidate.get("keywords"),
                tags.get("keywords") if isinstance(tags, dict) else None,
            ]
        )
        return _extract_terms(text)

    def _extract_candidates_from_stage2(self, stage2_decision: Dict[str, Any]) -> List[Dict[str, Any]]:
        match_result = stage2_decision.get("match_result", {}) or {}
        themes = match_result.get("themes") or []
        if isinstance(themes, list) and themes:
            return [t for t in themes if isinstance(t, dict)]

        best_match = match_result.get("best_match", {}) or {}
        if isinstance(best_match, dict) and best_match:
            return [best_match]

        top_theme = stage2_decision.get("theme_data", {}) or {}
        if isinstance(top_theme, dict) and top_theme:
            return [top_theme]

        return []

    def _pair_score(self, event_data: Dict[str, Any], candidate: Dict[str, Any]) -> PairScore:
        event_terms = self._event_terms(event_data)
        candidate_terms = self._candidate_terms(candidate)
        overlap = event_terms & candidate_terms
        overlap_count = len(overlap)

        semantic_confidence = _safe_float(
            candidate.get("confidence", candidate.get("match_confidence", 0.0)),
            0.0,
        )

        # Candidate-scoped score: overlap drives correctness, semantic is secondary.
        score = min(1.0, semantic_confidence * 0.6 + min(overlap_count, 5) * 0.1)
        return PairScore(
            candidate=candidate,
            score=score,
            overlap_count=overlap_count,
            semantic_confidence=semantic_confidence,
        )

    def _candidate_to_theme_data(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        theme_id = candidate.get("theme_id", candidate.get("id"))
        return {
            "id": theme_id,
            "theme_id": theme_id,
            "name": candidate.get("theme_name", candidate.get("name")),
            "code": candidate.get("theme_code", candidate.get("code")),
            "heat_score": candidate.get("heat_score"),
            "match_confidence": candidate.get("confidence", candidate.get("match_confidence", 0.0)),
        }

    async def review_stage1(
        self,
        *,
        event_data: Dict[str, Any],
        category_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        matched = bool(category_result.get("matched"))
        neighbors = (
            category_result.get("neighbor_candidates")
            or category_result.get("nearest_categories")
            or category_result.get("fallback_candidates")
            or []
        )
        request_id = self._request_id("stage1")

        if matched:
            return {
                "decision": "accept_category",
                "confidence": max(0.8, _safe_float(category_result.get("confidence"), 0.0)),
                "request_id": request_id,
                "model_name": "Qwen2.5-0.5B-Instruct",
                "timestamp": time.time(),
            }

        if isinstance(neighbors, list) and neighbors:
            best = neighbors[0]
            rerouted_info = best.get("category_info") if isinstance(best, dict) else None
            return {
                "decision": "reroute_category",
                "confidence": 0.72,
                "request_id": request_id,
                "model_name": "Qwen2.5-0.5B-Instruct",
                "timestamp": time.time(),
                "rerouted_category_info": rerouted_info,
            }

        # Fail-close to manual path when no reliable candidate exists.
        return {
            "decision": "category_uncertain",
            "confidence": 0.0,
            "request_id": request_id,
            "model_name": "Qwen2.5-0.5B-Instruct",
            "timestamp": time.time(),
        }

    async def review_stage2(
        self,
        *,
        event_data: Dict[str, Any],
        stage2_decision: Dict[str, Any],
        stream_type: str,
    ) -> Dict[str, Any]:
        request_id = self._request_id("stage2")
        candidates = self._extract_candidates_from_stage2(stage2_decision)
        if not candidates:
            return {
                "decision": "need_new_theme" if stream_type == "major" else "need_pending_cluster",
                "confidence": 0.0,
                "request_id": request_id,
                "model_name": "Qwen2.5-0.5B-Instruct",
                "timestamp": time.time(),
            }

        scored = [self._pair_score(event_data, c) for c in candidates]
        scored.sort(key=lambda x: x.score, reverse=True)
        best = scored[0]

        # Strong semantic but zero term overlap => classic false-positive pattern.
        if best.semantic_confidence >= self.high_semantic_threshold and best.overlap_count == 0:
            decision = "downgrade_no_match"
        elif best.score >= self.pair_pass_threshold and best.overlap_count >= 1:
            decision = "accept_match"
        else:
            decision = "need_new_theme" if stream_type == "major" else "need_pending_cluster"

        result = {
            "decision": decision,
            "confidence": best.score,
            "request_id": request_id,
            "model_name": "Qwen2.5-0.5B-Instruct",
            "timestamp": time.time(),
            "selected_theme_data": self._candidate_to_theme_data(best.candidate),
            "pair_overlap_count": best.overlap_count,
            "pair_semantic_confidence": best.semantic_confidence,
        }
        return result


@contextlib.contextmanager
def patch_theme_processor_with_embedded_llm(reviewer: CandidateScopedLLMReviewer):
    """Inject stage1/stage2 LLM gates without replacing baseline pipeline."""

    orig_infer = ThemeProcessor._infer_category_with_cache
    orig_stage1_failed = ThemeProcessor._process_stage_one_failed
    orig_stage2 = ThemeProcessor._process_stage_two_match

    async def wrapped_infer(self, event_id, event_data):
        category_result = await orig_infer(self, event_id, event_data)
        if not isinstance(category_result, dict):
            return category_result

        review = await reviewer.review_stage1(event_data=event_data, category_result=category_result)
        category_result["llm_stage1_review"] = review

        if review.get("decision") == "reroute_category":
            rerouted = review.get("rerouted_category_info")
            if isinstance(rerouted, dict) and rerouted:
                category_result["matched"] = True
                category_result["category_info"] = rerouted
                category_result["confidence"] = max(
                    _safe_float(category_result.get("confidence"), 0.0),
                    _safe_float(review.get("confidence"), 0.0),
                )
        elif review.get("decision") in {"category_uncertain", "abstain"}:
            category_result["matched"] = False
            category_result["force_manual_review"] = True
        return category_result

    async def wrapped_stage1_failed(self, stream_type, event_data, category_result, message_id):
        if isinstance(category_result, dict):
            review = category_result.get("llm_stage1_review", {}) or {}
            if review.get("decision") in {"category_uncertain", "abstain"}:
                decision = self._build_decision(
                    decision_type="CATEGORY_LLM_UNCERTAIN",
                    event_data=event_data,
                    stream_type=stream_type,
                    category_info=category_result,
                    confidence=category_result.get("confidence", 0),
                    reason="llm_stage1_uncertain_manual_review",
                    source="llm_stage1_review",
                )
                decision["judge_source"] = "final_judge"
                decision["judge_applied"] = True
                decision["manual_review_required"] = True
                decision["llm_stage1_review"] = review
                return decision
        return await orig_stage1_failed(self, stream_type, event_data, category_result, message_id)

    async def wrapped_stage2(self, stream_type, event_data, category_info, category_confidence, message_id):
        decision = await orig_stage2(self, stream_type, event_data, category_info, category_confidence, message_id)
        if not isinstance(decision, dict):
            return decision

        review = await reviewer.review_stage2(
            event_data=event_data,
            stage2_decision=decision,
            stream_type=stream_type,
        )
        decision["llm_stage2_review"] = review
        decision["judge_source"] = "final_judge"
        decision["judge_applied"] = True

        outcome = review.get("decision")
        if outcome in {"accept_match", "switch_theme", "recover_match"}:
            decision["action"] = "update_theme"
            selected_theme = review.get("selected_theme_data")
            if isinstance(selected_theme, dict) and selected_theme.get("id"):
                decision["theme_data"] = selected_theme
        elif outcome == "need_new_theme":
            decision["action"] = "create_new_theme"
        elif outcome in {"need_pending_cluster", "confirm_no_match", "downgrade_no_match"}:
            # Keep major no-match creating new themes; normal goes to pending/manual.
            decision["action"] = "create_new_theme" if stream_type == "major" else "publish_clustering"
            if outcome in {"confirm_no_match", "downgrade_no_match"}:
                decision["manual_review_required"] = True
        else:
            decision["action"] = "publish_clustering"
            decision["manual_review_required"] = True
        return decision

    ThemeProcessor._infer_category_with_cache = wrapped_infer
    ThemeProcessor._process_stage_one_failed = wrapped_stage1_failed
    ThemeProcessor._process_stage_two_match = wrapped_stage2
    try:
        yield
    finally:
        ThemeProcessor._infer_category_with_cache = orig_infer
        ThemeProcessor._process_stage_one_failed = orig_stage1_failed
        ThemeProcessor._process_stage_two_match = orig_stage2


def test_phase3_llm_pairwise_gate_blocks_high_semantic_but_unrelated_match():
    reviewer = CandidateScopedLLMReviewer(pair_pass_threshold=0.62, high_semantic_threshold=0.85)
    event_data = {
        "event_id": "evt_spacex",
        "title": "SpaceX估值翻倍并筹备IPO",
        "content": "SpaceX相关融资推进，市场关注航天产业链。",
        "ai_analysis": {
            "core_concept": "SpaceX IPO",
            "industry_keywords": ["SpaceX", "航天", "卫星", "军工采购"],
        },
    }
    stage2_decision = {
        "match_result": {
            "themes": [
                {
                    "id": "theme_fusion",
                    "name": "核聚变产业化",
                    "description": "核聚变材料与反应堆商业化",
                    "confidence": 0.91,
                    "tags": {"keywords": ["核聚变", "托卡马克", "聚变堆"]},
                }
            ]
        }
    }

    import asyncio

    result = asyncio.run(
        reviewer.review_stage2(
            event_data=event_data,
            stage2_decision=stage2_decision,
            stream_type="major",
        )
    )
    assert result["decision"] == "downgrade_no_match"
    assert result["pair_overlap_count"] == 0


@pytest.mark.asyncio
async def test_phase3_embedded_llm_pipeline_via_test_new_architecture_with_dataset():
    """Real integration smoke: baseline flow + embedded llm gates."""

    tester = RealIntegrationTester()
    setup_ok = await tester.setup()
    if not setup_ok:
        pytest.skip("integration dependency unavailable (redis/db/theme service)")

    sample_size = int(os.getenv("PHASE3_EMBEDDED_SAMPLE_SIZE", "10"))
    reviewer = CandidateScopedLLMReviewer()
    try:
        with patch_theme_processor_with_embedded_llm(reviewer):
            result = await tester.test_new_architecture_with_dataset(
                sample_size=sample_size,
                return_details=True,
            )
    finally:
        await tester.cleanup()

    assert isinstance(result, dict), "baseline result should return details dict"
    assert result.get("success") is True, f"pipeline failed: {result}"

    details = result.get("decision_details", []) or []
    assert len(details) > 0, "decision stream details should not be empty"

    llm_touched = [
        d
        for d in details
        if d.get("llm_stage1_decision") or d.get("llm_stage2_decision")
    ]
    assert len(llm_touched) > 0, "embedded LLM gate evidence is missing from decisions"

    # Small smoke threshold for integration noise; full threshold in benchmark scripts.
    coverage = len(llm_touched) / len(details)
    assert coverage >= 0.5, f"embedded llm coverage too low: {coverage:.2f}"
