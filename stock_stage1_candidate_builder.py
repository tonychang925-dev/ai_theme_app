#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from text2vec import SentenceModel


# =========================
# 通用工具
# =========================

WEAK_TERM_STOPWORDS = {
    "app", "网站", "平台", "系统", "方案", "产品", "服务", "应用", "业务",
    "能力", "功能", "模块", "终端", "软件", "硬件", "生态", "入口"
}


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


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


def vector_to_pgvector_literal(vec: List[float]) -> str:
    return "'[" + ",".join(f"{x:.6f}" for x in vec) + "]'::vector"


def parse_json_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [safe_str(i) for i in x if safe_str(i)]
    s = safe_str(x)
    if not s:
        return []
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [safe_str(i) for i in obj if safe_str(i)]
        if isinstance(obj, dict):
            return []
    except Exception:
        pass
    return [s]


def normalize_root_subject_key(root_key: str) -> str:
    rk = safe_str(root_key)
    if not rk:
        return ""
    if rk.startswith("JYHF_"):
        return rk
    return f"JYHF_{rk}"


def strip_jyhf_prefix(subject_key: str) -> str:
    sk = safe_str(subject_key)
    if sk.startswith("JYHF_"):
        return sk.replace("JYHF_", "", 1)
    return sk


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(a * a for a in vec2))
    return dot / (n1 * n2 + 1e-12)


def is_ascii_token(s: str) -> bool:
    s = safe_str(s)
    return bool(s) and all(ord(c) < 128 for c in s)


def filter_terms(
    terms: List[str],
    min_ascii_len: int = 4,
    min_cjk_len: int = 2,
) -> List[str]:
    out: List[str] = []
    for t in terms:
        s = safe_str(t)
        if not s:
            continue
        sl = s.lower()
        if sl in WEAK_TERM_STOPWORDS:
            continue
        if is_ascii_token(sl) and len(sl) < min_ascii_len:
            continue
        if (not is_ascii_token(sl)) and len(sl) < min_cjk_len:
            continue
        out.append(s)
    return unique_keep_order(out)


def contains_terms(text_lower: str, terms: List[str]) -> List[str]:
    hits = []
    for t in terms:
        s = safe_str(t)
        if not s:
            continue
        sl = s.lower()
        if is_ascii_token(sl):
            if re.search(r'(?<![A-Za-z0-9_])' + re.escape(sl) + r'(?![A-Za-z0-9_])', text_lower):
                hits.append(s)
        else:
            if sl in text_lower:
                hits.append(s)
    return unique_keep_order(hits)


def robust_parse_description(desc: Any) -> Dict[str, Any]:
    if isinstance(desc, dict):
        return desc

    s = safe_str(desc)
    if not s:
        return {}

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        frag = s[start:end + 1]
        try:
            obj = json.loads(frag)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    return {}


GENERIC_EVENT_WORDS = {
    "融资", "资金注入", "中国市场", "市场扩张", "国资参与",
    "估值", "IPO", "融资IPO", "扩张", "发展", "中国", "美国", "日本"
}

GENERIC_ANCHOR_STOPWORDS = {
    "中国", "美国", "日本", "全球", "国内", "国外", "海外", "全国", "本土",
    "中国市场", "海外市场", "国内市场", "国际市场", "市场", "产业", "行业"
}


def strip_generic_anchor_terms(terms: List[str]) -> List[str]:
    out = []
    for t in terms:
        s = safe_str(t)
        if not s:
            continue
        if s in GENERIC_ANCHOR_STOPWORDS:
            continue
        out.append(s)
    return unique_keep_order(out)


def expand_anchor_terms(terms: List[str]) -> List[str]:
    """Expand mixed or composite anchor strings into reusable sub-terms."""
    out: List[str] = []
    for t in terms:
        s = safe_str(t)
        if not s:
            continue
        out.append(s)
        # split common separators
        for part in re.split(r"[\/|｜、,，;；:：()（）\-—_]+", s):
            part = safe_str(part)
            if part:
                out.append(part)
        # split mixed Chinese / English chunks, e.g. "AI智能体Manus" -> ["AI", "智能体", "Manus"]
        for part in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", s):
            part = safe_str(part)
            if part:
                out.append(part)
    return unique_keep_order(out)


# =========================
# 数据结构
# =========================

@dataclass
class EventDoc:
    event_id: str
    theme_name: str = ""
    event_type: str = ""
    entities: List[str] = field(default_factory=list)
    summary: str = ""
    causal_claim: List[str] = field(default_factory=list)
    core_concepts: List[str] = field(default_factory=list)
    tech_phrases: List[str] = field(default_factory=list)
    raw_text: str = ""
    gt_subject_key: str = ""

    def event_text(self) -> str:
        parts = []
        if self.summary:
            parts.append(f"摘要：{self.summary}")
        if self.event_type:
            parts.append(f"事件类型：{self.event_type}")
        if self.entities:
            parts.append(f"实体：{'、'.join(unique_keep_order(self.entities))}")
        if self.causal_claim:
            parts.append(f"事件要点：{'；'.join(unique_keep_order(self.causal_claim))}")
        if self.tech_phrases:
            parts.append(f"技术词：{'、'.join(unique_keep_order(self.tech_phrases))}")
        if self.core_concepts:
            parts.append(f"核心概念：{'、'.join(unique_keep_order(self.core_concepts))}")
        if self.raw_text:
            parts.append(f"正文：{self.raw_text}")
        return "\n".join(parts)


@dataclass
class ThemeDirection:
    subject_key: str
    subject_name: str
    level: int = 0
    parent_id: str = ""
    ancestors: str = ""
    rerank_text: str = ""

    aliases: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    component_words: List[str] = field(default_factory=list)

    gate_must_terms: List[str] = field(default_factory=list)
    gate_should_terms: List[str] = field(default_factory=list)
    gate_strong_terms: List[str] = field(default_factory=list)
    gate_weak_terms: List[str] = field(default_factory=list)
    gate_negative_terms: List[str] = field(default_factory=list)

    negative_seeds: List[str] = field(default_factory=list)
    semantic_type: str = ""
    strategy_type: str = ""
    reason: str = ""
    stage1_theme_score: float = 0.0


@dataclass
class RootThemeCandidate:
    root_subject_key: str
    root_subject_name: str
    stage1_theme_score: float = 0.0
    directions: List[ThemeDirection] = field(default_factory=list)


@dataclass
class StockProfileRow:
    stock_id: str
    stock_name: str
    profile_text: str
    main_business_text: str = ""
    product_text: str = ""
    brand_text: str = ""
    order_text: str = ""
    relation_text: str = ""
    logic_text: str = ""
    fact_count: int = 0
    primary_fact_count: int = 0
    evidence_json: Dict[str, Any] = field(default_factory=dict)
    dense_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class StockFactRow:
    fact_id: int
    stock_id: str
    fact_type: str
    fact_value: str
    source: str
    confidence: float
    start_date: Optional[str]
    end_date: Optional[str]
    source_id: str
    evidence_span: str


@dataclass
class DirectionLevelStockCandidate:
    direction_key: str
    direction_name: str
    stock_id: str
    stock_name: str
    stage1_profile_score: float = 0.0
    stage1_gate_score: float = 0.0
    stage1_total_score: float = 0.0
    gate_passed: bool = False
    confidence_level: str = ""
    matched_fact_ids: List[int] = field(default_factory=list)
    matched_fact_types: List[str] = field(default_factory=list)
    anchor_hits: List[str] = field(default_factory=list)
    must_hits: List[str] = field(default_factory=list)
    should_hits: List[str] = field(default_factory=list)
    negative_hits: List[str] = field(default_factory=list)
    gate_reason: str = ""
    evidence_summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RootAggregatedStockCandidate:
    root_subject_key: str
    root_subject_name: str
    stock_id: str
    stock_name: str
    root_score: float = 0.0
    best_direction_score: float = 0.0
    direction_count: int = 0
    matched_direction_keys: List[str] = field(default_factory=list)
    matched_direction_names: List[str] = field(default_factory=list)
    matched_fact_ids: List[int] = field(default_factory=list)
    matched_fact_types: List[str] = field(default_factory=list)
    matched_terms: List[str] = field(default_factory=list)
    negative_hits: List[str] = field(default_factory=list)
    matched_directions: List[Dict[str, Any]] = field(default_factory=list)
    evidence_json: Dict[str, Any] = field(default_factory=dict)


