from __future__ import annotations

import pytest

from theme_service.services.theme_match_engine import (
    Candidate,
    ThemeMatchEngine,
    _build_event_query_text,
    _build_event_match_profile,
    _build_gate_evidence,
    _calc_feature_recall_score,
    _collect_direct_hit_subject_keys,
    _build_feature_recall_rows,
)
from theme_service.services.theme_match_types import ThemeDecisionEnvelope, ThemeMatchRequest, ThemeProfile
from theme_service.tools.profile_eval_common import hard_negative_wrong_hits


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


class _RaisingJudge:
    def enabled(self):
        return True

    def judge(self, *args, **kwargs):
        raise AssertionError("LLM judge should not be called")


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


@pytest.mark.asyncio
async def test_match_event_attaches_performance_audit(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "9062142",
                "蓝箭航天IPO",
                aliases=["蓝箭航天IPO"],
                core_objects=["蓝箭航天", "朱雀三号"],
                must_terms=["蓝箭航天"],
                strong_terms=["朱雀三号", "火箭"],
            )
        ])
    )

    result = await engine.match_event(_lanjian_request())

    perf = result.audit.get("performance") or {}
    assert result.decision == "MATCH"
    assert perf.get("timing_ms", {}).get("total_match_ms") is not None
    assert perf.get("counters", {}).get("llm_judge_mode") == "off"
    assert perf.get("counters", {}).get("llm_judge_count") == 0


@pytest.mark.asyncio
async def test_llm_judge_off_skips_enabled_judge(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "9062142",
                "蓝箭航天IPO",
                aliases=["蓝箭航天IPO"],
                core_objects=["蓝箭航天"],
                must_terms=["蓝箭航天"],
            )
        ])
    )
    engine._judge = _RaisingJudge()

    result = await engine.match_event(_lanjian_request())

    assert result.decision == "MATCH"


@pytest.mark.asyncio
async def test_high_noise_v1_fallback_match_is_downgraded_to_review(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "9034920",
                "东方头",
                aliases=["东方头"],
                core_objects=["科技"],
                must_terms=["科技"],
            )
        ])
    )

    result = await engine.match_event(
        ThemeMatchRequest(
            event_id=2,
            news_id=2,
            title="东方头相关消息进入题材匹配",
            content="东方头 fallback gate 触发测试。",
            summary="东方头",
            event_type="公告",
        )
    )

    assert result.decision == "HUMAN_REVIEW"
    assert result.reason_code == "high_noise_v1_fallback_review"
    assert result.audit["high_noise_fallback_guard"]["runtime_profile_source"] == "v1_fallback"


@pytest.mark.asyncio
async def test_high_noise_v2_profile_keeps_match(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "9050084",
                "精酿啤酒",
                aliases=["精酿啤酒"],
                core_objects=["精酿啤酒"],
                must_terms=["精酿啤酒"],
                gate_json={"profile_version": "v2"},
            )
        ])
    )

    result = await engine.match_event(
        ThemeMatchRequest(
            event_id=3,
            news_id=3,
            title="精酿啤酒新品带动小酒馆消费升温",
            content="精酿啤酒消费链路。",
            summary="精酿啤酒消费",
            event_type="产业",
        )
    )

    assert result.decision == "MATCH"


@pytest.mark.asyncio
async def test_low_value_v1_alias_direct_hit_is_dropped(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "phase2b-v1-region",
                "福建题材",
                aliases=["福建"],
                must_terms=["福建"],
            )
        ])
    )

    result = await engine.match_event(
        ThemeMatchRequest(
            event_id=4,
            news_id=4,
            title="福建发布天气预警",
            content="福建地方新闻触发旧 fallback direct hit。",
            summary="福建天气",
            event_type="地方新闻",
        )
    )

    assert result.decision == "DROPPED"
    assert result.reason_code == "weather_disaster_low_value"
    assert result.review_required is False
    assert result.audit["low_value_event_rule_only_guard"]["blocked"] is True


