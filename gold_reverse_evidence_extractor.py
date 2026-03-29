#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gold_reverse_evidence_extractor.py

用途：
1. 读取久赢恒丰 gold 股票池（按 subject / group / direction 组织）
2. 从 PostgreSQL 反查 gold 股票在本地库中的 profile + facts
3. 生成：
   - gold_evidence_detail.json
   - gold_direction_term_pack.json
   - gold_gap_report.json

依赖：
pip install psycopg2-binary jieba

示例：
python gold_reverse_evidence_extractor.py \
  --gold-json satcom_gold_pool.json \
  --db-dsn "postgresql://postgres:xxx@127.0.0.1:5432/stock_data_test" \
  --out-dir ./gold_reverse_out
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Set

import jieba
import psycopg2
import psycopg2.extras


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

PRIMARY_FACT_TYPES = {
    "main_business",
    "product",
    "technology",
    "order_contract",
    "investment",
}

CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9\-\+\.]+")

DEFAULT_STOPWORDS = {
    "公司", "业务", "产品", "系统", "方案", "平台", "能力", "领域", "项目", "客户",
    "服务", "设备", "材料", "技术", "相关", "实现", "形成", "推进", "可以", "以及",
    "国内", "中国", "全球", "行业", "发展", "应用", "布局", "建设", "提供", "开展",
    "业务领域", "主营业务", "上市公司", "高新技术企业", "解决方案", "供应商", "生产基地",
}

SATCOM_HINT_TERMS = {
    "卫星", "低轨卫星", "卫星互联网", "卫星通信", "载荷", "星载", "相控阵", "天线",
    "测控", "遥感", "导航", "北斗", "火箭", "运载火箭", "商业航天", "发射场", "组网",
    "星间链路", "地面站", "中继传输", "空间算力", "太空数据中心", "航天", "航天电子",
    "卫通", "火箭部件", "卫星制造", "卫星运营",
}


def safe_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def uniq_keep_order(items: List[str]) -> List[str]:
    out = []
    seen = set()
    for x in items:
        s = safe_str(x)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def normalize_text(text: str) -> str:
    text = safe_str(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []
    coarse = []
    for token in jieba.cut(text, cut_all=False):
        token = safe_str(token)
        if not token:
            continue
        if len(token) <= 1:
            continue
        if token in DEFAULT_STOPWORDS:
            continue
        coarse.append(token)

    regex_tokens = CJK_TOKEN_RE.findall(text)
    merged = coarse + regex_tokens
    out = []
    for t in merged:
        t = safe_str(t)
        if len(t) <= 1:
            continue
        if t in DEFAULT_STOPWORDS:
            continue
        out.append(t)
    return uniq_keep_order(out)


def top_k_counter(counter: collections.Counter, k: int = 30, min_count: int = 2) -> List[Dict[str, Any]]:
    out = []
    for term, cnt in counter.most_common():
        if cnt < min_count:
            continue
        out.append({"term": term, "count": cnt})
        if len(out) >= k:
            break
    return out


@dataclass
class GoldStock:
    subject_key: str
    subject_name: str
    group_name: str
    direction_name: str
    stock_id: str = ""
    stock_name: str = ""


@dataclass
class StockProfile:
    stock_id: str
    stock_name: str
    profile_text: str = ""
    main_business_text: str = ""
    product_text: str = ""
    brand_text: str = ""
    order_text: str = ""
    relation_text: str = ""
    logic_text: str = ""
    fact_count: int = 0
    primary_fact_count: int = 0
    evidence_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StockFact:
    fact_id: int
    stock_id: str
    fact_type: str
    fact_value: str
    source: str = ""
    confidence: float = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source_id: str = ""
    evidence_span: str = ""


def parse_gold_pool(gold_obj: Dict[str, Any]) -> List[GoldStock]:
    subject_key = safe_str(gold_obj.get("subject_key"))
    subject_name = safe_str(gold_obj.get("subject_name"))
    out: List[GoldStock] = []

    for group in gold_obj.get("direction_groups") or []:
        group_name = safe_str(group.get("group_name"))
        for direction in group.get("directions") or []:
            direction_name = safe_str(direction.get("direction_name"))
            for s in direction.get("stocks") or []:
                if isinstance(s, dict):
                    stock = GoldStock(
                        subject_key=subject_key,
                        subject_name=subject_name,
                        group_name=group_name,
                        direction_name=direction_name,
                        stock_id=safe_str(s.get("stock_id")),
                        stock_name=safe_str(s.get("stock_name")),
                    )
                else:
                    stock = GoldStock(
                        subject_key=subject_key,
                        subject_name=subject_name,
                        group_name=group_name,
                        direction_name=direction_name,
                        stock_name=safe_str(s),
                    )
                out.append(stock)
    return out


def fetch_profiles_by_ids(conn, stock_ids: List[str]) -> Dict[str, StockProfile]:
    if not stock_ids:
        return {}

    sql = """
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
        evidence_json
    FROM stock_profile_ext
    WHERE stock_id = ANY(%s)
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_ids,))
        rows = list(cur.fetchall())

    out: Dict[str, StockProfile] = {}
    for r in rows:
        sp = StockProfile(
            stock_id=safe_str(r.get("stock_id")),
            stock_name=safe_str(r.get("stock_name")),
            profile_text=safe_str(r.get("profile_text")),
            main_business_text=safe_str(r.get("main_business_text")),
            product_text=safe_str(r.get("product_text")),
            brand_text=safe_str(r.get("brand_text")),
            order_text=safe_str(r.get("order_text")),
            relation_text=safe_str(r.get("relation_text")),
            logic_text=safe_str(r.get("logic_text")),
            fact_count=int(r.get("fact_count") or 0),
            primary_fact_count=int(r.get("primary_fact_count") or 0),
            evidence_json=r.get("evidence_json") or {},
        )
        out[sp.stock_id] = sp
    return out


def fetch_profiles_by_names(conn, stock_names: List[str]) -> Dict[str, StockProfile]:
    if not stock_names:
        return {}

    sql = """
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
        evidence_json
    FROM stock_profile_ext
    WHERE stock_name = ANY(%s)
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_names,))
        rows = list(cur.fetchall())

    out: Dict[str, StockProfile] = {}
    for r in rows:
        sp = StockProfile(
            stock_id=safe_str(r.get("stock_id")),
            stock_name=safe_str(r.get("stock_name")),
            profile_text=safe_str(r.get("profile_text")),
            main_business_text=safe_str(r.get("main_business_text")),
            product_text=safe_str(r.get("product_text")),
            brand_text=safe_str(r.get("brand_text")),
            order_text=safe_str(r.get("order_text")),
            relation_text=safe_str(r.get("relation_text")),
            logic_text=safe_str(r.get("logic_text")),
            fact_count=int(r.get("fact_count") or 0),
            primary_fact_count=int(r.get("primary_fact_count") or 0),
            evidence_json=r.get("evidence_json") or {},
        )
        out[sp.stock_name] = sp
    return out