# =========================
# 事件加载
# =========================

def load_events(path: str) -> List[EventDoc]:
    out: List[EventDoc] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = safe_str(line)
            if not line:
                continue
            obj = json.loads(line)
            evidence_set = obj.get("evidence_set") or {}

            entities = []
            for e in obj.get("entities") or []:
                if isinstance(e, dict):
                    name = safe_str(e.get("normalized") or e.get("name"))
                    if name:
                        entities.append(name)
                else:
                    name = safe_str(e)
                    if name:
                        entities.append(name)

            out.append(
                EventDoc(
                    event_id=safe_str(obj.get("event_id")),
                    theme_name=safe_str(obj.get("theme_name")),
                    event_type=safe_str(obj.get("event_type")),
                    entities=unique_keep_order(entities),
                    summary=safe_str(obj.get("summary")),
                    causal_claim=[safe_str(x) for x in (obj.get("causal_claim") or []) if safe_str(x)],
                    core_concepts=[safe_str(x) for x in (evidence_set.get("core_concepts") or []) if safe_str(x)],
                    tech_phrases=[safe_str(x) for x in (evidence_set.get("tech_phrases") or []) if safe_str(x)],
                    raw_text=safe_str(obj.get("raw_text")),
                    gt_subject_key=safe_str(obj.get("gt_subject_key")),
                )
            )
    return out


# =========================
# 数据库：root / profile / gate
# =========================

def fetch_root_theme_nodes(conn, root_subject_key: str) -> List[Dict[str, Any]]:
    norm_key = normalize_root_subject_key(root_subject_key)

    sql = """
    SELECT
        category_code AS subject_key,
        category_name AS name,
        category_level AS level,
        parent_code AS parent_subject_key,
        array_to_string(full_path, ',') AS ancestors
    FROM financial_categories
    WHERE category_code = %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (norm_key,))
        return list(cur.fetchall())


def fetch_theme_profile_ext_map(conn, subject_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    if not subject_keys:
        return {}

    sql = """
    SELECT
        subject_key,
        summary,
        core_anchors,
        supporting_entities,
        representative_events,
        embedding_text,
        rerank_text
    FROM theme_profile_ext
    WHERE subject_key = ANY(%s)
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (subject_keys,))
        rows = list(cur.fetchall())

    return {safe_str(r["subject_key"]): dict(r) for r in rows}