@pytest.mark.asyncio
async def test_full_v1_subject_name_direct_hit_keeps_match(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "phase2b-v1-full-name",
                "科技类重组",
                aliases=["科技类重组"],
                must_terms=["科技类重组"],
            )
        ])
    )

    result = await engine.match_event(
        ThemeMatchRequest(
            event_id=5,
            news_id=5,
            title="科技类重组预期升温",
            content="科技类重组出现专名证据。",
            summary="科技类重组",
            event_type="产业",
        )
    )

    assert result.decision == "MATCH"
    assert result.reason_code == "direct_theme_name_hit"


@pytest.mark.asyncio
async def test_v1_location_subject_direct_hit_regulatory_notice_is_blocked(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_LLM_JUDGE_MODE", "off")
    engine = _NoDenseThemeMatchEngine(
        _Repo([
            _profile(
                "9060389",
                "广东",
                aliases=["广东"],
                must_terms=["国资", "粤字辈"],
            )
        ])
    )

    result = await engine.match_event(
        ThemeMatchRequest(
            event_id=6,
            news_id=6,
            title="智度股份：收到广东证监局行政监管措施决定书",
            content="智度股份因信息披露违规收到广东证监局行政监管措施决定书，将积极整改。",
            summary="广东监管措施公告。",
            event_type="公告",
        )
    )

    assert result.decision != "MATCH"
    assert result.matched_subject_key != "9060389"


def test_rerank_doc_vector_cache_reuses_profile_vectors(monkeypatch):
    monkeypatch.setenv("THEME_MATCH_RERANK_VECTOR_CACHE_MAX", "10")

    class _FakeModel:
        def __init__(self):
            self.batch_encode_calls = 0

        def encode(self, value):
            if isinstance(value, list):
                self.batch_encode_calls += 1
                return [[1.0, 0.0] for _ in value]
            return [1.0, 0.0]

    engine = ThemeMatchEngine(_Repo([]))
    fake_model = _FakeModel()
    engine._sentence_model = fake_model
    profile = _profile(
        "9062142",
        "蓝箭航天IPO",
        aliases=["蓝箭航天IPO"],
        core_objects=["蓝箭航天"],
        must_terms=["蓝箭航天"],
        rerank_text="蓝箭航天 朱雀三号 商业航天",
    )
    request = _lanjian_request()
    rows = [{"subject_key": profile.subject_key, "dense_score": 0.1, "rerank_text": profile.rerank_text}]

    first_counters = {}
    second_counters = {}
    engine._rerank(request, rows, {profile.subject_key: profile}, _build_event_match_profile(request), first_counters)
    engine._rerank(request, rows, {profile.subject_key: profile}, _build_event_match_profile(request), second_counters)

    assert first_counters.get("rerank_doc_vector_cache_miss_count") == 1
    assert second_counters.get("rerank_doc_vector_cache_hit_count") == 1
    assert fake_model.batch_encode_calls == 1


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


def test_new_quality_productivity_support_terms_do_not_create_xinjiang_ftz_anchor_evidence():
    request = ThemeMatchRequest(
        event_id=14,
        news_id=14,
        title="合成生物产业创新发展行动计划推进，新质生产力平台落地。",
        content="合成生物产业创新发展行动计划推进，高通量筛选平台落地。",
        summary="合成生物与新质生产力推进。",
        event_type="产业政策",
        entities=["合成生物"],
    )
    event_profile = _build_event_match_profile(request)
    xinjiang_ftz = _profile(
        "9012396",
        "新疆自贸区",
        must_terms=["新质生产力"],
        strong_terms=["新质生产力", "生物制造"],
        aliases=["新疆自贸区"],
        core_objects=["新质生产力"],
        gate_json={"no_anchor_terms": ["新质生产力", "生物制造"]},
    )

    evidence = _build_gate_evidence(_build_event_query_text(request, event_profile), xinjiang_ftz, event_profile)

    assert evidence["must_hits"] == []
    assert evidence["strong_hits"] == []
    assert evidence["object_hits"] == []
    assert "新质生产力" in evidence["support_hits"]
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


def test_broad_category_strict_blocks_child_topic_direct_hit():
    request = ThemeMatchRequest(
        event_id=7,
        news_id=7,
        title="国产刻蚀机和薄膜沉积设备进入多家晶圆厂验证",
        content="国产刻蚀机和薄膜沉积设备进入多家晶圆厂验证，半导体设备订单持续增长。",
        summary="半导体设备验证加快。",
        event_type="产业事件",
        entities=["刻蚀机", "薄膜沉积设备"],
    )
    profile = _profile(
        "9013944",
        "半导体",
        must_terms=["半导体行业", "半导体板块"],
        strong_terms=["晶圆制造"],
        aliases=["半导体行业", "半导体板块"],
        core_objects=["半导体行业", "半导体板块"],
        negative_terms=["半导体设备", "刻蚀机", "薄膜沉积"],
        gate_json={
            "no_anchor_terms": ["半导体设备", "设备", "晶圆"],
            "support_terms": ["芯片", "晶圆", "设备"],
            "eval_metrics": {"related_policy": "broad_category_strict"},
        },
    )

    evidence = _build_gate_evidence(request.event_text(), profile, _build_event_match_profile(request))

    assert evidence["broad_category_blocked"] is True
    assert evidence["role_guard_blocked"] is True
    assert evidence["positive_score"] == 0
    assert _collect_direct_hit_subject_keys(request, {"9013944": profile}) == []


def test_broad_primary_direct_hit_yields_review_when_specific_candidate_has_nested_anchor():
    request = ThemeMatchRequest(
        event_id=8,
        news_id=8,
        title="CVD金刚石热沉材料用于功率半导体散热",
        content="高导热金刚石材料用于功率半导体散热。",
        summary="功率半导体散热材料进展。",
        event_type="产业事件",
        entities=["CVD金刚石热沉"],
    )
    broad = _profile("9013944", "半导体")
    specific = _profile("9064241", "金刚石散热")
    engine = ThemeMatchEngine(_Repo([broad, specific]))
    result = engine._final_decide_rule_only(
        request=request,
        candidates=[
            Candidate(
                subject_key="9013944",
                subject_name="半导体",
                dense_score=0.0,
                rerank_score=1.2,
                evidence={
                    "subject_name_direct_hit": True,
                    "theme_name_direct_hit": True,
                    "valid_anchor_terms": ["半导体"],
                    "conflict_score": 0,
                },
            ),
            Candidate(
                subject_key="9064241",
                subject_name="金刚石散热",
                dense_score=0.0,
                rerank_score=1.0,
                evidence={
                    "valid_anchor_terms": ["功率半导体散热", "CVD金刚石热沉"],
                    "conflict_score": 0,
                },
            ),
        ],
        direct_hit_keys=["9013944"],
        profile_map={"9013944": broad, "9064241": specific},
    )

    assert result.decision == "HUMAN_REVIEW"
    assert result.reason_code == "broad_primary_specific_candidate_review"
    assert result.matched_subject_key == "9013944"


def test_llm_accept_safety_gate_blocks_weak_v1_accept_without_full_subject_hit():
    request = ThemeMatchRequest(
        event_id=10,
        news_id=10,
        title="摄影课堂介绍夜景曝光技巧和暗房显影方法",
        content="该新闻属于摄影教学和兴趣培训。",
        summary="摄影爱好者学习曝光、显影等基础术语。",
        event_type="普通新闻",
    )
    profile = _profile("9018472", "光刻机", must_terms=["光刻机", "曝光", "显影"])
    engine = ThemeMatchEngine(_Repo([profile]))
    env = ThemeDecisionEnvelope(
        decision="MATCH",
        event_id=10,
        news_id=10,
        confidence=0.95,
        reason_code="llm_accept_match",
        matched_subject_key="9018472",
        matched_theme_name="光刻机",
        audit={},
    )
    evidence = {
        "must_hits_text": ["曝光", "显影"],
        "strong_hits_text": ["曝光", "显影"],
        "object_hits_text": ["曝光", "显影"],
        "accepted_anchor_hits": [],
        "subject_name_hit_terms": [],
        "theme_name_hit_terms": ["曝光", "显影"],
        "hit_term_roles": {"曝光": "main_anchor", "显影": "main_anchor"},
        "valid_anchor_terms": ["曝光", "显影"],
        "conflict_score": 0,
    }

    result = engine._post_llm_accept_safety_gate(env, request=request, profile=profile, evidence=evidence)

    assert result.decision == "HUMAN_REVIEW"
    assert result.reason_code == "weak_v1_llm_accept_review"
    assert result.audit["llm_accept_safety_gate"]["runtime_profile_source"] == "v1_fallback"


def test_llm_accept_safety_gate_allows_v2_accepted_anchor_match():
    request = ThemeMatchRequest(
        event_id=11,
        news_id=11,
        title="华为芯片链关注昇腾和海思供应链协同",
        content="昇腾、鲲鹏和海思芯片带动华为半导体供应链关注度提升。",
        summary="华为算力芯片与先进封装链路活跃。",
        event_type="产业新闻",
    )
    profile = _profile(
        "9028660",
        "华为芯片链",
        must_terms=["华为芯片链", "华为芯片", "海思", "昇腾"],
        gate_json={"profile_version": "v2", "boundary_rules": {"accept_requires_any": ["华为芯片链", "昇腾"]}},
    )
    engine = ThemeMatchEngine(_Repo([profile]))
    env = ThemeDecisionEnvelope(
        decision="MATCH",
        event_id=11,
        news_id=11,
        confidence=0.95,
        reason_code="llm_accept_match",
        matched_subject_key="9028660",
        matched_theme_name="华为芯片链",
        audit={},
    )
    evidence = {
        "must_hits_text": ["华为芯片链", "海思", "昇腾"],
        "accepted_anchor_hits": ["华为芯片链", "昇腾"],
        "subject_name_hit_terms": [],
        "theme_name_hit_terms": [],
        "hit_term_roles": {"华为芯片链": "main_anchor", "海思": "main_anchor", "昇腾": "main_anchor"},
        "valid_anchor_terms": ["华为芯片链", "海思", "昇腾"],
        "conflict_score": 0,
    }

    result = engine._post_llm_accept_safety_gate(env, request=request, profile=profile, evidence=evidence)

    assert result.decision == "MATCH"
    assert result.reason_code == "llm_accept_match"


def test_llm_accept_safety_gate_blocks_broad_v2_without_accepted_anchor():
    request = ThemeMatchRequest(
        event_id=12,
        news_id=12,
        title="晶圆代工厂提升先进封装产能",
        content="该事件属于泛半导体制造新闻。",
        summary="半导体制造和封装测试环节景气改善。",
        event_type="普通新闻",
    )
    profile = _profile(
        "9011277",
        "芯片大全",
        must_terms=["芯片大全", "先进封装"],
        gate_json={
            "profile_version": "v2",
            "boundary_rules": {"requires_subject_or_entity_anchor": True},
            "eval_metrics": {"generic_anchor_ratio": 0.2857},
        },
    )
    engine = ThemeMatchEngine(_Repo([profile]))
    env = ThemeDecisionEnvelope(
        decision="MATCH",
        event_id=12,
        news_id=12,
        confidence=0.92,
        reason_code="llm_accept_match",
        matched_subject_key="9011277",
        matched_theme_name="芯片大全",
        audit={},
    )
    evidence = {
        "must_hits_text": ["先进封装"],
        "strong_hits_text": ["先进封装"],
        "object_hits_text": ["先进封装"],
        "accepted_anchor_hits": [],
        "subject_name_hit_terms": [],
        "theme_name_hit_terms": ["先进封装"],
        "hit_term_roles": {"先进封装": "main_anchor"},
        "valid_anchor_terms": ["先进封装"],
        "conflict_score": 0,
    }

    result = engine._post_llm_accept_safety_gate(env, request=request, profile=profile, evidence=evidence)

    assert result.decision == "HUMAN_REVIEW"
    assert result.reason_code == "llm_accept_without_hard_evidence"


def test_llm_accept_safety_gate_blocks_low_value_v1_accept():
    request = ThemeMatchRequest(
        event_id=13,
        news_id=13,
        title="公司公告股东拟减持股份",
        content="股东计划通过集中竞价方式减持部分股份。",
        summary="普通减持公告。",
        event_type="公告",
    )
    profile = _profile("9000001", "普通题材", must_terms=["公司公告"])
    engine = ThemeMatchEngine(_Repo([profile]))
    env = ThemeDecisionEnvelope(
        decision="MATCH",
        event_id=13,
        news_id=13,
        confidence=0.92,
        reason_code="llm_accept_match",
        matched_subject_key="9000001",
        matched_theme_name="普通题材",
        audit={},
    )
    evidence = {
        "must_hits_text": ["公司公告"],
        "accepted_anchor_hits": [],
        "subject_name_hit_terms": [],
        "theme_name_hit_terms": [],
        "hit_term_roles": {"公司公告": "main_anchor"},
        "valid_anchor_terms": ["公司公告"],
        "conflict_score": 0,
    }

    result = engine._post_llm_accept_safety_gate(env, request=request, profile=profile, evidence=evidence)

    assert result.decision == "DROPPED"
    assert result.reason_code == "low_value_event_match_blocked"
    assert result.review_required is False


def test_no_anchor_term_blocks_bare_word_without_suppressing_configured_compound_anchor():
    request = ThemeMatchRequest(
        event_id=9,
        news_id=9,
        title="CVD金刚石热沉材料用于功率半导体散热",
        content="CVD金刚石热沉材料用于功率半导体散热。",
        summary="金刚石热沉材料进展。",
        event_type="产业事件",
        entities=["CVD金刚石热沉"],
    )
    profile = _profile(
        "9064241",
        "金刚石散热",
        must_terms=["金刚石", "金刚石热沉", "CVD金刚石热沉"],
        core_objects=["金刚石热沉"],
        gate_json={
            "no_anchor_terms": ["金刚石"],
            "boundary_rules": {"accept_requires_any": ["金刚石热沉", "CVD金刚石热沉"]},
        },
    )

    evidence = _build_gate_evidence(request.event_text(), profile, _build_event_match_profile(request))

    assert "金刚石" not in evidence["must_hits"]
    assert "金刚石热沉" in evidence["must_hits"]
    assert "CVD金刚石热沉" in evidence["must_hits"]


def test_hard_negative_name_matching_does_not_block_specific_child_theme():
    class _Result:
        matched_subject_key = "9011398"
        matched_theme_name = "半导体设备"
        related_matches = []

    hits = hard_negative_wrong_hits(
        _Result(),
        {
            "must_not_subject_keys": ["9013944"],
            "must_not_theme_names": ["半导体"],
        },
    )

    assert hits == {"subject_keys": [], "theme_names": []}


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


def test_public_news_alias_does_not_create_direct_hit_candidate():
    request = ThemeMatchRequest(
        event_id=4,
        news_id=4,
        title="捷克将接收一名曾接触埃博拉病毒感染者的美籍医生",
        content="捷克应美国请求接收一名曾接触埃博拉感染者的美籍医生，进行预防性观察。",
        summary="公共卫生观察事件。",
        event_type="国际新闻",
        entities=["捷克", "美国"],
    )
    profile = _profile(
        "9043458",
        "中国星际之门",
        aliases=["政府"],
        must_terms=["政府"],
    )

    assert _collect_direct_hit_subject_keys(request, {"9043458": profile}) == []


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


# ── Phase 4.6 P0-C1: AR glasses product-anchor protection ──────────


def test_product_anchor_ar_event_survives_role_guard():
    """AR智能眼镜论坛+鸿海+深圳 → "智能眼镜" is product_anchor, protects from role_guard."""
    from theme_service.services.theme_match_engine import (
        _is_product_anchor_term,
        _classify_hit_term_role,
    )
    event = "AI智能眼镜高峰论坛在深圳举办，鸿海与Porotech宣布合作进军AR眼镜市场"

    # Product anchors
    assert _is_product_anchor_term("智能眼镜", event) is True
    assert _is_product_anchor_term("AI智能眼镜", event) is True
    assert _is_product_anchor_term("眼镜论坛", event) is True

    # These remain blocking or domain roles — product_anchor only protects AR terms
    assert _is_product_anchor_term("深圳", event) is False
    assert _is_product_anchor_term("鸿海", event) is False
    assert _is_product_anchor_term("论坛", event) is False

    # Role classification: product_anchor beats blocking roles
    assert _classify_hit_term_role("智能眼镜", event, None, "object_hits", {"论坛", "深圳"}) == "product_anchor"
    assert _classify_hit_term_role("深圳", event, None, "object_hits", {"论坛", "深圳"}) == "support"  # no_anchor

    # With no_anchor_terms but product_anchor — still gets product_anchor role
    assert _classify_hit_term_role("AR眼镜", event, None, "profile_anchor_hits", {"论坛", "AR"}) == "product_anchor"


def test_product_anchor_bare_glasses_context_markers():
    """Bare '眼镜' only counts as product_anchor with AR/智能/manufacturer context."""
    from theme_service.services.theme_match_engine import _is_product_anchor_term

    # Positive: context markers present
    assert _is_product_anchor_term("眼镜", "Meta与雷朋打造Ray-Ban Meta在社交网站走红") is True
    assert _is_product_anchor_term("眼镜", "小米已开发出一款AI眼镜并将尽快推向市场") is True
    assert _is_product_anchor_term("眼镜", "苹果重启其增强现实AR眼镜计划") is True
    assert _is_product_anchor_term("眼镜", "三星、高通、谷歌强强联手研发智能眼镜") is True
    assert _is_product_anchor_term("眼镜", "华为申请智能眼镜专利") is True

    # Negative: no AR/manufacturer context
    assert _is_product_anchor_term("眼镜", "今天天气很好适合戴太阳眼镜出门") is False
    assert _is_product_anchor_term("眼镜", "参展商展示新款普通眼镜") is False


def test_product_anchor_not_confused_with_qualcomm_or_location():
    """高通/三星/深圳/合作 are NOT product anchors even in AR context."""
    from theme_service.services.theme_match_engine import _is_product_anchor_term

    event = "三星、谷歌、高通强强联手，正研发混合现实智能眼镜，在深圳举办合作论坛"
    assert _is_product_anchor_term("智能眼镜", event) is True
    assert _is_product_anchor_term("高通", event) is False  # pure company name
    assert _is_product_anchor_term("深圳", event) is False  # location
    assert _is_product_anchor_term("合作", event) is False  # generic
    assert _is_product_anchor_term("论坛", event) is False  # generic


def test_product_anchor_all_compound_patterns_detected():
    """All AR_GLASS_PRODUCT_ANCHOR_PATTERNS are recognized."""
    from theme_service.services.theme_match_engine import _is_product_anchor_term

    for pattern in ["AI智能眼镜", "AR眼镜", "智能眼镜", "XR眼镜", "AI眼镜",
                     "AI拍摄眼镜", "AR骑行镜", "眼镜计划", "眼镜产品",
                     "眼镜合作", "眼镜论坛", "增强现实眼镜", "智能AI眼镜"]:
        event = f"{pattern}发布会在北京举行"
        assert _is_product_anchor_term(pattern, event) is True, \
            f"Pattern '{pattern}' should be product_anchor"
