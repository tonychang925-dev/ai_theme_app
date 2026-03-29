#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
run_gate_match_baseline.py - 受限候选集合评测版（完整调试版）
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# =========================
# 工具函数
# =========================

def safe_str(x: Any) -> str:
    """安全转换为字符串"""
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    return str(x).strip()


def unique_keep_order(items: List[str]) -> List[str]:
    """去重并保持顺序"""
    seen = set()
    out = []
    for x in items:
        x = safe_str(x)
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def clip01(x: float) -> float:
    """限制在0-1之间"""
    return max(0.0, min(1.0, x))


def split_subject_keys(s: str) -> List[str]:
    """拆分逗号分隔的subject_key，确保返回字符串列表"""
    return [str(x.strip()) for x in s.split(",") if x.strip()]


def normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    return re.sub(r"\s+", " ", safe_str(text)).strip()


# =========================
# 数据结构
# =========================

@dataclass
class EventProfile:
    """标准化后的事件格式"""
    event_id: int
    theme_name_true: Optional[str]          # 测试集真值，仅评估用
    summary: str
    event_type: str
    entities: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)
    tech_terms: List[str] = field(default_factory=list)
    raw_text: str = ""
    text_for_recall: str = ""                # 召回主文本，统一拼好
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ThemeGateProfile:
    """题材门配置"""
    subject_key: str
    theme_name: str                           # 从search_text提取
    search_text: str
    must_terms: List[str] = field(default_factory=list)
    should_terms: List[str] = field(default_factory=list)
    not_terms: List[str] = field(default_factory=list)
    strong_terms: List[str] = field(default_factory=list)
    weak_terms: List[str] = field(default_factory=list)
    negative_terms: List[str] = field(default_factory=list)
    quality: str = ""


@dataclass
class CandidateScore:
    """候选题材得分"""
    subject_key: str
    theme_name: str
    recall_score: float
    must_score: float
    strong_score: float
    should_score: float
    weak_score: float
    negative_penalty: float
    not_penalty: float
    final_score: float
    must_hits: List[str] = field(default_factory=list)
    should_hits: List[str] = field(default_factory=list)
    strong_hits: List[str] = field(default_factory=list)
    weak_hits: List[str] = field(default_factory=list)
    negative_hits: List[str] = field(default_factory=list)
    not_hits: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    quality: str = ""


@dataclass
class MatchDecisionResult:
    """匹配决策结果"""
    event_id: int
    verdict: str                               # accept_match / abstain / no_match
    theme_id_final: Optional[int]               # 最终命中的题材ID
    tree_subject_key: Optional[str]             # 最终命中的subject_key
    branch_subject_key: Optional[str] = None
    leaf_theme_id: Optional[int] = None
    confidence_final: float = 0.0
    match_reason_final: str = ""
    matched_keywords_final: List[str] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    review_status: str = "pending_review"
    engine_version: str = "gate_matcher_v1"


# =========================
# 模块1：EventProfileBuilder
# =========================