def fetch_theme_gate_profile_map(conn, subject_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    if not subject_keys:
        return {}

    sql = """
    SELECT
        subject_key,
        semantic_type,
        strategy_type,
        ontology_json,
        gate_json,
        must_terms,
        should_terms,
        not_terms,
        strong_terms,
        weak_terms,
        negative_terms,
        search_text,
        concept,
        quality
    FROM theme_gate_profile
    WHERE subject_key = ANY(%s)
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (subject_keys,))
        rows = list(cur.fetchall())

    out = {}
    for r in rows:
        sk = safe_str(r["subject_key"])

        ontology_json = r.get("ontology_json") or {}
        gate_json = r.get("gate_json") or {}

        if isinstance(ontology_json, str):
            try:
                ontology_json = json.loads(ontology_json)
            except Exception:
                ontology_json = {}

        if isinstance(gate_json, str):
            try:
                gate_json = json.loads(gate_json)
            except Exception:
                gate_json = {}

        aliases = []
        keywords = []
        component_words = []
        reason = ""

        if isinstance(ontology_json, dict):
            aliases = parse_json_list(
                ontology_json.get("aliases")
                or ontology_json.get("synonyms")
                or ontology_json.get("alias_terms")
            )
            component_words = parse_json_list(
                ontology_json.get("core_objects")
                or ontology_json.get("component_words")
                or ontology_json.get("objects")
            )

        if isinstance(gate_json, dict):
            keywords = parse_json_list(
                gate_json.get("keywords")
                or gate_json.get("search_terms")
                or gate_json.get("query_terms")
            )
            reason = safe_str(
                gate_json.get("reason")
                or gate_json.get("description")
                or gate_json.get("summary")
            )

        out[sk] = {
            "subject_key": sk,
            "semantic_type": safe_str(r.get("semantic_type")),
            "strategy_type": safe_str(r.get("strategy_type")),
            "ontology_json": ontology_json,
            "gate_json": gate_json,
            "must_terms": parse_json_list(r.get("must_terms")),
            "should_terms": parse_json_list(r.get("should_terms")),
            "not_terms": parse_json_list(r.get("not_terms")),
            "strong_terms": parse_json_list(r.get("strong_terms")),
            "weak_terms": parse_json_list(r.get("weak_terms")),
            "negative_terms": parse_json_list(r.get("negative_terms")),
            "search_text": safe_str(r.get("search_text")),
            "concept": safe_str(r.get("concept")),
            "quality": safe_str(r.get("quality")),
            "aliases": aliases,
            "keywords": keywords,
            "component_words": component_words,
            "reason": reason,
        }

    return out


def load_root_theme_candidates_from_db(
    db_dsn: str,
    root_subject_keys: List[str],
) -> Dict[str, RootThemeCandidate]:
    conn = psycopg2.connect(db_dsn)
    try:
        result: Dict[str, RootThemeCandidate] = {}

        for root_subject_key in root_subject_keys:
            tree_rows = fetch_root_theme_nodes(conn, root_subject_key)
            print(f"[DEBUG] root_subject_key={root_subject_key} root_rows={len(tree_rows)}")

            if not tree_rows:
                continue

            subject_keys = [strip_jyhf_prefix(x["subject_key"]) for x in tree_rows]
            profile_map = fetch_theme_profile_ext_map(conn, subject_keys)
            gate_map = fetch_theme_gate_profile_map(conn, subject_keys)

            root_name = ""
            directions: List[ThemeDirection] = []

            for row in tree_rows:
                raw_subject_key = safe_str(row["subject_key"])
                sk = strip_jyhf_prefix(raw_subject_key)
                name = safe_str(row.get("name"))
                root_name = name

                profile = profile_map.get(sk, {})
                gate = gate_map.get(sk, {})

                aliases = filter_terms(gate.get("aliases", []))
                keywords = filter_terms(gate.get("keywords", []))
                component_words = filter_terms(gate.get("component_words", []))

                gate_must_terms = filter_terms(gate.get("must_terms", []))
                gate_should_terms = filter_terms(gate.get("should_terms", []))
                gate_strong_terms = filter_terms(gate.get("strong_terms", []))
                gate_weak_terms = filter_terms(gate.get("weak_terms", []))
                gate_negative_terms = filter_terms(
                    gate.get("not_terms", []) + gate.get("negative_terms", [])
                )

                directions.append(
                    ThemeDirection(
                        subject_key=sk,
                        subject_name=name,
                        level=int(row.get("level") or 0),
                        parent_id=safe_str(row.get("parent_subject_key")),
                        ancestors=safe_str(row.get("ancestors")),
                        rerank_text=safe_str(
                            profile.get("rerank_text")
                            or profile.get("embedding_text")
                            or profile.get("summary")
                        ),
                        aliases=aliases,
                        keywords=keywords,
                        component_words=component_words,
                        gate_must_terms=gate_must_terms,
                        gate_should_terms=gate_should_terms,
                        gate_strong_terms=gate_strong_terms,
                        gate_weak_terms=gate_weak_terms,
                        gate_negative_terms=gate_negative_terms,
                        negative_seeds=gate_negative_terms,
                        semantic_type=gate.get("semantic_type", ""),
                        strategy_type=gate.get("strategy_type", ""),
                        reason=gate.get("reason", "") or gate.get("concept", "") or safe_str(profile.get("summary")),
                        stage1_theme_score=0.0,
                    )
                )

            print(f"[DEBUG] built directions for root={root_subject_key}: {len(directions)}")

            result[root_subject_key] = RootThemeCandidate(
                root_subject_key=strip_jyhf_prefix(tree_rows[0]["subject_key"]),
                root_subject_name=root_name or root_subject_key,
                stage1_theme_score=0.0,
                directions=directions,
            )

        return result
    finally:
        conn.close()



def load_root_theme_candidates_from_json(
    json_path: str,
    event_id: str,
) -> Dict[str, RootThemeCandidate]:
    with open(json_path, "r", encoding="utf-8") as f:
        obj = json.load(f)

    rows = obj.get(event_id) or []
    result: Dict[str, RootThemeCandidate] = {}

    for root in rows:
        root_subject_key = safe_str(root.get("root_subject_key"))
        root_subject_name = safe_str(root.get("root_subject_name"))
        stage1_theme_score = safe_float(root.get("stage1_theme_score"), 0.0)

        directions: List[ThemeDirection] = []
        for d in root.get("directions") or []:
            direction_subject_key = safe_str(d.get("subject_key"))
            direction_subject_name = safe_str(d.get("subject_name"))
            parent_id = root_subject_key if direction_subject_key != root_subject_key else ""
            ancestors = root_subject_key if direction_subject_key != root_subject_key else ""

            directions.append(
                ThemeDirection(
                    subject_key=direction_subject_key,
                    subject_name=direction_subject_name,
                    level=int(d.get("level") or 0),
                    parent_id=parent_id,
                    ancestors=ancestors,
                    rerank_text="",
                    aliases=filter_terms(parse_json_list(d.get("aliases"))),
                    keywords=filter_terms(parse_json_list(d.get("keywords"))),
                    component_words=filter_terms(parse_json_list(d.get("component_words"))),
                    gate_must_terms=[],
                    gate_should_terms=[],
                    gate_strong_terms=[],
                    gate_weak_terms=[],
                    gate_negative_terms=[],
                    negative_seeds=filter_terms(parse_json_list(d.get("negative_seeds"))),
                    semantic_type=safe_str(d.get("semantic_type")),
                    strategy_type=safe_str(d.get("strategy_type")),
                    reason=safe_str(d.get("reason")),
                    stage1_theme_score=stage1_theme_score,
                )
            )

        result[root_subject_key] = RootThemeCandidate(
            root_subject_key=root_subject_key,
            root_subject_name=root_subject_name,
            stage1_theme_score=stage1_theme_score,
            directions=directions,
        )

    return result


# =========================
# query 构建
# =========================

def build_direction_stock_query_text(event: EventDoc, direction: ThemeDirection) -> str:
    parts = []

    if direction.rerank_text:
        parts.append(f"方向画像：{direction.rerank_text}")
    else:
        if direction.subject_name:
            parts.append(f"方向：{direction.subject_name}")
        if direction.aliases:
            parts.append(f"方向别名：{'、'.join(unique_keep_order(direction.aliases[:10]))}")
        if direction.keywords:
            parts.append(f"方向关键词：{'、'.join(unique_keep_order(direction.keywords[:10]))}")
        if direction.component_words:
            parts.append(f"核心对象：{'、'.join(unique_keep_order(direction.component_words[:10]))}")
        if direction.reason:
            parts.append(f"方向说明：{direction.reason}")

    object_entities = []
    for x in event.entities:
        s = safe_str(x)
        if s and s not in {"中国", "美国", "日本"}:
            object_entities.append(s)
    if object_entities:
        parts.append(f"事件实体：{'、'.join(unique_keep_order(object_entities[:10]))}")

    object_concepts = []
    for x in event.core_concepts + event.tech_phrases:
        s = safe_str(x)
        if not s or s in GENERIC_EVENT_WORDS:
            continue
        object_concepts.append(s)
    if object_concepts:
        parts.append(f"核心概念：{'、'.join(unique_keep_order(object_concepts[:10]))}")

    return "\n".join(parts)


# =========================
# 股票画像召回
# =========================

class StockProfileRecallStage:
    def __init__(self, db_dsn: str, model_name: str = "shibing624/text2vec-base-chinese"):
        self.db_dsn = db_dsn
        self.model = SentenceModel(model_name)

    def recall(self, query_text: str, top_k: int = 30) -> List[Dict[str, Any]]:
        query_vec = self.model.encode(query_text)
        if hasattr(query_vec, "tolist"):
            query_vec = query_vec.tolist()
        query_vec_literal = vector_to_pgvector_literal(query_vec)

        sql = f"""
        SELECT
            stock_id,
            stock_name,
            profile_text,
            main_business_text,
            product_text,
            brand_text,
            order_text,
            relation_text,
            logic_text,
            fact_count,
            primary_fact_count,
            evidence_json,
            1 - (embedding <=> {query_vec_literal}) AS dense_score
        FROM stock_profile_ext
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> {query_vec_literal}
        LIMIT %s
        """

        conn = psycopg2.connect(self.db_dsn)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (top_k,))
                return list(cur.fetchall())
        finally:
            conn.close()

    def rerank(self, query_text: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        query_vec = self.model.encode(query_text)
        if hasattr(query_vec, "tolist"):
            query_vec = query_vec.tolist()

        docs = [safe_str(x.get("profile_text")) for x in candidates]
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
            row["rerank_score"] = semantic_score
            reranked.append(row)

        reranked.sort(
            key=lambda x: (
                -safe_float(x.get("rerank_score")),
                -safe_float(x.get("dense_score")),
                safe_str(x.get("stock_id")),
            )
        )
        return reranked


# =========================
# 股票 facts
# =========================

IMPORTANT_FACT_TYPES = [
    "main_business",
    "product",
    "technology",
    "order_contract",
    "investment",
    "customer_supplier",
    "benefit_logic",
    "industry_role",
    "research_report",
    "media_claim",
]


def fetch_stock_facts_by_stock_ids(
    db_dsn: str,
    stock_ids: List[str],
) -> Dict[str, List[StockFactRow]]:
    if not stock_ids:
        return {}

    sql = """
    SELECT
        id,
        stock_id,
        fact_type,
        fact_value,
        source,
        confidence,
        start_date,
        end_date,
        source_id,
        evidence_span
    FROM stock_facts
    WHERE stock_id = ANY(%s)
      AND fact_type = ANY(%s)
    ORDER BY stock_id, id
    """
    conn = psycopg2.connect(db_dsn)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (stock_ids, IMPORTANT_FACT_TYPES))
            rows = list(cur.fetchall())
    finally:
        conn.close()

    out: Dict[str, List[StockFactRow]] = defaultdict(list)
    for r in rows:
        out[safe_str(r["stock_id"])] .append(
            StockFactRow(
                fact_id=int(r["id"]),
                stock_id=safe_str(r["stock_id"]),
                fact_type=safe_str(r["fact_type"]),
                source=safe_str(r.get("source")),
                confidence=safe_float(r.get("confidence"), 1.0),
                start_date=str(r["start_date"]) if r.get("start_date") else None,
                end_date=str(r["end_date"]) if r.get("end_date") else None,
                source_id=safe_str(r.get("source_id")),
                fact_value=safe_str(r.get("fact_value")),
                evidence_span=safe_str(r.get("evidence_span")),
            )
        )
    return out


def fetch_stock_profile_map(conn, stock_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not stock_ids:
        return {}

    sql = """
    SELECT
        stock_id,
        stock_name,
        profile_text,
        main_business_text,
        product_text,
        order_text,
        relation_text,
        logic_text
    FROM stock_profile_ext
    WHERE stock_id = ANY(%s)
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_ids,))
        rows = list(cur.fetchall())

    return {safe_str(r["stock_id"]): dict(r) for r in rows}


# =========================
# Gate + 打分
# =========================

PRIMARY_FACT_TYPES = {"main_business", "product", "technology", "order_contract", "investment"}


