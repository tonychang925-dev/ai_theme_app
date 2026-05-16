from __future__ import annotations

import pytest

from theme_service.services.theme_match_engine import (
    Candidate,
    ThemeMatchEngine,
    _build_event_query_text,
    _build_event_match_profile,
    _build_gate_evidence,
    _calc_feature_recall_score,
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
) -> ThemeProfile:
    return ThemeProfile(
        subject_key=subject_key,
        subject_name=name,
        theme_master_id=None,
        concept=name,
        semantic_type=semantic_type,
        strategy_type=strategy_type,
        ontology_json={},
        gate_json={},
        must_terms=must_terms or [],
        should_terms=should_terms or [],
        not_terms=[],
        strong_terms=strong_terms or [],
        weak_terms=[],
        negative_terms=[],
        search_text=name,
        quality="test",
        rerank_text=name,
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
