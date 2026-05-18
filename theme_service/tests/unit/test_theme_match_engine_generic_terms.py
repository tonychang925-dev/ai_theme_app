from __future__ import annotations

import pytest

from theme_service.services.theme_match_engine import (
    Candidate,
    ThemeMatchEngine,
    _build_event_query_text,
    _build_event_match_profile,
    _build_gate_evidence,
    _calc_feature_recall_score,
    _build_feature_recall_rows,
)
from theme_service.services.theme_match_types import ThemeMatchRequest, ThemeProfile


LANJIAN_TITLE = "蓝箭航天副总裁张静茹告诉《科创板日报》记者，蓝箭航天供应链600余家供应商覆盖全国90余城，民企占比近70%、国企30%"
LANJIAN_CONTENT = (
    "蓝箭航天副总裁张静茹告诉《科创板日报》记者，蓝箭航天供应链600余家供应商覆盖全国90余城，"
    "民企占比近70%、国企30%。同时，无锡朱雀三号装配基地正冲刺建设，力争年底验收，"
    "2026年投用，专注火箭装配与智能制造。"
)


def _profile(
    subject_key: str,
    name: str,
    *,
    must_terms: list[str] | None = None,
    strong_terms: list[str] | None = None,
    should_terms: list[str] | None = None,
    aliases: list[str] | None = None,
    core_objects: list[str] | None = None,
    entity_hints: list[str] | None = None,
    semantic_type: str = "产业题材",
    strategy_type: str = "event_driven",
    search_text: str | None = None,
    rerank_text: str | None = None,
    gate_json: dict | None = None,
    negative_terms: list[str] | None = None,
) -> ThemeProfile:
    return ThemeProfile(
        subject_key=subject_key,
        subject_name=name,
        theme_master_id=None,
        concept=name,
        semantic_type=semantic_type,
        strategy_type=strategy_type,
        ontology_json={},
        gate_json=gate_json or {},
        must_terms=must_terms or [],
        should_terms=should_terms or [],
        not_terms=[],
        strong_terms=strong_terms or [],
        weak_terms=[],
        negative_terms=negative_terms or [],
        search_text=search_text or name,
        quality="test",
        rerank_text=rerank_text or name,
        aliases=aliases or [],
        entity_hints=entity_hints or [],
        core_objects=core_objects or [],
    )


class _Repo:
    def __init__(self, profiles: list[ThemeProfile]):
        self._profiles = profiles

    async def load_active_profiles(self):
        return self._profiles


class _NoDenseThemeMatchEngine(ThemeMatchEngine):
    async def _dense_recall(self, request, event_profile=None):
        return []

    async def _sparse_recall(self, request, event_profile=None):
        return []

    def _rerank(self, request, candidate_rows, profile_map, event_profile=None):
        event_text = _build_event_query_text(request, event_profile)
        out = []
        for row in candidate_rows:
            item = dict(row)
            profile = profile_map[item["subject_key"]]
            evidence = _build_gate_evidence(event_text, profile, event_profile)
            item["evidence"] = evidence
            item["rerank_score"] = _calc_feature_recall_score({}, evidence)
            out.append(item)
        out.sort(key=lambda x: (-float(x.get("rerank_score") or 0.0), str(x.get("subject_key"))))
        return out


def _lanjian_request() -> ThemeMatchRequest:
    return ThemeMatchRequest(
        event_id=1,
        news_id=1,
        title=LANJIAN_TITLE,
        content=LANJIAN_CONTENT,
        summary="蓝箭航天副总裁透露供应链覆盖全国90余城，无锡朱雀三号装配基地冲刺建设。",
        event_type="行业观点",
        entities=["蓝箭航天", "朱雀三号", "火箭"],
    )


def test_lanjian_event_profile_keeps_supplier_words_out_of_anchors():
    profile = _build_event_match_profile(_lanjian_request())

    assert "蓝箭航天" in profile.entity_anchors
    assert "朱雀三号" in profile.entity_anchors or "朱雀三号" in profile.product_anchors
    assert "火箭" in profile.domain_anchors or "火箭" in profile.entity_anchors
    assert "供应链" in profile.support_terms
    assert "供应商" in profile.support_terms
    assert "供应链" not in profile.search_terms
    assert "供应商" not in profile.search_terms