class EventProfileBuilder:
    """模块A：事件标准化"""
    
    def __init__(self) -> None:
        pass

    def load_events_from_jsonl(self, path: str) -> List[Dict[str, Any]]:
        """读取 structured_events.jsonl 原始记录"""
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def build_batch(self, rows: List[Dict[str, Any]]) -> List[EventProfile]:
        """批量构建事件画像"""
        return [self.build_event_profile(row) for row in rows]

    def build_event_profile(self, row: Dict[str, Any]) -> EventProfile:
        """把单条原始结构化事件转成 EventProfile"""
        # 提取核心字段
        event_id = self._extract_event_id(row)
        theme_name_true = safe_str(row.get("theme_name") or row.get("theme") or "")
        summary = safe_str(row.get("summary") or row.get("event_summary") or "")
        event_type = safe_str(row.get("event_type") or "")
        
        # 提取结构化字段
        entities = self.normalize_entities(row.get("entities", []))
        claims = self.extract_claims(row)
        tech_terms = self.extract_tech_terms(row)
        raw_text = safe_str(row.get("raw_text") or row.get("content") or row.get("text") or "")

        # 构建召回文本
        text_for_recall = self.compose_text_for_recall(
            summary=summary,
            event_type=event_type,
            entities=entities,
            claims=claims,
            tech_terms=tech_terms,
            raw_text=raw_text,
        )

        meta = {
            "confidence": row.get("confidence"),
            "severity_score": row.get("severity_score"),
            "source_weight": row.get("source_weight"),
            "timestamp": row.get("timestamp"),
        }

        return EventProfile(
            event_id=event_id,
            theme_name_true=theme_name_true or None,
            summary=summary,
            event_type=event_type,
            entities=entities,
            claims=claims,
            tech_terms=tech_terms,
            raw_text=raw_text,
            text_for_recall=text_for_recall,
            meta=meta,
        )

    def _extract_event_id(self, row: Dict[str, Any]) -> int:
        """提取事件ID，处理可能的溢出"""
        val = row.get("event_id") or row.get("id")
        if val is None:
            raise ValueError(f"事件缺少 event_id/id: {row}")
        
        try:
            if isinstance(val, str):
                digits = re.findall(r"\d+", val)
                if digits:
                    int_val = int(digits[-1])
                else:
                    int_val = hash(val) % (2**31 - 1)
            else:
                int_val = int(val)
            
            if int_val > 2147483647:
                return hash(str(int_val)) % (2**31 - 1)
            return int_val
        except:
            return hash(str(val)) % (2**31 - 1)

    def compose_text_for_recall(
        self,
        summary: str,
        event_type: str,
        entities: List[str],
        claims: List[str],
        tech_terms: List[str],
        raw_text: str,
    ) -> str:
        """统一召回文本拼接逻辑"""
        print(f"\n[DEBUG-Compose] 构建召回文本:")
        print(f"  summary: {summary[:50] if summary else '空'}")
        print(f"  event_type: {event_type if event_type else '空'}")
        print(f"  entities: {entities[:3] if entities else '空'}")
        print(f"  claims: {claims[:3] if claims else '空'}")
        print(f"  tech_terms: {tech_terms[:3] if tech_terms else '空'}")
        print(f"  raw_text长度: {len(raw_text) if raw_text else 0}")
        
        parts = [
            summary,
            event_type,
            " ".join(entities),
            " ".join(claims),
            " ".join(tech_terms),
            raw_text[:500] if raw_text else "",
        ]
        result = normalize_whitespace(" ".join([p for p in parts if p]))
        print(f"  结果长度: {len(result)}")
        return result

    def normalize_entities(self, entities: Any) -> List[str]:
        """提取 normalized/name 并去重"""
        out = []
        if isinstance(entities, list):
            for item in entities:
                if isinstance(item, dict):
                    val = (
                        item.get("normalized")
                        or item.get("name")
                        or item.get("value")
                        or ""
                    )
                    val = safe_str(val)
                    if val:
                        out.append(val)
                else:
                    val = safe_str(item)
                    if val:
                        out.append(val)
        return unique_keep_order(out)

    def extract_claims(self, row: Dict[str, Any]) -> List[str]:
        """从 causal_claim 等字段提取 claim 列表"""
        claims = []
        for field in ["causal_claim", "claim"]:
            val = row.get(field)
            if isinstance(val, list):
                claims.extend([safe_str(x) for x in val if safe_str(x)])
            elif isinstance(val, str):
                claims.append(val)
        return unique_keep_order(claims)

    def extract_tech_terms(self, row: Dict[str, Any]) -> List[str]:
        """从 evidence_set.tech_phrases 提取技术词"""
        out = []
        evidence_set = row.get("evidence_set", {})
        if isinstance(evidence_set, dict):
            tech_phrases = evidence_set.get("tech_phrases", [])
            if isinstance(tech_phrases, list):
                out.extend([safe_str(x) for x in tech_phrases if safe_str(x)])
        return unique_keep_order(out)


# =========================
# 模块2：ThemeGateLoader
# =========================

class ThemeGateLoader:
    """模块B：从数据库加载题材gate"""
    
    def __init__(self, db_dsn: str) -> None:
        self.db_dsn = db_dsn

    def get_conn(self):
        return psycopg2.connect(self.db_dsn)

    def load_gates_by_subject_keys(self, subject_keys: List[str]) -> List[ThemeGateProfile]:
        """按 subject_key 列表读取 gate（受限评测用）"""
        print(f"\n[DEBUG-Loader] 尝试加载 subject_keys: {subject_keys}")
        
        sql = """
            SELECT
                subject_key,
                search_text,
                must_terms,
                should_terms,
                not_terms,
                strong_terms,
                weak_terms,
                negative_terms,
                quality
            FROM theme_gate_profile
            WHERE subject_key = ANY(%s)
            ORDER BY subject_key
        """
        with self.get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (subject_keys,))
                rows = cur.fetchall()
                print(f"[DEBUG-Loader] 查询到 {len(rows)} 条记录")
                
                if rows:
                    print(f"[DEBUG-Loader] 第一条记录示例:")
                    first_row = dict(rows[0])
                    for k, v in first_row.items():
                        print(f"  {k}: {str(v)[:100]}")

        return [self.parse_gate_row(dict(row)) for row in rows]

    def parse_gate_row(self, row: Dict[str, Any]) -> ThemeGateProfile:
        """把数据库行转为 ThemeGateProfile"""
        search_text = safe_str(row.get("search_text"))
        
        # theme_name = search_text的第一个词
        theme_name = search_text.split()[0].strip() if search_text else ""

        return ThemeGateProfile(
            subject_key=safe_str(row.get("subject_key")),
            theme_name=theme_name,
            search_text=search_text,
            must_terms=self.normalize_term_list(row.get("must_terms")),
            should_terms=self.normalize_term_list(row.get("should_terms")),
            not_terms=self.normalize_term_list(row.get("not_terms")),
            strong_terms=self.normalize_term_list(row.get("strong_terms")),
            weak_terms=self.normalize_term_list(row.get("weak_terms")),
            negative_terms=self.normalize_term_list(row.get("negative_terms")),
            quality=safe_str(row.get("quality")),
        )

    def normalize_term_list(self, value: Any) -> List[str]:
        """兼容 jsonb/list/str，统一成字符串列表"""
        if value is None:
            return []
        if isinstance(value, list):
            return unique_keep_order([safe_str(x) for x in value if safe_str(x)])
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return []
            try:
                obj = json.loads(s)
                if isinstance(obj, list):
                    return unique_keep_order([safe_str(x) for x in obj if safe_str(x)])
            except Exception:
                pass
            if "," in s:
                return [x.strip() for x in s.split(",") if x.strip()]
            return [s]
        return []

    def build_subject_key_map(self, gates: List[ThemeGateProfile]) -> Dict[str, ThemeGateProfile]:
        """生成 subject_key -> gate profile 映射"""
        return {g.subject_key: g for g in gates}

    def build_theme_name_map(self, gates: List[ThemeGateProfile]) -> Dict[str, str]:
        """生成 subject_key -> theme_name 映射"""
        return {g.subject_key: g.theme_name for g in gates}