def collect_direction_terms(direction: ThemeDirection, event: EventDoc) -> Dict[str, List[str]]:
    strong_anchor_candidates = expand_anchor_terms(
        [direction.subject_name]
        + direction.aliases
        + direction.component_words[:20]
        + direction.gate_strong_terms[:10]
        + direction.gate_must_terms[:10]
    )
    strong_anchor_terms = strip_generic_anchor_terms(filter_terms(strong_anchor_candidates))

    soft_anchor_candidates = expand_anchor_terms(
        direction.gate_should_terms[:8]
        + direction.keywords[:8]
        + event.entities[:8]
        + event.core_concepts[:8]
        + event.tech_phrases[:8]
    )
    soft_anchor_terms = strip_generic_anchor_terms(filter_terms(soft_anchor_candidates))

    must_terms = unique_keep_order(strong_anchor_terms)
    should_terms = strip_generic_anchor_terms(filter_terms(
        expand_anchor_terms(
            direction.gate_should_terms[:12]
            + direction.keywords[:8]
            + event.entities[:8]
            + event.core_concepts[:8]
            + event.tech_phrases[:8]
        )
    ))
    negative_terms = filter_terms(
        direction.gate_negative_terms[:12]
        + direction.negative_seeds[:8]
    )

    return {
        "strong_anchor_terms": unique_keep_order(strong_anchor_terms),
        "soft_anchor_terms": unique_keep_order(soft_anchor_terms),
        "must_terms": unique_keep_order(must_terms),
        "should_terms": unique_keep_order(should_terms),
        "negative_terms": unique_keep_order(negative_terms),
    }


def fact_text_for_match(f: StockFactRow) -> str:
    parts = [safe_str(f.fact_value), safe_str(f.evidence_span)]
    return "\n".join([x for x in parts if x]).lower()


def score_fact_type(fact_type: str) -> float:
    if fact_type == "main_business":
        return 1.00
    if fact_type in {"product", "technology"}:
        return 0.95
    if fact_type in {"order_contract", "investment"}:
        return 0.90
    if fact_type == "customer_supplier":
        return 0.75
    if fact_type in {"benefit_logic", "industry_role"}:
        return 0.65
    if fact_type in {"research_report", "media_claim"}:
        return 0.55
    return 0.40


def evaluate_direction_stock_candidate(
    direction: ThemeDirection,
    event: EventDoc,
    profile_row: StockProfileRow,
    fact_rows: List[StockFactRow],
) -> DirectionLevelStockCandidate:
    term_pack = collect_direction_terms(direction, event)

    strong_anchor_hits: List[str] = []
    soft_anchor_hits: List[str] = []
    must_hits: List[str] = []
    should_hits: List[str] = []
    negative_hits: List[str] = []
    matched_fact_ids: List[int] = []
    matched_fact_types: List[str] = []

    primary_hit_score = 0.0
    secondary_hit_score = 0.0

    # 1) facts 证据
    for f in fact_rows:
        text = fact_text_for_match(f)

        fact_strong_anchor_hits = contains_terms(text, term_pack["strong_anchor_terms"])
        fact_soft_anchor_hits = contains_terms(text, term_pack["soft_anchor_terms"])
        fact_must_hits = contains_terms(text, term_pack["must_terms"])
        fact_should_hits = contains_terms(text, term_pack["should_terms"])
        fact_negative_hits = contains_terms(text, term_pack["negative_terms"])

        if fact_strong_anchor_hits or fact_soft_anchor_hits or fact_must_hits or fact_should_hits or fact_negative_hits:
            matched_fact_ids.append(f.fact_id)
            matched_fact_types.append(f.fact_type)

        strong_anchor_hits.extend(fact_strong_anchor_hits)
        soft_anchor_hits.extend(fact_soft_anchor_hits)
        must_hits.extend(fact_must_hits)
        should_hits.extend(fact_should_hits)
        negative_hits.extend(fact_negative_hits)

        base_weight = score_fact_type(f.fact_type) * f.confidence

        if fact_strong_anchor_hits or fact_must_hits:
            if f.fact_type in PRIMARY_FACT_TYPES:
                primary_hit_score += 1.0 * base_weight
            else:
                secondary_hit_score += 0.6 * base_weight
        elif fact_soft_anchor_hits:
            if f.fact_type in PRIMARY_FACT_TYPES:
                primary_hit_score += 0.55 * base_weight
            else:
                secondary_hit_score += 0.35 * base_weight
        elif fact_should_hits:
            if f.fact_type in PRIMARY_FACT_TYPES:
                primary_hit_score += 0.20 * base_weight
            else:
                secondary_hit_score += 0.15 * base_weight

    # 2) profile 软锚点
    profile_anchor_text = "\n".join([
        safe_str(profile_row.profile_text),
        safe_str(profile_row.main_business_text),
        safe_str(profile_row.product_text),
        safe_str(profile_row.logic_text),
        safe_str(profile_row.relation_text),
    ]).lower()

    profile_strong_anchor_hits = strip_generic_anchor_terms(
        contains_terms(profile_anchor_text, term_pack["strong_anchor_terms"])
    )
    profile_soft_anchor_hits = strip_generic_anchor_terms(
        contains_terms(profile_anchor_text, term_pack["soft_anchor_terms"])
    )
    profile_should_hits = strip_generic_anchor_terms(
        contains_terms(profile_anchor_text, term_pack["should_terms"])
    )
    profile_negative_hits = contains_terms(profile_anchor_text, term_pack["negative_terms"])

    strong_anchor_hits.extend(profile_strong_anchor_hits)
    soft_anchor_hits.extend(profile_soft_anchor_hits)
    should_hits.extend(profile_should_hits)
    negative_hits.extend(profile_negative_hits)

    strong_anchor_hits = unique_keep_order(strip_generic_anchor_terms(strong_anchor_hits))
    soft_anchor_hits = unique_keep_order(strip_generic_anchor_terms(soft_anchor_hits))
    anchor_hits = unique_keep_order(strong_anchor_hits + soft_anchor_hits)
    must_hits = unique_keep_order(must_hits)
    should_hits = unique_keep_order(strip_generic_anchor_terms(should_hits))
    negative_hits = unique_keep_order(negative_hits)
    matched_fact_ids = [int(x) for x in unique_keep_order([str(x) for x in matched_fact_ids])]
    matched_fact_types = unique_keep_order(matched_fact_types)

    distinct_fact_id_count = len(matched_fact_ids)
    distinct_fact_type_count = len(matched_fact_types)

    gate_passed = False
    confidence_level = ""

    if negative_hits:
        gate_reason = "fail_negative_conflict"
    elif strong_anchor_hits and distinct_fact_id_count >= 2 and distinct_fact_type_count >= 2 and primary_hit_score > 0:
        gate_passed = True
        confidence_level = "high"
        gate_reason = "pass_anchor_and_coverage"
    elif anchor_hits and distinct_fact_id_count >= 1 and primary_hit_score >= 0.45:
        gate_passed = True
        confidence_level = "medium"
        gate_reason = "pass_soft_anchor_with_fact"
    elif profile_soft_anchor_hits and safe_float(profile_row.rerank_score) >= 0.68:
        gate_passed = True
        confidence_level = "low"
        gate_reason = "pass_profile_soft_anchor"
    elif (
        safe_float(profile_row.rerank_score) >= 0.705
        and safe_float(profile_row.dense_score) >= 0.705
        and len(fact_rows) == 0
    ):
        gate_passed = True
        confidence_level = "semantic_only"
        gate_reason = "pass_semantic_fallback"
    elif not anchor_hits and not profile_soft_anchor_hits:
        gate_reason = "fail_no_anchor"
    elif distinct_fact_id_count < 1 and not profile_soft_anchor_hits:
        gate_reason = "fail_no_fact"
    elif primary_hit_score < 0.45 and not profile_soft_anchor_hits:
        gate_reason = "fail_low_primary_support"
    else:
        gate_reason = "fail_insufficient_support"

    profile_score = 0.65 * safe_float(profile_row.rerank_score) + 0.35 * safe_float(profile_row.dense_score)
    gate_score = (
        min(primary_hit_score, 3.0) * 0.22 +
        min(secondary_hit_score, 2.0) * 0.12 +
        min(len(strong_anchor_hits), 5) * 0.08 +
        min(len(soft_anchor_hits), 5) * 0.04 +
        min(len(profile_soft_anchor_hits), 5) * 0.04 +
        min(len(should_hits), 5) * 0.02
    )
    if confidence_level == "semantic_only":
        gate_score *= 0.50
    elif confidence_level == "low":
        gate_score *= 0.75
    elif confidence_level == "medium":
        gate_score *= 0.90
    if negative_hits:
        gate_score -= 0.30

    total_score = profile_score + gate_score

    evidence_summary = {
        "anchor_hits": anchor_hits,
        "strong_anchor_hits": strong_anchor_hits,
        "soft_anchor_hits": soft_anchor_hits,
        "profile_soft_anchor_hits": profile_soft_anchor_hits,
        "must_hits": must_hits,
        "should_hits": should_hits,
        "negative_hits": negative_hits,
        "matched_fact_ids": matched_fact_ids,
        "matched_fact_types": matched_fact_types,
        "distinct_fact_id_count": distinct_fact_id_count,
        "distinct_fact_type_count": distinct_fact_type_count,
        "primary_hit_score": round(primary_hit_score, 6),
        "secondary_hit_score": round(secondary_hit_score, 6),
        "profile_score": round(profile_score, 6),
        "gate_score": round(gate_score, 6),
        "total_score": round(total_score, 6),
        "confidence_level": confidence_level,
        "gate_reason": gate_reason,
    }

    return DirectionLevelStockCandidate(
        direction_key=direction.subject_key,
        direction_name=direction.subject_name,
        stock_id=profile_row.stock_id,
        stock_name=profile_row.stock_name,
        stage1_profile_score=profile_score,
        stage1_gate_score=gate_score,
        stage1_total_score=total_score,
        gate_passed=gate_passed,
        confidence_level=confidence_level,
        matched_fact_ids=matched_fact_ids,
        matched_fact_types=matched_fact_types,
        anchor_hits=anchor_hits,
        must_hits=must_hits,
        should_hits=should_hits,
        negative_hits=negative_hits,
        gate_reason=gate_reason,
        evidence_summary=evidence_summary,
    )