def test_generic_supplier_gate_terms_do_not_create_anchor_evidence():
    request = _lanjian_request()
    event_profile = _build_event_match_profile(request)
    shein = _profile(
        "9046625",
        "SHEIN/希音IPO",
        must_terms=["供应链"],
        strong_terms=["包装及物流", "供应链"],
        aliases=["供应链"],
        core_objects=["供应链"],
    )

    evidence = _build_gate_evidence(_build_event_query_text(request, event_profile), shein, event_profile)

    assert evidence["must_hits"] == []
    assert evidence["strong_hits"] == []
    assert evidence["object_hits"] == []
    assert "供应链" in evidence["support_hits"]
    assert evidence["anchor_hits"] == []


def test_composite_supplier_terms_are_downgraded_to_support_hits():
    request = _lanjian_request()
    event_profile = _build_event_match_profile(request)
    profile = _profile(
        "x",
        "航天供应链",
        must_terms=["航天供应链"],
        strong_terms=["供应链体系"],
        aliases=["包装物流"],
        core_objects=["航天供应链", "供应链体系"],
    )

    evidence = _build_gate_evidence(_build_event_query_text(request, event_profile), profile, event_profile)

    assert evidence["must_hits"] == []
    assert evidence["strong_hits"] == []
    assert evidence["object_hits"] == []
    assert "航天供应链" in evidence["support_hits"]
    assert evidence["anchor_hits"] == []


def test_lanjian_entity_anchor_recalls_lanjian_ipo_profile_even_when_gate_terms_are_weak():
    request = _lanjian_request()
    event_profile = _build_event_match_profile(request)
    lanjian_ipo = _profile(
        "9062142",
        "蓝箭航天IPO",
        must_terms=["参股", "供货", "公司"],
        strong_terms=["参股", "供货", "公司", "蓝箭航天IPO"],
        should_terms=["民商火箭企业", "液体运载火箭研制", "朱雀一号运载火箭发射"],
        core_objects=["参股", "供货", "蓝箭航天IPO"],
        search_text="蓝箭航天IPO。蓝箭航天空间科技股份有限公司首次公开发行股票招股说明书被受理。",
        rerank_text=(
            "蓝箭航天IPO。蓝箭航天是国内最早成立的民商火箭企业之一，"
            "涉及朱雀系列运载火箭、液氧甲烷火箭。"
        ),
        semantic_type="公司事件",
        strategy_type="event_driven",
    )
    aviation_material = _profile(
        "9061860",
        "航天材料",
        should_terms=["火箭"],
        search_text="航天材料 火箭 材料",
        rerank_text="航天材料，火箭材料与关键部件。",
    )

    evidence = _build_gate_evidence(_build_event_query_text(request, event_profile), lanjian_ipo, event_profile)
    rows = _build_feature_recall_rows(
        request,
        {"9062142": lanjian_ipo, "9061860": aviation_material},
        event_profile,
        top_k=20,
    )

    assert "蓝箭航天" in evidence["profile_anchor_hits"]
    assert "蓝箭航天" in evidence["anchor_hits"]
    assert rows[0]["subject_key"] == "9062142"
    assert any(row["subject_key"] == "9062142" for row in rows[:20])


def test_related_matches_reject_alias_only_single_anchor_noise(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")
    primary = _profile("9030409", "AR眼镜")
    alias_only = _profile("9035171", "AI大娱乐")
    engine = ThemeMatchEngine(_Repo([primary, alias_only]))
    candidate = Candidate(
        subject_key="9035171",
        subject_name="AI大娱乐",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": True,
            "theme_name_hit_terms": ["智能眼镜"],
            "subject_name_direct_hit": False,
            "subject_name_hit_terms": [],
            "object_hits": ["智能眼镜"],
            "must_hits": ["智能眼镜"],
            "strong_hits": ["智能眼镜"],
            "anchor_hits": ["智能眼镜"],
            "profile_anchor_hits": [],
            "entity_hits": [],
            "conflict_score": 0,
        },
    )

    related = engine._build_related_matches(
        candidates=[candidate],
        profile_map={"9030409": primary, "9035171": alias_only},
        primary_subject_key="9030409",
    )

    assert related == []


def test_related_matches_reject_single_profile_entity_anchor_noise(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")
    primary = _profile("9030409", "AR眼镜")
    meta_noise = _profile("9036559", "ASIC芯片")
    engine = ThemeMatchEngine(_Repo([primary, meta_noise]))
    candidate = Candidate(
        subject_key="9036559",
        subject_name="ASIC芯片",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": False,
            "theme_name_hit_terms": [],
            "subject_name_direct_hit": False,
            "subject_name_hit_terms": [],
            "object_hits": [],
            "must_hits": [],
            "strong_hits": [],
            "anchor_hits": ["Meta"],
            "profile_anchor_hits": ["Meta"],
            "entity_hits": [],
            "conflict_score": 0,
        },
    )

    related = engine._build_related_matches(
        candidates=[candidate],
        profile_map={"9030409": primary, "9036559": meta_noise},
        primary_subject_key="9030409",
    )

    assert related == []