def fetch_facts_by_ids(conn, stock_ids: List[str]) -> Dict[str, List[StockFact]]:
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

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_ids, IMPORTANT_FACT_TYPES))
        rows = list(cur.fetchall())

    out: Dict[str, List[StockFact]] = collections.defaultdict(list)
    for r in rows:
        out[safe_str(r["stock_id"])].append(
            StockFact(
                fact_id=int(r["id"]),
                stock_id=safe_str(r["stock_id"]),
                fact_type=safe_str(r["fact_type"]),
                fact_value=safe_str(r.get("fact_value")),
                source=safe_str(r.get("source")),
                confidence=safe_float(r.get("confidence"), 1.0),
                start_date=str(r["start_date"]) if r.get("start_date") else None,
                end_date=str(r["end_date"]) if r.get("end_date") else None,
                source_id=safe_str(r.get("source_id")),
                evidence_span=safe_str(r.get("evidence_span")),
            )
        )
    return out


def score_evidence_strength(profile: Optional[StockProfile], facts: List[StockFact], direction_name: str) -> str:
    joined = "\n".join([
        normalize_text(profile.profile_text if profile else ""),
        normalize_text(profile.main_business_text if profile else ""),
        normalize_text(profile.product_text if profile else ""),
        normalize_text(profile.relation_text if profile else ""),
        normalize_text(profile.logic_text if profile else ""),
        "\n".join(normalize_text(f.fact_value) + "\n" + normalize_text(f.evidence_span) for f in facts),
    ])

    direction_tokens = set(tokenize(direction_name))
    hit_cnt = 0
    for t in direction_tokens:
        if t and t in joined:
            hit_cnt += 1

    primary_hits = sum(1 for f in facts if f.fact_type in PRIMARY_FACT_TYPES and any(tok in (f.fact_value + f.evidence_span) for tok in direction_tokens))
    satcom_hint_hits = sum(1 for t in SATCOM_HINT_TERMS if t in joined)

    if primary_hits >= 2 or (hit_cnt >= 3 and satcom_hint_hits >= 3):
        return "hard"
    if primary_hits >= 1 or hit_cnt >= 2 or satcom_hint_hits >= 2:
        return "medium"
    if facts or joined.strip():
        return "weak"
    return "missing"


