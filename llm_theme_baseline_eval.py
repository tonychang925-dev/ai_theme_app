#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
llm_theme_baseline_eval.py

两阶段题材匹配评估器（完整可运行版）

架构：
- Stage1-A：稳定的非LLM宽召回基础门禁
- Stage1-B：轻量LLM(Qwen)做“结构化证据门禁增强”
- Stage2：DeepSeek 做排他式最终精匹配裁决

关键原则：
1. Stage1-A 主导候选池，不依赖自由生成式 LLM 输出
2. Stage1-B 不做最终判定，只做 boost/down 增强
3. Stage1-B 输入采用紧凑 JSON 风格
4. Stage1-B 输出采用离散档位，而不是自由浮点分数
5. Stage1-B 输出若与真实 evidence 矛盾，直接 fallback neutral
6. Stage2 继续使用大模型做最终排他裁决
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, asdict, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from openai import OpenAI


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


def token_like_phrases(s: str) -> List[str]:
    s = safe_str(s)
    if not s:
        return []
    toks = re.findall(r"[A-Za-z0-9\-\+\.]+|[\u4e00-\u9fff]{2,}", s)
    return unique_keep_order([t for t in toks if len(t) >= 2])


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


def sat_count_score(hit_count: int, alpha: float = 2.0) -> float:
    if hit_count <= 0:
        return 0.0
    return 1.0 - math.exp(- hit_count / alpha)


def hit_at_k(predicted_keys: List[str], gt_key: str, k: int) -> bool:
    gt_key = safe_str(gt_key)
    if not gt_key:
        return False
    return gt_key in predicted_keys[:k]


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

    def event_phrases(self) -> List[str]:
        phrases: List[str] = []
        phrases.extend(self.entities)
        phrases.extend(self.claims)
        phrases.extend(self.tech_terms)
        if self.title:
            phrases.append(self.title)
        if self.summary:
            phrases.append(self.summary)
        raw = " ".join([self.title, self.summary, self.content])
        phrases.extend(token_like_phrases(raw))
        return unique_keep_order(phrases)


