from __future__ import annotations

import json
import hashlib
import inspect
import math
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from theme_service.services.theme_match_types import (
    ThemeDecisionEnvelope,
    ThemeMatchRequest,
    ThemeProfile,
)

CANONICAL_SUBJECT_KEY_MAP: Dict[str, str] = {
    "9037499": "9030409",
}

GENERIC_MATCH_STOPWORDS = {
    "AI",
    "AR",
    "VR",
    "XR",
    "IPO",
    "APP",
    "GPT",
    "AIGC",
    "产品",
    "设备",
    "公司",
    "合作",
    "美国",
    "动力系统",
    "应用",
    "金融",
    "供应链",
    "供应商",
    "产业链",
    "参股",
    "制造",
    "生产",
    "上游",
    "下游",
    "上游合作",
    "包装",
    "包装及物流",
    "物流",
    "客户",
    "订单",
    "合作伙伴",
    "民企",
    "国企",
    "部件",
    "关键部件",
    "系统部件",
    "项目",
    "采购",
}

SOURCE_ORG_TERMS = {
    "证券",
    "东方证券",
    "中信证券",
    "华泰证券",
    "招商证券",
    "广发证券",
    "海通证券",
    "国泰君安",
    "中金公司",
    "中信建投",
    "申万宏源",
    "方正证券",
    "国信证券",
    "光大证券",
    "财通证券",
}

LOCATION_TERMS = {
    "北京",
    "上海",
    "深圳",
    "广州",
    "杭州",
    "南京",
    "成都",
    "武汉",
    "苏州",
    "无锡",
    "合肥",
    "重庆",
    "天津",
    "西安",
    "海南",
}

SHORT_GENERIC_THEME_TERMS = {
    "中国",
    "美国",
    "深圳",
    "证券",
    "高温",
    "金融",
    "设备",
    "部件",
    "项目",
    "采购",
    "产品",
    "应用",
}

ROLE_BLOCKING_HIT_ROLES = {"source_org", "location", "generic_short_term", "support"}
STRONG_SHORT_THEME_EXCEPTIONS = {"星链", "朱雀", "火箭"}

# ── Product anchor protection ──────────────────────────────────────
# When these terms appear in event text, they serve as product_anchor
# that cannot be killed by source_org / location / generic / support
# role guards.  This prevents AR/智能眼镜 events from being blocked
# merely because the event also mentions companies, cities, forums etc.

AR_GLASS_PRODUCT_ANCHOR_PATTERNS = [
    "AI智能眼镜", "AR眼镜", "智能眼镜", "智能AR眼镜",
    "XR眼镜", "AI眼镜", "AI拍摄眼镜", "AR骑行镜",
    "眼镜计划", "眼镜产品", "眼镜合作", "眼镜论坛",
    "增强现实眼镜", "智能AI眼镜",
]
# "眼镜" alone must co-occur with a context marker.
AR_GLASS_CONTEXT_MARKERS = {
    "AI", "AR", "XR", "智能", "Meta", "苹果", "三星", "谷歌",
    "高通", "Oakley", "Ray-Ban", "Snap", "Rokid", "XREAL",
    "魅族", "小米", "华为", "OPPO", "vivo", "影目", "闪极",
    "鸿海", "Porotech", "博士眼镜", "星纪魅族",
}
_TEXT_TOKEN_CACHE_MAX = 256
_TEXT_TOKEN_CACHE: OrderedDict[str, set[str]] = OrderedDict()


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_text(text: str) -> str:
    return _safe_str(text).lower()