def build_stock_evidence_record(gs: GoldStock, profile: Optional[StockProfile], facts: List[StockFact]) -> Dict[str, Any]:
    profile_texts = {
        "profile_text": normalize_text(profile.profile_text if profile else ""),
        "main_business_text": normalize_text(profile.main_business_text if profile else ""),
        "product_text": normalize_text(profile.product_text if profile else ""),
        "brand_text": normalize_text(profile.brand_text if profile else ""),
        "order_text": normalize_text(profile.order_text if profile else ""),
        "relation_text": normalize_text(profile.relation_text if profile else ""),
        "logic_text": normalize_text(profile.logic_text if profile else ""),
    }

    merged_text = "\n".join([v for v in profile_texts.values() if v] + [
        normalize_text(f.fact_value) + "\n" + normalize_text(f.evidence_span)
        for f in facts
    ])

    tokens = tokenize(merged_text)
    hint_terms = [t for t in tokens if t in SATCOM_HINT_TERMS]

    fact_type_counter = collections.Counter([f.fact_type for f in facts])
    evidence_strength = score_evidence_strength(profile, facts, gs.direction_name)

    return {
        "subject_key": gs.subject_key,
        "subject_name": gs.subject_name,
        "group_name": gs.group_name,
        "direction_name": gs.direction_name,
        "stock_id": gs.stock_id,
        "stock_name": gs.stock_name,
        "db_stock_found": profile is not None,
        "profile": asdict(profile) if profile else None,
        "facts": [asdict(f) for f in facts],
        "fact_type_distribution": dict(fact_type_counter),
        "hint_terms": uniq_keep_order(hint_terms),
        "evidence_strength": evidence_strength,
        "text_preview": merged_text[:2000],
    }


