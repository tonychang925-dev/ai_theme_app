"""TC-P1P2-003 architecture guard tests.

Purpose:
- Validate the real architecture constraints behind ACC-P1-P2-03.
- Avoid generic workflow-only assertions.

Guards:
1) No random/zero-vector path should produce final semantic match decisions.
2) `generate_theme_data_only` must reuse upstream classification source and
   must not trigger secondary category inference in create flow.
3) ADR audit must include ADR-006 and ADR-011 with complete decision sections.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed
from theme_service.matchers.keyword_matcher import KeywordMatcher
from theme_service.matchers.semantic_matcher import TransformerSemanticMatcher
from theme_service.services.theme_service import ThemeService


def _unit(v):
    arr = np.array(v, dtype=float)
    norm = np.linalg.norm(arr)
    return arr / norm if norm else arr


def _build_min_semantic_matcher() -> TransformerSemanticMatcher:
    matcher = TransformerSemanticMatcher(
        {"semantic_threshold": 0.9, "enable_ai_boost": False, "max_results": 5}
    )
    matcher.initialized = True
    matcher.themes = {
        "T1": {"name": "半导体设备"},
        "T2": {"name": "人工智能应用"},
    }
    matcher.theme_embeddings = {
        "T1": _unit([1.0, 0.0, 0.0]),
        "T2": _unit([0.0, 1.0, 0.0]),
    }
    matcher.theme_keywords_cache = {
        "T1": ["半导体", "设备"],
        "T2": ["人工智能", "应用"],
    }
    return matcher


def test_tc003_no_zero_vector_final_decision_runtime():
    """TC-P1P2-003A / ACC-P1-P2-03: zero-vector path must not output final semantic decision."""
    matcher = _build_min_semantic_matcher()

    # Force anomaly path (zero vector embedding) and verify no final match.
    matcher._encode_text = lambda _text: np.zeros(3)  # type: ignore[attr-defined]
    results = matcher._match_themes_semantic(
        "异常输入文本",
        ["半导体"],
        {"event_id": "evt_zero_vec", "title": "异常输入", "content": "异常输入"},
    )
    assert results == [] or len(results) == 0, "zero-vector path still produced final decisions"


def test_tc003_generator_must_not_secondary_inference_when_upstream_given():
    """TC-P1P2-003B / ACC-P1-P2-03 + ADR-011: upstream classification should bypass _match_categories."""
    categories = [
        {
            "category_code": "630000",
            "category_name": "电子",
            "category_level": 1,
            "parent_code": "",
            "is_active": 1,
        },
        {
            "category_code": "630500",
            "category_name": "半导体",
            "category_level": 2,
            "parent_code": "630000",
            "is_active": 1,
        },
    ]
    generator = ThemeRuleBasedGeneratorFixed(categories)

    # If secondary inference is called, this test must fail immediately.
    def _secondary_infer_forbidden(_classification_result):
        raise AssertionError("secondary category inference called in generate_theme_data_only")

    generator._match_categories = _secondary_infer_forbidden  # type: ignore[method-assign]

    event_data = {
        "event_id": "evt_upstream_cls",
        "title": "半导体设备需求上行",
        "content": "半导体设备需求上行，产业链景气度提升",
        "classification_result": {
            "level1_category": "电子",
            "level2_category": "半导体",
            "category_code": "630500",
            "parent_code": "630000",
            "category_level": 2,
            "confidence": 0.93,
        },
        "ai_analysis": {
            "core_concept": "半导体设备",
            "industry_keywords": ["半导体", "设备"],
            "concept_confidence": 0.91,
        },
    }

    dto = generator.generate_theme_data_only(event_data)
    assert dto is not None, "generator returned empty result"
    assert dto.category_info["classification_source"] == "upstream"
    assert dto.category_info["level1_code"] == "630000"
    assert dto.category_info["level2_code"] == "630500"


def test_tc003_missing_upstream_classification_creates_concept_path():
    """TC-P1P2-003C / ACC-P1-P2-03: missing upstream classification should create concept path by AI keywords."""
    categories = [
        {
            "category_code": "630000",
            "category_name": "电子",
            "category_level": 1,
            "parent_code": "",
            "is_active": 1,
        }
    ]
    generator = ThemeRuleBasedGeneratorFixed(categories)

    # If secondary inference is called, this test must fail.
    def _secondary_infer_forbidden(_classification_result):
        raise AssertionError("fallback secondary category inference is forbidden")

    generator._match_categories = _secondary_infer_forbidden  # type: ignore[method-assign]

    event_data = {
        "event_id": "evt_missing_upstream_cls",
        "title": "未知事件",
        "content": "缺失上游分类信息，必须阻断",
        "ai_analysis": {
            "core_concept": "未知概念",
            "industry_keywords": ["未知"],
            "concept_confidence": 0.6,
        },
    }

    dto = generator.generate_theme_data_only(event_data)
    assert dto is not None
    assert dto.category_info["classification_source"] == "created_from_ai_keywords"
    assert dto.category_info["theme_type"] == "concept"
    assert dto.category_info["need_create_category"] is True
    assert len(dto.categories_to_create) >= 2
    assert dto.categories_to_create[0]["category_type"] == "concept"
    assert dto.categories_to_create[1]["category_type"] == "concept"
    for cat in dto.categories_to_create[:2]:
        assert cat.get("keywords"), "new concept categories must keep non-empty keywords for next matching"


def test_tc003_adr_list_audit_for_random_zero_and_secondary_inference():
    """TC-P1P2-003D: ADR audit MUST cover ADR-006 and ADR-011 with full decision structure."""
    adrs = Path("docs/adrs/ADR_LIST.md").read_text(encoding="utf-8", errors="ignore")

    for adr_id in ("ADR-006", "ADR-011"):
        assert adr_id in adrs, f"missing {adr_id} in ADR list"

    # Ensure each ADR section has mandatory fields.
    for adr_id in ("ADR-006", "ADR-011"):
        m = re.search(rf"(### {adr_id}:.*?)(?=\n### ADR-|\Z)", adrs, flags=re.S)
        assert m, f"{adr_id} section not found"
        section = m.group(1)
        for field in ("- Context", "- Problem", "- Proposed Decision", "- Alternatives", "- Consequences"):
            assert field in section, f"{adr_id} missing field: {field}"


def test_tc003_acceptance_feature_alignment():
    """Acceptance/Feature docs must explicitly align with ACC-P1-P2-03 constraints."""
    acceptance = Path("docs/project_control/ACCEPTANCE.md").read_text(encoding="utf-8", errors="ignore")
    feature = Path("docs/project_control/FEATURE_SPEC_P1.phase2.md").read_text(
        encoding="utf-8", errors="ignore"
    )

    assert "ACC-P1-P2-03" in acceptance
    assert "不得使用随机/零向量直接产出最终主题" in acceptance
    assert "generate_theme_data_only" in feature
    assert "禁止在创建路径触发 `_match_categories`" in feature


def test_tc003_category_inference_uses_event_keywords_when_industry_empty():
    """TC-P1P2-003B/C guard: category inference must work with event_keywords/core_concept only."""
    categories = [
        {
            "category_code": "CT0100",
            "category_name": "商业航天",
            "category_level": 1,
            "category_type": "concept",
            "keywords": ["商业航天", "航天"],
            "parent_code": "",
        },
        {
            "category_code": "CT0100_C01",
            "category_name": "SpaceX",
            "category_level": 2,
            "category_type": "concept",
            "keywords": ["SpaceX", "IPO", "估值"],
            "parent_code": "CT0100",
        },
    ]

    matcher = KeywordMatcher({"category_match_threshold": 1, "enable_category_inference": True})
    matcher.initialize(themes=[], categories=categories)

    result = matcher.infer_category_from_ai_keywords(
        {
            "industry_keywords": [],
            "event_keywords": ["SpaceX", "IPO"],
            "core_concept": "SpaceX",
        }
    )

    assert result.get("matched") is True
    assert result.get("level2_code") == "CT0100_C01"


def test_tc003_semantic_category_inference_uses_event_keywords_when_industry_empty():
    """Semantic matcher should also infer categories from event_keywords/core_concept."""
    categories = [
        {
            "category_code": "CT0200",
            "category_name": "商业航天",
            "category_level": 1,
            "category_type": "concept",
            "keywords": ["商业航天", "航天"],
            "parent_code": "",
        },
        {
            "category_code": "CT0200_C01",
            "category_name": "SpaceX",
            "category_level": 2,
            "category_type": "concept",
            "keywords": ["SpaceX", "IPO", "估值"],
            "parent_code": "CT0200",
        },
    ]

    matcher = TransformerSemanticMatcher({"category_match_threshold": 1, "enable_category_inference": True})
    matcher.initialize(themes=[], categories=categories)

    result = matcher.infer_category_from_ai_keywords(
        {
            "industry_keywords": [],
            "event_keywords": ["SpaceX", "IPO"],
            "core_concept": "SpaceX",
        }
    )

    assert result.get("matched") is True
    assert result.get("level2_code") == "CT0200_C01"


def test_tc003_guardrail_rejects_semantic_only_false_positive():
    """Semantic-only hit without keyword/core-concept consistency must be rejected."""
    service = ThemeService(enable_clustering=False)

    event_data = {
        "event_id": "evt_spacex_like",
        "title": "SpaceX相关新闻",
        "ai_analysis": {
            "core_concept": "SpaceX估值翻倍并筹备IPO",
            "industry_keywords": ["SpaceX", "IPO", "估值"],
            "event_keywords": ["航空航天", "科技金融"],
        },
    }
    themes = [
        {
            "id": "1001",
            "code": "TEST_CONCEPT_X",
            "name": "核聚变市场规模预测概念",
            "tags": {"keywords": ["核聚变", "清洁能源", "可控核聚变"]},
        }
    ]
    response = {
        "matched": True,
        "best_match": {
            "theme_id": "TEST_CONCEPT_X",
            "theme_name": "核聚变市场规模预测概念",
            "confidence": 0.97,
            "matched_keywords": [],
        },
        "themes": [],
        "confidence": 0.97,
        "processing_info": {},
    }

    guarded = service._apply_update_guardrails(event_data, themes, response)
    assert guarded.get("matched") is False
    assert guarded.get("reason") == "semantic_only_rejected_by_guardrail"
    assert guarded.get("rejected_best_match", {}).get("theme_name") == "核聚变市场规模预测概念"


def test_tc003_guardrail_allows_when_keyword_overlap_present():
    """When keywords overlap, guardrail should allow update path."""
    service = ThemeService(enable_clustering=False)

    event_data = {
        "event_id": "evt_overlap",
        "title": "SpaceX相关新闻",
        "ai_analysis": {
            "core_concept": "SpaceX估值翻倍并筹备IPO",
            "industry_keywords": ["SpaceX", "IPO"],
        },
    }
    themes = [
        {
            "id": "1002",
            "code": "TEST_CONCEPT_SPACEX",
            "name": "SpaceX估值与IPO进展",
            "tags": {"keywords": ["SpaceX", "IPO", "商业航天"]},
        }
    ]
    response = {
        "matched": True,
        "best_match": {
            "theme_id": "TEST_CONCEPT_SPACEX",
            "theme_name": "SpaceX估值与IPO进展",
            "confidence": 0.93,
            "matched_keywords": ["SpaceX"],
        },
        "themes": [],
        "confidence": 0.93,
        "processing_info": {},
    }

    guarded = service._apply_update_guardrails(event_data, themes, response)
    assert guarded.get("matched") is True
    assert guarded.get("guardrail", {}).get("passed") is True
    assert guarded.get("guardrail", {}).get("keyword_overlap_count", 0) >= 1