# =========================
# 单方向 -> 股票候选
# =========================

def build_candidates_for_direction(
    db_dsn: str,
    event: EventDoc,
    direction: ThemeDirection,
    model_name: str,
    recall_top_k: int = 30,
    final_top_k: int = 10,
    debug: bool = False,
) -> List[DirectionLevelStockCandidate]:
    recall_stage = StockProfileRecallStage(db_dsn, model_name=model_name)
    query_text = build_direction_stock_query_text(event, direction)

    if debug:
        print("\n[DEBUG] ===== direction_query_text =====")
        print(f"direction={direction.subject_name}")
        print(query_text)

    profile_rows_raw = recall_stage.recall(query_text=query_text, top_k=recall_top_k)
    profile_rows_raw = recall_stage.rerank(query_text=query_text, candidates=profile_rows_raw)

    profile_rows: List[StockProfileRow] = []
    for r in profile_rows_raw:
        profile_rows.append(
            StockProfileRow(
                stock_id=safe_str(r["stock_id"]),
                stock_name=safe_str(r["stock_name"]),
                profile_text=safe_str(r["profile_text"]),
                main_business_text=safe_str(r.get("main_business_text")),
                product_text=safe_str(r.get("product_text")),
                brand_text=safe_str(r.get("brand_text")),
                order_text=safe_str(r.get("order_text")),
                relation_text=safe_str(r.get("relation_text")),
                logic_text=safe_str(r.get("logic_text")),
                fact_count=int(r.get("fact_count") or 0),
                primary_fact_count=int(r.get("primary_fact_count") or 0),
                evidence_json=r.get("evidence_json") or {},
                dense_score=safe_float(r.get("dense_score")),
                rerank_score=safe_float(r.get("rerank_score")),
            )
        )

    if debug:
        print(f"\n[DEBUG] ===== direction recall total={len(profile_rows)} ({direction.subject_name}) =====")
        for i, x in enumerate(profile_rows[:10], start=1):
            print(
                f"[{i:02d}] stock_id={x.stock_id} stock_name={x.stock_name} "
                f"dense={x.dense_score:.4f} rerank={x.rerank_score:.4f}"
            )

    stock_ids = [x.stock_id for x in profile_rows]
    fact_map = fetch_stock_facts_by_stock_ids(db_dsn, stock_ids)

    candidates: List[DirectionLevelStockCandidate] = []
    fail_stats: Dict[str, int] = defaultdict(int)
    for p in profile_rows:
        fact_rows = fact_map.get(p.stock_id, [])
        cand = evaluate_direction_stock_candidate(
            direction=direction,
            event=event,
            profile_row=p,
            fact_rows=fact_rows,
        )
        if cand.gate_passed:
            candidates.append(cand)
        else:
            fail_stats[cand.gate_reason] += 1
            if debug:
                print(
                    f"[GATE_FAIL] stock_id={cand.stock_id} stock_name={cand.stock_name} "
                    f"reason={cand.gate_reason} "
                    f"anchor={cand.anchor_hits[:3]} "
                    f"profile_soft={cand.evidence_summary.get('profile_soft_anchor_hits', [])[:3]} "
                    f"must={cand.must_hits[:3]} "
                    f"fact_ids={len(cand.matched_fact_ids)} "
                    f"fact_types={cand.matched_fact_types[:5]}"
                )

    candidates.sort(
        key=lambda x: (-x.stage1_total_score, -x.stage1_profile_score, -x.stage1_gate_score, x.stock_id)
    )

    # verified 为空时，强制启用 semantic fallback 池
    if not candidates:
        semantic_pool: List[DirectionLevelStockCandidate] = []
        for p in profile_rows[: min(3, len(profile_rows))]:
            profile_score = 0.65 * safe_float(p.rerank_score) + 0.35 * safe_float(p.dense_score)
            semantic_pool.append(
                DirectionLevelStockCandidate(
                    direction_key=direction.subject_key,
                    direction_name=direction.subject_name,
                    stock_id=p.stock_id,
                    stock_name=p.stock_name,
                    stage1_profile_score=profile_score,
                    stage1_gate_score=0.0,
                    stage1_total_score=profile_score,
                    gate_passed=True,
                    confidence_level="semantic_only",
                    matched_fact_ids=[],
                    matched_fact_types=[],
                    anchor_hits=[],
                    must_hits=[],
                    should_hits=[],
                    negative_hits=[],
                    gate_reason="pass_semantic_pool_only",
                    evidence_summary={
                        "confidence_level": "semantic_only",
                        "matched_fact_ids": [],
                        "matched_fact_types": [],
                        "anchor_hits": [],
                        "profile_soft_anchor_hits": [],
                        "gate_reason": "pass_semantic_pool_only",
                        "profile_score": round(profile_score, 6),
                    },
                )
            )
        candidates = semantic_pool

    semantic_only_kept = 0
    filtered_candidates: List[DirectionLevelStockCandidate] = []
    for x in candidates:
        if x.confidence_level == "semantic_only":
            if semantic_only_kept >= 3:
                continue
            semantic_only_kept += 1
        filtered_candidates.append(x)
    candidates = filtered_candidates

    if debug:
        print(f"\n[DEBUG] ===== direction final candidates total={len(candidates)} ({direction.subject_name}) =====")
        for i, x in enumerate(candidates[:final_top_k], start=1):
            print(
                f"[{i:02d}] stock_id={x.stock_id} stock_name={x.stock_name} "
                f"total={x.stage1_total_score:.4f} confidence={x.confidence_level} "
                f"reason={x.gate_reason} anchor={x.anchor_hits[:3]} must={x.must_hits[:3]} facts={x.matched_fact_ids[:5]}"
            )
        print(f"[DEBUG] gate fail stats={dict(fail_stats)}")

    return candidates[:final_top_k]


# =========================
# root 聚合
# =========================