def test_related_matches_allow_subject_family_hit(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")
    primary = _profile("9030409", "AR眼镜")
    family = _profile("9038540", "AR眼镜四大品牌")
    engine = ThemeMatchEngine(_Repo([primary, family]))
    candidate = Candidate(
        subject_key="9038540",
        subject_name="AR眼镜四大品牌",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": False,
            "theme_name_hit_terms": [],
            "subject_name_direct_hit": False,
            "subject_name_hit_terms": [],
            "object_hits": [],
            "must_hits": [],
            "strong_hits": [],
            "anchor_hits": ["Meta"],
            "profile_anchor_hits": ["Meta"],
            "entity_hits": [],
            "conflict_score": 0,
        },
    )

    related = engine._build_related_matches(
        candidates=[candidate],
        profile_map={"9030409": primary, "9038540": family},
        primary_subject_key="9030409",
    )

    assert [item["subject_key"] for item in related] == ["9038540"]


@pytest.mark.asyncio
async def test_lanjian_supply_chain_news_ignores_generic_supplier_terms(monkeypatch):
    monkeypatch.delenv("THEME_MATCH_JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")

    shein = _profile(
        "9046625",
        "SHEIN/希音IPO",
        must_terms=["SHEIN（希音）", "包装及物流", "上游合作", "跨境电商平台", "供应链", "女装"],
        strong_terms=["SHEIN（希音）", "包装及物流", "上游合作", "跨境电商平台", "供应链", "女装", "SHEIN/希音IPO"],
        should_terms=["物流体系", "总部位于中国广州"],
        aliases=["SHEIN（希音）", "供应链"],
        core_objects=["SHEIN（希音）", "供应链"],
        entity_hints=["SHEIN", "希音"],
        semantic_type="公司事件",
        strategy_type="industry_chain",
    )
    aviation_engine = _profile(
        "9062904",
        "航空发动机集团",
        must_terms=["供应商", "参股"],
        strong_terms=["供应商", "参股", "航空发动机集团"],
        should_terms=["关键材料开发", "关键部件制造"],
        aliases=["供应商"],
        core_objects=["供应商"],
        entity_hints=["航空发动机集团"],
        semantic_type="公司事件",
        strategy_type="event_driven",
    )
    commercial_space = _profile(
        "9061851",
        "商业航天8大IPO",
        must_terms=["发射许可", "核心技术产品"],
        strong_terms=["商业航天8大IPO", "蓝箭航天", "朱雀", "火箭", "发射"],
        should_terms=["自主研发", "提供航天发射服务", "中大型运载火箭"],
        aliases=["蓝箭航天", "朱雀三号"],
        core_objects=["蓝箭航天", "朱雀", "火箭", "发射"],
        entity_hints=["蓝箭航天", "朱雀三号"],
        semantic_type="政策法规与产业标准",
        strategy_type="policy_driven",
    )
    engine = _NoDenseThemeMatchEngine(_Repo([shein, aviation_engine, commercial_space]))

    result = await engine.match_event(_lanjian_request())

    assert result.decision == "MATCH"
    assert result.matched_theme_name != "航空发动机集团"
    assert result.matched_theme_name in {"商业航天8大IPO"}
    assert all(item.get("theme_name") != "SHEIN/希音IPO" for item in result.related_matches)


def test_llm_accept_match_without_anchor_evidence_is_human_review(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")
    shein = _profile(
        "9046625",
        "SHEIN/希音IPO",
        must_terms=["供应链"],
        strong_terms=["供应链"],
        aliases=["供应链"],
        core_objects=["供应链"],
    )
    engine = ThemeMatchEngine(_Repo([shein]))
    candidate = Candidate(
        subject_key="9046625",
        subject_name="SHEIN/希音IPO",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": False,
            "object_hits": [],
            "must_hits": [],
            "strong_hits": [],
            "should_hits": [],
            "entity_hits": [],
            "positive_score": 0,
            "conflict_score": 0,
        },
    )

    result = engine._final_decide_with_llm(
        request=_lanjian_request(),
        candidates=[candidate],
        profile_map={"9046625": shein},
        llm_result={
            "verdict": "accept_match",
            "best_candidate": "C1",
            "best_theme_key": "9046625",
            "confidence": 0.92,
            "reason": "泛词供应链命中",
        },
    )

    assert result.decision == "HUMAN_REVIEW"
    assert result.reason_code == "llm_accept_without_anchor_evidence"