def build_direction_term_pack(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_direction: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in records:
        key = f"{r['group_name']}__{r['direction_name']}"
        by_direction[key].append(r)

    out: Dict[str, Any] = {}

    for key, items in by_direction.items():
        group_name, direction_name = key.split("__", 1)
        token_counter = collections.Counter()
        fact_type_counter = collections.Counter()
        stock_names = []
        hard_terms = collections.Counter()
        medium_terms = collections.Counter()

        for item in items:
            stock_names.append(item["stock_name"])
            profile = item.get("profile") or {}
            joined = "\n".join([
                safe_str(profile.get("profile_text")),
                safe_str(profile.get("main_business_text")),
                safe_str(profile.get("product_text")),
                safe_str(profile.get("relation_text")),
                safe_str(profile.get("logic_text")),
                safe_str(item.get("text_preview")),
            ])
            toks = tokenize(joined)
            token_counter.update(toks)

            for ft, cnt in (item.get("fact_type_distribution") or {}).items():
                fact_type_counter[ft] += cnt

            strength = item.get("evidence_strength")
            for t in toks:
                if strength == "hard":
                    hard_terms[t] += 1
                elif strength == "medium":
                    medium_terms[t] += 1

        # 去除方向名自身的重复词污染
        direction_tokens = set(tokenize(direction_name))
        for dt in direction_tokens:
            token_counter.pop(dt, None)
            hard_terms.pop(dt, None)
            medium_terms.pop(dt, None)

        aliases = []
        component_words = []
        must_terms = []
        strong_terms = []
        should_terms = []
        negative_terms = []

        # very strong
        for x in top_k_counter(hard_terms, k=12, min_count=2):
            term = x["term"]
            if term not in DEFAULT_STOPWORDS:
                must_terms.append(term)

        # strong
        for x in top_k_counter(token_counter, k=25, min_count=max(2, math.ceil(len(items) * 0.3))):
            term = x["term"]
            if term in must_terms:
                continue
            if term in SATCOM_HINT_TERMS:
                strong_terms.append(term)
            else:
                should_terms.append(term)

        # component words 偏实体/环节
        for t in must_terms + strong_terms + should_terms:
            if len(component_words) >= 15:
                break
            if any(k in t for k in ["卫星", "火箭", "天线", "测控", "导航", "芯片", "发射", "航天", "算力", "载荷", "遥感"]):
                component_words.append(t)

        # aliases 暂时用方向名 + 高频实体词近似生成
        aliases = uniq_keep_order([direction_name] + component_words[:5])

        out[key] = {
            "group_name": group_name,
            "direction_name": direction_name,
            "stock_count": len(items),
            "stocks": uniq_keep_order(stock_names),
            "fact_type_top": top_k_counter(fact_type_counter, k=10, min_count=1),
            "aliases": uniq_keep_order(aliases),
            "component_words": uniq_keep_order(component_words),
            "must_terms": uniq_keep_order(must_terms[:10]),
            "strong_terms": uniq_keep_order(strong_terms[:12]),
            "should_terms": uniq_keep_order(should_terms[:15]),
            "weak_terms": [],
            "negative_terms": negative_terms,
        }

    return out


def build_gap_report(records: List[Dict[str, Any]], direction_term_pack: Dict[str, Any]) -> Dict[str, Any]:
    missing_profiles = []
    missing_facts = []
    weak_evidence = []
    direction_stats = collections.defaultdict(lambda: {
        "stock_count": 0,
        "hard": 0,
        "medium": 0,
        "weak": 0,
        "missing": 0,
    })

    for r in records:
        key = f"{r['group_name']}__{r['direction_name']}"
        direction_stats[key]["stock_count"] += 1
        direction_stats[key][r["evidence_strength"]] += 1

        if not r["db_stock_found"]:
            missing_profiles.append({
                "direction_name": r["direction_name"],
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"],
            })

        if len(r.get("facts") or []) == 0:
            missing_facts.append({
                "direction_name": r["direction_name"],
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"],
            })

        if r["evidence_strength"] in {"weak", "missing"}:
            weak_evidence.append({
                "group_name": r["group_name"],
                "direction_name": r["direction_name"],
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"],
                "evidence_strength": r["evidence_strength"],
                "hint_terms": r.get("hint_terms") or [],
            })

    weak_directions = []
    for key, stat in direction_stats.items():
        pack = direction_term_pack.get(key, {})
        weak_directions.append({
            "group_name": pack.get("group_name"),
            "direction_name": pack.get("direction_name"),
            "stock_count": stat["stock_count"],
            "hard_count": stat["hard"],
            "medium_count": stat["medium"],
            "weak_count": stat["weak"],
            "missing_count": stat["missing"],
            "must_terms": pack.get("must_terms") or [],
            "strong_terms": pack.get("strong_terms") or [],
            "should_terms": pack.get("should_terms") or [],
        })

    weak_directions.sort(key=lambda x: (
        -(x["weak_count"] + x["missing_count"]),
        x["direction_name"] or ""
    ))

    return {
        "missing_profiles": missing_profiles,
        "missing_facts": missing_facts,
        "weak_evidence_stocks": weak_evidence,
        "direction_stats": weak_directions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold 股票池反查证据脚本")
    parser.add_argument("--gold-json", required=True, help="gold 股票池 JSON")
    parser.add_argument("--db-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    gold_obj = load_json(args.gold_json)
    gold_stocks = parse_gold_pool(gold_obj)

    gold_stock_ids = uniq_keep_order([x.stock_id for x in gold_stocks if x.stock_id])
    gold_stock_names = uniq_keep_order([x.stock_name for x in gold_stocks if x.stock_name])

    conn = psycopg2.connect(args.db_dsn)
    try:
        profile_by_id = fetch_profiles_by_ids(conn, gold_stock_ids)
        profile_by_name = fetch_profiles_by_names(conn, gold_stock_names)
        facts_by_id = fetch_facts_by_ids(conn, list(profile_by_id.keys()) if profile_by_id else gold_stock_ids)
    finally:
        conn.close()

    records = []
    for gs in gold_stocks:
        profile = None
        facts: List[StockFact] = []

        if gs.stock_id and gs.stock_id in profile_by_id:
            profile = profile_by_id[gs.stock_id]
        elif gs.stock_name and gs.stock_name in profile_by_name:
            profile = profile_by_name[gs.stock_name]
            if not gs.stock_id:
                gs.stock_id = profile.stock_id

        if gs.stock_id and gs.stock_id in facts_by_id:
            facts = facts_by_id[gs.stock_id]

        record = build_stock_evidence_record(gs, profile, facts)
        records.append(record)

    direction_term_pack = build_direction_term_pack(records)
    gap_report = build_gap_report(records, direction_term_pack)

    dump_json(
        {
            "subject_key": gold_obj.get("subject_key"),
            "subject_name": gold_obj.get("subject_name"),
            "record_count": len(records),
            "records": records,
        },
        os.path.join(args.out_dir, "gold_evidence_detail.json"),
    )

    dump_json(
        {
            "subject_key": gold_obj.get("subject_key"),
            "subject_name": gold_obj.get("subject_name"),
            "direction_term_pack": direction_term_pack,
        },
        os.path.join(args.out_dir, "gold_direction_term_pack.json"),
    )

    dump_json(
        {
            "subject_key": gold_obj.get("subject_key"),
            "subject_name": gold_obj.get("subject_name"),
            "gap_report": gap_report,
        },
        os.path.join(args.out_dir, "gold_gap_report.json"),
    )

    print("[DONE] wrote:")
    print(" -", os.path.join(args.out_dir, "gold_evidence_detail.json"))
    print(" -", os.path.join(args.out_dir, "gold_direction_term_pack.json"))
    print(" -", os.path.join(args.out_dir, "gold_gap_report.json"))


if __name__ == "__main__":
    main()