def aggregate_root_candidates(
    root: RootThemeCandidate,
    direction_results: Dict[str, List[DirectionLevelStockCandidate]],
    final_top_k: int = 15,
    debug: bool = False,
) -> List[RootAggregatedStockCandidate]:
    stock_map: Dict[str, Dict[str, Any]] = {}

    for direction in root.directions:
        rows = direction_results.get(direction.subject_key, [])
        for c in rows:
            sid = c.stock_id
            if sid not in stock_map:
                stock_map[sid] = {
                    "stock_id": c.stock_id,
                    "stock_name": c.stock_name,
                    "direction_scores": [],
                    "matched_direction_keys": [],
                    "matched_direction_names": [],
                    "matched_fact_ids": [],
                    "matched_fact_types": [],
                    "matched_terms": [],
                    "negative_hits": [],
                    "matched_directions": [],
                }

            stock_map[sid]["direction_scores"].append(c.stage1_total_score)
            stock_map[sid]["matched_direction_keys"].append(c.direction_key)
            stock_map[sid]["matched_direction_names"].append(c.direction_name)
            stock_map[sid]["matched_fact_ids"].extend(c.matched_fact_ids)
            stock_map[sid]["matched_fact_types"].extend(c.matched_fact_types)
            stock_map[sid]["matched_terms"].extend(c.anchor_hits + c.must_hits + c.should_hits)
            stock_map[sid]["negative_hits"].extend(c.negative_hits)
            stock_map[sid]["matched_directions"].append(
                {
                    "subject_key": c.direction_key,
                    "subject_name": c.direction_name,
                    "score": round(c.stage1_total_score, 6),
                    "confidence_level": c.confidence_level,
                    "anchor_hits": c.anchor_hits,
                    "matched_terms": unique_keep_order(c.anchor_hits + c.must_hits + c.should_hits),
                    "matched_fact_ids": c.matched_fact_ids,
                    "gate_reason": c.gate_reason,
                    "confidence_level": c.confidence_level,
                }
            )

    out: List[RootAggregatedStockCandidate] = []
    for sid, v in stock_map.items():
        direction_scores = sorted(v["direction_scores"], reverse=True)
        best_direction_score = direction_scores[0] if direction_scores else 0.0
        top2_sum = sum(direction_scores[:2])
        direction_count = len(direction_scores)
        evidence_strength = min(len(unique_keep_order([str(x) for x in v["matched_fact_ids"]])), 10) / 10.0

        root_score = (
            best_direction_score * 0.50 +
            top2_sum * 0.30 +
            min(direction_count, 3) * 0.10 +
            evidence_strength * 0.10
        )

        matched_fact_ids_unique = [int(x) for x in unique_keep_order([str(x) for x in v["matched_fact_ids"]])]

        evidence_json = {
            "root_subject_key": root.root_subject_key,
            "root_subject_name": root.root_subject_name,
            "root_score": round(root_score, 6),
            "best_direction_score": round(best_direction_score, 6),
            "direction_count": direction_count,
            "matched_directions": v["matched_directions"],
            "matched_fact_ids": [str(x) for x in matched_fact_ids_unique],
            "matched_fact_types": unique_keep_order(v["matched_fact_types"]),
            "matched_terms": unique_keep_order(v["matched_terms"]),
            "negative_hits": unique_keep_order(v["negative_hits"]),
            "top_direction": v["matched_directions"][0]["subject_name"] if v["matched_directions"] else "",
            "audit": {
                "rule_version": "stage1_gate_v8",
                "coverage_enabled": True,
                "anchor_required": True,
                "dual_pass_enabled": True,
            }
        }

        out.append(
            RootAggregatedStockCandidate(
                root_subject_key=root.root_subject_key,
                root_subject_name=root.root_subject_name,
                stock_id=v["stock_id"],
                stock_name=v["stock_name"],
                root_score=root_score,
                best_direction_score=best_direction_score,
                direction_count=direction_count,
                matched_direction_keys=unique_keep_order(v["matched_direction_keys"]),
                matched_direction_names=unique_keep_order(v["matched_direction_names"]),
                matched_fact_ids=matched_fact_ids_unique,
                matched_fact_types=unique_keep_order(v["matched_fact_types"]),
                matched_terms=unique_keep_order(v["matched_terms"]),
                negative_hits=unique_keep_order(v["negative_hits"]),
                matched_directions=v["matched_directions"],
                evidence_json=evidence_json,
            )
        )

    out.sort(key=lambda x: (-x.root_score, -x.best_direction_score, -x.direction_count, x.stock_id))

    if debug:
        print(f"\n[DEBUG] ===== root aggregated stocks total={len(out)} ({root.root_subject_name}) =====")
        for i, x in enumerate(out[:final_top_k], start=1):
            print(
                f"[{i:02d}] stock_id={x.stock_id} stock_name={x.stock_name} "
                f"root_score={x.root_score:.4f} best_direction={x.best_direction_score:.4f} "
                f"direction_count={x.direction_count} matched_dirs={x.matched_direction_names[:3]}"
            )

    return out[:final_top_k]


# =========================
# 叶子读取与锚点挂载
# =========================

def fetch_leaf_themes_by_root(conn, root_subject_key: str) -> List[Dict[str, Any]]:
    root_code = normalize_root_subject_key(root_subject_key)
    root_code_alt = strip_jyhf_prefix(root_code)

    sql_fc = """
    SELECT
        category_code,
        category_name,
        category_level,
        parent_code,
        full_path
    FROM financial_categories
    WHERE category_code = ANY(%s)
       OR parent_code = ANY(%s)
    ORDER BY category_level, category_code
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql_fc, ([root_code, root_code_alt], [root_code, root_code_alt]))
        fc_rows = list(cur.fetchall())

    if not fc_rows:
        return []

    l2_codes_raw = [safe_str(x["category_code"]) for x in fc_rows if int(x["category_level"] or 0) == 2]
    l2_codes = unique_keep_order(l2_codes_raw + [strip_jyhf_prefix(x) for x in l2_codes_raw if safe_str(x)])

    sql_tm = """
    SELECT
        id,
        name,
        code,
        description,
        category1_code,
        category2_code,
        category3_code,
        source_id,
        theme_type
    FROM theme_master
    WHERE category1_code = ANY(%s)
      AND (
            category2_code = ANY(%s)
            OR cardinality(%s::varchar[]) = 0
          )
    ORDER BY name
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql_tm, ([root_code, root_code_alt], l2_codes, l2_codes))
        leaf_rows = list(cur.fetchall())

    out = []
    for r in leaf_rows:
        desc_obj = robust_parse_description(r.get("description"))

        full_name = safe_str(desc_obj.get("full_name"))
        lead_stock_id = safe_str(desc_obj.get("lead_stock_id"))
        lead_stock_name = safe_str(desc_obj.get("lead_stock_name"))
        leaf_summary = safe_str(
            desc_obj.get("summary")
            or desc_obj.get("description")
            or desc_obj.get("intro")
        )
        leaf_keywords = parse_json_list(desc_obj.get("keywords"))
        leaf_entities = parse_json_list(desc_obj.get("entities"))

        out.append(
            {
                "subject_key": safe_str(r.get("source_id") or r.get("code") or r.get("id")),
                "subject_name": safe_str(r.get("name")),
                "full_name": full_name,
                "lead_stock_id": lead_stock_id,
                "lead_stock_name": lead_stock_name,
                "category1_code": safe_str(r.get("category1_code")),
                "category2_code": safe_str(r.get("category2_code")),
                "category3_code": safe_str(r.get("category3_code")),
                "theme_type": safe_str(r.get("theme_type")),
                "leaf_summary": leaf_summary,
                "leaf_keywords": leaf_keywords,
                "leaf_entities": leaf_entities,
            }
        )

    return out


def build_leaf_anchor_text(leaf: Dict[str, Any], lead_profile: Dict[str, Any]) -> str:
    parts = []

    if leaf.get("subject_name"):
        parts.append(f"叶子题材：{leaf['subject_name']}")
    if leaf.get("full_name"):
        parts.append(f"题材路径：{leaf['full_name']}")
    if leaf.get("lead_stock_name"):
        parts.append(f"代表股：{leaf['lead_stock_name']}")
    if lead_profile.get("profile_text"):
        parts.append(f"代表股画像：{lead_profile['profile_text']}")

    return "\n".join([x for x in parts if x])


