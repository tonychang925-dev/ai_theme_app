from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from theme_service.tools.compare_theme_profile_v1_v2 import _normalize_and_validate_db_args
from theme_service.tools.compare_theme_profile_v1_v2 import _hard_negative_subject_rows
from theme_service.tools.profile_eval_common import count_generic_only_related, hard_negative_wrong_hits
from theme_service.tools.profile_quality_common import is_generic_term, split_generic
from theme_service.tools.validate_theme_profile_v2 import _evaluate_hard_negatives, validate_profile


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


def test_hard_negative_wrong_hits_catches_xinjiang_ftz_and_deepsea_regressions():
    result = SimpleNamespace(
        matched_subject_key="9012396",
        matched_theme_name="新疆自贸区",
        related_matches=[
            {"subject_key": "9043698", "theme_name": "深海经济"},
        ],
    )
    hits = hard_negative_wrong_hits(
        result,
        {
            "must_not_subject_keys": ["9012396", "9043698"],
            "must_not_theme_names": ["新疆自贸区", "深海经济"],
        },
    )

    assert hits["subject_keys"] == ["9012396", "9043698"]
    assert hits["theme_names"] == ["新疆自贸区", "深海经济"]


@pytest.mark.asyncio
async def test_hard_negative_validator_loads_phase5_delta_jsonl():
    hard_negative_file = Path(__file__).resolve().parents[2] / "eval/gate_repair_phase5/e2e_delta_hard_negatives.jsonl"
    loaded_case_ids = {
        json.loads(line)["case_id"]
        for line in hard_negative_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    cases = [
        {
            "case_id": "phase5_hn_fusion_not_global_first_130855",
            "event_text": "核聚变能源企业TAE科技推进核聚变技术商业化，为人工智能产业提供能源支撑。",
            "positive_subject_keys": ["9017950"],
            "must_not_subject_keys": ["9054404"],
            "must_not_theme_names": ["A股全球第一"],
            "tags": ["phase5", "e2e_delta"],
        },
        {
            "case_id": "phase5_hn_biotech_not_xinjiang_ftz_131215",
            "event_text": "合成生物制造产业创新发展行动计划推进，生物制造菌种计算设计和高通量筛选平台落地。",
            "positive_subject_keys": ["9023196"],
            "must_not_subject_keys": ["9012396"],
            "must_not_theme_names": ["新疆自贸区"],
            "tags": ["phase5", "e2e_delta"],
        },
        {
            "case_id": "phase5_hn_rare_earth_not_deepsea_131216",
            "event_text": "商务部、海关总署发布公告2025年第56号，公布对部分稀土设备和原辅料相关物项实施出口管制的决定。",
            "positive_subject_keys": ["9010367"],
            "must_not_subject_keys": ["9043698"],
            "must_not_theme_names": ["深海经济"],
            "tags": ["phase5", "e2e_delta"],
        },
    ]
    profiles = [
        {
            "subject_key": "9012396",
            "subject_name": "新疆自贸区",
            "aliases": ["新疆自贸区"],
            "entity_anchors": ["新疆自贸区"],
            "domain_anchors": ["政策驱动"],
            "product_anchors": [],
            "technology_anchors": [],
            "must_terms": ["新质生产力"],
            "strong_terms": ["新质生产力"],
            "negative_terms": ["非新疆自贸区"],
            "confusion_subject_keys": ["9053522"],
            "evidence_refs": [{"source": "unit_test"}],
            "quality_score": 90,
        },
        {
            "subject_key": "9043698",
            "subject_name": "深海经济",
            "aliases": ["深海经济"],
            "entity_anchors": ["深海经济"],
            "domain_anchors": ["海洋经济"],
            "product_anchors": [],
            "technology_anchors": [],
            "must_terms": ["装备制造"],
            "strong_terms": ["装备制造"],
            "negative_terms": ["非深海经济"],
            "confusion_subject_keys": ["9044395"],
            "evidence_refs": [{"source": "unit_test"}],
            "quality_score": 90,
        },
        {
            "subject_key": "9054404",
            "subject_name": "A股全球第一",
            "aliases": ["A股全球第一"],
            "entity_anchors": ["A股全球第一"],
            "domain_anchors": ["全球第一"],
            "product_anchors": [],
            "technology_anchors": [],
            "must_terms": ["全球第一"],
            "strong_terms": ["全球第一"],
            "negative_terms": ["非A股全球第一"],
            "confusion_subject_keys": ["9034859"],
            "evidence_refs": [{"source": "unit_test"}],
            "quality_score": 90,
        },
    ]

    metrics, case_rows = await _evaluate_hard_negatives(profiles, cases, gate_only=True)
    case_ids = {row["case_id"] for row in case_rows}

    assert hard_negative_file.exists()
    assert {
        "phase5_btrc_vr_ai_glasses_not_vr_001",
        "phase5_btrc_vr_ar_headset_not_vr_002",
        "phase5_btrc_vr_content_not_vr_003",
        "phase5_btrc_ai_chain_not_umbrella_model_004",
        "phase5_btrc_ai_chain_not_umbrella_chip_005",
        "phase5_btrc_ai_chain_not_umbrella_policy_006",
        "phase5_btrc_agri_not_umbrella_breed_007",
        "phase5_btrc_agri_not_umbrella_machinery_008",
        "phase5_btrc_agri_not_umbrella_village_009",
        "phase5_btrc_auto_soe_not_policy_010",
        "phase5_btrc_auto_soe_not_sales_011",
        "phase5_btrc_auto_soe_not_reform_012",
        "phase5_btrc_a_share_not_rank_013",
        "phase5_btrc_a_share_not_chain_014",
        "phase5_btrc_a_share_not_promo_015",
    }.issubset(loaded_case_ids)
    assert "phase5_hn_biotech_not_xinjiang_ftz_131215" in case_ids
    assert "phase5_hn_rare_earth_not_deepsea_131216" in case_ids
    assert "phase5_hn_fusion_not_global_first_130855" in case_ids
    assert metrics["9012396"]["hard_negative_case_count"] >= 1
    assert metrics["9043698"]["hard_negative_case_count"] >= 1
    assert metrics["9054404"]["hard_negative_case_count"] >= 1

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


def test_hard_negative_subject_rows_exposes_watchlist_subject_reject_rates():
    subject_metrics = {
        "9054404": {
            "hard_negative_case_count": 3,
            "hard_negative_reject_count": 2,
            "hard_negative_reject_rate": 0.6667,
            "failed_hard_negative_cases": ["case_a"],
        },
        "9012396": {
            "hard_negative_case_count": 3,
            "hard_negative_reject_count": 3,
            "hard_negative_reject_rate": 1.0,
            "failed_hard_negative_cases": [],
        },
    }
    subject_names = {"9054404": "A股全球第一", "9012396": "新疆自贸区"}

    rows = _hard_negative_subject_rows(subject_metrics, subject_names, {"9054404", "9012396"})
    by_key = {row["subject_key"]: row for row in rows}

    assert by_key["9054404"]["subject_name"] == "A股全球第一"
    assert by_key["9054404"]["hard_negative_case_count"] == 3
    assert by_key["9054404"]["hard_negative_reject_count"] == 2
    assert by_key["9054404"]["hard_negative_reject_rate"] == 0.6667
    assert by_key["9012396"]["subject_name"] == "新疆自贸区"
    assert by_key["9012396"]["hard_negative_reject_rate"] == 1.0