def _unique(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        value = _safe_str(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            if isinstance(item, dict):
                candidate = (
                    item.get("normalized")
                    or item.get("name")
                    or item.get("claim")
                    or item.get("text")
                    or ""
                )
            else:
                candidate = item
            candidate = _safe_str(candidate)
            if candidate:
                out.append(candidate)
        return _unique(out)
    if isinstance(value, tuple):
        return _unique([_safe_str(x) for x in value if _safe_str(x)])
    return []


def _squash01(score: float) -> float:
    score = max(0.0, min(1.0, score))
    return round(score, 4)


def _phrase_similarity(a: str, b: str) -> float:
    a = _safe_str(a)
    b = _safe_str(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token_hit_terms(text: str, terms: List[str]) -> List[str]:
    hits: List[str] = []
    for term in terms:
        if _term_in_text(_safe_str(term), text):
            hits.append(_safe_str(term))
    return _unique(hits)


def _term_in_text(term: str, text: str) -> bool:
    """词边界匹配，短词必须分词命中，长专名允许子串兜底。"""
    term = _safe_str(term)
    text = _safe_str(text)
    if not term or not text or len(term) < 2:
        return False
    if len(term) >= 4:
        return _normalize_text(term) in _normalize_text(text)
    tokens = _token_set_for_text(text)
    if tokens:
        return term in tokens
    return _normalize_text(term) in _normalize_text(text)


def _token_set_for_text(text: str) -> set[str]:
    text = _safe_str(text)
    if not text:
        return set()
    cache_key = hashlib.sha1(text.encode("utf-8")).hexdigest()
    cached = _TEXT_TOKEN_CACHE.get(cache_key)
    if cached is not None:
        _TEXT_TOKEN_CACHE.move_to_end(cache_key)
        return cached
    try:
        import jieba

        tokens = set(jieba.lcut(text))
    except Exception:
        tokens = set()
    _TEXT_TOKEN_CACHE[cache_key] = tokens
    _TEXT_TOKEN_CACHE.move_to_end(cache_key)
    while len(_TEXT_TOKEN_CACHE) > _TEXT_TOKEN_CACHE_MAX:
        _TEXT_TOKEN_CACHE.popitem(last=False)
    return tokens


def _filter_generic_terms(terms: List[str]) -> List[str]:
    out: List[str] = []
    for term in terms:
        value = _safe_str(term)
        if not value:
            continue
        if value.upper() in GENERIC_MATCH_STOPWORDS or value in GENERIC_MATCH_STOPWORDS:
            continue
        out.append(value)
    return _unique(out)


def _profile_gate_terms(profile: ThemeProfile, key: str) -> List[str]:
    gate_json = profile.gate_json if isinstance(profile.gate_json, dict) else {}
    return _normalize_list(gate_json.get(key))


def _profile_eval_metrics(profile: ThemeProfile) -> Dict[str, Any]:
    gate_json = profile.gate_json if isinstance(profile.gate_json, dict) else {}
    metrics = gate_json.get("eval_metrics")
    if isinstance(metrics, str):
        try:
            parsed = json.loads(metrics)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return metrics if isinstance(metrics, dict) else {}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _llm_judge_mode() -> str:
    mode = os.getenv("THEME_MATCH_LLM_JUDGE_MODE", "always").strip().lower()
    return mode if mode in {"always", "auto", "off"} else "always"


def _is_source_org_term(term: str, event_text: str) -> bool:
    value = _safe_str(term)
    if not value:
        return False
    if value in SOURCE_ORG_TERMS and value != "证券":
        return True
    if value == "证券":
        return bool(
            re.search(
                r"(东方|中信|华泰|招商|广发|海通|国泰君安|中金|中信建投|申万宏源|方正|国信|光大|财通)证券",
                event_text,
            )
            or re.search(r"证券(预测|认为|指出|研报|测算|表示|预计)", event_text)
        )
    return False


def _is_location_term(term: str, event_text: str) -> bool:
    value = _safe_str(term)
    if value not in LOCATION_TERMS:
        return False
    if re.search(rf"(在|于|赴|落地|位于|举办|召开|举行|会场|总部|基地|园区)?{re.escape(value)}(市|省|举办|召开|举行|论坛|峰会|会议|会展|站|本地)?", event_text):
        return True
    return True


def _is_short_generic_theme_term(term: str) -> bool:
    value = _safe_str(term)
    if not value or value in STRONG_SHORT_THEME_EXCEPTIONS:
        return False
    return value in SHORT_GENERIC_THEME_TERMS


def _extract_event_tech_terms(request: ThemeMatchRequest) -> List[str]:
    evidence = request.evidence_set or {}
    out: List[str] = []
    if isinstance(evidence, dict):
        out.extend(_normalize_list(evidence.get("tech_phrases")))
        out.extend(_normalize_list(evidence.get("core_concepts")))
    return _unique(out)


DOMAIN_ANCHOR_HINTS = [
    "商业航天",
    "民营航天",
    "卫星互联网",
    "星链",
    "运载火箭",
    "火箭",
    "可回收火箭",
    "低空经济",
    "AI眼镜",
    "AR眼镜",
    "智能眼镜",
    "可控核聚变",
    "稀土永磁",
]

PRODUCT_ANCHOR_PATTERNS = [
    r"蓝箭航天",
    r"朱雀[一二三四五六七八九十\d]+号?",
    r"星舰",
    r"SpaceX",
    r"Meta",
    r"Oakley",
    r"OpenAI",
    r"Manus",
    r"SHEIN",
    r"希音",
]


def _build_event_match_profile(request: ThemeMatchRequest) -> EventMatchProfile:
    raw_text = request.event_text()
    evidence = request.evidence_set or {}
    support_terms = _unique([term for term in GENERIC_MATCH_STOPWORDS if _term_in_text(term, raw_text)])
    weak_terms = _unique([term for term in ["民企", "国企", "覆盖", "城市", "合作伙伴"] if _term_in_text(term, raw_text)])
    entity_anchors = _filter_generic_terms(_normalize_list(request.entities))
    domain_anchors = _filter_generic_terms([term for term in DOMAIN_ANCHOR_HINTS if _term_in_text(term, raw_text)])
    product_anchors: List[str] = []
    for pattern in PRODUCT_ANCHOR_PATTERNS:
        product_anchors.extend(re.findall(pattern, raw_text, flags=re.IGNORECASE))
    product_anchors = _filter_generic_terms(product_anchors)
    technology_anchors = _filter_generic_terms(
        _normalize_list(evidence.get("tech_phrases")) + _normalize_list(evidence.get("core_concepts"))
    )
    event_actions = _filter_generic_terms([term for term in ["发射", "首飞", "回收", "组网", "上市", "发布"] if _term_in_text(term, raw_text)])
    search_terms = _unique(entity_anchors + domain_anchors + product_anchors + technology_anchors + event_actions)
    query_text_for_recall = "\n".join(
        [
            "锚点：" + "、".join(search_terms[:16]) if search_terms else "",
            request.title,
            request.summary,
            request.content[:600] if request.content else "",
        ]
    ).strip()
    query_text_for_judge = "\n".join(
        [
            raw_text,
            "entity_anchors：" + "、".join(entity_anchors) if entity_anchors else "",
            "domain_anchors：" + "、".join(domain_anchors) if domain_anchors else "",
            "product_anchors：" + "、".join(product_anchors) if product_anchors else "",
            "technology_anchors：" + "、".join(technology_anchors) if technology_anchors else "",
            "support_terms：" + "、".join(support_terms) if support_terms else "",
            "weak_terms：" + "、".join(weak_terms) if weak_terms else "",
            "no_anchor_terms：" + "、".join(_unique(support_terms + weak_terms)) if support_terms or weak_terms else "",
        ]
    ).strip()
    return EventMatchProfile(
        raw_text=raw_text,
        search_terms=search_terms,
        entity_anchors=entity_anchors,
        domain_anchors=domain_anchors,
        product_anchors=product_anchors,
        technology_anchors=technology_anchors,
        event_actions=event_actions,
        support_terms=support_terms,
        weak_terms=weak_terms,
        no_anchor_terms=_unique(support_terms + weak_terms),
        query_text_for_recall=query_text_for_recall or raw_text,
        query_text_for_judge=query_text_for_judge or raw_text,
    )


class _EventProfileLLMExtractor:
    def __init__(self):
        self.base_url = os.getenv("THEME_MATCH_PROFILE_BASE_URL", os.getenv("THEME_MATCH_JUDGE_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.api_key = os.getenv("THEME_MATCH_PROFILE_API_KEY") or os.getenv("THEME_MATCH_JUDGE_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = os.getenv("THEME_MATCH_PROFILE_MODEL", os.getenv("THEME_MATCH_JUDGE_MODEL", "deepseek-chat"))
        self.session = requests.Session()

    def enabled(self) -> bool:
        enabled = os.getenv("THEME_MATCH_ENABLE_EVENT_PROFILE_LLM", "false").lower() in {"1", "true", "yes", "on"}
        return enabled and bool(self.api_key)

    def extract(self, request: ThemeMatchRequest, fallback: EventMatchProfile) -> EventMatchProfile:
        if not self.enabled():
            return fallback
        prompt = f"""
你是A股题材事件术语提取器。请从新闻中提取用于题材匹配的可检索术语。

输出 JSON：
{{
  "entity_anchors": [],
  "domain_anchors": [],
  "product_anchors": [],
  "technology_anchors": [],
  "event_actions": [],
  "support_terms": [],
  "weak_terms": []
}}

规则：
1. entity_anchors 提取事件主对象、公司、产品、机构，如蓝箭航天、SpaceX、Meta、SHEIN。
2. domain_anchors 提取产业/题材方向，如商业航天、火箭、卫星互联网。
3. support_terms 可包含供应链、供应商、产能、订单等，但这些不能单独作为题材匹配依据。
4. weak_terms 包含民企、国企、覆盖城市、合作伙伴等经营描述。
5. 禁止把“供应链、供应商、产业链、制造、合作、参股、物流、包装”等泛词放入 anchors。
6. 只输出 JSON，不要输出额外解释。

新闻：
{request.event_text()[:3000]}
""".strip()
        try:
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]},
                timeout=(10, 60),
            )
            resp.raise_for_status()
            text = _safe_str(resp.json()["choices"][0]["message"]["content"])
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"^```\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            data = json.loads(text)
        except Exception:
            return fallback

        entity_anchors = _filter_generic_terms(_normalize_list(data.get("entity_anchors")) + fallback.entity_anchors)
        domain_anchors = _filter_generic_terms(_normalize_list(data.get("domain_anchors")) + fallback.domain_anchors)
        product_anchors = _filter_generic_terms(_normalize_list(data.get("product_anchors")) + fallback.product_anchors)
        technology_anchors = _filter_generic_terms(_normalize_list(data.get("technology_anchors")) + fallback.technology_anchors)
        event_actions = _filter_generic_terms(_normalize_list(data.get("event_actions")) + fallback.event_actions)
        support_terms = _unique(_normalize_list(data.get("support_terms")) + fallback.support_terms)
        weak_terms = _unique(_normalize_list(data.get("weak_terms")) + fallback.weak_terms)
        no_anchor_terms = _unique([t for t in support_terms + weak_terms if t in GENERIC_MATCH_STOPWORDS or t in fallback.no_anchor_terms])
        search_terms = _unique(entity_anchors + domain_anchors + product_anchors + technology_anchors + event_actions)
        query_text_for_recall = "\n".join(
            [
                "锚点：" + "、".join(search_terms[:16]) if search_terms else "",
                request.title,
                request.summary,
            ]
        ).strip()
        query_text_for_judge = "\n".join(
            [
                fallback.raw_text,
                "entity_anchors：" + "、".join(entity_anchors) if entity_anchors else "",
                "domain_anchors：" + "、".join(domain_anchors) if domain_anchors else "",
                "product_anchors：" + "、".join(product_anchors) if product_anchors else "",
                "technology_anchors：" + "、".join(technology_anchors) if technology_anchors else "",
                "support_terms：" + "、".join(support_terms) if support_terms else "",
                "weak_terms：" + "、".join(weak_terms) if weak_terms else "",
                "no_anchor_terms：" + "、".join(no_anchor_terms) if no_anchor_terms else "",
            ]
        ).strip()
        return EventMatchProfile(
            raw_text=fallback.raw_text,
            search_terms=search_terms,
            entity_anchors=entity_anchors,
            domain_anchors=domain_anchors,
            product_anchors=product_anchors,
            technology_anchors=technology_anchors,
            event_actions=event_actions,
            support_terms=support_terms,
            weak_terms=weak_terms,
            no_anchor_terms=no_anchor_terms,
            query_text_for_recall=query_text_for_recall or fallback.query_text_for_recall,
            query_text_for_judge=query_text_for_judge or fallback.query_text_for_judge,
        )


def _build_event_query_text(request: ThemeMatchRequest, event_profile: EventMatchProfile | None = None) -> str:
    if event_profile is not None:
        return event_profile.query_text_for_recall or event_profile.raw_text
    parts = [request.event_text()]
    tech_terms = _extract_event_tech_terms(request)
    if tech_terms:
        parts.append("技术词：" + "、".join(tech_terms[:10]))
    return "\n".join([x for x in parts if _safe_str(x)])


def _canonical_subject_key(subject_key: str) -> str:
    key = _safe_str(subject_key)
    return CANONICAL_SUBJECT_KEY_MAP.get(key, key)


def _canonicalize_recall_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        canonical_key = _canonical_subject_key(row.get("subject_key"))
        if not canonical_key:
            continue
        item = dict(row)
        item["subject_key"] = canonical_key
        if canonical_key not in merged:
            merged[canonical_key] = item
            continue

        base = merged[canonical_key]
        for score_field in [
            "dense_score",
            "sparse_score",
            "rrf_score",
            "feature_recall_score",
            "rerank_score",
            "semantic_score",
            "feature_score",
        ]:
            base[score_field] = max(
                float(base.get(score_field) or 0.0),
                float(item.get(score_field) or 0.0),
            )
        if not _safe_str(base.get("rerank_text")) and _safe_str(item.get("rerank_text")):
            base["rerank_text"] = item.get("rerank_text")
        for rank_field in ["dense_rank", "sparse_rank"]:
            if base.get(rank_field) is None and item.get(rank_field) is not None:
                base[rank_field] = item.get(rank_field)
    return list(merged.values())


def _rrf_merge_rows(
    dense_rows: List[Dict[str, Any]],
    sparse_rows: List[Dict[str, Any]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for rank, row in enumerate(dense_rows, start=1):
        sk = _safe_str(row.get("subject_key"))
        if not sk:
            continue
        merged[sk] = {
            **dict(row),
            "rrf_score": 1.0 / (k + rank),
            "dense_rank": rank,
            "sparse_rank": None,
        }
    for rank, row in enumerate(sparse_rows, start=1):
        sk = _safe_str(row.get("subject_key"))
        if not sk:
            continue
        if sk not in merged:
            merged[sk] = {
                **dict(row),
                "dense_score": 0.0,
                "rrf_score": 1.0 / (k + rank),
                "dense_rank": None,
                "sparse_rank": rank,
            }
        else:
            merged[sk]["rrf_score"] = float(merged[sk].get("rrf_score") or 0.0) + 1.0 / (k + rank)
            merged[sk]["sparse_rank"] = rank
            if row.get("sparse_score") is not None:
                merged[sk]["sparse_score"] = row.get("sparse_score")
            if not _safe_str(merged[sk].get("rerank_text")) and _safe_str(row.get("rerank_text")):
                merged[sk]["rerank_text"] = row.get("rerank_text")
    rows = list(merged.values())
    rows.sort(
        key=lambda x: (
            -float(x.get("rrf_score") or 0.0),
            -float(x.get("dense_score") or 0.0),
            -float(x.get("sparse_score") or 0.0),
            _safe_str(x.get("subject_key")),
        )
    )
    return rows


def _clip_text(text: str, limit: int = 420) -> str:
    text = _safe_str(text)
    return text if len(text) <= limit else text[:limit]


@dataclass
class Candidate:
    subject_key: str
    subject_name: str
    dense_score: float
    rerank_score: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventMatchProfile:
    raw_text: str
    search_terms: List[str] = field(default_factory=list)
    entity_anchors: List[str] = field(default_factory=list)
    domain_anchors: List[str] = field(default_factory=list)
    product_anchors: List[str] = field(default_factory=list)
    technology_anchors: List[str] = field(default_factory=list)
    event_actions: List[str] = field(default_factory=list)
    support_terms: List[str] = field(default_factory=list)
    weak_terms: List[str] = field(default_factory=list)
    no_anchor_terms: List[str] = field(default_factory=list)
    query_text_for_recall: str = ""
    query_text_for_judge: str = ""


def _build_llm_prompt(
    request: ThemeMatchRequest,
    candidates: List[Candidate],
    profile_map: Dict[str, ThemeProfile],
    event_profile: EventMatchProfile | None = None,
) -> str:
    blocks = []
    for i, cand in enumerate(candidates, start=1):
        cid = f"C{i}"
        profile = profile_map[cand.subject_key]
        ev = cand.evidence or {}
        blocks.append(
            f"{cid}\n"
            f"题材名：{profile.subject_name}\n"
            f"subject_key：{profile.subject_key}\n"
            f"semantic_type：{profile.semantic_type}\n"
            f"strategy_type：{profile.strategy_type}\n"
            f"题材摘要：{_clip_text(profile.compact_text(), 260)}\n"
            f"dense_score：{round(cand.dense_score, 4)}\n"
            f"rerank_score：{round(cand.rerank_score, 4)}\n"
            f"theme_name_direct_hit：{'是' if ev.get('theme_name_direct_hit') else '否'}\n"
            f"theme_name_hit_terms：{'、'.join(ev.get('theme_name_hit_terms', [])) if ev.get('theme_name_hit_terms') else '无'}\n"
            f"theme_name_hit_score：{ev.get('theme_name_hit_score', 0)}\n"
            f"object_hits：{'、'.join(ev.get('object_hits', [])) if ev.get('object_hits') else '无'}\n"
            f"must_hits：{'、'.join(ev.get('must_hits', [])) if ev.get('must_hits') else '无'}\n"
            f"strong_hits：{'、'.join(ev.get('strong_hits', [])) if ev.get('strong_hits') else '无'}\n"
            f"should_hits：{'、'.join(ev.get('should_hits', [])) if ev.get('should_hits') else '无'}\n"
            f"entity_hits：{'、'.join(ev.get('entity_hits', [])) if ev.get('entity_hits') else '无'}\n"
            f"hit_term_roles：{json.dumps(ev.get('hit_term_roles', {}), ensure_ascii=False)}\n"
            f"role_guard_blocked：{'是' if ev.get('role_guard_blocked') else '否'}\n"
            f"conflict_terms：{'、'.join(ev.get('not_hits', []) + ev.get('negative_hits', [])) if (ev.get('not_hits') or ev.get('negative_hits')) else '无'}\n"
            f"positive_score：{ev.get('positive_score', 0)}\n"
            f"conflict_score：{ev.get('conflict_score', 0)}"
        )

    return f"""
你是A股新闻事件题材最终裁决器。

你的任务：
1. 在候选题材中做排他式比较，选出最符合事件主叙事的一个题材。
2. 优先考虑事件的主对象、关键动作、核心实体、主叙事，而不是只看表面词汇重合。
3. dense_score 和 rerank_score 只是参考，不可机械决定最终结果。
4. gate 提供的命中项只是支持性证据，没有否决权。
5. 如果事件文本直接出现某个候选题材名或其别名（theme_name_direct_hit=是），这属于强证据，必须显著重视。
6. 如果存在 theme_name_direct_hit=是 的候选，除非事件主叙事明显不属于它，否则优先选择该候选。
7. 不能因为某个候选语义更泛，就忽略事件对特定题材名/产品名/公司名的直接命中。
8. 所有题材都使用统一逻辑判断，不针对任何特定题材使用特殊规则。
9. 如果所有候选都不够准确，才能输出 need_new_theme。
10. 供应链、供应商、产业链、制造、生产、合作、参股、包装、物流、上游、下游等泛化经营词不可作为题材主证据。
11. 只有命中题材名、专有实体、核心产品、核心技术或产业域锚点，才能 accept_match。
12. 如果候选的 role_guard_blocked=是，说明命中只来自信息源机构、地点、短泛词或支撑词，不得 accept_match。
13. 只输出 JSON，不要输出额外解释。

输出格式：
{{
  "verdict": "accept_match",
  "best_candidate": "C1",
  "confidence": 0.86,
  "reason": "一句话说明为什么这个题材最匹配",
  "new_theme_name": "",
  "new_theme_desc": ""
}}

事件：
{event_profile.query_text_for_judge if event_profile else request.event_text()}

候选：
{chr(10).join(blocks)}
""".strip()


class _FinalLLMJudge:
    def __init__(self):
        self.base_url = os.getenv("THEME_MATCH_JUDGE_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = os.getenv("THEME_MATCH_JUDGE_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = os.getenv("THEME_MATCH_JUDGE_MODEL", "deepseek-chat")

        self.session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def enabled(self) -> bool:
        return bool(self.api_key)

    def judge(
        self,
        request: ThemeMatchRequest,
        candidates: List[Candidate],
        profile_map: Dict[str, ThemeProfile],
        event_profile: EventMatchProfile | None = None,
    ) -> Dict[str, Any]:
        if not self.enabled():
            return {
                "verdict": "review",
                "best_candidate": "",
                "best_theme_key": "",
                "best_theme_name": "",
                "confidence": 0.0,
                "reason": "THEME_MATCH_JUDGE_API_KEY/DEEPSEEK_API_KEY 未设置",
                "new_theme_name": "",
                "new_theme_desc": "",
            }

        idx_map: Dict[str, Candidate] = {f"C{i}": c for i, c in enumerate(candidates, start=1)}
        prompt = _build_llm_prompt(request, candidates, profile_map, event_profile=event_profile)
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }

        last_err: Exception | None = None
        for attempt in range(1, 5):
            try:
                resp = self.session.post(url, headers=headers, json=payload, timeout=(20, 180))
                resp.raise_for_status()
                data = resp.json()
                text = _safe_str(data["choices"][0]["message"]["content"])
                text = re.sub(r"^```json\s*", "", text)
                text = re.sub(r"^```\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                try:
                    obj = json.loads(text)
                except Exception:
                    return {
                        "verdict": "review",
                        "best_candidate": "",
                        "best_theme_key": "",
                        "best_theme_name": "",
                        "confidence": 0.0,
                        "reason": f"JSON解析失败: {text[:200]}",
                        "new_theme_name": "",
                        "new_theme_desc": "",
                    }

                best_candidate = _safe_str(obj.get("best_candidate"))
                best = idx_map.get(best_candidate)
                return {
                    "verdict": _safe_str(obj.get("verdict") or "review"),
                    "best_candidate": best_candidate,
                    "best_theme_key": best.subject_key if best else "",
                    "best_theme_name": profile_map[best.subject_key].subject_name if best else "",
                    "confidence": _squash01(float(obj.get("confidence") or 0.0)),
                    "reason": _safe_str(obj.get("reason")),
                    "new_theme_name": _safe_str(obj.get("new_theme_name")),
                    "new_theme_desc": _safe_str(obj.get("new_theme_desc")),
                }
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        return {
            "verdict": "review",
            "best_candidate": "",
            "best_theme_key": "",
            "best_theme_name": "",
            "confidence": 0.0,
            "reason": f"LLM请求失败: {repr(last_err)}",
            "new_theme_name": "",
            "new_theme_desc": "",
        }


def _profile_text_anchor_hits(profile: ThemeProfile, event_profile: EventMatchProfile | None = None) -> List[str]:
    if event_profile is None:
        return []
    profile_text = "\n".join(
        [
            profile.subject_name,
            profile.concept,
            " ".join(profile.aliases),
            " ".join(profile.entity_hints),
            " ".join(profile.core_objects),
            profile.search_text,
            profile.rerank_text,
            profile.compact_text(),
        ]
    )
    candidate_terms = _filter_generic_terms(
        _unique(
            event_profile.entity_anchors
            + event_profile.product_anchors
            + event_profile.technology_anchors
            + [term for term in event_profile.domain_anchors if len(_safe_str(term)) >= 4]
        )
    )
    return _unique([term for term in candidate_terms if _term_in_text(term, profile_text)])


def _collect_profile_hit_features(
    request: ThemeMatchRequest,
    profile: ThemeProfile,
    event_profile: EventMatchProfile | None = None,
) -> Dict[str, Any]:
    event_text_norm = _normalize_text(request.event_text())
    entity_names = {_normalize_text(x) for x in _normalize_list(request.entities)}

    exact_name_terms = []
    for term in _unique([profile.subject_name, profile.concept] + profile.aliases):
        value = _safe_str(term)
        if not value:
            continue
        exact_name_terms.append(value)

    entity_align_terms = []
    for term in _unique(
        [profile.subject_name, profile.concept]
        + profile.aliases
        + profile.entity_hints
        + profile.core_objects
    ):
        value = _safe_str(term)
        if not value:
            continue
        entity_align_terms.append(value)

    exact_name_hits: List[str] = []
    entity_align_hits: List[str] = []
    for term in exact_name_terms:
        norm = _normalize_text(term)
        if not norm:
            continue
        if norm in event_text_norm:
            exact_name_hits.append(term)

    for term in entity_align_terms:
        norm = _normalize_text(term)
        if not norm:
            continue
        if norm in entity_names:
            entity_align_hits.append(term)

    exact_name_hits = [
        term
        for term in _filter_generic_terms(exact_name_hits)
        if _classify_hit_term_role(term, request.event_text(), profile, "theme_name_hit_terms", set())
        not in ROLE_BLOCKING_HIT_ROLES
    ]
    return {
        "exact_name_hits": exact_name_hits,
        "entity_align_hits": _filter_generic_terms(entity_align_hits),
        "profile_anchor_hits": _profile_text_anchor_hits(profile, event_profile),
    }


def _calc_rerank_feature_score(hit_features: Dict[str, Any]) -> float:
    exact_name_hit_n = len(hit_features.get("exact_name_hits", []))
    entity_align_n = len(hit_features.get("entity_align_hits", []))
    profile_anchor_n = len(hit_features.get("profile_anchor_hits", []))
    score = 0.0
    score += exact_name_hit_n * 0.20
    score += entity_align_n * 0.25
    score += profile_anchor_n * 0.30
    return min(score, 0.75)


def _build_gate_evidence(
    event_text: str,
    profile: ThemeProfile,
    event_profile: EventMatchProfile | None = None,
) -> Dict[str, Any]:
    search_terms = set(event_profile.search_terms if event_profile else [])
    support_terms = set(event_profile.support_terms if event_profile else [])
    support_terms.update(_profile_gate_terms(profile, "support_terms"))
    support_terms.update(_profile_gate_terms(profile, "weak_terms"))
    no_anchor_terms = set(event_profile.no_anchor_terms if event_profile else [])
    no_anchor_terms.update(_profile_gate_terms(profile, "no_anchor_terms"))
    no_anchor_terms.update(_profile_gate_terms(profile, "support_terms"))
    no_anchor_terms.update(_profile_gate_terms(profile, "weak_terms"))

    def _split_hits(terms: List[str]) -> tuple[List[str], List[str]]:
        llm_hits = _filter_generic_terms([t for t in terms if t in search_terms])
        text_hits = _filter_generic_terms([t for t in terms if t not in search_terms and _term_in_text(t, event_text)])
        return llm_hits, text_hits

    must_hits_llm, must_hits_text = _split_hits(profile.must_terms)
    strong_hits_llm, strong_hits_text = _split_hits(profile.strong_terms)
    must_hits = _unique(must_hits_llm + must_hits_text)
    strong_hits = _unique(strong_hits_llm + strong_hits_text)
    should_hits = _filter_generic_terms(
        [t for t in profile.should_terms if t in search_terms or _term_in_text(t, event_text)]
    )
    not_hits = _token_hit_terms(event_text, profile.not_terms)
    negative_hits = _token_hit_terms(event_text, profile.negative_terms)
    object_terms = profile.core_objects + profile.aliases
    object_hits_llm, object_hits_text = _split_hits(object_terms)
    object_hits = _unique(object_hits_llm + object_hits_text)
    entity_hits = _filter_generic_terms(
        [t for t in profile.entity_hints if t in search_terms or _term_in_text(t, event_text)]
    )
    profile_anchor_hits = _profile_text_anchor_hits(profile, event_profile)
    raw_support_hits = _unique(
        [
            t
            for t in profile.must_terms + profile.strong_terms + profile.should_terms + object_terms
            if (t in search_terms or _term_in_text(t, event_text))
            and (_is_no_anchor_term(t, support_terms) or _is_no_anchor_term(t, no_anchor_terms))
        ]
    )

    candidate_names = _unique([profile.subject_name, profile.concept] + profile.aliases)
    subject_name_terms = _unique([profile.subject_name, profile.concept])
    theme_name_hit_terms: List[str] = []
    subject_name_hit_terms: List[str] = []
    event_text_norm = _normalize_text(event_text)
    for name in candidate_names:
        s = _safe_str(name)
        if not s:
            continue
        if _normalize_text(s) in event_text_norm or s in event_text:
            theme_name_hit_terms.append(s)
    for name in subject_name_terms:
        s = _safe_str(name)
        if not s:
            continue
        if _normalize_text(s) in event_text_norm or s in event_text:
            subject_name_hit_terms.append(s)

    theme_name_hit_terms = [
        term for term in _filter_generic_terms(theme_name_hit_terms)
        if _is_product_anchor_term(term, event_text) or not _is_no_anchor_term(term, no_anchor_terms)
    ]
    subject_name_hit_terms = [
        term for term in _filter_generic_terms(subject_name_hit_terms)
        if _is_product_anchor_term(term, event_text) or not _is_no_anchor_term(term, no_anchor_terms)
    ]
    theme_name_direct_hit = len(theme_name_hit_terms) > 0
    subject_name_direct_hit = len(subject_name_hit_terms) > 0
    must_hits = [t for t in must_hits if _is_product_anchor_term(t, event_text) or not _is_no_anchor_term(t, no_anchor_terms)]
    strong_hits = [t for t in strong_hits if _is_product_anchor_term(t, event_text) or not _is_no_anchor_term(t, no_anchor_terms)]
    object_hits = [t for t in object_hits if _is_product_anchor_term(t, event_text) or not _is_no_anchor_term(t, no_anchor_terms)]
    should_hits = [t for t in should_hits if _is_product_anchor_term(t, event_text) or not _is_no_anchor_term(t, no_anchor_terms)]
    entity_hits = [t for t in entity_hits if _is_product_anchor_term(t, event_text) or not _is_no_anchor_term(t, no_anchor_terms)]
    support_hits = _unique(
        raw_support_hits
        + [t for t in must_hits + strong_hits + object_hits + should_hits
           if not _is_product_anchor_term(t, event_text) and _is_no_anchor_term(t, no_anchor_terms)]
    )
    evidence_for_roles = {
        "theme_name_hit_terms": theme_name_hit_terms,
        "subject_name_hit_terms": subject_name_hit_terms,
        "object_hits": object_hits,
        "must_hits": must_hits,
        "strong_hits": strong_hits,
        "should_hits": should_hits,
        "entity_hits": entity_hits,
        "profile_anchor_hits": profile_anchor_hits,
        "support_hits": support_hits,
    }
    role_meta = _annotate_evidence_hit_roles(
        evidence_for_roles,
        event_profile.raw_text if event_profile else event_text,
        profile,
        no_anchor_terms,
    )
    broad_category_blocked = _broad_category_direct_hit_blocked(
        event_text=event_text,
        profile=profile,
        evidence=evidence_for_roles,
        negative_hits=negative_hits,
        no_anchor_terms=no_anchor_terms,
    )
    if broad_category_blocked:
        role_meta["role_guard_blocked"] = True
        role_meta["role_guard_reasons"] = _unique(
            _normalize_list(role_meta.get("role_guard_reasons")) + ["broad_category_strict"]
        )
        role_meta["blocking_hit_terms"] = _unique(
            _normalize_list(role_meta.get("blocking_hit_terms")) + theme_name_hit_terms + subject_name_hit_terms
        )
        role_meta["valid_anchor_terms"] = []
    role_guard_blocked = bool(role_meta.get("role_guard_blocked"))
    valid_anchor_set = set(role_meta.get("valid_anchor_terms") or [])
    theme_name_hit_score = 50 if theme_name_direct_hit and not role_guard_blocked else 0
    positive_score = (
        len([t for t in object_hits_llm if t in valid_anchor_set]) * 5
        + len([t for t in object_hits_text if t in valid_anchor_set]) * 2
        + len([t for t in must_hits_llm if t in valid_anchor_set]) * 5
        + len([t for t in must_hits_text if t in valid_anchor_set]) * 2
        + len([t for t in strong_hits_llm if t in valid_anchor_set]) * 3
        + len([t for t in strong_hits_text if t in valid_anchor_set])
        + len([t for t in should_hits if t in valid_anchor_set])
        + len([t for t in entity_hits if t in valid_anchor_set])
        + len([t for t in profile_anchor_hits if t in valid_anchor_set]) * 6
        + theme_name_hit_score
    )
    conflict_score = len(_unique(not_hits + negative_hits))
    return {
        "theme_name_direct_hit": theme_name_direct_hit,
        "theme_name_hit_terms": theme_name_hit_terms,
        "subject_name_direct_hit": subject_name_direct_hit,
        "subject_name_hit_terms": subject_name_hit_terms,
        "theme_name_hit_score": theme_name_hit_score,
        "object_hits": object_hits,
        "must_hits": must_hits,
        "strong_hits": strong_hits,
        "object_hits_llm": object_hits_llm,
        "object_hits_text": object_hits_text,
        "must_hits_llm": must_hits_llm,
        "must_hits_text": must_hits_text,
        "strong_hits_llm": strong_hits_llm,
        "strong_hits_text": strong_hits_text,
        "should_hits": should_hits,
        "entity_hits": entity_hits,
        "profile_anchor_hits": profile_anchor_hits,
        "support_hits": support_hits,
        "anchor_hits": _unique(object_hits + must_hits + strong_hits + entity_hits + profile_anchor_hits + theme_name_hit_terms),
        "not_hits": not_hits,
        "negative_hits": negative_hits,
        "broad_category_blocked": broad_category_blocked,
        "positive_score": positive_score,
        "conflict_score": conflict_score,
        **role_meta,
        "evidence_summary": {
            "theme_name_hits": theme_name_hit_terms[:5],
            "subject_name_hits": subject_name_hit_terms[:5],
            "anchor_terms": _valid_anchor_terms({**evidence_for_roles, **role_meta})[:8],
            "support_terms": _unique(should_hits + entity_hits)[:8],
            "conflict_terms": _unique(not_hits + negative_hits)[:8],
            "role_guard_blocked": role_guard_blocked,
            "role_guard_reasons": role_meta.get("role_guard_reasons") or [],
        },
    }


def _broad_category_direct_hit_blocked(
    *,
    event_text: str,
    profile: ThemeProfile,
    evidence: Dict[str, Any],
    negative_hits: List[str],
    no_anchor_terms: List[str] | set[str],
) -> bool:
    if _safe_str(_profile_eval_metrics(profile).get("related_policy")) != "broad_category_strict":
        return False
    direct_hits = _normalize_list(evidence.get("theme_name_hit_terms")) + _normalize_list(
        evidence.get("subject_name_hit_terms")
    )
    if not direct_hits:
        return False
    blocking_phrases = _unique(
        _normalize_list(negative_hits)
        + [
            term
            for term in _normalize_list(list(no_anchor_terms))
            if len(term) > len(_safe_str(profile.subject_name))
            and (_term_in_text(term, event_text) or _normalize_text(term) in _normalize_text(event_text))
        ]
    )
    if not blocking_phrases:
        return False
    strong_specific_hits = _unique(
        [
            term
            for term in (
                _normalize_list(evidence.get("object_hits"))
                + _normalize_list(evidence.get("must_hits"))
                + _normalize_list(evidence.get("strong_hits"))
                + _normalize_list(evidence.get("profile_anchor_hits"))
            )
            if term not in direct_hits
            and (_is_product_anchor_term(term, event_text) or not _is_no_anchor_term(term, no_anchor_terms))
        ]
    )
    return not strong_specific_hits


def _compute_dynamic_topk(
    candidate_rows: List[Dict[str, Any]],
    min_topk: int = 8,
    max_topk: int = 15,
    ratio_to_best: float = 0.90,
    margin_threshold: float = 0.035,
) -> int:
    if not candidate_rows:
        return min_topk
    rows = candidate_rows[:max_topk]
    rerank_scores = [float(r.get("rerank_score") or 0.0) for r in rows]
    if not rerank_scores:
        return min_topk
    best_score = rerank_scores[0]
    keep_by_ratio = sum(1 for s in rerank_scores if s >= best_score * ratio_to_best)
    dynamic_topk = max(min_topk, keep_by_ratio)
    if len(rerank_scores) >= 2:
        margin = rerank_scores[0] - rerank_scores[1]
        if margin < margin_threshold:
            dynamic_topk = max(dynamic_topk, min_topk + 2)
    return min(dynamic_topk, max_topk)


def _calc_feature_recall_score(hit_features: Dict[str, Any], gate_evidence: Dict[str, Any]) -> float:
    score = 0.0
    if hit_features.get("exact_name_hits"):
        score += 1.20
    if hit_features.get("entity_align_hits"):
        score += 1.00
    if gate_evidence.get("theme_name_direct_hit") and not gate_evidence.get("role_guard_blocked"):
        score += 2.50

    valid_anchor_set = set(_valid_anchor_terms(gate_evidence))
    score += len([t for t in (gate_evidence.get("object_hits") or []) if t in valid_anchor_set]) * 0.35
    score += len([t for t in (gate_evidence.get("must_hits") or []) if t in valid_anchor_set]) * 0.35
    score += len([t for t in (gate_evidence.get("strong_hits") or []) if t in valid_anchor_set]) * 0.25
    score += len([t for t in (gate_evidence.get("profile_anchor_hits") or []) if t in valid_anchor_set]) * 0.50
    score += len([t for t in (gate_evidence.get("should_hits") or []) if t in valid_anchor_set]) * 0.12
    score += len([t for t in (gate_evidence.get("entity_hits") or []) if t in valid_anchor_set]) * 0.12
    score -= len(gate_evidence.get("not_hits") or []) * 0.20
    score -= len(gate_evidence.get("negative_hits") or []) * 0.20
    return round(score, 6)


def _anchor_terms(
    evidence: Dict[str, Any],
    fields: Tuple[str, ...] = ("object_hits", "must_hits", "strong_hits", "profile_anchor_hits"),
) -> List[str]:
    terms: List[str] = []
    for field_name in fields:
        value = evidence.get(field_name) or []
        if isinstance(value, list):
            terms.extend(_safe_str(item) for item in value)
    return _filter_generic_terms(terms)


def _has_primary_anchor_evidence(evidence: Dict[str, Any]) -> bool:
    if evidence.get("role_guard_blocked"):
        return bool(_valid_anchor_terms(evidence))
    return bool((evidence.get("theme_name_direct_hit") and _valid_anchor_terms(evidence)) or _anchor_terms(evidence))


def _has_only_generic_evidence(evidence: Dict[str, Any]) -> bool:
    if not evidence:
        return True
    return not _has_primary_anchor_evidence(evidence)


def _has_blocking_conflict_evidence(evidence: Dict[str, Any]) -> bool:
    if int(evidence.get("conflict_score") or 0) <= 0:
        return False
    # A literal subject-name hit can still be a legitimate match that needs LLM
    # or review. Alias-only hits with explicit negative evidence are commonly
    # source/nearby mentions and should not outrank a clean domain candidate.
    return not bool(evidence.get("subject_name_direct_hit"))


def _is_product_anchor_term(term: str, event_text: str) -> bool:
    """Return True when *term* is a recognised AR/XR/智能眼镜 product anchor.

    Compound patterns (e.g. ``AI智能眼镜``) always count as product anchor.
    Bare ``眼镜`` only counts when the event contains AR/XR/智能/AI or a known
    manufacturer/ecosystem marker (e.g. Meta, Rokid, 小米).
    """
    value = _safe_str(term)
    if not value:
        return False
    # Compound product anchor patterns
    if value in AR_GLASS_PRODUCT_ANCHOR_PATTERNS:
        return True
    # Bare "眼镜" — only if event text has a context marker
    if value == "眼镜":
        ev_lower = _normalize_text(event_text)
        for marker in AR_GLASS_CONTEXT_MARKERS:
            if _normalize_text(marker) in ev_lower:
                return True
        # Also recognise "智能眼镜" and "AR眼镜" as compound markers
        for pat in AR_GLASS_PRODUCT_ANCHOR_PATTERNS:
            if _normalize_text(pat) in ev_lower:
                return True
    return False


def _is_no_anchor_term(term: str, no_anchor_terms: List[str] | set[str]) -> bool:
    value = _safe_str(term)
    if not value:
        return False
    terms = [_safe_str(item) for item in no_anchor_terms if _safe_str(item)]
    return value in terms or any(item and item in value for item in terms)


def _classify_hit_term_role(
    term: str,
    event_text: str,
    profile: ThemeProfile | None = None,
    evidence_field: str = "",
    no_anchor_terms: List[str] | set[str] | None = None,
) -> str:
    value = _safe_str(term)
    if not value:
        return "support"
    # Product anchors bypass all role guard blocking — legitimate AR/智能眼镜
    # events must not be killed just because they mention a company or a city.
    if _is_product_anchor_term(value, event_text):
        return "product_anchor"
    if _is_no_anchor_term(value, no_anchor_terms or set()):
        return "support"
    if _is_source_org_term(value, event_text):
        return "source_org"
    if _is_location_term(value, event_text):
        return "location"
    if _is_short_generic_theme_term(value):
        return "generic_short_term"
    if evidence_field in {"theme_name_hit_terms", "subject_name_hit_terms", "object_hits", "must_hits", "strong_hits", "profile_anchor_hits"}:
        return "main_anchor"
    if evidence_field == "entity_hits":
        return "domain_anchor"
    return "support"


def _annotate_evidence_hit_roles(
    evidence: Dict[str, Any],
    event_text: str,
    profile: ThemeProfile | None,
    no_anchor_terms: List[str] | set[str],
) -> Dict[str, Any]:
    hit_terms: List[str] = []
    term_roles: Dict[str, str] = {}
    role_sources: Dict[str, List[str]] = {}
    for field_name in (
        "theme_name_hit_terms",
        "subject_name_hit_terms",
        "object_hits",
        "must_hits",
        "strong_hits",
        "should_hits",
        "entity_hits",
        "profile_anchor_hits",
        "support_hits",
    ):
        values = evidence.get(field_name) or []
        if not isinstance(values, list):
            continue
        for term in values:
            value = _safe_str(term)
            if not value:
                continue
            role = _classify_hit_term_role(value, event_text, profile, field_name, no_anchor_terms)
            hit_terms.append(value)
            previous = term_roles.get(value)
            if previous in ROLE_BLOCKING_HIT_ROLES and role not in ROLE_BLOCKING_HIT_ROLES:
                term_roles[value] = role
            else:
                term_roles.setdefault(value, role)
            role_sources.setdefault(value, []).append(field_name)

    hit_terms = _unique(hit_terms)
    valid_anchor_terms = [
        term
        for term in hit_terms
        if term_roles.get(term) not in ROLE_BLOCKING_HIT_ROLES
        and term in set(
            _normalize_list(evidence.get("theme_name_hit_terms"))
            + _normalize_list(evidence.get("subject_name_hit_terms"))
            + _normalize_list(evidence.get("object_hits"))
            + _normalize_list(evidence.get("must_hits"))
            + _normalize_list(evidence.get("strong_hits"))
            + _normalize_list(evidence.get("entity_hits"))
            + _normalize_list(evidence.get("profile_anchor_hits"))
        )
    ]
    blocking_terms = [term for term in hit_terms if term_roles.get(term) in ROLE_BLOCKING_HIT_ROLES]
    has_any_hit = bool(hit_terms)
    role_guard_blocked = has_any_hit and not valid_anchor_terms
    return {
        "hit_terms": hit_terms,
        "hit_term_roles": term_roles,
        "hit_term_role_sources": role_sources,
        "valid_anchor_terms": _unique(valid_anchor_terms),
        "role_guard_blocked": role_guard_blocked,
        "role_guard_reasons": _unique([term_roles.get(term, "support") for term in blocking_terms]) if role_guard_blocked else [],
        "blocking_hit_terms": blocking_terms if role_guard_blocked else [],
    }


def _valid_anchor_terms(evidence: Dict[str, Any]) -> List[str]:
    terms = _normalize_list(evidence.get("valid_anchor_terms"))
    if terms:
        return terms
    roles = evidence.get("hit_term_roles") if isinstance(evidence.get("hit_term_roles"), dict) else {}
    raw = _unique(
        _normalize_list(evidence.get("theme_name_hit_terms"))
        + _normalize_list(evidence.get("subject_name_hit_terms"))
        + _normalize_list(evidence.get("object_hits"))
        + _normalize_list(evidence.get("must_hits"))
        + _normalize_list(evidence.get("strong_hits"))
        + _normalize_list(evidence.get("entity_hits"))
        + _normalize_list(evidence.get("profile_anchor_hits"))
    )
    return [term for term in raw if roles.get(term) not in ROLE_BLOCKING_HIT_ROLES]


def _ontology_terms(profile: ThemeProfile) -> set[str]:
    terms: set[str] = set()
    for value in [profile.semantic_type, profile.strategy_type]:
        if _safe_str(value):
            terms.add(_safe_str(value))
    ontology = profile.ontology_json if isinstance(profile.ontology_json, dict) else {}
    for key in ("domain", "domains", "category", "categories", "industry", "industries", "parent", "ancestors"):
        terms.update(_filter_generic_terms(_normalize_list(ontology.get(key))))
        if _safe_str(ontology.get(key)) and not isinstance(ontology.get(key), (list, tuple, dict)):
            terms.add(_safe_str(ontology.get(key)))
    return {_safe_str(item) for item in terms if _safe_str(item)}


def _same_industry_domain(left: ThemeProfile | None, right: ThemeProfile | None) -> bool:
    if not left or not right:
        return False
    left_terms = _ontology_terms(left)
    right_terms = _ontology_terms(right)
    overlap = _filter_generic_terms(list(left_terms & right_terms))
    return bool(overlap)


def _build_feature_recall_rows(
    request: ThemeMatchRequest,
    profile_map: Dict[str, ThemeProfile],
    event_profile: EventMatchProfile | None = None,
    top_k: int = 25,
    evidence_cache: Dict[str, Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    event_text = _build_event_query_text(request, event_profile)
    rows: List[Dict[str, Any]] = []
    for sk, profile in profile_map.items():
        hit_features = _collect_profile_hit_features(request, profile, event_profile)
        gate_evidence = _build_gate_evidence(event_text, profile, event_profile)
        if evidence_cache is not None:
            evidence_cache[sk] = gate_evidence
        feature_recall_score = _calc_feature_recall_score(hit_features, gate_evidence)
        if feature_recall_score <= 0:
            continue
        rows.append(
            {
                "subject_key": sk,
                "subject_name": profile.subject_name,
                "dense_score": 0.0,
                "feature_recall_score": feature_recall_score,
                "feature_recall_hit_features": hit_features,
                "feature_recall_evidence": gate_evidence,
                "rerank_text": profile.rerank_text or profile.compact_text(),
            }
        )
    rows.sort(
        key=lambda x: (-float(x.get("feature_recall_score") or 0.0), _safe_str(x.get("subject_key")))
    )
    return rows[:top_k]


def _merge_recall_rows(
    dense_rows: List[Dict[str, Any]],
    feature_rows: List[Dict[str, Any]],
    merge_top_k: int = 40,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for row in dense_rows:
        sk = _safe_str(row.get("subject_key"))
        if not sk:
            continue
        item = dict(row)
        item.setdefault("feature_recall_score", 0.0)
        merged[sk] = item

    for row in feature_rows:
        sk = _safe_str(row.get("subject_key"))
        if not sk:
            continue
        if sk in merged:
            merged[sk]["feature_recall_score"] = max(
                float(merged[sk].get("feature_recall_score") or 0.0),
                float(row.get("feature_recall_score") or 0.0),
            )
            if not _safe_str(merged[sk].get("rerank_text")) and _safe_str(row.get("rerank_text")):
                merged[sk]["rerank_text"] = row.get("rerank_text")
        else:
            merged[sk] = dict(row)

    rows = list(merged.values())
    rows.sort(
        key=lambda x: (
            -float(x.get("feature_recall_score") or 0.0),
            -float(x.get("dense_score") or 0.0),
            _safe_str(x.get("subject_key")),
        )
    )
    return rows[:merge_top_k]


def _collect_direct_hit_subject_keys(request: ThemeMatchRequest, profile_map: Dict[str, ThemeProfile]) -> List[str]:
    event_text_norm = _normalize_text(request.event_text())
    event_text = request.event_text()
    out: List[str] = []
    for sk, profile in profile_map.items():
        candidate_names = _unique([profile.subject_name, profile.concept] + profile.aliases)
        for name in candidate_names:
            s = _safe_str(name)
            if not s:
                continue
            if s.upper() in GENERIC_MATCH_STOPWORDS or s in GENERIC_MATCH_STOPWORDS:
                continue
            if _classify_hit_term_role(s, request.event_text(), profile, "theme_name_hit_terms", set()) in ROLE_BLOCKING_HIT_ROLES:
                continue
            if _broad_category_direct_hit_name_blocked(event_text, profile, s):
                continue
            if _normalize_text(s) in event_text_norm:
                out.append(sk)
                break
    return _unique(out)


def _broad_category_direct_hit_name_blocked(event_text: str, profile: ThemeProfile, hit_name: str) -> bool:
    if _safe_str(_profile_eval_metrics(profile).get("related_policy")) != "broad_category_strict":
        return False
    if not hit_name or hit_name not in {_safe_str(profile.subject_name), _safe_str(profile.concept)}:
        return False
    blockers = (
        _normalize_list(profile.negative_terms)
        + _profile_gate_terms(profile, "no_anchor_terms")
        + _profile_gate_terms(profile, "support_terms")
    )
    return any(
        term
        and len(term) > len(hit_name)
        and hit_name in term
        and (_term_in_text(term, event_text) or _normalize_text(term) in _normalize_text(event_text))
        for term in blockers
    )


def _inject_direct_hit_candidates(
    reranked_rows: List[Dict[str, Any]],
    direct_hit_keys: List[str],
    profile_map: Dict[str, ThemeProfile],
    final_topk: int,
    max_inject: int = 2,
) -> List[Dict[str, Any]]:
    reranked_rows = [dict(x) for x in reranked_rows]
    if final_topk <= 0:
        return []

    base_n = max(final_topk - max_inject, 1)
    final_rows = reranked_rows[:base_n]
    final_keys = {_safe_str(x.get("subject_key")) for x in final_rows}
    appended_rows: List[Dict[str, Any]] = []

    for sk in direct_hit_keys:
        if sk in final_keys:
            continue
        found = None
        for row in reranked_rows:
            if _safe_str(row.get("subject_key")) == sk:
                found = dict(row)
                found["is_direct_hit_reserved"] = True
                break
        if found is None:
            profile = profile_map.get(sk)
            if not profile:
                continue
            found = {
                "subject_key": sk,
                "subject_name": profile.subject_name,
                "dense_score": 0.0,
                "rerank_score": 0.0,
                "evidence": {},
                "is_injected": True,
                "is_direct_hit_reserved": True,
            }
        appended_rows.append(found)
        if len(appended_rows) >= max_inject:
            break

    merged = final_rows + appended_rows
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in merged:
        sk = _safe_str(row.get("subject_key"))
        if not sk or sk in seen:
            continue
        seen.add(sk)
        deduped.append(row)

    if len(deduped) < final_topk:
        for row in reranked_rows:
            sk = _safe_str(row.get("subject_key"))
            if not sk or sk in seen:
                continue
            seen.add(sk)
            deduped.append(dict(row))
            if len(deduped) >= final_topk:
                break

    return deduped[:final_topk]


class ThemeMatchEngine:
    """
    运行时题材匹配内核。
    按 final_theme_matcher 的主干逻辑组织：
    候选召回 -> rerank -> dynamic topk -> direct-hit reserve -> gate evidence -> final decision
    """

    def __init__(self, profile_repository):
        self.profile_repository = profile_repository
        self._sentence_model = None
        self._judge = _FinalLLMJudge()
        self._event_profile_extractor = _EventProfileLLMExtractor()
        self._rerank_doc_vector_cache: OrderedDict[tuple[str, str], List[float]] = OrderedDict()
        self._query_vector_cache: OrderedDict[str, List[float]] = OrderedDict()

    async def match_event(self, request: ThemeMatchRequest) -> ThemeDecisionEnvelope:
        started_at = time.perf_counter()
        last_stage_at = started_at
        timing_ms: Dict[str, float] = {}
        counters: Dict[str, Any] = {
            "llm_judge_count": 0,
            "event_profile_llm_count": 0,
            "llm_judge_mode": _llm_judge_mode(),
            "query_vector_cache_hit_count": 0,
            "query_vector_cache_miss_count": 0,
            "rerank_doc_vector_cache_hit_count": 0,
            "rerank_doc_vector_cache_miss_count": 0,
        }

        def mark(stage: str) -> None:
            nonlocal last_stage_at
            now = time.perf_counter()
            timing_ms[stage] = round((now - last_stage_at) * 1000, 3)
            last_stage_at = now

        load_profile_map = getattr(self.profile_repository, "load_active_profile_map", None)
        if callable(load_profile_map):
            profile_map = await load_profile_map()
        else:
            profiles = await self.profile_repository.load_active_profiles()
            profile_map = {p.subject_key: p for p in profiles}
        mark("load_profiles_ms")

        if not profile_map:
            env = ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="no_profile_loaded",
                review_required=False,
                audit={"top_candidates": []},
            )
            timing_ms["total_match_ms"] = round((time.perf_counter() - started_at) * 1000, 3)
            return self._attach_runtime_audit(env, timing_ms, counters)

        counters["event_profile_llm_count"] = int(self._event_profile_extractor.enabled())
        event_profile = self._event_profile_extractor.extract(request, _build_event_match_profile(request))
        mark("event_profile_extract_ms")
        recalled_rows = await self._dense_recall(request, event_profile)
        mark("dense_recall_ms")
        sparse_rows = await self._sparse_recall(request, event_profile)
        mark("sparse_recall_ms")
        hybrid_rows = _rrf_merge_rows(recalled_rows, sparse_rows)
        evidence_cache: Dict[str, Dict[str, Any]] = {}
        feature_rows = _build_feature_recall_rows(request, profile_map, event_profile, evidence_cache=evidence_cache)
        mark("feature_recall_ms")
        candidate_rows = _merge_recall_rows(hybrid_rows, feature_rows)
        if "counters" in inspect.signature(self._rerank).parameters:
            reranked_rows = self._rerank(request, candidate_rows, profile_map, event_profile, counters=counters, evidence_cache=evidence_cache)
        else:
            reranked_rows = self._rerank(request, candidate_rows, profile_map, event_profile)
        mark("rerank_ms")
        dynamic_topk = _compute_dynamic_topk(reranked_rows)
        direct_hit_keys = _collect_direct_hit_subject_keys(request, profile_map)
        final_rows = _inject_direct_hit_candidates(
            reranked_rows,
            direct_hit_keys,
            profile_map,
            final_topk=dynamic_topk,
            max_inject=2,
        )

        candidates = self._materialize_candidates(final_rows, profile_map)
        if not candidates:
            mark("final_decision_ms")
            env = ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="no_candidate_hit",
                review_required=False,
                audit={"top_candidates": []},
            )
            timing_ms["llm_judge_ms"] = 0.0
            timing_ms["total_match_ms"] = round((time.perf_counter() - started_at) * 1000, 3)
            return self._attach_runtime_audit(env, timing_ms, counters)

        mode = _llm_judge_mode()
        should_call_llm = self._judge.enabled() and mode != "off"
        if mode == "auto" and should_call_llm:
            should_call_llm = self._should_call_llm_auto(candidates, direct_hit_keys)
        counters["llm_judge_skipped"] = int(not should_call_llm)
        if should_call_llm:
            llm_started = time.perf_counter()
            llm_result = self._judge.judge(request, candidates, profile_map, event_profile)
            counters["llm_judge_count"] = 1
            timing_ms["llm_judge_ms"] = round((time.perf_counter() - llm_started) * 1000, 3)
            last_stage_at = time.perf_counter()
            env = self._final_decide_with_llm(request, candidates, profile_map, llm_result)
        else:
            timing_ms["llm_judge_ms"] = 0.0
            last_stage_at = time.perf_counter()
            env = self._final_decide_rule_only(request, candidates, direct_hit_keys, profile_map)
        mark("final_decision_ms")
        timing_ms["total_match_ms"] = round((time.perf_counter() - started_at) * 1000, 3)
        return self._attach_runtime_audit(env, timing_ms, counters)

    def _get_sentence_model(self):
        if self._sentence_model is not None:
            return self._sentence_model

        model_name = os.getenv("THEME_MATCH_TEXT2VEC_MODEL", "shibing624/text2vec-base-chinese")
        try:
            from text2vec import SentenceModel
        except Exception as exc:
            raise RuntimeError(
                "ThemeMatchEngine 真实语义召回依赖 text2vec，请在 theme_matcher_env 中运行"
            ) from exc

        self._sentence_model = SentenceModel(model_name)
        return self._sentence_model

    @staticmethod
    def _to_vector_list(value: Any) -> List[float]:
        if value is None:
            return []
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, list):
            return [float(x) for x in value]
        if isinstance(value, tuple):
            return [float(x) for x in value]
        return []

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        an = math.sqrt(sum(x * x for x in a))
        bn = math.sqrt(sum(y * y for y in b))
        return dot / (an * bn + 1e-12)

    async def _dense_recall(self, request: ThemeMatchRequest, event_profile: EventMatchProfile | None = None) -> List[Dict[str, Any]]:
        model = self._get_sentence_model()
        query_text = _build_event_query_text(request, event_profile)
        query_vec = self._encode_query_vector(model, query_text)
        rows = await self.profile_repository.semantic_recall_candidates(query_vec, top_k=25)
        rows = _canonicalize_recall_rows(rows)
        rows.sort(
            key=lambda x: (-float(x.get("dense_score") or 0.0), _safe_str(x.get("subject_key")))
        )
        return rows

    async def _sparse_recall(self, request: ThemeMatchRequest, event_profile: EventMatchProfile | None = None) -> List[Dict[str, Any]]:
        query_text = _build_event_query_text(request, event_profile)
        rows = await self.profile_repository.sparse_recall_candidates(query_text, top_k=25)
        rows = _canonicalize_recall_rows(rows)
        rows.sort(
            key=lambda x: (-float(x.get("sparse_score") or 0.0), _safe_str(x.get("subject_key")))
        )
        return rows

    def _rerank(
        self,
        request: ThemeMatchRequest,
        candidate_rows: List[Dict[str, Any]],
        profile_map: Dict[str, ThemeProfile],
        event_profile: EventMatchProfile | None = None,
        counters: Dict[str, Any] | None = None,
        evidence_cache: Dict[str, Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        if not candidate_rows:
            return []

        model = self._get_sentence_model()
        event_text = _build_event_query_text(request, event_profile)
        query_vec = self._encode_query_vector(model, event_text, counters)
        valid_rows: List[Dict[str, Any]] = []
        doc_texts: List[str] = []
        for cand in candidate_rows:
            row = dict(cand)
            subject_key = _safe_str(row.get("subject_key"))
            profile = profile_map.get(subject_key)
            if not profile:
                continue
            doc_text = _safe_str(row.get("rerank_text")) or profile.rerank_text or profile.compact_text()
            row["rerank_text"] = doc_text
            valid_rows.append(row)
            doc_texts.append(doc_text)

        doc_vectors = self._encode_rerank_doc_vectors(model, valid_rows, doc_texts, counters)
        out: List[Dict[str, Any]] = []

        for row, doc_vec in zip(valid_rows, doc_vectors):
            profile = profile_map.get(_safe_str(row.get("subject_key")))
            if not profile:
                continue

            hit_features = _collect_profile_hit_features(request, profile, event_profile)
            feature_score = _calc_rerank_feature_score(hit_features)
            semantic_score = self._cosine_similarity(query_vec, doc_vec)
            cache_key = _safe_str(row.get("subject_key"))
            gate_evidence = (evidence_cache or {}).get(cache_key)
            if gate_evidence is None:
                gate_evidence = _build_gate_evidence(event_text, profile, event_profile)
                if evidence_cache is not None and cache_key:
                    evidence_cache[cache_key] = gate_evidence
            final_score = semantic_score + feature_score

            row["semantic_score"] = float(semantic_score)
            row["feature_score"] = feature_score
            row["rerank_score"] = float(final_score)
            row["rerank_hit_features"] = hit_features
            row["evidence"] = gate_evidence
            out.append(row)

        out.sort(
            key=lambda x: (-float(x.get("rerank_score") or 0.0), -float(x.get("dense_score") or 0.0), _safe_str(x.get("subject_key")))
        )
        return out

    def _encode_query_vector(
        self,
        model: Any,
        text: str,
        counters: Dict[str, Any] | None = None,
    ) -> List[float]:
        max_cache_size = _env_int("THEME_MATCH_QUERY_VECTOR_CACHE_MAX", 512)
        if max_cache_size <= 0:
            return self._to_vector_list(model.encode(text))
        cache_key = hashlib.sha1(_safe_str(text).encode("utf-8")).hexdigest()
        cached = self._query_vector_cache.get(cache_key)
        if cached is not None:
            self._query_vector_cache.move_to_end(cache_key)
            if counters is not None:
                counters["query_vector_cache_hit_count"] = int(counters.get("query_vector_cache_hit_count") or 0) + 1
            return cached
        if counters is not None:
            counters["query_vector_cache_miss_count"] = int(counters.get("query_vector_cache_miss_count") or 0) + 1
        vector = self._to_vector_list(model.encode(text))
        self._query_vector_cache[cache_key] = vector
        self._query_vector_cache.move_to_end(cache_key)
        while len(self._query_vector_cache) > max_cache_size:
            self._query_vector_cache.popitem(last=False)
        return vector

    def _encode_rerank_doc_vectors(
        self,
        model: Any,
        rows: List[Dict[str, Any]],
        doc_texts: List[str],
        counters: Dict[str, Any] | None = None,
    ) -> List[List[float]]:
        if not doc_texts:
            return []
        max_cache_size = _env_int("THEME_MATCH_RERANK_VECTOR_CACHE_MAX", 5000)
        if max_cache_size <= 0:
            encoded = model.encode(doc_texts)
            return [self._to_vector_list(x) for x in encoded]

        vectors: List[List[float] | None] = [None] * len(doc_texts)
        miss_indexes: List[int] = []
        miss_texts: List[str] = []
        for idx, (row, doc_text) in enumerate(zip(rows, doc_texts)):
            subject_key = _safe_str(row.get("subject_key"))
            cache_key = (subject_key, hashlib.sha1(doc_text.encode("utf-8")).hexdigest())
            cached = self._rerank_doc_vector_cache.get(cache_key)
            if cached is not None:
                self._rerank_doc_vector_cache.move_to_end(cache_key)
                vectors[idx] = cached
                if counters is not None:
                    counters["rerank_doc_vector_cache_hit_count"] = int(counters.get("rerank_doc_vector_cache_hit_count") or 0) + 1
                continue
            row["_rerank_vector_cache_key"] = cache_key
            miss_indexes.append(idx)
            miss_texts.append(doc_text)
            if counters is not None:
                counters["rerank_doc_vector_cache_miss_count"] = int(counters.get("rerank_doc_vector_cache_miss_count") or 0) + 1

        if miss_texts:
            encoded = [self._to_vector_list(x) for x in model.encode(miss_texts)]
            for idx, vector in zip(miss_indexes, encoded):
                cache_key = rows[idx].get("_rerank_vector_cache_key")
                if isinstance(cache_key, tuple):
                    self._rerank_doc_vector_cache[cache_key] = vector
                    self._rerank_doc_vector_cache.move_to_end(cache_key)
                    while len(self._rerank_doc_vector_cache) > max_cache_size:
                        self._rerank_doc_vector_cache.popitem(last=False)
                vectors[idx] = vector

        return [vector or [] for vector in vectors]

    def _should_call_llm_auto(self, candidates: List[Candidate], direct_hit_keys: List[str]) -> bool:
        if not candidates:
            return False
        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        best_ev = best.evidence or {}
        if best_ev.get("role_guard_blocked"):
            return False
        best_gap = float(best.rerank_score or 0.0) - (float(second.rerank_score or 0.0) if second else 0.0)
        conflict_score = int(best_ev.get("conflict_score") or 0)
        anchor_terms = _valid_anchor_terms(best_ev)
        direct_hit_set = set(direct_hit_keys)
        if best.subject_key in direct_hit_set and best_gap >= _env_float("THEME_MATCH_LLM_AUTO_DIRECT_GAP", 0.03) and anchor_terms and conflict_score == 0:
            return False
        if (
            best_ev.get("theme_name_direct_hit")
            and best_gap >= _env_float("THEME_MATCH_LLM_AUTO_NAME_GAP", 0.04)
            and anchor_terms
            and conflict_score == 0
        ):
            return False
        top = candidates[: min(5, len(candidates))]
        if top and all((c.evidence or {}).get("role_guard_blocked") or int((c.evidence or {}).get("positive_score") or 0) < 3 for c in top):
            return False
        return True

    def _materialize_candidates(self, rows: List[Dict[str, Any]], profile_map: Dict[str, ThemeProfile]) -> List[Candidate]:
        out: List[Candidate] = []
        for row in rows:
            sk = _safe_str(row.get("subject_key"))
            profile = profile_map.get(sk)
            if not profile:
                continue
            out.append(
                Candidate(
                    subject_key=sk,
                    subject_name=profile.subject_name,
                    dense_score=float(row.get("dense_score") or 0.0),
                    rerank_score=float(row.get("rerank_score") or 0.0),
                    evidence=row.get("evidence") or {},
                )
            )
        return out

    def _attach_runtime_audit(
        self,
        env: ThemeDecisionEnvelope,
        timing_ms: Dict[str, float],
        counters: Dict[str, Any],
    ) -> ThemeDecisionEnvelope:
        audit = env.audit if isinstance(env.audit, dict) else {}
        repo_stats: Dict[str, Any] = {}
        get_cache_stats = getattr(self.profile_repository, "get_cache_stats", None)
        if callable(get_cache_stats):
            try:
                repo_stats = get_cache_stats()
            except Exception:
                repo_stats = {}
        audit["performance"] = {
            "timing_ms": timing_ms,
            "counters": counters,
            "profile_cache_stats": repo_stats,
            "rerank_doc_vector_cache_size": len(self._rerank_doc_vector_cache),
            "query_vector_cache_size": len(self._query_vector_cache),
        }
        env.audit = audit
        return env

    def _build_related_matches(
        self,
        candidates: List[Candidate],
        profile_map: Dict[str, ThemeProfile],
        primary_subject_key: str,
    ) -> List[Dict[str, Any]]:
        if os.getenv("THEME_MATCH_ENABLE_MULTI_MATCH", "false").lower() not in {"1", "true", "yes", "on"}:
            return []
        max_related = max(0, int(os.getenv("THEME_MATCH_RELATED_MAX", "5") or 5))
        min_conf = float(os.getenv("THEME_MATCH_RELATED_MIN_CONF", "0.55") or 0.55)
        require_evidence = os.getenv("THEME_MATCH_RELATED_REQUIRE_EVIDENCE", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        related: List[Dict[str, Any]] = []
        seen = {str(primary_subject_key)}
        primary_profile = profile_map.get(primary_subject_key)
        for cand in candidates:
            if len(related) >= max_related:
                break
            if cand.subject_key in seen:
                continue
            evidence = cand.evidence or {}
            profile = profile_map.get(cand.subject_key)
            if not profile:
                continue
            if evidence.get("role_guard_blocked"):
                continue
            valid_anchor_terms = _valid_anchor_terms(evidence)
            entity_hits = _filter_generic_terms(evidence.get("entity_hits") or [])
            profile_anchor_hits = _filter_generic_terms(evidence.get("profile_anchor_hits") or [])
            same_domain = _same_industry_domain(primary_profile, profile)
            subject_family_hit = False
            if primary_profile:
                primary_name = _safe_str(primary_profile.subject_name)
                candidate_name = _safe_str(profile.subject_name)
                subject_family_hit = (
                    len(primary_name) >= 3
                    and len(candidate_name) >= 3
                    and (primary_name in candidate_name or candidate_name in primary_name)
                )
            strong_name_hit = bool((evidence.get("subject_name_direct_hit") and valid_anchor_terms) or subject_family_hit)
            has_evidence = bool(
                strong_name_hit
                or len([t for t in profile_anchor_hits if t in set(valid_anchor_terms)]) >= 2
                or (same_domain and len(valid_anchor_terms) >= 2)
                or (same_domain and len(entity_hits) >= 1 and len(valid_anchor_terms) >= 2)
            )
            if int(evidence.get("conflict_score") or 0) > 0 and not strong_name_hit:
                continue
            if require_evidence and not has_evidence:
                continue
            confidence = _squash01(0.52 + min(float(cand.rerank_score or 0.0) * 0.10, 0.25))
            if confidence < min_conf:
                continue
            related.append(
                {
                    "subject_key": cand.subject_key,
                    "theme_name": profile.subject_name,
                    "confidence": round(confidence, 4),
                    "relation_type": "related",
                    "reason": "top_candidate_evidence_related",
                    "evidence": evidence,
                }
            )
            seen.add(cand.subject_key)
        return related

    def _final_decide_rule_only(
        self,
        request: ThemeMatchRequest,
        candidates: List[Candidate],
        direct_hit_keys: List[str],
        profile_map: Dict[str, ThemeProfile],
    ) -> ThemeDecisionEnvelope:
        filtered_candidates = [
            cand for cand in candidates if not _has_blocking_conflict_evidence(cand.evidence or {})
        ]
        if candidates and not filtered_candidates:
            top_candidates = []
            for cand in candidates[:5]:
                profile = profile_map[cand.subject_key]
                top_candidates.append(
                    {
                        "subject_key": cand.subject_key,
                        "subject_name": profile.subject_name,
                        "dense_score": round(cand.dense_score, 4),
                        "rerank_score": round(cand.rerank_score, 4),
                        "evidence": cand.evidence,
                    }
                )
            return ThemeDecisionEnvelope(
                decision="HUMAN_REVIEW",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=_squash01(0.5),
                reason_code="all_candidates_conflicting_evidence",
                review_required=True,
                audit={"top_candidates": top_candidates, "best_evidence": candidates[0].evidence or {}},
            )
        if filtered_candidates:
            candidates = filtered_candidates
            direct_hit_keys = [key for key in direct_hit_keys if any(c.subject_key == key for c in candidates)]

        top_candidates = []
        for cand in candidates[:5]:
            profile = profile_map[cand.subject_key]
            top_candidates.append(
                {
                    "subject_key": cand.subject_key,
                    "subject_name": profile.subject_name,
                    "dense_score": round(cand.dense_score, 4),
                    "rerank_score": round(cand.rerank_score, 4),
                    "evidence": cand.evidence,
                }
            )

        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        best_profile = profile_map[best.subject_key]
        best_ev = best.evidence or {}
        best_gap = best.rerank_score - (second.rerank_score if second else 0.0)
        direct_hit_set = set(direct_hit_keys)
        related_matches = self._build_related_matches(candidates[1:], profile_map, best.subject_key)

        if best.rerank_score <= 0:
            return ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="no_candidate_hit",
                review_required=False,
                audit={"top_candidates": top_candidates},
            )

        if best_ev.get("role_guard_blocked"):
            return ThemeDecisionEnvelope(
                decision="HUMAN_REVIEW",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=_squash01(0.5),
                reason_code="role_guard_blocked",
                review_required=True,
                audit={"top_candidates": top_candidates, "best_evidence": best_ev},
            )

        if best.subject_key in direct_hit_set:
            competing_direct_hits = [c for c in candidates[1:5] if c.subject_key in direct_hit_set]
            if competing_direct_hits and best_gap < 0.03:
                return ThemeDecisionEnvelope(
                    decision="HUMAN_REVIEW",
                    event_id=request.event_id,
                    news_id=request.news_id,
                    confidence=_squash01(0.5),
                    reason_code="ambiguous_direct_hit_candidates",
                    matched_subject_key=best.subject_key,
                    matched_theme_name=best_profile.subject_name,
                    matched_theme_id=best_profile.theme_master_id,
                    review_required=True,
                    audit={"top_candidates": top_candidates, "best_evidence": best_ev},
                )

            return ThemeDecisionEnvelope(
                decision="MATCH",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=_squash01(0.88 + min(best.rerank_score * 0.08, 0.1)),
                reason_code="direct_theme_name_hit",
                matched_subject_key=best.subject_key,
                matched_theme_name=best_profile.subject_name,
                matched_theme_id=best_profile.theme_master_id,
                related_matches=related_matches,
                review_required=False,
                audit={"top_candidates": top_candidates, "best_evidence": best_ev},
            )

        if best_ev.get("theme_name_direct_hit") and best_gap >= 0.04:
            return ThemeDecisionEnvelope(
                decision="MATCH",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=_squash01(0.82 + min(best.rerank_score * 0.1, 0.12)),
                reason_code="profile_hit",
                matched_subject_key=best.subject_key,
                matched_theme_name=best_profile.subject_name,
                matched_theme_id=best_profile.theme_master_id,
                related_matches=related_matches,
                review_required=False,
                audit={"top_candidates": top_candidates, "best_evidence": best_ev},
            )

        if best_gap < 0.025:
            return ThemeDecisionEnvelope(
                decision="HUMAN_REVIEW",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=_squash01(0.5),
                reason_code="ambiguous_top_candidate",
                matched_subject_key=best.subject_key,
                matched_theme_name=best_profile.subject_name,
                matched_theme_id=best_profile.theme_master_id,
                review_required=True,
                audit={"top_candidates": top_candidates, "best_evidence": best_ev},
            )

        if best_ev.get("positive_score", 0) < 3:
            return ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="weak_candidate_evidence",
                review_required=False,
                audit={"top_candidates": top_candidates, "best_evidence": best_ev},
            )

        return ThemeDecisionEnvelope(
            decision="MATCH",
            event_id=request.event_id,
            news_id=request.news_id,
            confidence=_squash01(0.70 + min(best.rerank_score * 0.12, 0.18)),
            reason_code="profile_hit",
            matched_subject_key=best.subject_key,
            matched_theme_name=best_profile.subject_name,
            matched_theme_id=best_profile.theme_master_id,
            related_matches=related_matches,
            review_required=False,
            audit={"top_candidates": top_candidates, "best_evidence": best_ev},
        )

    def _final_decide_with_llm(
        self,
        request: ThemeMatchRequest,
        candidates: List[Candidate],
        profile_map: Dict[str, ThemeProfile],
        llm_result: Dict[str, Any],
    ) -> ThemeDecisionEnvelope:
        top_candidates = []
        for cand in candidates[:5]:
            profile = profile_map[cand.subject_key]
            top_candidates.append(
                {
                    "subject_key": cand.subject_key,
                    "subject_name": profile.subject_name,
                    "dense_score": round(cand.dense_score, 4),
                    "rerank_score": round(cand.rerank_score, 4),
                    "evidence": cand.evidence,
                }
            )

        verdict = _safe_str(llm_result.get("verdict"))
        conf = _squash01(float(llm_result.get("confidence") or 0.0))
        matched_theme_key = _safe_str(llm_result.get("best_theme_key"))
        matched_theme = profile_map.get(matched_theme_key) if matched_theme_key else None
        related_matches = self._build_related_matches(candidates, profile_map, matched_theme_key) if matched_theme_key else []
        audit = {
            "top_candidates": top_candidates,
            "llm_result": llm_result,
        }

        if verdict == "accept_match":
            if conf < 0.50 or not matched_theme:
                return ThemeDecisionEnvelope(
                    decision="HUMAN_REVIEW",
                    event_id=request.event_id,
                    news_id=request.news_id,
                    confidence=conf,
                    reason_code="llm_low_confidence_review",
                    matched_subject_key=matched_theme_key if matched_theme else "",
                    matched_theme_name=matched_theme.subject_name if matched_theme else "",
                    matched_theme_id=matched_theme.theme_master_id if matched_theme else None,
                    review_required=True,
                    audit=audit,
                )
            matched_candidate = next((c for c in candidates if c.subject_key == matched_theme.subject_key), None)
            matched_evidence = (matched_candidate.evidence if matched_candidate else {}) or {}
            if matched_evidence.get("role_guard_blocked"):
                return ThemeDecisionEnvelope(
                    decision="HUMAN_REVIEW",
                    event_id=request.event_id,
                    news_id=request.news_id,
                    confidence=min(conf, _squash01(0.5)),
                    reason_code="llm_accept_role_guard_blocked",
                    review_required=True,
                    audit={**audit, "best_evidence": matched_evidence},
                )
            if _has_only_generic_evidence(matched_evidence):
                return ThemeDecisionEnvelope(
                    decision="HUMAN_REVIEW",
                    event_id=request.event_id,
                    news_id=request.news_id,
                    confidence=min(conf, _squash01(0.5)),
                    reason_code="llm_accept_without_anchor_evidence",
                    matched_subject_key=matched_theme.subject_key,
                    matched_theme_name=matched_theme.subject_name,
                    matched_theme_id=matched_theme.theme_master_id,
                    review_required=True,
                    audit={**audit, "best_evidence": matched_evidence},
                )
            if _has_blocking_conflict_evidence(matched_evidence):
                return ThemeDecisionEnvelope(
                    decision="HUMAN_REVIEW",
                    event_id=request.event_id,
                    news_id=request.news_id,
                    confidence=min(conf, _squash01(0.5)),
                    reason_code="llm_accept_conflicting_alias_evidence",
                    matched_subject_key=matched_theme.subject_key,
                    matched_theme_name=matched_theme.subject_name,
                    matched_theme_id=matched_theme.theme_master_id,
                    review_required=True,
                    audit={**audit, "best_evidence": matched_evidence},
                )
            return ThemeDecisionEnvelope(
                decision="MATCH",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=conf,
                reason_code="llm_accept_match",
                matched_subject_key=matched_theme.subject_key,
                matched_theme_name=matched_theme.subject_name,
                matched_theme_id=matched_theme.theme_master_id,
                related_matches=related_matches,
                review_required=False,
                audit=audit,
            )

        if verdict in ("need_new_theme", "no_match"):
            return ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="llm_need_new_theme",
                review_required=False,
                audit=audit,
            )

        return ThemeDecisionEnvelope(
            decision="HUMAN_REVIEW",
            event_id=request.event_id,
            news_id=request.news_id,
            confidence=conf,
            reason_code="llm_review",
            matched_subject_key=matched_theme.subject_key if matched_theme else "",
            matched_theme_name=matched_theme.subject_name if matched_theme else "",
            matched_theme_id=matched_theme.theme_master_id if matched_theme else None,
            review_required=True,
            audit=audit,
        )