def build_leaf_evidence_terms(leaf: Dict[str, Any]) -> List[str]:
    terms = []
    terms.extend([safe_str(leaf.get("subject_name"))])
    terms.extend([safe_str(leaf.get("full_name"))])
    terms.extend(parse_json_list(leaf.get("leaf_keywords")))
    terms.extend(parse_json_list(leaf.get("leaf_entities")))

    full_name = safe_str(leaf.get("full_name"))
    if full_name:
        for x in re.split(r"[/\-｜|>→]+", full_name):
            x = safe_str(x)
            if x:
                terms.append(x)

    summary = safe_str(leaf.get("leaf_summary"))
    if summary:
        for x in re.split(r"[，,；;、/\|\n]+", summary):
            x = safe_str(x)
            if x:
                terms.append(x)

    return filter_terms(unique_keep_order(terms))


def score_leaf_evidence(leaf: Dict[str, Any], fact_rows: List[StockFactRow]) -> float:
    anchor_terms = filter_terms(
        [safe_str(leaf.get("subject_name"))]
        + parse_json_list(leaf.get("leaf_entities"))
        + parse_json_list(leaf.get("leaf_keywords"))
    )
    business_terms = filter_terms(
        [safe_str(leaf.get("full_name")), safe_str(leaf.get("leaf_summary"))]
    )

    anchor_score = 0.0
    business_score = 0.0
    relation_score = 0.0

    for f in fact_rows:
        text = (safe_str(f.fact_value) + "\n" + safe_str(f.evidence_span)).lower()
        if not text.strip():
            continue

        anchor_hits = contains_terms(text, anchor_terms)
        business_hits = contains_terms(text, business_terms)

        if anchor_hits:
            if f.fact_type in {"product", "technology", "main_business", "order_contract"}:
                anchor_score += 1.0 * f.confidence
            else:
                anchor_score += 0.5 * f.confidence

        if business_hits:
            if f.fact_type in {"main_business", "product", "order_contract", "investment"}:
                business_score += 0.8 * f.confidence
            elif f.fact_type in {"customer_supplier", "industry_role", "benefit_logic"}:
                relation_score += 0.4 * f.confidence
            else:
                relation_score += 0.2 * f.confidence

    anchor_score = min(anchor_score, 3.0) / 3.0
    business_score = min(business_score, 3.0) / 3.0
    relation_score = min(relation_score, 2.0) / 2.0

    final_score = 0.50 * anchor_score + 0.35 * business_score + 0.15 * relation_score
    return final_score


