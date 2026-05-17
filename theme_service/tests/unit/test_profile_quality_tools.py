from __future__ import annotations

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