# =========================
# 模块3：ThemeRecallEngine
# =========================

class ThemeRecallEngine:
    """模块C：基于 search_text 做粗召回"""
    
    def __init__(self, analyzer: str = "char", ngram_range: Tuple[int, int] = (2, 4)) -> None:
        self.analyzer = analyzer
        self.ngram_range = ngram_range
        self.vectorizer = None
        self.gate_matrix = None
        self.subject_keys: List[str] = []
        self.theme_names: List[str] = []
        self.gates: List[ThemeGateProfile] = []

    def fit(self, gates: List[ThemeGateProfile]) -> None:
        """用 gate search_text 建召回索引"""
        self.gates = gates
        self.subject_keys = [g.subject_key for g in gates]
        self.theme_names = [g.theme_name for g in gates]
        docs = [self.get_gate_doc_text(g) for g in gates]
        
        print(f"\n[DEBUG-Recall] 建立召回索引，题材数: {len(gates)}")
        print(f"[DEBUG-Recall] 第一个题材search_text: {docs[0][:100] if docs else '空'}")
        
        self.vectorizer = TfidfVectorizer(analyzer=self.analyzer, ngram_range=self.ngram_range)
        self.gate_matrix = self.vectorizer.fit_transform(docs)

    def recall_top_k(
        self,
        event: EventProfile,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """对单条事件召回 top-k"""
        if self.vectorizer is None or self.gate_matrix is None:
            raise RuntimeError("ThemeRecallEngine 未 fit")

        query = self.get_event_query_text(event)
        print(f"\n[DEBUG-Recall] 事件 {event.event_id} 召回查询文本长度: {len(query)}")
        
        q = self.vectorizer.transform([query])
        sims = cosine_similarity(q, self.gate_matrix)[0]

        pairs = []
        for idx, score in enumerate(sims):
            pairs.append({
                "subject_key": self.subject_keys[idx],
                "theme_name": self.theme_names[idx],
                "recall_score": float(score),
            })

        pairs.sort(key=lambda x: x["recall_score"], reverse=True)
        
        print(f"[DEBUG-Recall] Top3召回分数:")
        for i, p in enumerate(pairs[:3]):
            print(f"  {i+1}. {p['theme_name']}: {p['recall_score']:.4f}")
            
        return pairs[:top_k]

    def get_event_query_text(self, event: EventProfile) -> str:
        """获取事件召回文本"""
        return event.text_for_recall

    def get_gate_doc_text(self, gate: ThemeGateProfile) -> str:
        """获取题材召回文本，默认 search_text"""
        return gate.search_text


# =========================
# 模块4：GateReranker
# =========================

class GateReranker:
    """模块D：对召回 top-k 候选用 gate 做精排"""
    
    def __init__(
        self,
        w_recall: float = 0.35,
        w_must: float = 0.25,
        w_strong: float = 0.15,
        w_should: float = 0.10,
        w_weak: float = 0.05,
        w_negative: float = 0.15,
        w_not: float = 0.15,
    ) -> None:
        self.w_recall = w_recall
        self.w_must = w_must
        self.w_strong = w_strong
        self.w_should = w_should
        self.w_weak = w_weak
        self.w_negative = w_negative
        self.w_not = w_not

    def rerank_candidates(
        self,
        event: EventProfile,
        recalled: List[Dict[str, Any]],
        gate_map: Dict[str, ThemeGateProfile],
    ) -> List[CandidateScore]:
        """对召回候选做 gate 精排"""
        out = []
        for item in recalled:
            subject_key = item["subject_key"]
            recall_score = float(item["recall_score"])
            gate = gate_map[subject_key]
            out.append(self.score_single_candidate(event, gate, recall_score))
        out.sort(key=lambda x: x.final_score, reverse=True)
        return out

    def build_event_text_for_gate(self, event: EventProfile) -> str:
        """构造用于 gate 命中判断的全文本"""
        parts = [
            event.summary,
            event.event_type,
            " ".join(event.entities),
            " ".join(event.claims),
            " ".join(event.tech_terms),
            event.raw_text,
        ]
        
        print(f"\n[DEBUG-BuildText] 构建gate匹配文本:")
        print(f"  summary: {event.summary[:50] if event.summary else '空'}")
        print(f"  entities: {event.entities[:3] if event.entities else '空'}")
        print(f"  claims: {event.claims[:3] if event.claims else '空'}")
        print(f"  tech_terms: {event.tech_terms[:3] if event.tech_terms else '空'}")
        
        result = normalize_whitespace(" ".join([p for p in parts if p]))
        print(f"  最终文本长度: {len(result)}")
        return result

    def calc_match_score(
        self,
        event_text: str,
        terms: List[str],
    ) -> Tuple[float, List[str]]:
        """计算某组 terms 的命中得分和命中词"""
        terms = [t for t in unique_keep_order(terms) if t]
        if not terms:
            return 0.0, []
        
        hits = []
        for term in terms:
            if term and term in event_text:
                hits.append(term)
        
        score = len(hits) / max(len(terms), 1)
        return clip01(score), hits

    def calc_penalty_score(
        self,
        event_text: str,
        terms: List[str],
    ) -> Tuple[float, List[str]]:
        """计算 negative/not 惩罚"""
        terms = [t for t in unique_keep_order(terms) if t]
        if not terms:
            return 0.0, []
        hits = [t for t in terms if t and t in event_text]
        score = len(hits) / max(len(terms), 1)
        return clip01(score), hits

    def score_single_candidate(
        self,
        event: EventProfile,
        gate: ThemeGateProfile,
        recall_score: float,
    ) -> CandidateScore:
        """计算单个候选的最终得分"""
        print(f"\n{'='*60}")
        print(f"[DEBUG-Score] 事件ID: {event.event_id}, 事件真值: {event.theme_name_true}")
        print(f"[DEBUG-Score] 题材: {gate.theme_name} (subject_key: {gate.subject_key})")
        
        event_text = self.build_event_text_for_gate(event)
        
        if not event_text or len(event_text.strip()) == 0:
            print(f"[ERROR] 事件文本为空！")
        
        print(f"\n[DEBUG-Score] 开始匹配计算:")
        
        must_score, must_hits = self.calc_match_score(event_text, gate.must_terms)
        print(f"  must_terms ({len(gate.must_terms)}个): {gate.must_terms[:5]}")
        print(f"  must_hits: {must_hits}")
        print(f"  must_score: {must_score:.4f}")
        
        strong_score, strong_hits = self.calc_match_score(event_text, gate.strong_terms)
        print(f"  strong_hits: {strong_hits}")
        print(f"  strong_score: {strong_score:.4f}")
        
        should_score, should_hits = self.calc_match_score(event_text, gate.should_terms)
        print(f"  should_hits: {should_hits}")
        print(f"  should_score: {should_score:.4f}")
        
        weak_score, weak_hits = self.calc_match_score(event_text, gate.weak_terms)
        
        negative_penalty, negative_hits = self.calc_penalty_score(event_text, gate.negative_terms)
        print(f"  negative_hits: {negative_hits}")
        print(f"  negative_penalty: {negative_penalty:.4f}")
        
        not_penalty, not_hits = self.calc_penalty_score(event_text, gate.not_terms)

        base_score = (
            self.w_recall * recall_score
            + self.w_must * must_score
            + self.w_strong * strong_score
            + self.w_should * should_score
            + self.w_weak * weak_score
            - self.w_negative * negative_penalty
            - self.w_not * not_penalty
        )
        
        print(f"\n[DEBUG-Score] 分数计算:")
        print(f"  recall_score: {recall_score:.4f} * {self.w_recall} = {self.w_recall * recall_score:.4f}")
        print(f"  must_score: {must_score:.4f} * {self.w_must} = {self.w_must * must_score:.4f}")
        print(f"  strong_score: {strong_score:.4f} * {self.w_strong} = {self.w_strong * strong_score:.4f}")
        print(f"  base_score: {base_score:.4f}")

        final_score = self.apply_quality_bonus(base_score, gate.quality)
        print(f"  final_score: {final_score:.4f}")

        matched_keywords = unique_keep_order(
            must_hits + strong_hits + should_hits + weak_hits
        )
        print(f"  matched_keywords: {matched_keywords}")

        return CandidateScore(
            subject_key=gate.subject_key,
            theme_name=gate.theme_name,
            recall_score=clip01(recall_score),
            must_score=clip01(must_score),
            strong_score=clip01(strong_score),
            should_score=clip01(should_score),
            weak_score=clip01(weak_score),
            negative_penalty=clip01(negative_penalty),
            not_penalty=clip01(not_penalty),
            final_score=clip01(final_score),
            must_hits=must_hits,
            should_hits=should_hits,
            strong_hits=strong_hits,
            weak_hits=weak_hits,
            negative_hits=negative_hits,
            not_hits=not_hits,
            matched_keywords=matched_keywords,
            quality=gate.quality,
        )

    def apply_quality_bonus(self, base_score: float, quality: str) -> float:
        """可选：根据 gate 质量做轻微调权"""
        quality = safe_str(quality).lower()
        if quality == "strong":
            base_score += 0.03
        elif quality == "weak":
            base_score -= 0.03
        return clip01(base_score)


# =========================
# 模块5：DecisionEngine
# =========================

class DecisionEngine:
    """模块E：根据 top1/top2/final_score/margin 生成 verdict"""
    
    def __init__(
        self,
        accept_threshold: float = 0.75,
        abstain_threshold: float = 0.55,
        margin_threshold: float = 0.12,
        engine_version: str = "gate_matcher_v1",
    ) -> None:
        self.accept_threshold = accept_threshold
        self.abstain_threshold = abstain_threshold
        self.margin_threshold = margin_threshold
        self.engine_version = engine_version

    def decide(
        self,
        event: EventProfile,
        ranked: List[CandidateScore],
    ) -> MatchDecisionResult:
        """对单条事件生成最终裁决"""
        print(f"\n{'='*60}")
        print(f"[DEBUG-Decide] 事件 {event.event_id} 决策开始")
        
        top1 = ranked[0] if ranked else None
        top2 = ranked[1] if len(ranked) > 1 else None

        if top1:
            print(f"  Top1: {top1.theme_name} (score={top1.final_score:.4f})")
            print(f"  Top1 matched: {top1.matched_keywords}")
        if top2:
            print(f"  Top2: {top2.theme_name} (score={top2.final_score:.4f})")

        verdict = self.determine_verdict(top1, top2)
        confidence = self.calc_confidence(top1, top2)
        
        print(f"  Verdict: {verdict}")
        print(f"  Confidence: {confidence:.4f}")
        print(f"  Thresholds: accept={self.accept_threshold}, abstain={self.abstain_threshold}")

        match_reason = self.build_match_reason(top1, verdict)
        rationale = self.build_rationale(event, ranked, verdict)

        theme_id_final: Optional[int] = None
        tree_subject_key: Optional[str] = None

        if verdict == "accept_match" and top1:
            tree_subject_key = top1.subject_key
            try:
                theme_id_final = int(top1.subject_key)
            except Exception:
                theme_id_final = None

        return MatchDecisionResult(
            event_id=event.event_id,
            verdict=verdict,
            theme_id_final=theme_id_final,
            tree_subject_key=tree_subject_key,
            confidence_final=round(confidence, 4),
            match_reason_final=match_reason,
            matched_keywords_final=top1.matched_keywords if top1 else [],
            candidates=self.serialize_candidates(ranked, top_n=3),
            rationale=rationale,
            review_status="pending_review",
            engine_version=self.engine_version,
        )

    def determine_verdict(
        self,
        top1: Optional[CandidateScore],
        top2: Optional[CandidateScore],
    ) -> str:
        """判断 accept_match / abstain / no_match"""
        if top1 is None:
            return "no_match"

        margin = top1.final_score - (top2.final_score if top2 else 0.0)
        print(f"  Margin: {margin:.4f} (threshold={self.margin_threshold})")

        if top1.final_score >= self.accept_threshold and margin >= self.margin_threshold:
            return "accept_match"
        if top1.final_score >= self.abstain_threshold:
            return "abstain"
        return "no_match"

    def calc_confidence(
        self,
        top1: Optional[CandidateScore],
        top2: Optional[CandidateScore],
    ) -> float:
        """根据分数和 margin 生成最终置信度"""
        if top1 is None:
            return 0.0
        margin = top1.final_score - (top2.final_score if top2 else 0.0)
        confidence = 0.8 * top1.final_score + 0.2 * clip01(margin)
        return clip01(confidence)

    def build_match_reason(
        self,
        candidate: Optional[CandidateScore],
        verdict: str,
    ) -> str:
        """短理由"""
        if candidate is None:
            return "无有效候选题材"
        if verdict == "accept_match":
            return f"候选题材[{candidate.theme_name}]得分最高，且与第二候选拉开差距"
        if verdict == "abstain":
            return f"候选题材[{candidate.theme_name}]有一定匹配，但边界仍需人工复核"
        return "未达到可接受匹配阈值"

    def build_rationale(
        self,
        event: EventProfile,
        ranked: List[CandidateScore],
        verdict: str,
    ) -> str:
        """长解释"""
        if not ranked:
            return "未召回到有效候选题材。"

        top1 = ranked[0]
        top2 = ranked[1] if len(ranked) > 1 else None
        margin = top1.final_score - (top2.final_score if top2 else 0.0)

        return (
            f"事件主题真值={event.theme_name_true or 'N/A'}；"
            f"Top1={top1.theme_name}(score={top1.final_score:.4f})；"
            f"Top2={(top2.theme_name if top2 else 'N/A')}"
            f"(score={(top2.final_score if top2 else 0.0):.4f})；"
            f"margin={margin:.4f}；"
            f"must_hits={top1.must_hits}；"
            f"strong_hits={top1.strong_hits}；"
            f"should_hits={top1.should_hits}；"
            f"negative_hits={top1.negative_hits}；"
            f"not_hits={top1.not_hits}；"
            f"最终 verdict={verdict}。"
        )

    def serialize_candidates(
        self,
        ranked: List[CandidateScore],
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """转成 match_decisions.candidates 的 JSON 结构"""
        out = []
        for rank, c in enumerate(ranked[:top_n], start=1):
            out.append({
                "rank": rank,
                "subject_key": c.subject_key,
                "theme_name": c.theme_name,
                "recall_score": round(c.recall_score, 4),
                "must_score": round(c.must_score, 4),
                "strong_score": round(c.strong_score, 4),
                "should_score": round(c.should_score, 4),
                "weak_score": round(c.weak_score, 4),
                "negative_penalty": round(c.negative_penalty, 4),
                "not_penalty": round(c.not_penalty, 4),
                "final_score": round(c.final_score, 4),
                "must_hits": c.must_hits,
                "should_hits": c.should_hits,
                "strong_hits": c.strong_hits,
                "weak_hits": c.weak_hits,
                "negative_hits": c.negative_hits,
                "not_hits": c.not_hits,
                "matched_keywords": c.matched_keywords,
                "quality": c.quality,
            })
        return out


# =========================
# 模块6：DecisionWriter
# =========================

class DecisionWriter:
    """写入 match_decisions 表"""
    
    def __init__(self, db_dsn: str) -> None:
        self.db_dsn = db_dsn

    def get_conn(self):
        return psycopg2.connect(self.db_dsn)

    def upsert_match_decision(self, result: MatchDecisionResult) -> None:
        """单条 upsert 到 match_decisions"""
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT decision_id FROM match_decisions WHERE event_id = %s", (result.event_id,))
                existing = cur.fetchone()
                
                if existing:
                    sql = """
                    UPDATE match_decisions SET
                        theme_id_final = %(theme_id_final)s,
                        verdict = %(verdict)s,
                        confidence_final = %(confidence_final)s,
                        match_reason_final = %(match_reason_final)s,
                        matched_keywords_final = %(matched_keywords_final)s::jsonb,
                        candidates = %(candidates)s::jsonb,
                        rationale = %(rationale)s,
                        review_status = %(review_status)s,
                        engine_version = %(engine_version)s,
                        tree_subject_key = %(tree_subject_key)s,
                        branch_subject_key = %(branch_subject_key)s,
                        leaf_theme_id = %(leaf_theme_id)s,
                        updated_at = now()
                    WHERE event_id = %(event_id)s
                    """
                else:
                    sql = """
                    INSERT INTO match_decisions (
                        event_id,
                        theme_id_final,
                        verdict,
                        confidence_final,
                        match_reason_final,
                        matched_keywords_final,
                        candidates,
                        rationale,
                        review_status,
                        engine_version,
                        tree_subject_key,
                        branch_subject_key,
                        leaf_theme_id,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %(event_id)s,
                        %(theme_id_final)s,
                        %(verdict)s,
                        %(confidence_final)s,
                        %(match_reason_final)s,
                        %(matched_keywords_final)s::jsonb,
                        %(candidates)s::jsonb,
                        %(rationale)s,
                        %(review_status)s,
                        %(engine_version)s,
                        %(tree_subject_key)s,
                        %(branch_subject_key)s,
                        %(leaf_theme_id)s,
                        now(),
                        now()
                    )
                    """
        
        matched_keywords_json = json.dumps(result.matched_keywords_final, ensure_ascii=False)
        
        payload = {
            "event_id": result.event_id,
            "theme_id_final": result.theme_id_final,
            "verdict": result.verdict,
            "confidence_final": float(result.confidence_final),
            "match_reason_final": result.match_reason_final,
            "matched_keywords_final": matched_keywords_json,
            "candidates": json.dumps(result.candidates, ensure_ascii=False),
            "rationale": result.rationale,
            "review_status": result.review_status,
            "engine_version": result.engine_version,
            "tree_subject_key": result.tree_subject_key,
            "branch_subject_key": result.branch_subject_key,
            "leaf_theme_id": result.leaf_theme_id,
        }

        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, payload)
            conn.commit()


# =========================
# 模块7：Evaluator
# =========================

class Evaluator:
    """评估模块"""
    
    def evaluate(
        self,
        events: List[EventProfile],
        results: List[MatchDecisionResult],
        subject_key_to_theme_name: Dict[str, str],
    ) -> Dict[str, Any]:
        """计算 accuracy/top3/abstain/no_match 等指标"""
        event_map = {e.event_id: e for e in events}
        total = len(results)

        accept_cnt = 0
        abstain_cnt = 0
        no_match_cnt = 0
        top1_correct = 0
        top3_correct = 0

        confusion = {}

        for r in results:
            e = event_map[r.event_id]
            true_name = e.theme_name_true or ""
            pred_name = ""
            if r.tree_subject_key:
                pred_name = subject_key_to_theme_name.get(r.tree_subject_key, "")

            if r.verdict == "accept_match":
                accept_cnt += 1
            elif r.verdict == "abstain":
                abstain_cnt += 1
            else:
                no_match_cnt += 1

            if pred_name and true_name and pred_name == true_name:
                top1_correct += 1

            cand_names = [c["theme_name"] for c in r.candidates]
            if true_name and true_name in cand_names:
                top3_correct += 1

            if true_name and pred_name and true_name != pred_name:
                key = (true_name, pred_name)
                confusion[key] = confusion.get(key, 0) + 1

        confusion_pairs = [
            {"true_theme": k[0], "pred_theme": k[1], "count": v}
            for k, v in sorted(confusion.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "total_events": total,
            "accept_match_count": accept_cnt,
            "abstain_count": abstain_cnt,
            "no_match_count": no_match_cnt,
            "top1_accuracy": round(top1_correct / total, 4) if total else 0.0,
            "top3_accuracy": round(top3_correct / total, 4) if total else 0.0,
            "accept_rate": round(accept_cnt / total, 4) if total else 0.0,
            "abstain_rate": round(abstain_cnt / total, 4) if total else 0.0,
            "no_match_rate": round(no_match_cnt / total, 4) if total else 0.0,
            "confusion_pairs": confusion_pairs[:20],
        }

    def export_detail_csv(
        self,
        path: str,
        events: List[EventProfile],
        results: List[MatchDecisionResult],
        subject_key_to_theme_name: Dict[str, str],
    ) -> None:
        """导出逐条结果"""
        event_map = {e.event_id: e for e in events}
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "event_id",
                "theme_name_true",
                "theme_name_pred",
                "subject_key_pred",
                "verdict",
                "confidence_final",
                "top1_score",
                "margin",
                "top3_candidates",
                "matched_keywords_final",
            ])
            writer.writeheader()

            for r in results:
                e = event_map[r.event_id]
                top1_score = r.candidates[0]["final_score"] if r.candidates else 0.0
                top2_score = r.candidates[1]["final_score"] if len(r.candidates) > 1 else 0.0
                margin = round(top1_score - top2_score, 4)
                pred_name = subject_key_to_theme_name.get(r.tree_subject_key, "") if r.tree_subject_key else ""
                top3_names = [c["theme_name"] for c in r.candidates]

                writer.writerow({
                    "event_id": r.event_id,
                    "theme_name_true": e.theme_name_true or "",
                    "theme_name_pred": pred_name,
                    "subject_key_pred": r.tree_subject_key or "",
                    "verdict": r.verdict,
                    "confidence_final": r.confidence_final,
                    "top1_score": top1_score,
                    "margin": margin,
                    "top3_candidates": json.dumps(top3_names, ensure_ascii=False),
                    "matched_keywords_final": json.dumps(r.matched_keywords_final, ensure_ascii=False),
                })

    def export_summary_json(
        self,
        path: str,
        summary: Dict[str, Any],
    ) -> None:
        """导出汇总 JSON"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


# =========================
# 主入口函数
# =========================

def parse_args():
    parser = argparse.ArgumentParser(description="受限候选集合评测版 - 只允许在指定10个题材里匹配")
    parser.add_argument("--events", required=True, help="structured_events.jsonl 路径")
    parser.add_argument("--subject-keys", required=True, help="逗号分隔的测试题材 subject_key 列表（10个）")
    parser.add_argument("--db-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--top-k", type=int, default=5, help="粗召回 top-k")
    parser.add_argument("--detail-out", default="match_results_detail.csv", help="逐条结果 CSV")
    parser.add_argument("--summary-out", default="match_metrics_summary.json", help="汇总 JSON")
    parser.add_argument("--dry-run", action="store_true", help="只跑评估，不写库")
    return parser.parse_args()


def main():
    """主流程：受限候选集合评测"""
    print("\n" + "="*60)
    print("开始运行受限候选集合评测")
    print("="*60)
    
    args = parse_args()

    # 解析subject_keys，确保是字符串
    subject_keys = split_subject_keys(args.subject_keys)
    if not subject_keys:
        raise ValueError("subject_keys 不能为空")
    print(f"\n[配置] 限定候选题材数量: {len(subject_keys)} 个")
    print(f"[配置] subject_keys: {subject_keys}")

    # 1) 事件标准化
    print("\n" + "-"*40)
    print("步骤1: 事件标准化")
    print("-"*40)
    
    builder = EventProfileBuilder()
    raw_rows = builder.load_events_from_jsonl(args.events)
    
    print(f"\n[原始数据] 加载了 {len(raw_rows)} 条原始事件")
    if raw_rows:
        print("\n[原始数据] 第一条事件原始内容:")
        first_raw = raw_rows[0]
        print(f"  event_id: {first_raw.get('event_id')}")
        print(f"  theme_name: {first_raw.get('theme_name')}")
        print(f"  summary: {str(first_raw.get('summary'))[:100]}...")
        print(f"  entities: {first_raw.get('entities', [])[:5]}")
    
    events = builder.build_batch(raw_rows)
    print(f"\n[处理后] 构建了 {len(events)} 条事件Profile")
    
    if events:
        print("\n[处理后] 第一条事件Profile:")
        print(f"  event_id: {events[0].event_id}")
        print(f"  theme_name_true: {events[0].theme_name_true}")
        print(f"  summary: {events[0].summary[:100]}...")
        print(f"  entities: {events[0].entities[:10]}")
        print(f"  claims: {events[0].claims[:10]}")
        print(f"  tech_terms: {events[0].tech_terms[:10]}")
        print(f"  text_for_recall长度: {len(events[0].text_for_recall)}")

    # 2) 加载指定题材的gate
    print("\n" + "-"*40)
    print("步骤2: 加载题材Gate")
    print("-"*40)
    
    gate_loader = ThemeGateLoader(args.db_dsn)
    gates = gate_loader.load_gates_by_subject_keys(subject_keys)
    
    if not gates:
        raise RuntimeError("未加载到任何 gate，请检查 subject_keys 或数据库")
    
    gate_map = gate_loader.build_subject_key_map(gates)
    subject_key_to_theme_name = gate_loader.build_theme_name_map(gates)
    
    print(f"\n[Gate] 加载了 {len(gates)} 个题材")
    print(f"[Gate] 题材列表:")
    for sk, tn in subject_key_to_theme_name.items():
        print(f"  {sk}: {tn}")

    # 3) 召回引擎
    print("\n" + "-"*40)
    print("步骤3: 初始化召回引擎")
    print("-"*40)
    
    recall_engine = ThemeRecallEngine()
    recall_engine.fit(gates)

    # 4) 精排引擎
    reranker = GateReranker()

    # 5) 决策引擎
    decider = DecisionEngine(engine_version="gate_matcher_v1_restricted")

    # 6) 写入器
    writer = DecisionWriter(args.db_dsn)

    # 7) 评估器
    evaluator = Evaluator()

    # 执行匹配
    print("\n" + "-"*40)
    print("步骤4: 开始匹配")
    print("-"*40)
    
    results = []
    for idx, event in enumerate(events, start=1):
        print(f"\n>>> 处理第 {idx}/{len(events)} 个事件 (ID: {event.event_id})")
        
        # 召回
        recalled = recall_engine.recall_top_k(event, top_k=args.top_k)
        
        # 精排
        ranked = reranker.rerank_candidates(event, recalled, gate_map)
        
        # 决策
        result = decider.decide(event, ranked)
        results.append(result)

        # 落库
        if not args.dry_run:
            try:
                writer.upsert_match_decision(result)
                print(f"[进度] 事件 {event.event_id} 写入成功")
            except Exception as e:
                print(f"[错误] 事件 {event.event_id} 写入失败: {e}")

    # 评估
    print("\n" + "-"*40)
    print("步骤5: 评估结果")
    print("-"*40)
    
    summary = evaluator.evaluate(events, results, subject_key_to_theme_name)
    
    # 导出
    evaluator.export_detail_csv(args.detail_out, events, results, subject_key_to_theme_name)
    evaluator.export_summary_json(args.summary_out, summary)

    # 打印结果
    print("\n" + "="*50)
    print("评测结果摘要")
    print("="*50)
    print(f"总事件数: {summary['total_events']}")
    print(f"Accept匹配: {summary['accept_match_count']}")
    print(f"Abstain待定: {summary['abstain_count']}")
    print(f"No_match未匹配: {summary['no_match_count']}")
    print(f"Top1准确率: {summary['top1_accuracy']*100:.2f}%")
    print(f"Top3准确率: {summary['top3_accuracy']*100:.2f}%")
    
    if summary['confusion_pairs']:
        print("\n常见混淆对:")
        for pair in summary['confusion_pairs'][:5]:
            print(f"  {pair['true_theme']} → {pair['pred_theme']}: {pair['count']}次")
    
    print(f"\n详细结果已保存至: {args.detail_out}")
    print(f"汇总指标已保存至: {args.summary_out}")
    print("\n" + "="*50)


if __name__ == "__main__":
    main()