def assign_root_candidates_to_leafs(
    db_dsn: str,
    root_subject_key: str,
    root_candidates: List[Dict[str, Any]],
    model_name: str = "shibing624/text2vec-base-chinese",
    min_leaf_score: float = 0.55,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    conn = psycopg2.connect(db_dsn)
    model = SentenceModel(model_name)

    try:
        leafs = fetch_leaf_themes_by_root(conn, root_subject_key)
        if debug:
            print(f"[DEBUG] leaf themes total={len(leafs)} for root={root_subject_key}")

        if not leafs:
            out = []
            for cand in root_candidates:
                cand["leaf_status"] = "no_leaf_data_in_theme_master"
                cand["best_leaf_subject_key"] = None
                cand["best_leaf_subject_name"] = None
                cand["best_leaf_score"] = 0.0
                cand["secondary_leaf_subject_key"] = None
                cand["matched_leafs"] = []
                out.append(cand)
            if debug:
                print(f"[DEBUG] assigned leafs for root candidates total={len(out)} (no leaf data)")
            return out

        lead_stock_ids = [safe_str(x["lead_stock_id"]) for x in leafs if safe_str(x["lead_stock_id"])]
        lead_profile_map = fetch_stock_profile_map(conn, lead_stock_ids)

        candidate_stock_ids = [safe_str(x["stock_id"]) for x in root_candidates]
        candidate_profile_map = fetch_stock_profile_map(conn, candidate_stock_ids)
        fact_map = fetch_stock_facts_by_stock_ids(db_dsn, candidate_stock_ids)

        leaf_vec_map = {}
        for leaf in leafs:
            lead_stock_id = safe_str(leaf.get("lead_stock_id"))
            lead_profile = lead_profile_map.get(lead_stock_id, {})

            if lead_profile:
                anchor_text = build_leaf_anchor_text(leaf, lead_profile)
                has_lead_profile = True
            else:
                anchor_text = "\n".join([
                    f"叶子题材：{safe_str(leaf.get('subject_name'))}",
                    f"题材路径：{safe_str(leaf.get('full_name'))}",
                    f"叶子摘要：{safe_str(leaf.get('leaf_summary'))}",
                ])
                has_lead_profile = False

            leaf_text = "\n".join([
                safe_str(leaf.get("subject_name")),
                safe_str(leaf.get("full_name")),
                safe_str(leaf.get("leaf_summary")),
                " ".join(parse_json_list(leaf.get("leaf_keywords"))),
                " ".join(parse_json_list(leaf.get("leaf_entities"))),
            ])

            anchor_vec = model.encode(anchor_text)
            leaf_text_vec = model.encode(leaf_text)

            if hasattr(anchor_vec, "tolist"):
                anchor_vec = anchor_vec.tolist()
            if hasattr(leaf_text_vec, "tolist"):
                leaf_text_vec = leaf_text_vec.tolist()

            leaf_vec_map[leaf["subject_key"]] = {
                "leaf": leaf,
                "has_lead_profile": has_lead_profile,
                "anchor_text": anchor_text,
                "anchor_vec": anchor_vec,
                "leaf_text": leaf_text,
                "leaf_text_vec": leaf_text_vec,
            }

        out = []
        cand_vec_cache: Dict[str, List[float]] = {}

        for cand in root_candidates:
            stock_id = safe_str(cand["stock_id"])
            stock_profile = candidate_profile_map.get(stock_id, {})
            if not stock_profile:
                cand["leaf_status"] = "no_stock_profile"
                cand["best_leaf_subject_key"] = None
                cand["best_leaf_subject_name"] = None
                cand["best_leaf_score"] = 0.0
                cand["secondary_leaf_subject_key"] = None
                cand["matched_leafs"] = []
                out.append(cand)
                continue

            if stock_id not in cand_vec_cache:
                cand_vec = model.encode(stock_profile["profile_text"])
                if hasattr(cand_vec, "tolist"):
                    cand_vec = cand_vec.tolist()
                cand_vec_cache[stock_id] = cand_vec
            cand_vec = cand_vec_cache[stock_id]

            leaf_scores = []
            for item in leaf_vec_map.values():
                leaf = item["leaf"]
                lead_anchor_similarity = cosine_similarity(cand_vec, item["anchor_vec"])
                leaf_text_similarity = cosine_similarity(cand_vec, item["leaf_text_vec"])
                evidence_score = score_leaf_evidence(leaf, fact_map.get(stock_id, []))

                if item["has_lead_profile"]:
                    final_score = (
                        0.45 * lead_anchor_similarity +
                        0.20 * leaf_text_similarity +
                        0.35 * min(evidence_score, 1.0)
                    )
                else:
                    final_score = (
                        0.00 * lead_anchor_similarity +
                        0.45 * leaf_text_similarity +
                        0.55 * min(evidence_score, 1.0)
                    )

                leaf_scores.append(
                    {
                        "subject_key": leaf["subject_key"],
                        "subject_name": leaf["subject_name"],
                        "lead_stock_id": leaf.get("lead_stock_id"),
                        "lead_stock_name": leaf.get("lead_stock_name"),
                        "score": round(final_score, 6),
                        "has_lead_profile": item["has_lead_profile"],
                        "lead_anchor_similarity": round(lead_anchor_similarity, 6),
                        "leaf_text_similarity": round(leaf_text_similarity, 6),
                        "leaf_evidence_score": round(evidence_score, 6),
                    }
                )

            leaf_scores.sort(key=lambda x: -x["score"])
            matched_leafs = [x for x in leaf_scores if x["score"] >= min_leaf_score]

            if matched_leafs:
                cand["leaf_status"] = "matched"
                cand["best_leaf_subject_key"] = matched_leafs[0]["subject_key"]
                cand["best_leaf_subject_name"] = matched_leafs[0]["subject_name"]
                cand["best_leaf_score"] = matched_leafs[0]["score"]
                cand["secondary_leaf_subject_key"] = matched_leafs[1]["subject_key"] if len(matched_leafs) > 1 else None
                cand["matched_leafs"] = matched_leafs[:3]
            else:
                cand["leaf_status"] = "leafs_exist_but_unmatched"
                cand["best_leaf_subject_key"] = None
                cand["best_leaf_subject_name"] = None
                cand["best_leaf_score"] = 0.0
                cand["secondary_leaf_subject_key"] = None
                cand["matched_leafs"] = []

            out.append(cand)

        if debug:
            print(f"[DEBUG] assigned leafs for root candidates total={len(out)}")

        return out
    finally:
        conn.close()


# =========================
# 输出
# =========================

def direction_candidate_to_dict(c: DirectionLevelStockCandidate) -> Dict[str, Any]:
    return {
        "direction_key": c.direction_key,
        "direction_name": c.direction_name,
        "stock_id": c.stock_id,
        "stock_name": c.stock_name,
        "stage1_total_score": round(c.stage1_total_score, 6),
        "confidence_level": c.confidence_level,
        "anchor_hits": c.anchor_hits,
        "must_hits": c.must_hits,
        "should_hits": c.should_hits,
        "negative_hits": c.negative_hits,
        "matched_fact_ids": c.matched_fact_ids,
        "matched_fact_types": c.matched_fact_types,
        "distinct_fact_id_count": c.evidence_summary.get("distinct_fact_id_count", 0),
        "distinct_fact_type_count": c.evidence_summary.get("distinct_fact_type_count", 0),
        "primary_hit_score": c.evidence_summary.get("primary_hit_score", 0.0),
        "gate_reason": c.gate_reason,
        "confidence_level": c.confidence_level,
        "profile_soft_anchor_hits": c.evidence_summary.get("profile_soft_anchor_hits", []),
    }


def root_candidate_to_dict(c: RootAggregatedStockCandidate) -> Dict[str, Any]:
    return {
        "root_subject_key": c.root_subject_key,
        "root_subject_name": c.root_subject_name,
        "stock_id": c.stock_id,
        "stock_name": c.stock_name,
        "root_score": round(c.root_score, 6),
        "best_direction_score": round(c.best_direction_score, 6),
        "direction_count": c.direction_count,
        "matched_direction_keys": c.matched_direction_keys,
        "matched_direction_names": c.matched_direction_names,
        "matched_fact_ids": c.matched_fact_ids,
        "matched_fact_types": c.matched_fact_types,
        "matched_terms": c.matched_terms,
        "negative_hits": c.negative_hits,
        "matched_directions": c.matched_directions,
        "evidence_json": c.evidence_json,
    }


# =========================
# main
# =========================

def main():
    parser = argparse.ArgumentParser(description="Stage1 L1题材股票候选池 + 叶子软依赖锚点挂载")
    parser.add_argument("--events", required=True, help="结构化事件 jsonl")
    parser.add_argument("--db-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--model-name", default="shibing624/text2vec-base-chinese")
    parser.add_argument("--event-id", default="", help="仅跑单个 event_id")
    parser.add_argument("--root-subject-keys", default="", help="逗号分隔，例如 9043089；若单条事件且不传，则退化用事件里的 gt_subject_key")
    parser.add_argument("--direction-recall-top-k", type=int, default=30)
    parser.add_argument("--direction-final-top-k", type=int, default=10)
    parser.add_argument("--root-final-top-k", type=int, default=15)
    parser.add_argument("--leaf-min-score", type=float, default=0.55)
    parser.add_argument("--theme-candidates-json", default="", help="手工题材候选JSON，按 event_id 提供 root 和 directions")
    parser.add_argument("--disable-leaf-assignment", action="store_true", help="跳过 leaf 挂载，仅输出 root 股票池")
    parser.add_argument("--out", default="root_stock_stage1_candidates.json")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    events = load_events(args.events)
    event_map = {e.event_id: e for e in events}

    if args.event_id:
        event_ids = [args.event_id]
    else:
        event_ids = [e.event_id for e in events]

    root_keys = [x.strip() for x in args.root_subject_keys.split(",") if x.strip()]
    if not root_keys and args.event_id:
        ev = event_map.get(args.event_id)
        if ev and ev.gt_subject_key:
            root_keys = [ev.gt_subject_key]

    if not root_keys:
        raise ValueError("未提供 --root-subject-keys，且事件里也没有 gt_subject_key，无法确定 root 题材。")

    output = []

    for event_id in event_ids:
        event = event_map.get(event_id)
        if not event:
            print(f"[WARN] event_id={event_id} not found in events")
            continue

        if args.theme_candidates_json:
            root_theme_map = load_root_theme_candidates_from_json(
                args.theme_candidates_json,
                event_id,
            )
        else:
            root_theme_map = load_root_theme_candidates_from_db(args.db_dsn, root_keys)

        root_outputs = []

        for _, root in root_theme_map.items():
            direction_results: Dict[str, List[DirectionLevelStockCandidate]] = {}

            for direction in root.directions:
                rows = build_candidates_for_direction(
                    db_dsn=args.db_dsn,
                    event=event,
                    direction=direction,
                    model_name=args.model_name,
                    recall_top_k=args.direction_recall_top_k,
                    final_top_k=args.direction_final_top_k,
                    debug=args.debug,
                )
                direction_results[direction.subject_key] = rows

            root_candidates = aggregate_root_candidates(
                root=root,
                direction_results=direction_results,
                final_top_k=args.root_final_top_k,
                debug=args.debug,
            )

            root_candidate_dicts = [root_candidate_to_dict(x) for x in root_candidates]

            if args.disable_leaf_assignment:
                for cand in root_candidate_dicts:
                    cand["leaf_status"] = "leaf_assignment_disabled"
                    cand.setdefault("best_leaf_subject_key", None)
                    cand.setdefault("best_leaf_subject_name", None)
                    cand.setdefault("best_leaf_score", 0.0)
                    cand.setdefault("secondary_leaf_subject_key", None)
                    cand.setdefault("matched_leafs", [])
            else:
                root_candidate_dicts = assign_root_candidates_to_leafs(
                    db_dsn=args.db_dsn,
                    root_subject_key=root.root_subject_key,
                    root_candidates=root_candidate_dicts,
                    model_name=args.model_name,
                    min_leaf_score=args.leaf_min_score,
                    debug=args.debug,
                )

            root_outputs.append(
                {
                    "root_subject_key": root.root_subject_key,
                    "root_subject_name": root.root_subject_name,
                    "stage1_theme_score": root.stage1_theme_score,
                    "theme_source": "manual_theme_candidates_json" if args.theme_candidates_json else "db_theme_profiles",
                    "directions": [
                        {
                            "subject_key": d.subject_key,
                            "subject_name": d.subject_name,
                            "level": d.level,
                            "semantic_type": d.semantic_type,
                            "strategy_type": d.strategy_type,
                            "reason": d.reason,
                            "source": "manual_theme_candidates" if args.theme_candidates_json else "db_theme_profiles",
                            "stocks": [direction_candidate_to_dict(x) for x in direction_results.get(d.subject_key, [])],
                        }
                        for d in root.directions
                    ],
                    "root_stocks": root_candidate_dicts,
                }
            )

        output.append(
            {
                "event_id": event.event_id,
                "gt_subject_key": event.gt_subject_key,
                "theme_name": event.theme_name,
                "root_theme_candidates": root_outputs,
            }
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[DONE] wrote: {args.out}")


if __name__ == "__main__":
    main()