def build_event_doc(row: Dict[str, Any]) -> EventDoc:
    return EventDoc(
        event_id=safe_str(row.get("event_id") or row.get("id")),
        title=safe_str(row.get("title") or row.get("headline") or ""),
        summary=safe_str(row.get("summary") or row.get("text") or row.get("description") or ""),
        content=safe_str(row.get("content") or row.get("raw_text") or row.get("text") or row.get("summary") or ""),
        event_type=safe_str(row.get("event_type") or ""),
        entities=normalize_entities(row.get("entities")),
        claims=normalize_claims(row.get("claims") or row.get("causal_claim")),
        tech_terms=normalize_jsonb_list(row.get("tech_terms")),
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
    fts_score: float = 0.0
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


@dataclass
class Stage1AResult:
    subject_key: str
    subject_name: str
    recall_score: float
    lexical_score: float
    object_score: float
    must_score: float
    strong_score: float
    should_score: float
    weak_score: float
    semantic_type_score: float
    summary_score: float
    fts_score: float
    not_penalty: float
    negative_penalty: float
    object_hit_terms: List[str] = field(default_factory=list)
    must_hit_terms: List[str] = field(default_factory=list)
    strong_hit_terms: List[str] = field(default_factory=list)
    should_hit_terms: List[str] = field(default_factory=list)
    weak_hit_terms: List[str] = field(default_factory=list)
    not_hit_terms: List[str] = field(default_factory=list)
    negative_hit_terms: List[str] = field(default_factory=list)
    caps: List[str] = field(default_factory=list)


@dataclass
class Stage1Result:
    subject_key: str
    subject_name: str
    stage1a_score: float
    gate_boost_score: float
    final_score: float
    boost_level: str
    reason_code: str
    evidence_focus: str
    evidence: Dict[str, Any] = field(default_factory=dict)


class ThemeRepository:
    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn

    def load_all_profiles(self) -> List[ThemeProfile]:
        conn = psycopg2.connect(self.db_dsn)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    WITH fc AS (
                        SELECT DISTINCT
                            source_id::text AS subject_key,
                            category_name AS subject_name
                        FROM financial_categories
                        WHERE source_system = 'jyhf'
                          AND source_id IS NOT NULL
                    ),
                    tm AS (
                        SELECT DISTINCT
                            source_id::text AS subject_key,
                            name AS subject_name
                        FROM theme_master
                        WHERE source_system = 'jyhf'
                          AND source_id IS NOT NULL
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

            out.append(
                ThemeProfile(
                    subject_key=safe_str(r.get("subject_key")),
                    subject_name=safe_str(r.get("subject_name")),
                    concept=safe_str(r.get("concept")),
                    semantic_type=safe_str(r.get("semantic_type")),
                    strategy_type=safe_str(r.get("strategy_type")),
                    ontology_json=ontology,
                    gate_json=load_json_maybe(r.get("gate_json")) or {},
                    must_terms=normalize_jsonb_list(r.get("must_terms")),
                    should_terms=normalize_jsonb_list(r.get("should_terms")),
                    not_terms=normalize_jsonb_list(r.get("not_terms")),
                    strong_terms=normalize_jsonb_list(r.get("strong_terms")),
                    weak_terms=normalize_jsonb_list(r.get("weak_terms")),
                    negative_terms=normalize_jsonb_list(r.get("negative_terms")),
                    search_text=safe_str(r.get("search_text")),
                    quality=safe_str(r.get("quality")),
                    aliases=unique_keep_order(aliases + [safe_str(r.get("subject_name")), safe_str(r.get("concept"))]),
                    entity_hints=unique_keep_order(entity_hints),
                    core_objects=unique_keep_order(core_objects + [safe_str(r.get("subject_name")), safe_str(r.get("concept"))]),
                )
            )
        return out

    def fts_recall(self, event: EventDoc, limit_n: int = 80) -> Dict[str, float]:
        query_terms: List[str] = []
        query_terms.extend(event.entities[:8])
        query_terms.extend(event.tech_terms[:8])
        query_terms.extend(event.claims[:6])
        if event.title:
            query_terms.append(event.title)
        if event.summary:
            query_terms.append(event.summary)
        query_text = " ".join([safe_str(x) for x in query_terms if safe_str(x)])
        if not query_text:
            return {}

        conn = psycopg2.connect(self.db_dsn)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        subject_key,
                        ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS rank
                    FROM theme_gate_profile
                    WHERE search_vector @@ websearch_to_tsquery('simple', %s)
                    ORDER BY rank DESC
                    LIMIT %s
                """, (query_text, query_text, limit_n))
                rows = cur.fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()

        if not rows:
            return {}

        max_rank = max([safe_float(x["rank"], 0.0) for x in rows] + [1.0])
        return {
            safe_str(r["subject_key"]): safe_float(r["rank"], 0.0) / max_rank
            for r in rows
        }


def quality_to_weight(quality: str) -> float:
    q = safe_str(quality).lower()
    if q in ("strong", "high", "a"):
        return 1.05
    if q in ("medium", "mid", "b"):
        return 1.00
    if q in ("weak", "low", "c"):
        return 0.92
    return 0.98


def semantic_type_score(event: EventDoc, theme: ThemeProfile) -> float:
    st = safe_str(theme.semantic_type)
    et = safe_str(event.event_type)
    score = 0.45
    if not st:
        return score
    if ("发布" in et or "产品" in et) and any(x in st for x in ["产品", "技术", "应用", "消费", "event"]):
        score += 0.20
    if any(x in event.event_text() for x in ["政策", "法规", "关税", "制裁", "出口管制"]) and any(x in st for x in ["政策", "监管", "国际", "军事"]):
        score += 0.20
    return squash01(score)


def lexical_score(event: EventDoc, theme: ThemeProfile) -> float:
    text = event.event_text()
    norm_text = normalize_name(text)
    for term in unique_keep_order([theme.subject_name, theme.concept] + theme.aliases[:12]):
        nt = normalize_name(term)
        if nt and nt in norm_text:
            return 0.95
    return 0.0


def best_hit_terms(event_phrases: List[str], terms: List[str], threshold: float) -> Tuple[float, List[str]]:
    hits: List[str] = []
    best = 0.0
    hit_count = 0
    for term in terms:
        term = safe_str(term)
        if not term:
            continue
        local_best = 0.0
        for ep in event_phrases:
            s = phrase_similarity(ep, term)
            if s > local_best:
                local_best = s
        if local_best >= threshold:
            hits.append(term)
            hit_count += 1
        best = max(best, local_best)
    score = max(best, sat_count_score(hit_count, alpha=2.0))
    return squash01(score), unique_keep_order(hits)


def compute_stage1a_for_theme(event: EventDoc, theme: ThemeProfile) -> Stage1AResult:
    phrases = event.event_phrases()

    object_score, object_hits = best_hit_terms(phrases, theme.core_objects + theme.aliases, threshold=0.90)
    must_score, must_hits = best_hit_terms(phrases, theme.must_terms + theme.core_objects[:4], threshold=0.88)
    strong_score, strong_hits = best_hit_terms(phrases, theme.strong_terms + theme.aliases[:4], threshold=0.86)
    should_score, should_hits = best_hit_terms(phrases, theme.should_terms + theme.entity_hints[:4], threshold=0.84)
    weak_score, weak_hits = best_hit_terms(phrases, theme.weak_terms, threshold=0.82)

    not_score, not_hits = best_hit_terms(phrases, theme.not_terms, threshold=0.97)
    neg_score, neg_hits = best_hit_terms(phrases, theme.negative_terms, threshold=0.97)

    summary_score = max(0.0, phrase_similarity(event.summary, theme.compact_text()) - 0.75) * 0.5
    fts = theme.fts_score
    lex = lexical_score(event, theme)
    st_score = semantic_type_score(event, theme)

    raw = (
        0.26 * object_score
        + 0.22 * must_score
        + 0.16 * strong_score
        + 0.08 * should_score
        + 0.03 * weak_score
        + 0.07 * lex
        + 0.05 * st_score
        + 0.03 * summary_score
        + 0.03 * fts
    )

    caps: List[str] = []
    anchor = max(object_score, must_score, strong_score, lex)

    if anchor < 0.65:
        raw -= 0.05 * neg_score
        raw -= 0.08 * not_score
        if not_score > 0 or neg_score > 0:
            caps.append("negative_active_without_anchor")
    else:
        raw -= 0.005 * neg_score
        raw -= 0.01 * not_score
        if not_score > 0 or neg_score > 0:
            caps.append("negative_softened_by_anchor")

    if max(object_score, must_score, strong_score) < 0.45:
        raw = min(raw, 0.42)
        caps.append("cap_without_core_anchor")

    if max(object_score, must_score, strong_score, lex) < 0.25:
        raw = min(raw, 0.25)
        caps.append("cap_no_positive_signal")

    final = quality_to_weight(theme.quality) * max(0.0, raw)

    return Stage1AResult(
        subject_key=theme.subject_key,
        subject_name=theme.subject_name,
        recall_score=final,
        lexical_score=lex,
        object_score=object_score,
        must_score=must_score,
        strong_score=strong_score,
        should_score=should_score,
        weak_score=weak_score,
        semantic_type_score=st_score,
        summary_score=summary_score,
        fts_score=fts,
        not_penalty=not_score,
        negative_penalty=neg_score,
        object_hit_terms=object_hits,
        must_hit_terms=must_hits,
        strong_hit_terms=strong_hits,
        should_hit_terms=should_hits,
        weak_hit_terms=weak_hits,
        not_hit_terms=not_hits,
        negative_hit_terms=neg_hits,
        caps=caps,
    )


BOOST_MAP = {
    "strong_up": 0.12,
    "up": 0.06,
    "neutral": 0.00,
    "down": -0.05,
    "strong_down": -0.10,
}

ALLOWED_LEVELS = set(BOOST_MAP.keys())
ALLOWED_REASON_CODES = {
    "must_hit",
    "strong_hit",
    "should_core_semantic",
    "should_generic",
    "weak_hit",
    "not_hit",
    "negative_hit",
    "mixed",
    "neutral",
    "other",
}


class Stage1StructuredGateBooster:
    def __init__(self, base_url: str, api_key: str, model: str, debug: bool = False):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.debug = debug

    def build_payload(self, event: EventDoc, theme: ThemeProfile, sc: Stage1AResult) -> Dict[str, Any]:
        return {
            "event": {
                "summary": event.summary,
                "event_type": event.event_type,
                "entities": event.entities[:8],
                "claims": event.claims[:8],
                "tech_terms": event.tech_terms[:8],
            },
            "theme": {
                "name": theme.subject_name,
                "semantic_type": theme.semantic_type,
                "strategy_type": theme.strategy_type,
                "concept": theme.concept,
            },
            "evidence": {
                "object_hits": sc.object_hit_terms,
                "must_hits": sc.must_hit_terms,
                "strong_hits": sc.strong_hit_terms,
                "should_hits": sc.should_hit_terms,
                "weak_hits": sc.weak_hit_terms,
                "not_hits": sc.not_hit_terms,
                "negative_hits": sc.negative_hit_terms,
            },
            "stage1a": {
                "base_score": round(sc.recall_score, 4),
                "object_score": round(sc.object_score, 4),
                "must_score": round(sc.must_score, 4),
                "strong_score": round(sc.strong_score, 4),
                "should_score": round(sc.should_score, 4),
                "weak_score": round(sc.weak_score, 4),
            }
        }

    def prompt_from_payload(self, payload: Dict[str, Any]) -> str:
        return f"""
你是A股新闻事件题材第一阶段“门禁增强器”。

你的职责不是最终匹配，不是淘汰候选。
你只需要根据给定的结构化证据，输出一个离散增强档位 boost_level。

必须遵守：
1. 只能输出以下 boost_level 之一：
   - strong_up
   - up
   - neutral
   - down
   - strong_down
2. must_hits 非空时，通常应 strong_up 或 up。
3. strong_hits 非空时，通常应 up 或 strong_up。
4. should_hits 非空时，如果 should 承载事件核心语义，可输出 up；如果只是泛相关，最多 neutral。
5. weak_hits 非空时，通常最多 up，且多数情况下是 neutral。
6. not_hits 非空时，应 down 或 strong_down。
7. negative_hits 非空时，应 down 或 strong_down。
8. 如果没有任何正向或负向证据，通常输出 neutral。
9. 不要编造证据，不要复述整段事件原文。
10. 只输出 JSON。

输出格式：
{{
  "boost_level": "neutral",
  "reason_code": "should_core_semantic",
  "evidence_summary": "不超过20字"
}}

输入数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()

    def _validate_output(self, obj: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[str, str, str, bool]:
        level = safe_str(obj.get("boost_level"))
        reason = safe_str(obj.get("reason_code"))
        summary = clip_text(safe_str(obj.get("evidence_summary")), 40)

        ev = payload["evidence"]
        must_hits = ev["must_hits"]
        strong_hits = ev["strong_hits"]
        should_hits = ev["should_hits"]
        weak_hits = ev["weak_hits"]
        not_hits = ev["not_hits"]
        negative_hits = ev["negative_hits"]

        valid = True

        if level not in ALLOWED_LEVELS:
            valid = False
        if reason not in ALLOWED_REASON_CODES:
            valid = False

        if reason == "must_hit" and not must_hits:
            valid = False
        if reason == "strong_hit" and not strong_hits:
            valid = False
        if reason == "should_core_semantic" and not should_hits:
            valid = False
        if reason == "should_generic" and not should_hits:
            valid = False
        if reason == "weak_hit" and not weak_hits:
            valid = False
        if reason == "not_hit" and not not_hits:
            valid = False
        if reason == "negative_hit" and not negative_hits:
            valid = False

        pos_any = bool(must_hits or strong_hits or should_hits or weak_hits)
        neg_any = bool(not_hits or negative_hits)

        if (not pos_any and not neg_any) and level != "neutral":
            valid = False
        if neg_any and level in ("up", "strong_up") and not pos_any:
            valid = False
        if not neg_any and level in ("down", "strong_down") and not pos_any:
            valid = False
        if must_hits and level in ("down", "strong_down"):
            valid = False
        if strong_hits and level == "strong_down":
            valid = False
        if reason == "neutral" and level != "neutral":
            valid = False

        if not valid:
            return "neutral", "invalid_output_fallback", "输出与证据矛盾，回退中性", False

        return level, reason, (summary or "结构化证据增强"), True

    def boost_one(self, event: EventDoc, theme: ThemeProfile, sc: Stage1AResult) -> Dict[str, Any]:
        payload = self.build_payload(event, theme, sc)
        prompt = self.prompt_from_payload(payload)

        if self.debug:
            print("\n[DEBUG][Stage1-B Struct Prompt]")
            print(prompt)

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = safe_str(resp.choices[0].message.content)
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"^```\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            if self.debug:
                print("\n[DEBUG][Stage1-B Struct Raw]")
                print(text)

            obj = json.loads(text)
            level, reason, summary, ok = self._validate_output(obj, payload)

            return {
                "boost_level": level,
                "gate_boost_score": BOOST_MAP[level],
                "reason_code": reason,
                "evidence_summary": summary,
                "validated": ok,
            }
        except Exception:
            return {
                "boost_level": "neutral",
                "gate_boost_score": 0.0,
                "reason_code": "llm_error_fallback",
                "evidence_summary": "LLM增强失败，回退中性",
                "validated": False,
            }


class Stage1Pipeline:
    def __init__(self, repo: ThemeRepository, booster: Stage1StructuredGateBooster, debug: bool = False):
        self.repo = repo
        self.booster = booster
        self.debug = debug
        self.all_profiles = self.repo.load_all_profiles()
        self.profile_map = {p.subject_key: p for p in self.all_profiles}

    def generate_candidates(self, event: EventDoc, fts_limit: int = 80, candidate_pool_size: int = 60) -> List[Tuple[ThemeProfile, Stage1AResult]]:
        fts_scores = self.repo.fts_recall(event, limit_n=fts_limit)

        rows: List[Tuple[ThemeProfile, Stage1AResult]] = []
        for p in self.all_profiles:
            p.fts_score = fts_scores.get(p.subject_key, 0.0)
            sc = compute_stage1a_for_theme(event, p)
            rows.append((p, sc))

        rows.sort(key=lambda x: x[1].recall_score, reverse=True)
        return rows[:candidate_pool_size]

    def rerank_with_gate_boost(
        self,
        event: EventDoc,
        stage1a_pool: List[Tuple[ThemeProfile, Stage1AResult]],
        stage1_b_topm: int = 12,
        top_k: int = 20,
    ) -> List[Stage1Result]:
        out: List[Stage1Result] = []
        stage1_b_topm = max(1, stage1_b_topm)

        for idx, (theme, sc) in enumerate(stage1a_pool):
            if idx < stage1_b_topm:
                row = self.booster.boost_one(event, theme, sc)
                boost_level = row["boost_level"]
                gate_boost_score = safe_float(row["gate_boost_score"], 0.0)
                reason_code = safe_str(row["reason_code"])
                evidence_focus = safe_str(row["evidence_summary"])
                validated = bool(row.get("validated"))
            else:
                boost_level = "neutral"
                gate_boost_score = 0.0
                reason_code = "tail_neutral"
                evidence_focus = "候选尾部未进入LLM增强"
                validated = True

            anchor = max(sc.object_score, sc.must_score, sc.strong_score, sc.lexical_score)
            constraint_score = 1.0 if anchor >= 0.55 else 0.72 if anchor >= 0.35 else 0.45

            base_score = 0.80 * sc.recall_score + 0.20 * constraint_score
            final_score = squash01(base_score + gate_boost_score)

            evidence = {
                "stage1a_score": round(sc.recall_score, 4),
                "gate_boost_score": round(gate_boost_score, 4),
                "constraint_score": round(constraint_score, 4),
                "base_score": round(base_score, 4),
                "object_score": round(sc.object_score, 4),
                "must_score": round(sc.must_score, 4),
                "strong_score": round(sc.strong_score, 4),
                "should_score": round(sc.should_score, 4),
                "weak_score": round(sc.weak_score, 4),
                "fts_score": round(sc.fts_score, 4),
                "lexical_score": round(sc.lexical_score, 4),
                "semantic_type_score": round(sc.semantic_type_score, 4),
                "summary_score": round(sc.summary_score, 4),
                "negative_penalty": round(sc.negative_penalty, 4),
                "not_penalty": round(sc.not_penalty, 4),
                "object_hit_terms": sc.object_hit_terms,
                "must_hit_terms": sc.must_hit_terms,
                "strong_hit_terms": sc.strong_hit_terms,
                "should_hit_terms": sc.should_hit_terms,
                "weak_hit_terms": sc.weak_hit_terms,
                "not_hit_terms": sc.not_hit_terms,
                "negative_hit_terms": sc.negative_hit_terms,
                "caps": sc.caps,
                "boost_level": boost_level,
                "reason_code": reason_code,
                "evidence_focus": evidence_focus,
                "validated": validated,
            }

            out.append(
                Stage1Result(
                    subject_key=theme.subject_key,
                    subject_name=theme.subject_name,
                    stage1a_score=sc.recall_score,
                    gate_boost_score=gate_boost_score,
                    final_score=final_score,
                    boost_level=boost_level,
                    reason_code=reason_code,
                    evidence_focus=evidence_focus,
                    evidence=evidence,
                )
            )

        out.sort(key=lambda x: x.final_score, reverse=True)

        if self.debug:
            print("\n[DEBUG][Stage1 Top15]")
            for x in out[:15]:
                ev = x.evidence
                print(
                    f"{x.subject_name} | final={x.final_score:.4f} "
                    f"| base={ev['base_score']:.4f} stage1a={x.stage1a_score:.4f} boost={x.gate_boost_score:+.4f} "
                    f"| obj={ev['object_score']:.2f} must={ev['must_score']:.2f} strong={ev['strong_score']:.2f} "
                    f"| should={ev['should_score']:.2f} weak={ev['weak_score']:.2f} "
                    f"| level={x.boost_level} reason={x.reason_code} valid={ev['validated']} "
                    f"| caps={ev['caps']}"
                )

        return out[:top_k]

    def run(
        self,
        event: EventDoc,
        fts_limit: int = 80,
        candidate_pool_size: int = 60,
        stage1_b_topm: int = 12,
        top_k: int = 20,
    ) -> List[Stage1Result]:
        pool = self.generate_candidates(event, fts_limit, candidate_pool_size)
        return self.rerank_with_gate_boost(event, pool, stage1_b_topm, top_k)


class Stage2DeepSeekJudge:
    def __init__(self, base_url: str, api_key: str, model: str, debug: bool = False):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.debug = debug

    def judge(self, event: EventDoc, stage1_ranked: List[Stage1Result], profile_map: Dict[str, ThemeProfile]) -> Dict[str, Any]:
        blocks: List[str] = []
        idx_map: Dict[str, Stage1Result] = {}

        for i, sc in enumerate(stage1_ranked, start=1):
            cid = f"C{i}"
            idx_map[cid] = sc
            p = profile_map[sc.subject_key]
            ev = sc.evidence
            blocks.append(
                f"{cid}\n"
                f"题材名：{sc.subject_name}\n"
                f"semantic_type：{p.semantic_type}\n"
                f"题材摘要：{clip_text(p.compact_text(), 260)}\n"
                f"Stage1最终分：{round(sc.final_score, 4)}\n"
                f"Stage1增强级别：{sc.boost_level}\n"
                f"对象命中：{'、'.join(ev.get('object_hit_terms', [])) if ev.get('object_hit_terms') else '无'}\n"
                f"must命中：{'、'.join(ev.get('must_hit_terms', [])) if ev.get('must_hit_terms') else '无'}\n"
                f"strong命中：{'、'.join(ev.get('strong_hit_terms', [])) if ev.get('strong_hit_terms') else '无'}\n"
                f"should命中：{'、'.join(ev.get('should_hit_terms', [])) if ev.get('should_hit_terms') else '无'}\n"
                f"not命中：{'、'.join(ev.get('not_hit_terms', [])) if ev.get('not_hit_terms') else '无'}\n"
                f"负向命中：{'、'.join(ev.get('negative_hit_terms', [])) if ev.get('negative_hit_terms') else '无'}"
            )

        prompt = f"""
你是A股题材精匹配裁判器。
你必须在候选题材中做排他式判断，或明确输出 need_new_theme。

规则：
1. 优先看主叙事、主对象、关键动作，不看泛泛相关。
2. Stage1 分数仅作参考，不能盲从。
3. 若候选都不准确，必须输出 need_new_theme。
4. 只输出 JSON。

返回格式：
{{
  "verdict": "accept_match",
  "best_candidate": "C2",
  "confidence": 0.86,
  "reason": "一句话理由",
  "new_theme_name": "",
  "new_theme_desc": ""
}}

事件：
{event.event_text()}

候选题材：
{chr(10).join(blocks)}
""".strip()

        if self.debug:
            print("\n[DEBUG][Stage2 Prompt]")
            print(prompt)

        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        text = safe_str(resp.choices[0].message.content)
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        if self.debug:
            print("\n[DEBUG][Stage2 Raw]")
            print(text)

        try:
            obj = json.loads(text)
        except Exception:
            return {
                "verdict": "abstain",
                "best_candidate": "",
                "best_theme_key": "",
                "best_theme_name": "",
                "confidence": 0.0,
                "reason": f"JSON解析失败: {text[:300]}",
                "new_theme_name": "",
                "new_theme_desc": "",
            }

        best_candidate = safe_str(obj.get("best_candidate"))
        best_sc = idx_map.get(best_candidate)

        return {
            "verdict": safe_str(obj.get("verdict") or "abstain"),
            "best_candidate": best_candidate,
            "best_theme_key": best_sc.subject_key if best_sc else "",
            "best_theme_name": best_sc.subject_name if best_sc else "",
            "confidence": squash01(safe_float(obj.get("confidence"), 0.0)),
            "reason": safe_str(obj.get("reason")),
            "new_theme_name": safe_str(obj.get("new_theme_name")),
            "new_theme_desc": safe_str(obj.get("new_theme_desc")),
        }


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
    stage1_topk: List[Dict[str, Any]]
    stage2_result: Dict[str, Any]
    evidence_json: Dict[str, Any]


class DecisionExecutor:
    def __init__(self, accept_threshold: float = 0.72, review_threshold: float = 0.55, new_theme_threshold: float = 0.40):
        self.accept_threshold = accept_threshold
        self.review_threshold = review_threshold
        self.new_theme_threshold = new_theme_threshold

    def decide(self, event: EventDoc, stage1_ranked: List[Stage1Result], stage2_result: Dict[str, Any]) -> FinalDecision:
        top = stage1_ranked[0] if stage1_ranked else None
        stage2_conf = safe_float(stage2_result.get("confidence"), 0.0)
        stage1_conf = top.final_score if top else 0.0
        final_conf = round(max(stage2_conf, stage1_conf * 0.95), 4)

        verdict = safe_str(stage2_result.get("verdict"))
        matched_theme_id = safe_str(stage2_result.get("best_theme_key")) or None
        matched_theme_name = safe_str(stage2_result.get("best_theme_name")) or None
        reason = safe_str(stage2_result.get("reason"))
        new_theme_name = safe_str(stage2_result.get("new_theme_name"))
        new_theme_desc = safe_str(stage2_result.get("new_theme_desc"))
        need_new_theme = False

        if verdict in ("accept_match", "switch_theme"):
            if final_conf < self.review_threshold:
                verdict = "abstain"
        elif verdict in ("need_new_theme", "no_match"):
            if final_conf < self.new_theme_threshold or stage1_conf < self.review_threshold:
                verdict = "need_new_theme"
                need_new_theme = True
                matched_theme_id = None
                matched_theme_name = None
            else:
                verdict = "abstain"
        else:
            verdict = "abstain"

        stage1_topk = [{
            "subject_key": sc.subject_key,
            "subject_name": sc.subject_name,
            "final_score": round(sc.final_score, 4),
            "stage1a_score": round(sc.stage1a_score, 4),
            "gate_boost_score": round(sc.gate_boost_score, 4),
            "boost_level": sc.boost_level,
            "reason_code": sc.reason_code,
            "evidence_focus": sc.evidence_focus,
            "evidence": sc.evidence,
        } for sc in stage1_ranked]

        evidence_json = {
            "event_id": event.event_id,
            "stage1_topk": stage1_topk,
            "stage2_result": stage2_result,
            "thresholds": {
                "accept_threshold": self.accept_threshold,
                "review_threshold": self.review_threshold,
                "new_theme_threshold": self.new_theme_threshold,
            }
        }

        return FinalDecision(
            verdict=verdict,
            matched_theme_id=matched_theme_id,
            matched_theme_name=matched_theme_name,
            confidence=final_conf,
            reason=reason,
            need_new_theme=need_new_theme,
            new_theme_name=new_theme_name,
            new_theme_desc=new_theme_desc,
            stage1_topk=stage1_topk,
            stage2_result=stage2_result,
            evidence_json=evidence_json,
        )


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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--events", required=True, help="structured_events.jsonl")
    parser.add_argument("--db-dsn", required=True, help="PostgreSQL DSN")

    parser.add_argument("--stage1-model", default="qwen2.5-1.5b-instruct")
    parser.add_argument("--stage1-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--stage1-api-key", default="EMPTY")

    parser.add_argument("--stage2-model", default="deepseek-chat")
    parser.add_argument("--stage2-base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--stage2-api-key", default="EMPTY")

    parser.add_argument("--fts-limit", type=int, default=80)
    parser.add_argument("--candidate-pool-size", type=int, default=60)
    parser.add_argument(
        "--stage1-batch-size",
        dest="stage1_batch_size",
        type=int,
        default=12,
        help="进入 Stage1-B 结构化增强的前 M 个候选数量",
    )
    parser.add_argument("--top-k", type=int, default=20)

    parser.add_argument("--event-id", default="")
    parser.add_argument("--limit", type=int, default=0)

    parser.add_argument("--detail-out", default="match_detail.json")
    parser.add_argument("--metrics-out", default="match_metrics.json")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    repo = ThemeRepository(args.db_dsn)
    booster = Stage1StructuredGateBooster(
        base_url=args.stage1_base_url,
        api_key=args.stage1_api_key,
        model=args.stage1_model,
        debug=args.debug,
    )
    stage1 = Stage1Pipeline(repo=repo, booster=booster, debug=args.debug)
    stage2 = Stage2DeepSeekJudge(
        base_url=args.stage2_base_url,
        api_key=args.stage2_api_key,
        model=args.stage2_model,
        debug=args.debug,
    )
    decider = DecisionExecutor()
    gt_resolver = GTResolver(stage1.all_profiles)

    print(f"[INFO] 加载题材: {len(stage1.all_profiles)} 个")

    events = load_events(args.events)
    print(f"[INFO] 读取事件: {len(events)} 条")

    if args.event_id:
        events = [e for e in events if e.event_id == args.event_id]
        print(f"[INFO] 按 event_id 过滤后: {len(events)}")

    if args.limit > 0:
        events = events[:args.limit]
        print(f"[INFO] 按 limit 截断后: {len(events)}")

    profile_map = stage1.profile_map

    results: List[Dict[str, Any]] = []
    total = len(events)
    top1 = top3 = top5 = 0

    for idx, event in enumerate(events, start=1):
        stage1_ranked = stage1.run(
            event=event,
            fts_limit=args.fts_limit,
            candidate_pool_size=args.candidate_pool_size,
            stage1_b_topm=args.stage1_batch_size,
            top_k=args.top_k,
        )

        stage2_result = stage2.judge(
            event=event,
            stage1_ranked=stage1_ranked,
            profile_map=profile_map,
        )

        decision = decider.decide(
            event=event,
            stage1_ranked=stage1_ranked,
            stage2_result=stage2_result,
        )

        predicted_keys: List[str] = []
        if decision.matched_theme_id:
            predicted_keys.append(decision.matched_theme_id)
        predicted_keys.extend([
            x["subject_key"] for x in decision.stage1_topk
            if x["subject_key"] != decision.matched_theme_id
        ])

        gt_key = event.gt_subject_key or gt_resolver.resolve(event.gt_theme)

        if args.debug:
            print(f"[DEBUG] event_id={event.event_id} gt_theme={event.gt_theme!r}")
            print(f"[DEBUG] resolved_gt_key={gt_key!r}")
            print(f"[DEBUG] matched_theme_id={decision.matched_theme_id!r}")
            print(f"[DEBUG] predicted_keys_top5={predicted_keys[:5]!r}")

        if gt_key:
            if hit_at_k(predicted_keys, gt_key, 1):
                top1 += 1
            if hit_at_k(predicted_keys, gt_key, 3):
                top3 += 1
            if hit_at_k(predicted_keys, gt_key, 5):
                top5 += 1

        results.append({
            "event_id": event.event_id,
            "gt_theme": event.gt_theme,
            "gt_subject_key": gt_key,
            "event_text": event.event_text(),
            "decision": asdict(decision),
        })

        print(
            f"[{idx}/{len(events)}] "
            f"event_id={event.event_id} "
            f"verdict={decision.verdict} "
            f"theme={decision.matched_theme_name} "
            f"conf={decision.confidence}"
        )

    metrics = {
        "events": total,
        "top1_accuracy": round(top1 / total, 4) if total else 0.0,
        "top3_accuracy": round(top3 / total, 4) if total else 0.0,
        "top5_accuracy": round(top5 / total, 4) if total else 0.0,
    }

    with open(args.detail_out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(args.metrics_out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print("\n[完成] 评估指标：")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"[输出] 详细结果: {args.detail_out}")
    print(f"[输出] 评估指标: {args.metrics_out}")


if __name__ == "__main__":
    main()
