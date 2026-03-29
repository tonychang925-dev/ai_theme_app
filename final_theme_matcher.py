#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import re
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from text2vec import SentenceModel


# =========================
# 通用工具
# =========================

def safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def squash01(x: float) -> float:
    return max(0.0, min(1.0, x))


def clip_text(text: str, max_len: int = 420) -> str:
    text = safe_str(text)
    return text if len(text) <= max_len else text[:max_len]


def normalize_text(text: Optional[str]) -> str:
    return safe_str(text)


def safe_json_loads(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def unique_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for x in items:
        s = safe_str(x)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def load_json_maybe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return s
    return v


def normalize_jsonb_list(v: Any) -> List[str]:
    v = load_json_maybe(v)
    if v is None:
        return []
    if isinstance(v, list):
        return unique_keep_order([safe_str(x) for x in v if safe_str(x)])
    if isinstance(v, str):
        return [v] if v else []
    return []


def normalize_name(s: str) -> str:
    s = safe_str(s).lower()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("－", "-").replace("—", "-").replace("–", "-")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[ \t\r\n/_\-.·]+", "", s)
    return s


def phrase_similarity(a: str, b: str) -> float:
    a = safe_str(a)
    b = safe_str(b)
    if not a or not b:
        return 0.0
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    return max(
        SequenceMatcher(None, na, nb).ratio(),
        SequenceMatcher(None, a, b).ratio(),
    )


def vector_to_pgvector_literal(vec: List[float]) -> str:
    return "'[" + ",".join(f"{x:.6f}" for x in vec) + "]'::vector"


# =========================
# Event
# =========================

def normalize_entities(v: Any) -> List[str]:
    v = load_json_maybe(v)
    out: List[str] = []
    if v is None:
        return out
    if isinstance(v, str):
        s = safe_str(v)
        return [s] if s else []
    if isinstance(v, list):
        for item in v:
            if isinstance(item, str):
                s = safe_str(item)
                if s:
                    out.append(s)
            elif isinstance(item, dict):
                cand = (
                    item.get("normalized")
                    or item.get("name")
                    or item.get("value")
                    or item.get("entity")
                    or ""
                )
                cand = safe_str(cand)
                if cand:
                    out.append(cand)
    return unique_keep_order(out)


def normalize_claims(v: Any) -> List[str]:
    v = load_json_maybe(v)
    out: List[str] = []
    if v is None:
        return out
    if isinstance(v, str):
        s = safe_str(v)
        return [s] if s else []
    if isinstance(v, list):
        for item in v:
            if isinstance(item, str):
                s = safe_str(item)
                if s:
                    out.append(s)
            elif isinstance(item, dict):
                cand = (
                    item.get("normalized")
                    or item.get("claim")
                    or item.get("text")
                    or item.get("name")
                    or ""
                )
                cand = safe_str(cand)
                if cand:
                    out.append(cand)
    return unique_keep_order(out)


@dataclass
class EventDoc:
    event_id: str
    title: str
    summary: str
    content: str
    event_type: str
    entities: List[str]
    claims: List[str]
    tech_terms: List[str]
    gt_theme: str = ""
    gt_subject_key: str = ""

    def event_text(self) -> str:
        parts: List[str] = []
        if self.title:
            parts.append(f"标题：{self.title}")
        if self.summary:
            parts.append(f"摘要：{self.summary}")
        if self.event_type:
            parts.append(f"事件类型：{self.event_type}")
        if self.entities:
            parts.append("实体：" + "、".join(self.entities[:12]))
        if self.claims:
            parts.append("事件要点：" + "；".join(self.claims[:10]))
        if self.tech_terms:
            parts.append("技术词：" + "、".join(self.tech_terms[:10]))
        if self.content:
            parts.append("正文：" + clip_text(self.content, 1200))
        return "\n".join(parts)


def build_event_doc(row: Dict[str, Any]) -> EventDoc:
    evidence_set = load_json_maybe(row.get("evidence_set")) or {}
    tech_terms = []

    if isinstance(evidence_set, dict):
        tech_terms.extend(normalize_jsonb_list(evidence_set.get("tech_phrases")))
        tech_terms.extend(normalize_jsonb_list(evidence_set.get("core_concepts")))

    tech_terms.extend(normalize_jsonb_list(row.get("tech_terms")))

    return EventDoc(
        event_id=safe_str(row.get("event_id") or row.get("id")),
        title=safe_str(row.get("title") or row.get("headline") or ""),
        summary=safe_str(row.get("summary") or row.get("text") or row.get("description") or ""),
        content=safe_str(row.get("content") or row.get("raw_text") or row.get("text") or row.get("summary") or ""),
        event_type=safe_str(row.get("event_type") or ""),
        entities=normalize_entities(row.get("entities")),
        claims=normalize_claims(row.get("claims") or row.get("causal_claim")),
        tech_terms=unique_keep_order(tech_terms),
        gt_theme=safe_str(row.get("gt_theme") or row.get("theme_name") or row.get("theme") or row.get("label") or ""),
        gt_subject_key=safe_str(row.get("gt_subject_key") or row.get("gt_theme_id") or ""),
    )


def load_events(path: str) -> List[EventDoc]:
    events: List[EventDoc] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    events.append(build_event_doc(obj))
            except Exception as e:
                print(f"[WARN] 跳过无效 JSONL 行 line={line_no}: {e}")
    return events


def build_event_query_text(event: EventDoc) -> str:
    return event.event_text()


# =========================
# ThemeProfile / Repo
# =========================

@dataclass
class ThemeProfile:
    subject_key: str
    subject_name: str
    concept: str
    semantic_type: str
    strategy_type: str
    ontology_json: Dict[str, Any]
    gate_json: Dict[str, Any]
    must_terms: List[str]
    should_terms: List[str]
    not_terms: List[str]
    strong_terms: List[str]
    weak_terms: List[str]
    negative_terms: List[str]
    search_text: str
    quality: str
    aliases: List[str] = field(default_factory=list)
    entity_hints: List[str] = field(default_factory=list)
    core_objects: List[str] = field(default_factory=list)

    def compact_text(self) -> str:
        return " ".join([
            safe_str(self.subject_name),
            safe_str(self.concept),
            safe_str(self.semantic_type),
            safe_str(self.strategy_type),
            " ".join(self.core_objects[:8]),
            " ".join(self.must_terms[:8]),
            " ".join(self.strong_terms[:8]),
            clip_text(self.search_text, 180),
        ]).strip()


class ThemeRepository:
    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn

    def load_all_profiles(self) -> List[ThemeProfile]:
        conn = psycopg2.connect(self.db_dsn)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    WITH fc AS (
                        SELECT DISTINCT source_id::text AS subject_key, category_name AS subject_name
                        FROM financial_categories
                        WHERE source_system = 'jyhf' AND source_id IS NOT NULL
                    ),
                    tm AS (
                        SELECT DISTINCT source_id::text AS subject_key, name AS subject_name
                        FROM theme_master
                        WHERE source_system = 'jyhf' AND source_id IS NOT NULL
                    )
                    SELECT
                        t.subject_key,
                        COALESCE(fc.subject_name, tm.subject_name, t.concept, t.subject_key) AS subject_name,
                        t.concept,
                        t.semantic_type,
                        t.strategy_type,
                        t.ontology_json,
                        t.gate_json,
                        t.must_terms,
                        t.should_terms,
                        t.not_terms,
                        t.strong_terms,
                        t.weak_terms,
                        t.negative_terms,
                        t.search_text,
                        t.quality
                    FROM theme_gate_profile t
                    LEFT JOIN fc ON fc.subject_key = t.subject_key
                    LEFT JOIN tm ON tm.subject_key = t.subject_key
                    ORDER BY t.subject_key
                """)
                rows = cur.fetchall()
        finally:
            conn.close()

        out: List[ThemeProfile] = []

        # 只过滤“明显泛词”，不要误伤 Manus / SpaceX / MLCP
        generic_alias_stopwords = {
            "AI", "AR", "VR", "XR", "IPO", "APP", "GPT", "AIGC"
        }

        for r in rows:
            ontology = load_json_maybe(r.get("ontology_json")) or {}
            aliases: List[str] = []
            entity_hints: List[str] = []
            core_objects: List[str] = []

            for key in ["aliases", "synonyms", "alias", "same_as"]:
                aliases.extend(normalize_jsonb_list(ontology.get(key)))
            for key in ["entities", "entity_hints", "brands", "products", "companies"]:
                entity_hints.extend(normalize_jsonb_list(ontology.get(key)))
            for key in ["core_objects", "objects", "anchors", "anchor_terms"]:
                core_objects.extend(normalize_jsonb_list(ontology.get(key)))

            base_subject_name = safe_str(r.get("subject_name"))
            base_concept = safe_str(r.get("concept"))

            auto_aliases = [base_subject_name, base_concept]

            # 自动抽取英文/字母数字 token
            # 注意：这里不能把 Manus 这种产品名过滤掉
            for source_text in [base_subject_name, base_concept]:
                if not source_text:
                    continue
                for tok in re.findall(r"[A-Za-z][A-Za-z0-9._-]{1,}", source_text):
                    tok = safe_str(tok)
                    if not tok:
                        continue
                    if tok.upper() in generic_alias_stopwords:
                        continue
                    auto_aliases.append(tok)

            # must_terms 里像 Manus 这种锚点，也并入 aliases，增强直命中召回
            must_terms = normalize_jsonb_list(r.get("must_terms"))
            for tok in must_terms:
                s = safe_str(tok)
                if not s:
                    continue
                if s.upper() in generic_alias_stopwords:
                    continue
                auto_aliases.append(s)

            final_aliases = unique_keep_order(aliases + auto_aliases)

            out.append(
                ThemeProfile(
                    subject_key=safe_str(r.get("subject_key")),
                    subject_name=base_subject_name,
                    concept=base_concept,
                    semantic_type=safe_str(r.get("semantic_type")),
                    strategy_type=safe_str(r.get("strategy_type")),
                    ontology_json=ontology,
                    gate_json=load_json_maybe(r.get("gate_json")) or {},
                    must_terms=must_terms,
                    should_terms=normalize_jsonb_list(r.get("should_terms")),
                    not_terms=normalize_jsonb_list(r.get("not_terms")),
                    strong_terms=normalize_jsonb_list(r.get("strong_terms")),
                    weak_terms=normalize_jsonb_list(r.get("weak_terms")),
                    negative_terms=normalize_jsonb_list(r.get("negative_terms")),
                    search_text=safe_str(r.get("search_text")),
                    quality=safe_str(r.get("quality")),
                    aliases=final_aliases,
                    entity_hints=unique_keep_order(entity_hints),
                    core_objects=unique_keep_order(core_objects + [base_subject_name, base_concept]),
                )
            )
        return out


# =========================
# Dense Recall + Rerank
# =========================

@dataclass
class Candidate:
    subject_key: str
    subject_name: str
    dense_score: float
    rerank_score: float = 0.0
    rerank_text: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

def collect_profile_hit_features(event: EventDoc, profile: ThemeProfile) -> Dict[str, Any]:
    """
    rerank 只看两类强信号：
    1. 题材名本体（subject_name / concept）直命中
    2. 题材名本体与结构化实体对齐

    注意：
    - aliases / must / strong / core_objects 不参与 rerank 特征分
    - 它们仍保留给 GateEvidenceBuilder / LLM 使用
    """
    event_text = event.event_text()
    event_text_norm = safe_str(event_text).lower()
    entity_names = {safe_str(x).lower() for x in event.entities if safe_str(x)}

    exact_name_terms = unique_keep_order(
        [profile.subject_name, profile.concept]
    )

    exact_name_hits = []
    entity_align_hits = []

    for t in exact_name_terms:
        s = safe_str(t)
        if not s:
            continue
        if s.lower() in event_text_norm:
            exact_name_hits.append(s)
        if s.lower() in entity_names:
            entity_align_hits.append(s)

    return {
        "exact_name_hits": unique_keep_order(exact_name_hits),
        "entity_align_hits": unique_keep_order(entity_align_hits),
    }


def calc_rerank_feature_score(hit_features: Dict[str, Any]) -> float:
    """
    rerank 辅助分只做温和前移：
    - exact_name_hits：题材名本体直命中
    - entity_align_hits：题材名本体与结构化实体对齐

    不再使用 must / strong / core_objects 干预 rerank，
    避免导弹/卫星这类 gate 锚点把排序冲坏。
    """
    exact_name_hit_n = len(hit_features.get("exact_name_hits", []))
    entity_align_n = len(hit_features.get("entity_align_hits", []))

    score = 0.0
    score += exact_name_hit_n * 0.20
    score += entity_align_n * 0.25

    return min(score, 0.45)

class DenseRecallStage:
    def __init__(self, db_dsn: str, model_name: str = "shibing624/text2vec-base-chinese"):
        self.db_dsn = db_dsn
        self.model = SentenceModel(model_name)

    def recall(self, query_text: str, top_k: int = 20) -> List[Dict[str, Any]]:
        query_vec = self.model.encode(query_text)
        if hasattr(query_vec, "tolist"):
            query_vec = query_vec.tolist()
        query_vec_literal = vector_to_pgvector_literal(query_vec)

        sql = f"""
        select
            t.subject_key,
            t.rerank_text,
            1 - (t.embedding <=> {query_vec_literal}) as dense_score
        from theme_profile_ext t
        where t.embedding is not null
        order by t.embedding <=> {query_vec_literal}
        limit %s
        """

        conn = psycopg2.connect(self.db_dsn)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (top_k,))
                return list(cur.fetchall())
        finally:
            conn.close()

    def rerank(
        self,
        event: EventDoc,
        candidates: List[Dict[str, Any]],
        profile_map: Dict[str, ThemeProfile],
    ) -> List[Dict[str, Any]]:
        """
        融合式 rerank：
        - 仍以 semantic cosine 为主体
        - 加入主题直命中 / entity 对齐 / must/strong/core_objects 命中辅助分
        - 让正确题材在 rerank 阶段自然前移，减少后置 inject 的副作用
        """
        if not candidates:
            return []

        query_text = build_event_query_text(event)

        query_vec = self.model.encode(query_text)
        if hasattr(query_vec, "tolist"):
            query_vec = query_vec.tolist()

        docs = [normalize_text(x.get("rerank_text")) for x in candidates]
        doc_vecs = self.model.encode(docs)

        reranked = []
        for cand, doc_vec in zip(candidates, doc_vecs):
            if hasattr(doc_vec, "tolist"):
                doc_vec = doc_vec.tolist()

            dot = sum(a * b for a, b in zip(query_vec, doc_vec))
            qn = math.sqrt(sum(a * a for a in query_vec))
            dn = math.sqrt(sum(a * a for a in doc_vec))
            semantic_score = dot / (qn * dn + 1e-12)

            row = dict(cand)
            sk = safe_str(row.get("subject_key"))
            profile = profile_map.get(sk)

            hit_features = {
                "theme_name_hits": [],
                "entity_align_hits": [],
                "must_hits": [],
                "strong_hits": [],
                "object_hits": [],
            }
            feature_score = 0.0

            if profile:
                hit_features = collect_profile_hit_features(event, profile)
                feature_score = calc_rerank_feature_score(hit_features)

            final_score = semantic_score + feature_score

            row["semantic_score"] = semantic_score
            row["feature_score"] = feature_score
            row["rerank_score"] = final_score
            row["rerank_hit_features"] = hit_features
            reranked.append(row)

        reranked.sort(
            key=lambda x: (
                -safe_float(x.get("rerank_score")),
                -safe_float(x.get("dense_score")),
                safe_str(x.get("subject_key")),
            )
        )
        return reranked


# =========================
# 动态 TopK
# =========================

def compute_dynamic_topk(
    candidate_rows: List[Dict[str, Any]],
    min_topk: int = 8,
    max_topk: int = 15,
    ratio_to_best: float = 0.90,
    margin_threshold: float = 0.035,
) -> int:
    if not candidate_rows:
        return min_topk

    rows = candidate_rows[:max_topk]
    rerank_scores = [safe_float(r.get("rerank_score"), 0.0) for r in rows]

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

def debug_print_candidate_rows(
    stage: str,
    rows: List[Dict[str, Any]],
    profile_map: Optional[Dict[str, "ThemeProfile"]] = None,
    target_subject_key: str = "9043089",
    limit: int = 30,
):
    print(f"\n[DEBUG] ===== {stage} | total={len(rows)} =====")
    for i, row in enumerate(rows[:limit], start=1):
        sk = safe_str(row.get("subject_key"))
        profile = profile_map.get(sk) if profile_map else None
        subject_name = profile.subject_name if profile else safe_str(row.get("subject_name"))
        print(
            f"[{i:02d}] "
            f"subject_key={sk} "
            f"subject_name={subject_name} "
            f"dense={safe_float(row.get('dense_score')):.4f} "
            f"semantic={safe_float(row.get('semantic_score')):.4f} "
            f"feature={safe_float(row.get('feature_score')):.4f} "
            f"rerank={safe_float(row.get('rerank_score')):.4f} "
            f"reserved={row.get('is_direct_hit_reserved', False)} "
            f"injected={row.get('is_injected', False)}"
        )

    target_rows = [r for r in rows if safe_str(r.get("subject_key")) == target_subject_key]
    print(f"[DEBUG] target_subject_key={target_subject_key} found={len(target_rows) > 0}")
    if target_rows:
        for row in target_rows:
            profile = profile_map.get(target_subject_key) if profile_map else None
            subject_name = profile.subject_name if profile else safe_str(row.get("subject_name"))
            print(
                f"[DEBUG][TARGET] "
                f"subject_key={target_subject_key} "
                f"subject_name={subject_name} "
                f"dense={safe_float(row.get('dense_score')):.4f} "
                f"semantic={safe_float(row.get('semantic_score')):.4f} "
                f"feature={safe_float(row.get('feature_score')):.4f} "
                f"rerank={safe_float(row.get('rerank_score')):.4f} "
                f"reserved={row.get('is_direct_hit_reserved', False)} "
                f"injected={row.get('is_injected', False)} "
                f"hit_features={row.get('rerank_hit_features', {})}"
            )

# =========================
# 候选注入：题材名/别名直命中
# =========================

def collect_direct_hit_subject_keys(
    event: EventDoc,
    profile_map: Dict[str, ThemeProfile],
) -> List[str]:
    """
    只收集题材名/别名在事件文本里直命中的题材。
    不排序，不加分。
    """
    event_text_norm = safe_str(event.event_text()).lower()
    out = []

    for sk, profile in profile_map.items():
        candidate_names = unique_keep_order(
            [profile.subject_name, profile.concept] + profile.aliases
        )

        for name in candidate_names:
            s = safe_str(name)
            if not s:
                continue
            if s.lower() in event_text_norm:
                out.append(sk)
                break

    return unique_keep_order(out)


def inject_direct_hit_candidates(
    reranked_rows: List[Dict[str, Any]],
    direct_hit_keys: List[str],
    profile_map: Dict[str, ThemeProfile],
    final_topk: int,
    max_inject: int = 2,
) -> List[Dict[str, Any]]:
    """
    inject 只做候选保底：
    - 不改变 rerank 主排序
    - 只给直命中但未入围的题材补少量席位
    - 最终候选数必须补满到 final_topk
    """
    reranked_rows = [dict(x) for x in reranked_rows]

    if final_topk <= 0:
        return []

    base_n = max(final_topk - max_inject, 1)
    final_rows = reranked_rows[:base_n]
    final_keys = {safe_str(x.get("subject_key")) for x in final_rows}

    appended_rows = []

    for sk in direct_hit_keys:
        if sk in final_keys:
            continue

        found = None
        for row in reranked_rows:
            if safe_str(row.get("subject_key")) == sk:
                found = dict(row)
                found["is_direct_hit_reserved"] = True
                break

        if found is None:
            profile = profile_map.get(sk)
            if not profile:
                continue
            found = {
                "subject_key": sk,
                "rerank_text": profile.compact_text(),
                "dense_score": 0.0,
                "semantic_score": 0.0,
                "feature_score": 0.0,
                "rerank_score": 0.0,
                "rerank_hit_features": {},
                "is_injected": True,
                "is_direct_hit_reserved": True,
            }

        appended_rows.append(found)
        if len(appended_rows) >= max_inject:
            break

    merged = final_rows + appended_rows

    deduped = []
    seen = set()
    for row in merged:
        sk = safe_str(row.get("subject_key"))
        if not sk or sk in seen:
            continue
        seen.add(sk)
        deduped.append(row)

    # 关键修复：如果直命中保底没补满，就按原 rerank 顺序补齐
    if len(deduped) < final_topk:
        for row in reranked_rows:
            sk = safe_str(row.get("subject_key"))
            if not sk or sk in seen:
                continue
            seen.add(sk)
            deduped.append(dict(row))
            if len(deduped) >= final_topk:
                break

    return deduped[:final_topk]

# =========================
# Gate Evidence Builder
# =========================

def token_hit_terms(text: str, terms: List[str]) -> List[str]:
    """
    返回 text 中命中的 term 列表（大小写不敏感），去重保持顺序。
    """
    text_norm = normalize_text(text).lower()
    hits = []
    for t in terms:
        t_norm = normalize_text(t).lower()
        if not t_norm:
            continue
        if t_norm in text_norm:
            hits.append(t)
    return unique_keep_order(hits)


class GateEvidenceBuilder:
    def build(self, event_text: str, theme: ThemeProfile) -> Dict[str, Any]:
        must_hits = token_hit_terms(event_text, theme.must_terms)
        strong_hits = token_hit_terms(event_text, theme.strong_terms)
        should_hits = token_hit_terms(event_text, theme.should_terms)
        not_hits = token_hit_terms(event_text, theme.not_terms)
        negative_hits = token_hit_terms(event_text, theme.negative_terms)
        object_hits = token_hit_terms(event_text, theme.core_objects + theme.aliases)
        entity_hits = token_hit_terms(event_text, theme.entity_hints)

        generic_alias_stopwords = {
            "AI", "AR", "VR", "XR", "IPO", "APP", "GPT", "AIGC"
        }

        # 只过滤明显泛词，不过滤 Manus / SpaceX
        object_hits = [
            x for x in object_hits
            if safe_str(x) and safe_str(x).upper() not in generic_alias_stopwords
        ]

        candidate_names = unique_keep_order(
            [theme.subject_name, theme.concept] + theme.aliases
        )

        event_text_norm = safe_str(event_text).lower()

        theme_name_hit_terms = []
        for name in candidate_names:
            name = safe_str(name)
            if not name:
                continue
            if name.upper() in generic_alias_stopwords:
                continue
            if name.lower() in event_text_norm:
                theme_name_hit_terms.append(name)
            if name in event_text:
                theme_name_hit_terms.append(name)

        theme_name_hit_terms = unique_keep_order(theme_name_hit_terms)
        theme_name_direct_hit = len(theme_name_hit_terms) > 0

        # 直命中分值必须明显高，才能让 LLM 真正重视
        theme_name_hit_score = 50 if theme_name_direct_hit else 0

        positive_score = (
            len(object_hits) * 3
            + len(must_hits) * 3
            + len(strong_hits) * 2
            + len(should_hits)
            + theme_name_hit_score
        )
        conflict_score = len(unique_keep_order(not_hits + negative_hits))

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
                "anchor_terms": unique_keep_order(object_hits + must_hits + strong_hits)[:8],
                "support_terms": unique_keep_order(should_hits + entity_hits)[:8],
                "conflict_terms": unique_keep_order(not_hits + negative_hits)[:8],
            }
        }

# =========================
# LLM Prompt Builder
# =========================

def build_llm_prompt(event: EventDoc, candidates: List[Candidate], profile_map: Dict[str, ThemeProfile]) -> str:
    blocks = []

    for i, c in enumerate(candidates, start=1):
        cid = f"C{i}"
        p = profile_map[c.subject_key]
        ev = c.evidence

        blocks.append(
            f"{cid}\n"
            f"题材名：{p.subject_name}\n"
            f"subject_key：{p.subject_key}\n"
            f"semantic_type：{p.semantic_type}\n"
            f"strategy_type：{p.strategy_type}\n"
            f"题材摘要：{clip_text(p.compact_text(), 260)}\n"
            f"dense_score：{round(c.dense_score, 4)}\n"
            f"rerank_score：{round(c.rerank_score, 4)}\n"
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

    prompt = f"""
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
{event.event_text()}

候选：
{chr(10).join(blocks)}
""".strip()

    return prompt


# =========================
# LLM Final Judge
# =========================

class FinalLLMJudge:
    def __init__(self, base_url: str, api_key: str, model: str, debug: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.debug = debug

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
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def judge(self, event: EventDoc, candidates: List[Candidate], profile_map: Dict[str, ThemeProfile]) -> Dict[str, Any]:
        idx_map: Dict[str, Candidate] = {}
        for i, c in enumerate(candidates, start=1):
            idx_map[f"C{i}"] = c

        prompt = build_llm_prompt(event, candidates, profile_map)

        if self.debug:
            print("\n[DEBUG][FinalLLMJudge Prompt]")
            print(prompt)

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

        last_err = None
        for attempt in range(1, 5):
            try:
                resp = self.session.post(url, headers=headers, json=payload, timeout=(20, 180))
                resp.raise_for_status()
                data = resp.json()

                text = safe_str(data["choices"][0]["message"]["content"])
                text = re.sub(r"^```json\s*", "", text)
                text = re.sub(r"^```\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

                if self.debug:
                    print("\n[DEBUG][FinalLLMJudge Raw]")
                    print(text)

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

                best_candidate = safe_str(obj.get("best_candidate"))
                best = idx_map.get(best_candidate)

                return {
                    "verdict": safe_str(obj.get("verdict") or "review"),
                    "best_candidate": best_candidate,
                    "best_theme_key": best.subject_key if best else "",
                    "best_theme_name": profile_map[best.subject_key].subject_name if best else "",
                    "confidence": squash01(safe_float(obj.get("confidence"), 0.0)),
                    "reason": safe_str(obj.get("reason")),
                    "new_theme_name": safe_str(obj.get("new_theme_name")),
                    "new_theme_desc": safe_str(obj.get("new_theme_desc")),
                }

            except (requests.exceptions.SSLError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.HTTPError) as e:
                last_err = e
                wait_s = min(2 ** attempt, 8)
                print(f"[WARN] LLM请求失败 event_id={event.event_id} attempt={attempt}/4 err={repr(e)}，{wait_s}s后重试")
                time.sleep(wait_s)
            except Exception as e:
                last_err = e
                break

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


# =========================
# Final Decision
# =========================

@dataclass
class FinalDecision:
    verdict: str
    matched_theme_id: Optional[str]
    matched_theme_name: Optional[str]
    confidence: float
    reason: str
    need_new_theme: bool
    new_theme_name: str
    new_theme_desc: str
    candidates: List[Dict[str, Any]]
    llm_result: Dict[str, Any]


class FinalDecisionExecutor:
    def __init__(self, review_threshold: float = 0.50):
        self.review_threshold = review_threshold

    def decide(self, llm_result: Dict[str, Any], candidates: List[Candidate], profile_map: Dict[str, ThemeProfile]) -> FinalDecision:
        verdict = safe_str(llm_result.get("verdict"))
        conf = safe_float(llm_result.get("confidence"), 0.0)

        matched_theme_id = safe_str(llm_result.get("best_theme_key")) or None
        matched_theme_name = safe_str(llm_result.get("best_theme_name")) or None
        need_new_theme = False

        if verdict == "accept_match":
            if conf < self.review_threshold:
                verdict = "review"
                matched_theme_id = None
                matched_theme_name = None
        elif verdict in ("need_new_theme", "no_match"):
            verdict = "need_new_theme"
            need_new_theme = True
            matched_theme_id = None
            matched_theme_name = None
        else:
            verdict = "review"
            matched_theme_id = None
            matched_theme_name = None

        cand_dump = []
        for c in candidates:
            p = profile_map[c.subject_key]
            cand_dump.append({
                "subject_key": c.subject_key,
                "subject_name": p.subject_name,
                "dense_score": round(c.dense_score, 4),
                "rerank_score": round(c.rerank_score, 4),
                "evidence": c.evidence,
            })

        return FinalDecision(
            verdict=verdict,
            matched_theme_id=matched_theme_id,
            matched_theme_name=matched_theme_name,
            confidence=round(conf, 4),
            reason=safe_str(llm_result.get("reason")),
            need_new_theme=need_new_theme,
            new_theme_name=safe_str(llm_result.get("new_theme_name")),
            new_theme_desc=safe_str(llm_result.get("new_theme_desc")),
            candidates=cand_dump,
            llm_result=llm_result,
        )


# =========================
# GT Resolver
# =========================

class GTResolver:
    def __init__(self, profiles: List[ThemeProfile]):
        self.profiles = profiles

    def resolve(self, gt_theme: str) -> str:
        gt_theme = safe_str(gt_theme)
        if not gt_theme:
            return ""

        best_key = ""
        best_score = 0.0

        for p in self.profiles:
            candidates = unique_keep_order([p.subject_name, p.concept] + p.aliases[:20])
            local_best = 0.0
            for c in candidates:
                local_best = max(local_best, phrase_similarity(gt_theme, c))
            if local_best > best_score:
                best_score = local_best
                best_key = p.subject_key

        return best_key if best_score >= 0.88 else ""


# =========================
# Main Pipeline
# =========================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument("--dense-model", default="shibing624/text2vec-base-chinese")
    parser.add_argument("--judge-model", default="deepseek-chat")
    parser.add_argument("--judge-base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--judge-api-key", required=True)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--llm-top-k", type=int, default=8)
    parser.add_argument("--llm-max-top-k", type=int, default=15)
    parser.add_argument("--event-id", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--detail-out", default="final_match_detail.json")
    parser.add_argument("--metrics-out", default="final_match_metrics.json")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    repo = ThemeRepository(args.db_dsn)
    profiles = repo.load_all_profiles()
    profile_map = {p.subject_key: p for p in profiles}

    dense_stage = DenseRecallStage(args.db_dsn, model_name=args.dense_model)
    gate_builder = GateEvidenceBuilder()
    judge = FinalLLMJudge(
        base_url=args.judge_base_url,
        api_key=args.judge_api_key,
        model=args.judge_model,
        debug=args.debug,
    )
    decider = FinalDecisionExecutor()
    gt_resolver = GTResolver(profiles)

    if args.debug:
        target_sk = "9043089"
        target_profile = profile_map.get(target_sk)
        print("\n[DEBUG] ===== target profile inspect =====")
        print(f"[DEBUG] target_sk={target_sk} exists={target_profile is not None}")
        if target_profile:
            print(f"[DEBUG] subject_name={target_profile.subject_name}")
            print(f"[DEBUG] concept={target_profile.concept}")
            print(f"[DEBUG] must_terms={target_profile.must_terms}")
            print(f"[DEBUG] should_terms={target_profile.should_terms}")
            print(f"[DEBUG] aliases={target_profile.aliases}")
            print(f"[DEBUG] core_objects={target_profile.core_objects}")

    events = load_events(args.events)
    if args.event_id:
        events = [e for e in events if e.event_id == args.event_id]
    if args.limit > 0:
        events = events[:args.limit]

    results = []
    total = len(events)
    top1 = top3 = top5 = 0

    group_stats = defaultdict(lambda: {
        "gt_subject_key": "",
        "gt_theme_name": "",
        "total": 0,
        "top1_hit": 0,
        "top3_hit": 0,
        "top5_hit": 0,
        "pred_counter": Counter(),
        "confusion_counter": Counter(),
    })

    def dump_progress():
        per_theme_metrics = []
        for gt_key, gs in group_stats.items():
            total_n = gs["total"]
            pred_counter = gs["pred_counter"]
            confusion_counter = gs["confusion_counter"]

            most_common_pred = ""
            most_common_pred_count = 0
            if pred_counter:
                most_common_pred, most_common_pred_count = pred_counter.most_common(1)[0]

            confusion_top3 = []
            for pred_key, cnt in confusion_counter.most_common(3):
                confusion_top3.append({
                    "pred_subject_key": pred_key,
                    "count": cnt,
                })

            per_theme_metrics.append({
                "gt_subject_key": gt_key,
                "gt_theme_name": gs["gt_theme_name"],
                "total": total_n,
                "top1_hit": gs["top1_hit"],
                "top3_hit": gs["top3_hit"],
                "top5_hit": gs["top5_hit"],
                "top1_accuracy": round(gs["top1_hit"] / total_n, 4) if total_n else 0.0,
                "top3_accuracy": round(gs["top3_hit"] / total_n, 4) if total_n else 0.0,
                "top5_accuracy": round(gs["top5_hit"] / total_n, 4) if total_n else 0.0,
                "most_common_top1_pred": most_common_pred,
                "most_common_top1_pred_count": most_common_pred_count,
                "confusion_top3": confusion_top3,
            })

        per_theme_metrics.sort(key=lambda x: (-x["total"], x["gt_subject_key"]))

        metrics = {
            "events": total,
            "processed": len(results),
            "top1_accuracy": round(top1 / len(results), 4) if results else 0.0,
            "top3_accuracy": round(top3 / len(results), 4) if results else 0.0,
            "top5_accuracy": round(top5 / len(results), 4) if results else 0.0,
            "per_theme_metrics": per_theme_metrics,
        }

        with open(args.detail_out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        with open(args.metrics_out, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)

        return metrics

    for idx, event in enumerate(events, start=1):
        try:
            query_text = build_event_query_text(event)

            if args.debug:
                print("\n" + "=" * 100)
                print(f"[DEBUG] event_id={event.event_id}")
                print(f"[DEBUG] gt_subject_key={event.gt_subject_key}")
                print(f"[DEBUG] gt_theme={event.gt_theme}")
                print(f"[DEBUG] query_text=\n{query_text}")

                gt_p = profile_map.get(event.gt_subject_key) if event.gt_subject_key else None
                print("\n[DEBUG] ===== GT profile inspect =====")
                print(f"[DEBUG] gt_subject_key={event.gt_subject_key}")
                print(f"[DEBUG] exists={gt_p is not None}")
                if gt_p:
                    print(f"[DEBUG] subject_name={gt_p.subject_name}")
                    print(f"[DEBUG] must_terms={gt_p.must_terms}")
                    print(f"[DEBUG] aliases={gt_p.aliases}")

            dense_rows = dense_stage.recall(query_text, top_k=args.top_k)
            if args.debug:
                debug_print_candidate_rows(
                    stage="after dense recall",
                    rows=dense_rows,
                    profile_map=profile_map,
                    target_subject_key=event.gt_subject_key or "9043089",
                    limit=30,
                )

            reranked_rows = dense_stage.rerank(
                event=event,
                candidates=dense_rows,
                profile_map=profile_map,
            )
            if args.debug:
                debug_print_candidate_rows(
                    stage="after fused rerank",
                    rows=reranked_rows,
                    profile_map=profile_map,
                    target_subject_key=event.gt_subject_key or "9043089",
                    limit=30,
                )

            dynamic_topk = compute_dynamic_topk(
                reranked_rows,
                min_topk=args.llm_top_k,
                max_topk=args.llm_max_top_k,
            )
            if args.debug:
                print(f"\n[DEBUG] dynamic_topk={dynamic_topk}")

            direct_hit_keys = collect_direct_hit_subject_keys(
                event=event,
                profile_map=profile_map,
            )
            if args.debug:
                print(f"\n[DEBUG] direct_hit_keys={direct_hit_keys}")

            candidate_rows = inject_direct_hit_candidates(
                reranked_rows=reranked_rows,
                direct_hit_keys=direct_hit_keys,
                profile_map=profile_map,
                final_topk=dynamic_topk,
                max_inject=2,
            )
            if args.debug:
                debug_print_candidate_rows(
                    stage="final candidate_rows after direct-hit reserve",
                    rows=candidate_rows,
                    profile_map=profile_map,
                    target_subject_key=event.gt_subject_key or "9043089",
                    limit=30,
                )

            candidates: List[Candidate] = []
            for row in candidate_rows:
                sk = safe_str(row["subject_key"])
                profile = profile_map.get(sk)
                if not profile:
                    if args.debug:
                        print(f"[DEBUG][WARN] subject_key={sk} not found in profile_map, skip")
                    continue

                evidence = gate_builder.build(query_text, profile)

                if args.debug:
                    print(
                        f"\n[DEBUG][EVIDENCE] "
                        f"subject_key={sk} "
                        f"subject_name={profile.subject_name} "
                        f"theme_name_direct_hit={evidence.get('theme_name_direct_hit')} "
                        f"theme_name_hit_terms={evidence.get('theme_name_hit_terms')} "
                        f"must_hits={evidence.get('must_hits')} "
                        f"strong_hits={evidence.get('strong_hits')} "
                        f"should_hits={evidence.get('should_hits')} "
                        f"object_hits={evidence.get('object_hits')} "
                        f"positive_score={evidence.get('positive_score')} "
                        f"conflict_score={evidence.get('conflict_score')}"
                    )

                candidates.append(
                    Candidate(
                        subject_key=sk,
                        subject_name=profile.subject_name,
                        dense_score=safe_float(row.get("dense_score")),
                        rerank_score=safe_float(row.get("rerank_score")),
                        rerank_text=safe_str(row.get("rerank_text")),
                        evidence=evidence,
                    )
                )

            llm_result = judge.judge(event, candidates, profile_map)
            if args.debug:
                print("\n[DEBUG] ===== llm_result =====")
                print(json.dumps(llm_result, ensure_ascii=False, indent=2))

            decision = decider.decide(llm_result, candidates, profile_map)
            if args.debug:
                print("\n[DEBUG] ===== final decision =====")
                print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))

            predicted_keys = []
            if decision.matched_theme_id:
                predicted_keys.append(decision.matched_theme_id)
            predicted_keys.extend(
                [x["subject_key"] for x in decision.candidates if x["subject_key"] != decision.matched_theme_id]
            )

            gt_key = event.gt_subject_key or gt_resolver.resolve(event.gt_theme)

            if gt_key:
                pred_top1 = predicted_keys[0] if predicted_keys else ""

                if gt_key in predicted_keys[:1]:
                    top1 += 1
                if gt_key in predicted_keys[:3]:
                    top3 += 1
                if gt_key in predicted_keys[:5]:
                    top5 += 1

                gs = group_stats[gt_key]
                gs["gt_subject_key"] = gt_key
                gs["gt_theme_name"] = event.gt_theme or gs["gt_theme_name"]
                gs["total"] += 1

                if gt_key in predicted_keys[:1]:
                    gs["top1_hit"] += 1
                if gt_key in predicted_keys[:3]:
                    gs["top3_hit"] += 1
                if gt_key in predicted_keys[:5]:
                    gs["top5_hit"] += 1

                if pred_top1:
                    gs["pred_counter"][pred_top1] += 1
                    if pred_top1 != gt_key:
                        gs["confusion_counter"][pred_top1] += 1

            results.append({
                "event_id": event.event_id,
                "gt_theme": event.gt_theme,
                "gt_subject_key": gt_key,
                "dynamic_llm_topk": dynamic_topk,
                "event_text": event.event_text(),
                "decision": asdict(decision),
            })

            print(
                f"[{idx}/{total}] "
                f"event_id={event.event_id} "
                f"topk={dynamic_topk} "
                f"verdict={decision.verdict} "
                f"theme={decision.matched_theme_name} "
                f"conf={decision.confidence}"
            )

        except Exception as e:
            print(f"[ERROR] event_id={event.event_id} 处理失败: {repr(e)}")
            results.append({
                "event_id": event.event_id,
                "gt_theme": event.gt_theme,
                "gt_subject_key": event.gt_subject_key or "",
                "dynamic_llm_topk": None,
                "event_text": event.event_text(),
                "decision": {
                    "verdict": "error",
                    "matched_theme_id": None,
                    "matched_theme_name": None,
                    "confidence": 0.0,
                    "reason": repr(e),
                    "need_new_theme": False,
                    "new_theme_name": "",
                    "new_theme_desc": "",
                    "candidates": [],
                    "llm_result": {},
                },
            })

        dump_progress()

    metrics = dump_progress()

    print("\n[完成] 评估指标：")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    print("\n[按 gt_subject_key 分组统计]")
    for row in metrics["per_theme_metrics"]:
        print(
            f"gt_subject_key={row['gt_subject_key']} "
            f"gt_theme_name={row['gt_theme_name']} "
            f"total={row['total']} "
            f"top1={row['top1_accuracy']:.4f} "
            f"top3={row['top3_accuracy']:.4f} "
            f"top5={row['top5_accuracy']:.4f} "
            f"most_common_top1_pred={row['most_common_top1_pred']} "
            f"pred_count={row['most_common_top1_pred_count']} "
            f"confusion_top3={row['confusion_top3']}"
        )


if __name__ == "__main__":
    main()