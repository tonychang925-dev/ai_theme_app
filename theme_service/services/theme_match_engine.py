from __future__ import annotations

import json
import math
import os
import re
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
    "商业航天",
    "应用",
    "卫星",
    "金融",
}


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
    text_norm = _normalize_text(text)
    hits: List[str] = []
    for term in terms:
        norm = _normalize_text(term)
        if norm and norm in text_norm:
            hits.append(_safe_str(term))
    return _unique(hits)


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


def _extract_event_tech_terms(request: ThemeMatchRequest) -> List[str]:
    evidence = request.evidence_set or {}
    out: List[str] = []
    if isinstance(evidence, dict):
        out.extend(_normalize_list(evidence.get("tech_phrases")))
        out.extend(_normalize_list(evidence.get("core_concepts")))
    return _unique(out)


def _build_event_query_text(request: ThemeMatchRequest) -> str:
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


def _build_llm_prompt(
    request: ThemeMatchRequest,
    candidates: List[Candidate],
    profile_map: Dict[str, ThemeProfile],
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
10. 只输出 JSON，不要输出额外解释。

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
{request.event_text()}

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
        prompt = _build_llm_prompt(request, candidates, profile_map)
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


def _collect_profile_hit_features(request: ThemeMatchRequest, profile: ThemeProfile) -> Dict[str, Any]:
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

    return {
        "exact_name_hits": _filter_generic_terms(exact_name_hits),
        "entity_align_hits": _filter_generic_terms(entity_align_hits),
    }


def _calc_rerank_feature_score(hit_features: Dict[str, Any]) -> float:
    exact_name_hit_n = len(hit_features.get("exact_name_hits", []))
    entity_align_n = len(hit_features.get("entity_align_hits", []))
    score = 0.0
    score += exact_name_hit_n * 0.20
    score += entity_align_n * 0.25
    return min(score, 0.45)


def _build_gate_evidence(event_text: str, profile: ThemeProfile) -> Dict[str, Any]:
    must_hits = _filter_generic_terms(_token_hit_terms(event_text, profile.must_terms))
    strong_hits = _filter_generic_terms(_token_hit_terms(event_text, profile.strong_terms))
    should_hits = _token_hit_terms(event_text, profile.should_terms)
    not_hits = _token_hit_terms(event_text, profile.not_terms)
    negative_hits = _token_hit_terms(event_text, profile.negative_terms)
    object_hits = _filter_generic_terms(_token_hit_terms(event_text, profile.core_objects + profile.aliases))
    entity_hits = _token_hit_terms(event_text, profile.entity_hints)

    candidate_names = _unique([profile.subject_name, profile.concept] + profile.aliases)
    theme_name_hit_terms: List[str] = []
    event_text_norm = _normalize_text(event_text)
    for name in candidate_names:
        s = _safe_str(name)
        if not s:
            continue
        if _normalize_text(s) in event_text_norm or s in event_text:
            theme_name_hit_terms.append(s)

    theme_name_hit_terms = _filter_generic_terms(theme_name_hit_terms)
    theme_name_direct_hit = len(theme_name_hit_terms) > 0
    theme_name_hit_score = 50 if theme_name_direct_hit else 0
    positive_score = (
        len(object_hits) * 3
        + len(must_hits) * 3
        + len(strong_hits) * 2
        + len(should_hits)
        + len(entity_hits)
        + theme_name_hit_score
    )
    conflict_score = len(_unique(not_hits + negative_hits))
    return {
        "theme_name_direct_hit": theme_name_direct_hit,
        "theme_name_hit_terms": theme_name_hit_terms,
        "theme_name_hit_score": theme_name_hit_score,
        "object_hits": object_hits,
        "must_hits": must_hits,
        "strong_hits": strong_hits,
        "should_hits": should_hits,
        "entity_hits": entity_hits,
        "not_hits": not_hits,
        "negative_hits": negative_hits,
        "positive_score": positive_score,
        "conflict_score": conflict_score,
        "evidence_summary": {
            "theme_name_hits": theme_name_hit_terms[:5],
            "anchor_terms": _unique(object_hits + must_hits + strong_hits)[:8],
            "support_terms": _unique(should_hits + entity_hits)[:8],
            "conflict_terms": _unique(not_hits + negative_hits)[:8],
        },
    }


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
    if gate_evidence.get("theme_name_direct_hit"):
        score += 2.50

    score += len(gate_evidence.get("object_hits") or []) * 0.35
    score += len(gate_evidence.get("must_hits") or []) * 0.35
    score += len(gate_evidence.get("strong_hits") or []) * 0.25
    score += len(gate_evidence.get("should_hits") or []) * 0.12
    score += len(gate_evidence.get("entity_hits") or []) * 0.12
    score -= len(gate_evidence.get("not_hits") or []) * 0.20
    score -= len(gate_evidence.get("negative_hits") or []) * 0.20
    return round(score, 6)


def _build_feature_recall_rows(
    request: ThemeMatchRequest,
    profile_map: Dict[str, ThemeProfile],
    top_k: int = 25,
) -> List[Dict[str, Any]]:
    event_text = _build_event_query_text(request)
    rows: List[Dict[str, Any]] = []
    for sk, profile in profile_map.items():
        hit_features = _collect_profile_hit_features(request, profile)
        gate_evidence = _build_gate_evidence(event_text, profile)
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
    out: List[str] = []
    for sk, profile in profile_map.items():
        candidate_names = _unique([profile.subject_name, profile.concept] + profile.aliases)
        for name in candidate_names:
            s = _safe_str(name)
            if not s:
                continue
            if s.upper() in GENERIC_MATCH_STOPWORDS or s in GENERIC_MATCH_STOPWORDS:
                continue
            if _normalize_text(s) in event_text_norm:
                out.append(sk)
                break
    return _unique(out)


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

    async def match_event(self, request: ThemeMatchRequest) -> ThemeDecisionEnvelope:
        profiles = await self.profile_repository.load_active_profiles()
        if not profiles:
            return ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="no_profile_loaded",
                review_required=False,
                audit={"top_candidates": []},
            )

        profile_map = {p.subject_key: p for p in profiles}
        recalled_rows = await self._dense_recall(request)
        sparse_rows = await self._sparse_recall(request)
        hybrid_rows = _rrf_merge_rows(recalled_rows, sparse_rows)
        feature_rows = _build_feature_recall_rows(request, profile_map)
        candidate_rows = _merge_recall_rows(hybrid_rows, feature_rows)
        reranked_rows = self._rerank(request, candidate_rows, profile_map)
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
            return ThemeDecisionEnvelope(
                decision="UNKNOWN",
                event_id=request.event_id,
                news_id=request.news_id,
                confidence=0.0,
                reason_code="no_candidate_hit",
                review_required=False,
                audit={"top_candidates": []},
            )

        if self._judge.enabled():
            llm_result = self._judge.judge(request, candidates, profile_map)
            return self._final_decide_with_llm(request, candidates, profile_map, llm_result)
        return self._final_decide_rule_only(request, candidates, direct_hit_keys, profile_map)

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

    async def _dense_recall(self, request: ThemeMatchRequest) -> List[Dict[str, Any]]:
        model = self._get_sentence_model()
        query_text = _build_event_query_text(request)
        query_vec = self._to_vector_list(model.encode(query_text))
        rows = await self.profile_repository.semantic_recall_candidates(query_vec, top_k=25)
        rows = _canonicalize_recall_rows(rows)
        rows.sort(
            key=lambda x: (-float(x.get("dense_score") or 0.0), _safe_str(x.get("subject_key")))
        )
        return rows

    async def _sparse_recall(self, request: ThemeMatchRequest) -> List[Dict[str, Any]]:
        query_text = _build_event_query_text(request)
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
    ) -> List[Dict[str, Any]]:
        if not candidate_rows:
            return []

        model = self._get_sentence_model()
        event_text = _build_event_query_text(request)
        query_vec = self._to_vector_list(model.encode(event_text))
        valid_rows: List[Dict[str, Any]] = []
        doc_texts: List[str] = []
        for cand in candidate_rows:
            row = dict(cand)
            profile = profile_map.get(_safe_str(row.get("subject_key")))
            if not profile:
                continue
            doc_text = _safe_str(row.get("rerank_text")) or profile.rerank_text or profile.compact_text()
            row["rerank_text"] = doc_text
            valid_rows.append(row)
            doc_texts.append(doc_text)

        doc_vectors = [self._to_vector_list(x) for x in model.encode(doc_texts)] if doc_texts else []
        out: List[Dict[str, Any]] = []

        for row, doc_vec in zip(valid_rows, doc_vectors):
            profile = profile_map.get(_safe_str(row.get("subject_key")))
            if not profile:
                continue

            hit_features = _collect_profile_hit_features(request, profile)
            feature_score = _calc_rerank_feature_score(hit_features)
            semantic_score = self._cosine_similarity(query_vec, doc_vec)
            gate_evidence = _build_gate_evidence(event_text, profile)
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
        for cand in candidates:
            if len(related) >= max_related:
                break
            if cand.subject_key in seen:
                continue
            evidence = cand.evidence or {}
            has_evidence = bool(
                evidence.get("theme_name_direct_hit")
                or evidence.get("positive_score", 0) >= 3
                or evidence.get("core_object_hits")
                or evidence.get("must_term_hits")
                or evidence.get("strong_term_hits")
            )
            if require_evidence and not has_evidence:
                continue
            confidence = _squash01(0.52 + min(float(cand.rerank_score or 0.0) * 0.10, 0.25))
            if confidence < min_conf:
                continue
            profile = profile_map.get(cand.subject_key)
            if not profile:
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
