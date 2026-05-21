from __future__ import annotations

from types import SimpleNamespace

import pytest

from theme_service.tools.compare_theme_profile_v1_v2 import _normalize_and_validate_db_args
from theme_service.tools.profile_eval_common import count_generic_only_related, hard_negative_wrong_hits
from theme_service.tools.profile_quality_common import is_generic_term, split_generic
from theme_service.tools.validate_theme_profile_v2 import validate_profile


def test_profile_quality_generic_term_detection_keeps_specific_ipo_and_equipment_terms():
    assert is_generic_term("供应链")
    assert is_generic_term("航天供应链")
    assert is_generic_term("参股")
    assert not is_generic_term("蓝箭航天IPO")
    assert not is_generic_term("电力设备")
    assert not is_generic_term("AI大娱乐")


def test_split_generic_keeps_specific_anchor_terms():
    anchors, generic = split_generic(["蓝箭航天IPO", "供应链", "电力设备", "参股"])

    assert anchors == ["蓝箭航天IPO", "电力设备"]
    assert generic == ["供应链", "参股"]


def test_validate_theme_profile_v2_accepts_clean_profile():
    result = validate_profile(
        {
            "subject_key": "9062142",
            "subject_name": "蓝箭航天IPO",
            "aliases": ["蓝箭航天IPO", "蓝箭航天"],
            "entity_anchors": ["蓝箭航天", "朱雀三号"],
            "domain_anchors": ["商业航天"],
            "product_anchors": ["朱雀"],
            "technology_anchors": [],
            "must_terms": ["蓝箭航天IPO"],
            "strong_terms": ["蓝箭航天", "朱雀三号", "商业航天"],
            "negative_terms": ["非SHEIN"],
            "confusion_subject_keys": [],
            "evidence_refs": [{"source": "theme_gate_profile"}],
            "quality_score": 88,
        }
    )

    assert result["passed"]


def test_validate_theme_profile_v2_rejects_generic_anchor_profile():
    result = validate_profile(
        {
            "subject_key": "x",
            "subject_name": "泛供应链",
            "aliases": ["供应链"],
            "entity_anchors": ["供应链"],
            "domain_anchors": [],
            "product_anchors": [],
            "technology_anchors": [],
            "must_terms": ["供应商"],
            "strong_terms": ["供应链"],
            "negative_terms": [],
            "confusion_subject_keys": [],
            "evidence_refs": [],
            "quality_score": 50,
        }
    )

    assert not result["passed"]
    assert "must_terms_contain_generic" in result["failures"]
    assert "aliases_contain_generic" in result["failures"]


def test_validate_theme_profile_v2_rejects_low_hard_negative_rate():
    result = validate_profile(
        {
            "subject_key": "9046625",
            "subject_name": "SHEIN/希音IPO",
            "aliases": ["SHEIN/希音IPO"],
            "entity_anchors": ["SHEIN", "希音"],
            "domain_anchors": ["快时尚"],
            "product_anchors": [],
            "technology_anchors": [],
            "must_terms": ["SHEIN"],
            "strong_terms": ["希音", "快时尚"],
            "negative_terms": ["蓝箭航天"],
            "confusion_subject_keys": ["9062142"],
            "evidence_refs": [{"source": "theme_gate_profile"}],
            "quality_score": 90,
            "eval_metrics": {"hard_negative_reject_rate": 0.5},
        }
    )

    assert not result["passed"]
    assert "hard_negative_reject_rate_lt_0_80" in result["failures"]


def test_validate_theme_profile_v2_rejects_numeric_subject_name():
    result = validate_profile(
        {
            "subject_key": "9060949",
            "subject_name": "9060949",
            "aliases": ["9060949"],
            "entity_anchors": ["SpaceX", "星舰", "星链"],
            "domain_anchors": ["商业航天"],
            "product_anchors": [],
            "technology_anchors": [],
            "must_terms": ["SpaceX"],
            "strong_terms": ["星舰", "星链"],
            "negative_terms": ["SHEIN"],
            "confusion_subject_keys": [],
            "evidence_refs": [{"source": "theme_profile_ext"}],
            "quality_score": 90,
        }
    )

    assert not result["passed"]
    assert "subject_name_equals_subject_key" in result["failures"]
    assert "subject_name_numeric" in result["failures"]
    assert "aliases_only_numeric_subject_key" in result["failures"]


def test_hard_negative_wrong_hits_match_related_subject_and_name():
    result = SimpleNamespace(
        matched_subject_key="9062142",
        matched_theme_name="蓝箭航天IPO",
        related_matches=[
            {"subject_key": "9046625", "theme_name": "SHEIN/希音IPO"},
            {"subject_key": "9019807", "theme_name": "卫星互联网"},
        ],
    )
    hits = hard_negative_wrong_hits(
        result,
        {
            "must_not_subject_keys": ["9046625"],
            "must_not_theme_names": ["航空发动机集团", "SHEIN/希音IPO"],
        },
    )

    assert hits["subject_keys"] == ["9046625"]
    assert hits["theme_names"] == ["SHEIN/希音IPO"]


def test_count_generic_only_related_detects_polluted_related_evidence():
    result = SimpleNamespace(
        related_matches=[
            {"evidence": {"anchor_terms": ["供应链", "供应商"]}},
            {"evidence": {"anchor_terms": ["蓝箭航天", "供应链"]}},
        ]
    )

    assert count_generic_only_related(result) == 1


def test_compare_tool_defaults_write_db_to_read_db():
    args = SimpleNamespace(read_db_name="stock_data_test", write_db_name=None, allow_cross_db=False)

    _normalize_and_validate_db_args(args)

    assert args.write_db_name == "stock_data_test"


def test_compare_tool_rejects_cross_db_without_explicit_allow():
    args = SimpleNamespace(read_db_name="stock_data_test", write_db_name="stock_data", allow_cross_db=False)

    with pytest.raises(RuntimeError, match="Refuse cross-db validation"):
        _normalize_and_validate_db_args(args)


def test_compare_tool_allows_explicit_cross_db():
    args = SimpleNamespace(read_db_name="stock_data_test", write_db_name="stock_data", allow_cross_db=True)

    _normalize_and_validate_db_args(args)

    assert args.write_db_name == "stock_data"