def test_microfluid_chip_cooling_does_not_anchor_high_temperature_theme():
    request = ThemeMatchRequest(
        event_id=2,
        news_id=2,
        title="微软与Corintis合作开发微流体冷却技术，可降低芯片最高温升65%",
        content="微软与Corintis合作开发微流体冷却技术，可降低芯片最高温升65%。",
        summary="芯片微流体冷却技术降低最高温升。",
        event_type="产业技术",
        entities=["微软", "Corintis", "微流体冷却"],
    )
    event_profile = _build_event_match_profile(request)
    high_temp = _profile(
        "9028694",
        "高温",
        must_terms=["高温"],
        strong_terms=["高温"],
        aliases=["高温"],
        core_objects=["高温"],
    )

    evidence = _build_gate_evidence(_build_event_query_text(request, event_profile), high_temp, event_profile)

    assert evidence["role_guard_blocked"] is True
    assert evidence["hit_term_roles"]["高温"] == "generic_short_term"
    assert evidence["positive_score"] == 0


def test_source_org_securities_does_not_enter_related(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")
    primary = _profile("9013689", "液冷数据中心")
    securities = _profile("9016841", "证券")
    engine = ThemeMatchEngine(_Repo([primary, securities]))
    candidate = Candidate(
        subject_key="9016841",
        subject_name="证券",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": True,
            "subject_name_direct_hit": True,
            "theme_name_hit_terms": ["证券"],
            "subject_name_hit_terms": ["证券"],
            "object_hits": ["证券"],
            "must_hits": ["证券"],
            "strong_hits": ["证券"],
            "valid_anchor_terms": [],
            "hit_term_roles": {"证券": "source_org"},
            "role_guard_blocked": True,
            "conflict_score": 0,
        },
    )

    related = engine._build_related_matches(
        candidates=[candidate],
        profile_map={"9013689": primary, "9016841": securities},
        primary_subject_key="9013689",
    )

    assert related == []


def test_location_name_shenzhen_does_not_enter_related(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_ENABLE_MULTI_MATCH", "true")
    primary = _profile("9030409", "AI智能眼镜")
    shenzhen = _profile("9033923", "深圳")
    engine = ThemeMatchEngine(_Repo([primary, shenzhen]))
    candidate = Candidate(
        subject_key="9033923",
        subject_name="深圳",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": True,
            "subject_name_direct_hit": True,
            "theme_name_hit_terms": ["深圳"],
            "subject_name_hit_terms": ["深圳"],
            "valid_anchor_terms": [],
            "hit_term_roles": {"深圳": "location"},
            "role_guard_blocked": True,
            "conflict_score": 0,
        },
    )

    related = engine._build_related_matches(
        candidates=[candidate],
        profile_map={"9030409": primary, "9033923": shenzhen},
        primary_subject_key="9030409",
    )

    assert related == []


def test_llm_accept_role_guard_blocked_candidate_has_no_matched_subject(monkeypatch):
    securities = _profile("9016841", "证券")
    engine = ThemeMatchEngine(_Repo([securities]))
    candidate = Candidate(
        subject_key="9016841",
        subject_name="证券",
        dense_score=0.0,
        rerank_score=0.8,
        evidence={
            "theme_name_direct_hit": True,
            "theme_name_hit_terms": ["证券"],
            "role_guard_blocked": True,
            "hit_term_roles": {"证券": "source_org"},
        },
    )

    result = engine._final_decide_with_llm(
        request=ThemeMatchRequest(
            event_id=3,
            news_id=3,
            title="东方证券预测谷歌服务器液冷市场提升",
            content="东方证券预测2026年谷歌服务器液冷市场规模约180亿元。",
            summary="东方证券预测服务器液冷市场规模提升。",
            event_type="研报",
            entities=["谷歌", "服务器液冷"],
        ),
        candidates=[candidate],
        profile_map={"9016841": securities},
        llm_result={
            "verdict": "accept_match",
            "best_candidate": "C1",
            "best_theme_key": "9016841",
            "confidence": 0.92,
            "reason": "证券命中",
        },
    )

    assert result.decision == "HUMAN_REVIEW"
    assert result.reason_code == "llm_accept_role_guard_blocked"
    assert result.matched_subject_key == ""
