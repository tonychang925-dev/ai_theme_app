#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_quality_audit.py v1.2

校准目标：
- 下调 TITLE_NOT_ALIGNED / LOW_EVIDENCE_DIVERSITY / WEAK_NOT_BOUNDARY 的影响
- 强化 generic_must_score / confusability_score / separability_score
- 让 A 档更集中到“泛 must + 高误召回 + 近邻冲突”
- 抓出公共新闻高频词伪装 hard anchor 的 gate
- 同时审计 subject_gates 与运行时 theme_profile_v2
"""


from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
DEFAULT_GATE_DIR = PROJECT_ROOT / "subject_gates"
DEFAULT_THEME_LIST = PROJECT_ROOT / "theme_data_complete/lists/full_theme_list.sync.jsonl"
DEFAULT_RUNTIME_DETAIL = PROJECT_ROOT / "tmp/runtime_theme_match_detail_100.json"
DEFAULT_FULLCHAIN_REPORT = PROJECT_ROOT / "tmp/p2_phase0_full_chain_100_to_decision.report.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "tmp/gate_quality_audit"

GENERIC_SUSPECT_TERMS = {
    "产业链", "平台", "系统", "应用", "方案", "智能", "数字化", "终端", "服务",
    "产品", "设备", "公司", "合作", "美国", "卫星", "商业航天", "金融", "动力系统",
}
GLOBAL_NO_ANCHOR_TERMS = {
    "政府", "中国", "美国", "国家", "企业", "公司", "项目", "平台", "系统", "服务",
    "应用", "产业链", "政策", "部门", "机构", "集群", "建设", "合作", "发布", "申请",
    "批准", "接收", "观察", "预防",
}
PUBLIC_NEWS_TERMS = GLOBAL_NO_ANCHOR_TERMS | {"消息", "新闻", "相关", "推进", "披露"}
MEDICAL_PUBLIC_HEALTH_TERMS = {"接收", "观察", "预防", "医生", "感染", "病毒", "公共卫生"}
SOURCE_BUCKETS = {"primary_anchor", "secondary_anchor", "event_term", "descriptive_term", "knowledge_term"}


@dataclass
class GateRecord:
    subject_key: str
    subject_name: str
    strategy_type: str
    semantic_type: str
    must: List[str]
    should: List[str]
    not_terms: List[str]
    strong: List[str]
    aliases: List[str]
    entity_hints: List[str]
    core_objects: List[str]
    evidence_refs: List[Dict[str, Any]]
    quality: str = ""
    source: str = "subject_gates"
    no_anchor_terms: List[str] | None = None

    @property
    def title_terms(self) -> List[str]:
        return [self.subject_name, *self.aliases]

    @property
    def all_terms(self) -> List[str]:
        return _uniq(
            self.must
            + self.strong
            + self.should
            + self.aliases
            + self.entity_hints
            + self.core_objects
            + [self.subject_name]
        )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _uniq(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        s = _norm(v)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa = {_norm(x) for x in a if _norm(x)}
    sb = {_norm(x) for x in b if _norm(x)}
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _seq(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _contains_related(term: str, title_terms: Iterable[str]) -> bool:
    for title in title_terms:
        t = _norm(title)
        if not t:
            continue
        if term == t or term in t or t in term:
            return True
    return False


def _strip_global_no_anchor_fragments(term: str) -> str:
    remaining = _norm(term)
    for value in sorted(GLOBAL_NO_ANCHOR_TERMS, key=len, reverse=True):
        remaining = remaining.replace(value, "")
    return remaining.strip(" /-_、，,。；;（）()[]【】")


def _is_global_no_anchor_term(term: str) -> bool:
    value = _norm(term)
    return bool(value) and (value in GLOBAL_NO_ANCHOR_TERMS or not _strip_global_no_anchor_fragments(value))


def _has_public_news_term(terms: Iterable[str]) -> bool:
    return any(_is_global_no_anchor_term(term) or _norm(term) in PUBLIC_NEWS_TERMS for term in terms)


def _has_medical_public_health_term(terms: Iterable[str]) -> bool:
    return any(any(value in _norm(term) for value in MEDICAL_PUBLIC_HEALTH_TERMS) for term in terms)


def _hard_anchor_terms(gate: GateRecord) -> List[str]:
    candidates = gate.must + gate.strong + gate.entity_hints + gate.core_objects
    no_anchor = set(gate.no_anchor_terms or [])
    return [
        term
        for term in _uniq(candidates)
        if term not in no_anchor and not _is_global_no_anchor_term(term)
    ]


def load_subject_names(path: Path) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for row in _read_jsonl(path):
        subject_key = _norm(row.get("subjectId"))
        name = _norm(row.get("name"))
        if subject_key and name:
            names[subject_key] = name
    return names


def load_gates(gate_dir: Path, subject_names: Dict[str, str]) -> List[GateRecord]:
    gates: List[GateRecord] = []
    for path in sorted(gate_dir.glob("*_gate.json")):
        obj = _read_json(path)
        subject_key = _norm(obj.get("subject_id") or path.name.split("_", 1)[0])
        gates.append(
            GateRecord(
                subject_key=subject_key,
                subject_name=_norm(subject_names.get(subject_key) or obj.get("concept") or subject_key),
                strategy_type=_norm(obj.get("strategy_type")),
                semantic_type=_norm(obj.get("semantic_type")),
                must=_uniq(obj.get("must") or []),
                should=_uniq(obj.get("should") or []),
                not_terms=_uniq(obj.get("not") or []),
                strong=_uniq(obj.get("strong") or []),
                aliases=_uniq(obj.get("aliases") or []),
                entity_hints=_uniq(obj.get("entity_hints") or []),
                core_objects=_uniq(obj.get("core_objects") or []),
                evidence_refs=obj.get("evidence_refs") or [],
                quality=_norm(obj.get("quality")),
                source="subject_gates",
                no_anchor_terms=[],
            )
        )
    return gates


def _normalize_json_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return _uniq(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return _uniq(parsed)
        return _uniq(part for part in value.replace("，", ",").split(","))
    return []


async def load_v2_gates(db_name: str, status: str) -> List[GateRecord]:
    import asyncpg

    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
        port=int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))),
        user=os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
        password=os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres")),
        database=db_name,
    )
    try:
        rows = await conn.fetch(
            """
            SELECT
                subject_key, subject_name, status, aliases,
                must_terms, strong_terms, should_terms, support_terms,
                entity_anchors, domain_anchors, product_anchors, technology_anchors,
                no_anchor_terms, negative_terms
            FROM theme_profile_v2
            WHERE ($1::text = 'all' OR status = $1::text)
            ORDER BY subject_key
            """,
            status,
        )
    finally:
        await conn.close()

    gates: List[GateRecord] = []
    for row in rows:
        obj = dict(row)
        gates.append(
            GateRecord(
                subject_key=_norm(obj.get("subject_key")),
                subject_name=_norm(obj.get("subject_name") or obj.get("subject_key")),
                strategy_type="event_driven",
                semantic_type="profile_v2",
                must=_normalize_json_list(obj.get("must_terms")),
                should=_uniq(
                    _normalize_json_list(obj.get("should_terms"))
                    + _normalize_json_list(obj.get("support_terms"))
                ),
                not_terms=_normalize_json_list(obj.get("negative_terms")),
                strong=_normalize_json_list(obj.get("strong_terms")),
                aliases=_normalize_json_list(obj.get("aliases")),
                entity_hints=_normalize_json_list(obj.get("entity_anchors")),
                core_objects=_uniq(
                    _normalize_json_list(obj.get("domain_anchors"))
                    + _normalize_json_list(obj.get("product_anchors"))
                    + _normalize_json_list(obj.get("technology_anchors"))
                ),
                evidence_refs=[],
                quality="v2",
                source=f"theme_profile_v2:{_norm(obj.get('status'))}",
                no_anchor_terms=_normalize_json_list(obj.get("no_anchor_terms")),
            )
        )
    return gates


def build_global_term_freq(gates: List[GateRecord]) -> Counter:
    freq: Counter = Counter()
    for gate in gates:
        for term in set(gate.must):
            freq[term] += 1
    return freq


def build_backtest_stats(
    runtime_detail_path: Path,
    fullchain_report_path: Path,
    subject_names: Dict[str, str],
) -> Tuple[Dict[str, Dict[str, Any]], Counter]:
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "subject_key": "",
            "subject_name": "",
            "total_hit_count": 0,
            "true_positive_count": 0,
            "false_positive_count": 0,
            "false_negative_count": 0,
            "tp_confusions": Counter(),
            "fp_from_gt": Counter(),
            "false_positive_events": [],
        }
    )
    pair_counter: Counter = Counter()

    runtime_rows = _read_json(runtime_detail_path) if runtime_detail_path.exists() else []
    if isinstance(runtime_rows, list):
        for row in runtime_rows:
            gt = _norm(row.get("gt_subject_key"))
            pred = _norm(row.get("matched_subject_key"))
            if gt:
                item = stats[gt]
                item["subject_key"] = gt
                item["subject_name"] = _norm(subject_names.get(gt) or row.get("gt_theme_name") or gt)
                if pred == gt:
                    item["true_positive_count"] += 1
                else:
                    item["false_negative_count"] += 1
                    if pred:
                        item["tp_confusions"][pred] += 1
                        pair_counter[(gt, pred)] += 1
            if pred:
                p = stats[pred]
                p["subject_key"] = pred
                p["subject_name"] = _norm(subject_names.get(pred) or row.get("matched_theme_name") or pred)
                p["total_hit_count"] += 1
                if pred != gt:
                    p["false_positive_count"] += 1
                    p["fp_from_gt"][gt] += 1
                    p["false_positive_events"].append(
                        {
                            "event_id": row.get("event_id"),
                            "gt_subject_key": gt,
                            "reason_code": row.get("reason_code"),
                        }
                    )

    fullchain = _read_json(fullchain_report_path) if fullchain_report_path.exists() else {}
    for row in fullchain.get("details", []):
        gt = _norm(row.get("expected_subject_key"))
        pred = _norm(row.get("matched_subject_key"))
        if gt:
            item = stats[gt]
            item["subject_key"] = gt
            item["subject_name"] = _norm(subject_names.get(gt) or row.get("expected_theme_name") or gt)
            if pred == gt:
                item["true_positive_count"] += 1
            else:
                item["false_negative_count"] += 1
                if pred:
                    item["tp_confusions"][pred] += 1
                    pair_counter[(gt, pred)] += 1
        if pred:
            p = stats[pred]
            p["subject_key"] = pred
            p["subject_name"] = _norm(subject_names.get(pred) or row.get("matched_theme_name") or pred)
            p["total_hit_count"] += 1
            if pred != gt:
                p["false_positive_count"] += 1
                p["fp_from_gt"][gt] += 1
                p["false_positive_events"].append(
                    {
                        "event_id": row.get("news_id"),
                        "gt_subject_key": gt,
                        "reason_code": row.get("reason_code"),
                    }
                )

    for item in stats.values():
        tp = item["true_positive_count"]
        fp = item["false_positive_count"]
        fn = item["false_negative_count"]
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
        item["precision_score"] = round(precision, 4)
        item["recall_score"] = round(recall, 4)
        item["f1_score"] = round(f1, 4)
        item["common_confused_subjects"] = [
            {"subject_key": k, "count": c} for k, c in item["tp_confusions"].most_common(10)
        ]
        item["common_false_positive_events"] = item["false_positive_events"][:10]
        item["common_false_positive_sources"] = [
            {"subject_key": k, "count": c} for k, c in item["fp_from_gt"].most_common(10)
        ]
    return stats, pair_counter


def compute_title_align_score(gate: GateRecord) -> float:
    if not gate.must:
        return 0.0
    aligned = 0
    title_terms = gate.title_terms
    related_terms = _uniq(title_terms + gate.entity_hints + gate.core_objects)
    for term in gate.must:
        if _contains_related(term, title_terms):
            aligned += 1
        elif _contains_related(term, related_terms):
            aligned += 0.6
    return round(min(1.0, aligned / max(len(gate.must), 1)), 4)


def compute_coverage_score(gate: GateRecord) -> Tuple[float, float]:
    sources = set()
    term_to_sources: Dict[str, set] = defaultdict(set)
    for ref in gate.evidence_refs:
        term = _norm(ref.get("term"))
        source = _norm(ref.get("source"))
        if not term or not source:
            continue
        bucket = source if source in SOURCE_BUCKETS else "knowledge_term"
        if term in gate.must:
            sources.add(bucket)
            term_to_sources[term].add(bucket)
    coverage = len(sources) / max(len(SOURCE_BUCKETS), 1)
    diversity = sum(len(v) for v in term_to_sources.values()) / max(len(gate.must) * len(SOURCE_BUCKETS), 1)
    return round(coverage, 4), round(diversity, 4)


def compute_not_effectiveness(gate: GateRecord, neighbor_rows: List[Dict[str, Any]]) -> float:
    if not neighbor_rows:
        return 0.5 if gate.not_terms else 0.0
    blocked = 0
    total = 0
    for row in neighbor_rows[:5]:
        for term in row["neighbor_must"]:
            total += 1
            if term in gate.not_terms:
                blocked += 1
    if total == 0:
        return 0.5 if gate.not_terms else 0.0
    return round(blocked / total, 4)


def build_neighbor_rows(gates: List[GateRecord]) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    neighbors_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    flat_rows: List[Dict[str, Any]] = []
    gate_text = {g.subject_key: " ".join(g.all_terms) for g in gates}
    for gate in gates:
        rows: List[Dict[str, Any]] = []
        for other in gates:
            if other.subject_key == gate.subject_key:
                continue
            must_overlap = sorted(set(gate.must) & set(other.must))
            should_overlap = sorted(set(gate.should) & set(other.should))
            title_similarity = max(
                _seq(gate.subject_name, other.subject_name),
                max((_seq(a, other.subject_name) for a in gate.aliases), default=0.0),
            )
            ontology_similarity = 0.0
            if gate.semantic_type and other.semantic_type:
                ontology_similarity = _seq(gate.semantic_type, other.semantic_type)
            gate_similarity = (
                0.6 * _jaccard(gate.must + gate.strong + gate.core_objects, other.must + other.strong + other.core_objects)
                + 0.4 * _jaccard(gate.should + gate.aliases, other.should + other.aliases)
            )
            confusion_score = round(
                min(1.0, 0.45 * gate_similarity + 0.25 * title_similarity + 0.15 * ontology_similarity
                    + 0.15 * _jaccard(gate_text[gate.subject_key].split(), gate_text[other.subject_key].split())),
                4,
            )
            row = {
                "subject_key": gate.subject_key,
                "subject_name": gate.subject_name,
                "neighbor_subject_key": other.subject_key,
                "neighbor_subject_name": other.subject_name,
                "must_overlap_count": len(must_overlap),
                "must_overlap_terms": must_overlap,
                "should_overlap_count": len(should_overlap),
                "should_overlap_terms": should_overlap,
                "title_similarity": round(title_similarity, 4),
                "ontology_similarity": round(ontology_similarity, 4),
                "gate_similarity": round(gate_similarity, 4),
                "confusion_score": confusion_score,
                "conflict_reason": _build_conflict_reason(must_overlap, should_overlap, title_similarity, ontology_similarity),
                "neighbor_must": other.must,
            }
            rows.append(row)
        rows.sort(key=lambda x: x["confusion_score"], reverse=True)
        neighbors_map[gate.subject_key] = rows[:10]
        flat_rows.extend(rows[:10])
    return neighbors_map, flat_rows


def _build_conflict_reason(
    must_overlap: List[str],
    should_overlap: List[str],
    title_similarity: float,
    ontology_similarity: float,
) -> List[str]:
    reasons: List[str] = []
    if must_overlap:
        reasons.append("must_overlap")
    if len(should_overlap) >= 2:
        reasons.append("should_overlap")
    if title_similarity >= 0.55:
        reasons.append("title_similar")
    if ontology_similarity >= 0.65:
        reasons.append("semantic_similar")
    return reasons


def compute_audit_rows(
    gates: List[GateRecord],
    backtest_stats: Dict[str, Dict[str, Any]],
    pair_counter: Counter,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    must_freq = build_global_term_freq(gates)
    max_freq = max(must_freq.values()) if must_freq else 1
    neighbors_map, flat_neighbor_rows = build_neighbor_rows(gates)
    audit_rows: List[Dict[str, Any]] = []
    for gate in gates:
        generic_components = []
        suspect_count = 0
        shared_count = 0
        illegal_must_terms = [term for term in gate.must if _is_global_no_anchor_term(term)]
        for term in gate.must:
            freq = must_freq.get(term, 1)
            generic_components.append(min(1.0, math.log(1 + freq) / math.log(1 + max_freq)))
            if freq > 1:
                shared_count += 1
            if term in GENERIC_SUSPECT_TERMS or _is_global_no_anchor_term(term) or len(term) <= 2:
                suspect_count += 1
        generic_must_score = round(
            min(
                1.0,
                (sum(generic_components) / max(len(generic_components), 1)) * 0.7
                + (suspect_count / max(len(gate.must), 1)) * 0.3,
            ),
            4,
        )
        must_title_align_score = compute_title_align_score(gate)
        # v1.1: title 对齐仍保留，但不再重罚；
        # 好 gate 的 must 往往是对象/环节/技术词，不一定直接贴题材标题字符串。
        specificity_score = round(0.92 * (1 - generic_must_score) + 0.08 * must_title_align_score, 4)

        neighbor_rows = neighbors_map.get(gate.subject_key, [])
        max_neighbor_confusion = max((row["confusion_score"] for row in neighbor_rows), default=0.0)
        separability_score = round(max(0.0, 1 - max_neighbor_confusion), 4)
        coverage_score, evidence_diversity_score = compute_coverage_score(gate)

        back = backtest_stats.get(gate.subject_key, {})
        false_positive_rate = back.get("false_positive_count", 0) / max(back.get("total_hit_count", 0), 1)
        confusability_score = round(min(1.0, 0.6 * false_positive_rate + 0.4 * max_neighbor_confusion), 4)
        stability_score = 0.0
        must_shared_ratio = round(shared_count / max(len(gate.must), 1), 4)
        not_effectiveness_score = compute_not_effectiveness(gate, neighbor_rows)
        # v1.1 校准目标：
        # 1) 下调 TITLE_NOT_ALIGNED / LOW_EVIDENCE_DIVERSITY / WEAK_NOT_BOUNDARY 的影响
        # 2) 强化 generic_must / confusability / separability
        # 3) 让 A 档更集中到“泛 must + 高误召回 + 近邻冲突”
        overall_score = round(
            0.24 * specificity_score
            + 0.26 * separability_score
            + 0.05 * coverage_score
            + 0.30 * (1 - confusability_score)
            + 0.10 * stability_score
            + 0.05 * must_title_align_score,
            4,
        )
        risk_flags = []
        hard_anchor_terms = _hard_anchor_terms(gate)
        must_only_generic = bool(gate.must) and len(illegal_must_terms) == len(gate.must)
        no_hard_anchor = not hard_anchor_terms
        empty_negative_boundary = not gate.not_terms and not (gate.no_anchor_terms or [])
        if illegal_must_terms:
            risk_flags.append("ILLEGAL_MUST_TERM")
        if must_only_generic:
            risk_flags.append("MUST_ONLY_GENERIC")
        if no_hard_anchor:
            risk_flags.append("NO_HARD_ANCHOR")
        if gate.quality.lower() == "weak" and empty_negative_boundary:
            risk_flags.append("WEAK_GATE_WITH_EMPTY_NOT")
        if empty_negative_boundary:
            risk_flags.append("EMPTY_NEGATIVE_BOUNDARY")
        if _has_public_news_term(gate.must) and no_hard_anchor:
            risk_flags.append("PUBLIC_NEWS_FALSE_POSITIVE_RISK")
        if _has_medical_public_health_term(gate.must + gate.should) and no_hard_anchor:
            risk_flags.append("MEDICAL_PUBLIC_HEALTH_FALSE_POSITIVE_RISK")
        if gate.strategy_type == "policy_driven" and illegal_must_terms:
            risk_flags.append("POLICY_WORD_OVERFIT")
        if generic_must_score >= 0.6:
            risk_flags.append("GENERIC_MUST")
        if must_shared_ratio >= 0.5:
            risk_flags.append("MUST_TOO_COMMON")
        if separability_score < 0.35:
            risk_flags.append("LOW_SEPARABILITY")
        if max_neighbor_confusion > 0.65:
            risk_flags.append("NEIGHBOR_COLLISION")
        if coverage_score < 0.08:
            risk_flags.append("LOW_EVIDENCE_DIVERSITY")
        if evidence_diversity_score < 0.04:
            risk_flags.append("SINGLE_SOURCE_GATE")
        if confusability_score > 0.60:
            risk_flags.append("HIGH_FALSE_POSITIVE")
        if back.get("common_confused_subjects"):
            risk_flags.append("FREQUENT_CONFUSION")
        if must_title_align_score < 0.08:
            risk_flags.append("TITLE_NOT_ALIGNED")
        if (
            not_effectiveness_score < 0.01
            and neighbor_rows
            and gate.not_terms
            and max_neighbor_confusion > 0.60
        ):
            risk_flags.append("WEAK_NOT_BOUNDARY")

        a_hard = (
            generic_must_score >= 0.72
            or confusability_score >= 0.68
            or separability_score < 0.28
        )
        a_combo = (
            (generic_must_score >= 0.60 and confusability_score >= 0.55)
            or (generic_must_score >= 0.60 and separability_score < 0.35)
            or (confusability_score >= 0.55 and separability_score < 0.35)
        )

        public_anchor_rebuild = "ILLEGAL_MUST_TERM" in risk_flags and "NO_HARD_ANCHOR" in risk_flags
        if public_anchor_rebuild or overall_score < 0.42 or a_hard or a_combo:
            risk_level = "A"
            suggested_action = "REBUILD"
        elif overall_score < 0.62:
            risk_level = "B"
            suggested_action = "LIGHT_FIX"
        elif overall_score < 0.78:
            risk_level = "C"
            suggested_action = "LIGHT_FIX"
        else:
            risk_level = "D"
            suggested_action = "KEEP"
        if "UNSTABLE_MUST" in risk_flags or "ANCHOR_DRIFT" in risk_flags:
            suggested_action = "MANUAL_REVIEW"

        top_confused_subjects = [
            {
                "subject_key": row["neighbor_subject_key"],
                "subject_name": row["neighbor_subject_name"],
                "confusion_score": row["confusion_score"],
                "must_overlap_terms": row["must_overlap_terms"],
            }
            for row in neighbor_rows[:5]
        ]
        notes = []
        for pred, cnt in pair_counter.items():
            gt_key, pred_key = pred
            if gt_key == gate.subject_key and cnt >= 2:
                notes.append(f"FN常见混淆->{pred_key}:{cnt}")
        audit_rows.append(
            {
                "subject_key": gate.subject_key,
                "subject_name": gate.subject_name,
                "source": gate.source,
                "quality": gate.quality,
                "strategy_type": gate.strategy_type,
                "must_count": len(gate.must),
                "should_count": len(gate.should),
                "not_count": len(gate.not_terms),
                "generic_must_score": generic_must_score,
                "specificity_score": specificity_score,
                "separability_score": separability_score,
                "coverage_score": coverage_score,
                "confusability_score": confusability_score,
                "stability_score": stability_score,
                "overall_score": overall_score,
                "must_shared_ratio": must_shared_ratio,
                "must_title_align_score": must_title_align_score,
                "evidence_diversity_score": evidence_diversity_score,
                "not_effectiveness_score": not_effectiveness_score,
                "risk_level": risk_level,
                "risk_flags": risk_flags,
                "suggested_action": suggested_action,
                "top_confused_subjects": top_confused_subjects,
                "illegal_must_terms": illegal_must_terms,
                "hard_anchor_terms": hard_anchor_terms,
                "notes": " | ".join(notes),
                "audit_version": "gate_audit.v1.2",
            }
        )
    audit_rows.sort(key=lambda x: (x["risk_level"], x["overall_score"]))
    return audit_rows, flat_neighbor_rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: Path, audit_rows: List[Dict[str, Any]], neighbor_rows: List[Dict[str, Any]]) -> None:
    counts = Counter(row["risk_level"] for row in audit_rows)
    high_risk = sorted(audit_rows, key=lambda x: (x["risk_level"], x["overall_score"], -x["confusability_score"]))[:20]
    generic_top = sorted(audit_rows, key=lambda x: x["generic_must_score"], reverse=True)[:20]
    confusion_top = sorted(audit_rows, key=lambda x: x["confusability_score"], reverse=True)[:20]
    neighbor_top = sorted(neighbor_rows, key=lambda x: x["confusion_score"], reverse=True)[:20]

    lines = [
        "# gate_quality_audit.v1.2",
        "",
        "## 1. 总览",
        f"- 总题材数: `{len(audit_rows)}`",
        f"- A档: `{counts.get('A', 0)}`",
        f"- B档: `{counts.get('B', 0)}`",
        f"- C档: `{counts.get('C', 0)}`",
        f"- D档: `{counts.get('D', 0)}`",
        "",
        "## 2. Top20 高风险题材",
    ]
    for row in high_risk:
        lines.append(
            f"- `{row['subject_key']}` `{row['subject_name']}` "
            f"`overall={row['overall_score']:.4f}` "
            f"`generic={row['generic_must_score']:.4f}` "
            f"`sep={row['separability_score']:.4f}` "
            f"`conf={row['confusability_score']:.4f}` "
            f"`action={row['suggested_action']}` "
            f"`flags={','.join(row['risk_flags'])}`"
        )
    lines.extend(["", "## 3. Top20 must 过泛题材"])
    for row in generic_top:
        lines.append(
            f"- `{row['subject_key']}` `{row['subject_name']}` "
            f"`generic={row['generic_must_score']:.4f}` "
            f"`must_shared_ratio={row['must_shared_ratio']:.4f}`"
        )
    lines.extend(["", "## 4. Top20 误召回风险题材"])
    for row in confusion_top:
        lines.append(
            f"- `{row['subject_key']}` `{row['subject_name']}` "
            f"`confusability={row['confusability_score']:.4f}` "
            f"`overall={row['overall_score']:.4f}`"
        )
    lines.extend(["", "## 5. Top20 近邻冲突对"])
    for row in neighbor_top:
        lines.append(
            f"- `{row['subject_key']}/{row['subject_name']}` <-> "
            f"`{row['neighbor_subject_key']}/{row['neighbor_subject_name']}` "
            f"`score={row['confusion_score']:.4f}` "
            f"`must_overlap={row['must_overlap_terms']}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_rebuild_plan(path: Path, audit_rows: List[Dict[str, Any]]) -> None:
    rebuild_rows = [row for row in audit_rows if row["risk_level"] == "A"]
    light_fix_rows = [row for row in audit_rows if row["risk_level"] == "B"]
    lines = [
        "# Gate Rebuild Plan",
        "",
        "## A 档：必须重建",
    ]
    for row in rebuild_rows:
        lines.extend(
            [
                f"- `{row['subject_key']}` `{row['subject_name']}` `{row['source']}`",
                f"  - 问题: flags=`{','.join(row['risk_flags'])}` illegal_must=`{row['illegal_must_terms']}`",
                f"  - 风险: overall=`{row['overall_score']}` generic=`{row['generic_must_score']}` conf=`{row['confusability_score']}`",
                "  - 修复: 重建 hard anchor，剔除公共新闻词伪 anchor，补 no_anchor/negative 边界。",
            ]
        )
    lines.extend(["", "## B 档：轻修边界"])
    for row in light_fix_rows:
        lines.extend(
            [
                f"- `{row['subject_key']}` `{row['subject_name']}` `{row['source']}`",
                f"  - 问题: flags=`{','.join(row['risk_flags'])}`",
                f"  - 风险: overall=`{row['overall_score']}` generic=`{row['generic_must_score']}` conf=`{row['confusability_score']}`",
                "  - 修复: 复核 must 强度，补近邻 negative/no_anchor，避免扩大召回。",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="gate quality audit v1.2")
    parser.add_argument("--source", choices=("subject_gates", "theme_profile_v2"), default="subject_gates")
    parser.add_argument("--gate-dir", type=Path, default=DEFAULT_GATE_DIR)
    parser.add_argument("--theme-list", type=Path, default=DEFAULT_THEME_LIST)
    parser.add_argument("--runtime-detail", type=Path, default=DEFAULT_RUNTIME_DETAIL)
    parser.add_argument("--fullchain-report", type=Path, default=DEFAULT_FULLCHAIN_REPORT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--read-db-name", default=os.getenv("READ_DB_NAME", "stock_data_test"))
    parser.add_argument("--v2-status", default=os.getenv("THEME_PROFILE_V2_STATUS", "accepted_candidate"))
    args = parser.parse_args()

    subject_names = load_subject_names(args.theme_list)
    if args.source == "theme_profile_v2":
        gates = asyncio.run(load_v2_gates(args.read_db_name, args.v2_status))
    else:
        gates = load_gates(args.gate_dir, subject_names)
    backtest_stats, pair_counter = build_backtest_stats(args.runtime_detail, args.fullchain_report, subject_names)
    audit_rows, neighbor_rows = compute_audit_rows(gates, backtest_stats, pair_counter)

    backtest_rows = [backtest_stats[k] for k in sorted(backtest_stats.keys())]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "gate_quality_audit.jsonl", audit_rows)
    write_jsonl(args.out_dir / "gate_neighbor_confusion.jsonl", neighbor_rows)
    write_jsonl(args.out_dir / "gate_match_backtest_stats.jsonl", backtest_rows)
    write_report(args.out_dir / "gate_quality_report.md", audit_rows, neighbor_rows)
    write_rebuild_plan(args.out_dir / "gate_rebuild_plan.md", audit_rows)

    print(
        json.dumps(
            {
                "gates": len(gates),
                "source": args.source,
                "audit_path": str(args.out_dir / "gate_quality_audit.jsonl"),
                "neighbor_path": str(args.out_dir / "gate_neighbor_confusion.jsonl"),
                "backtest_path": str(args.out_dir / "gate_match_backtest_stats.jsonl"),
                "report_path": str(args.out_dir / "gate_quality_report.md"),
                "rebuild_plan_path": str(args.out_dir / "gate_rebuild_plan.md"),
                "risk_distribution": dict(Counter(row["risk_level"] for row in audit_rows)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
