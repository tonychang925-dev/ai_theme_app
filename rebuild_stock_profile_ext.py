#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from text2vec import SentenceModel


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


@dataclass
class StockFact:
    id: int
    stock_id: str
    fact_type: str
    fact_value: str
    source: str
    confidence: float
    start_date: Optional[str]
    end_date: Optional[str]
    source_id: str
    evidence_span: str


PRIMARY_TYPES = {
    "main_business",
    "product",
    "technology",
    "capacity",
    "market_share",
    "order_contract",
    "investment",
}

GROUP_MAP = {
    "main_business": "main_business",
    "product": "product",          # 后续再拆成 core / brand
    "technology": "product",
    "capacity": "product",
    "market_share": "product",
    "order_contract": "order",
    "investment": "order",
    "customer_supplier": "relation",
    "customer": "relation",
    "benefit_logic": "logic",
    "industry_role": "logic",
    "research_report": "logic",
    "media_claim": "logic",
}

GROUP_LABELS = {
    "main_business_text": "主营业务",
    "product_text": "核心产品与技术",
    "order_text": "订单/合作/投资",
    "logic_text": "受益逻辑与行业角色",
}

# 这些词更像“可进入主 embedding 的业务/产品/技术语义”
PRODUCT_CORE_HINTS = [
    "服务", "平台", "方案", "系统", "设备", "技术", "产品", "业务", "中心",
    "解决", "模组", "芯片", "材料", "软件", "硬件", "冷库", "高标库",
    "物流", "公寓", "住房", "空间", "物业", "开发", "管理", "AI", "IoT", "BPaaS"
]


def ensure_pgvector_extension(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()


def ensure_stock_profile_ext_table(conn, vector_dim: int) -> None:
    """
    自动创建并补齐 stock_profile_ext 字段。
    brand_text / relation_text 保留，但不进入主 embedding。
    """
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS stock_profile_ext (
        stock_id varchar(20) PRIMARY KEY,
        stock_name varchar(100) NOT NULL,

        profile_text text NOT NULL,
        main_business_text text,
        product_text text,
        brand_text text,
        order_text text,
        relation_text text,
        logic_text text,

        fact_count integer DEFAULT 0,
        primary_fact_count integer DEFAULT 0,

        evidence_json jsonb,

        embedding vector({vector_dim}),
        embedding_model varchar(100),
        embedding_updated_at timestamp,

        created_at timestamp DEFAULT now(),
        updated_at timestamp DEFAULT now()
    );
    """

    alter_sqls = [
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS main_business_text text;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS product_text text;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS brand_text text;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS order_text text;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS relation_text text;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS logic_text text;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS fact_count integer DEFAULT 0;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS primary_fact_count integer DEFAULT 0;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS evidence_json jsonb;",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS embedding_model varchar(100);",
        "ALTER TABLE stock_profile_ext ADD COLUMN IF NOT EXISTS embedding_updated_at timestamp;",
    ]

    idx_sqls = [
        "CREATE INDEX IF NOT EXISTS idx_stock_profile_name ON stock_profile_ext(stock_name);",
        "CREATE INDEX IF NOT EXISTS idx_stock_profile_updated_at ON stock_profile_ext(updated_at);",
        (
            "CREATE INDEX IF NOT EXISTS idx_stock_profile_embedding_cosine "
            "ON stock_profile_ext USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
        ),
    ]

    with conn.cursor() as cur:
        cur.execute(create_sql)
        for s in alter_sqls:
            cur.execute(s)
        for s in idx_sqls:
            cur.execute(s)

    conn.commit()


def fetch_stock_rows(conn, stock_id: Optional[str] = None) -> List[Tuple[str, str]]:
    sql = """
    SELECT stock_id, name
    FROM stocks
    """
    params: List[Any] = []
    if stock_id:
        sql += " WHERE stock_id = %s"
        params.append(stock_id)
    sql += " ORDER BY stock_id"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_stock_facts(conn, stock_id: str) -> List[StockFact]:
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
    WHERE stock_id = %s
    ORDER BY id
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_id,))
        rows = list(cur.fetchall())

    out: List[StockFact] = []
    for r in rows:
        out.append(
            StockFact(
                id=int(r["id"]),
                stock_id=safe_str(r["stock_id"]),
                fact_type=safe_str(r["fact_type"]),
                fact_value=safe_str(r["fact_value"]),
                source=safe_str(r.get("source")),
                confidence=safe_float(r.get("confidence"), 1.0),
                start_date=str(r["start_date"]) if r.get("start_date") else None,
                end_date=str(r["end_date"]) if r.get("end_date") else None,
                source_id=safe_str(r.get("source_id")),
                evidence_span=safe_str(r.get("evidence_span")),
            )
        )
    return out


def merge_fact_text(fact: StockFact) -> str:
    """
    单条 fact 转可读文本。
    优先保留 fact_value；如果 evidence_span 有补充信息，则附加进去。
    """
    fact_value = safe_str(fact.fact_value)
    evidence_span = safe_str(fact.evidence_span)

    if fact_value and evidence_span:
        if evidence_span == fact_value:
            return fact_value
        if fact_value in evidence_span:
            return evidence_span
        return f"{fact_value}（{evidence_span}）"

    return fact_value or evidence_span


def is_product_brand_like(fact_value: str, evidence_span: str) -> bool:
    """
    判断 product 类事实更像品牌/项目名，还是更像可进入主 embedding 的产品/技术/服务。

    目标：
    - 品牌/项目名（如 印象城 / 印象汇 / 万科广场 / 泊寓） -> brand_text
    - 产品/服务/技术能力（如 AIoT及BPaaS解决方案服务 / 冷库 / 高标库） -> product_text
    """
    v = safe_str(fact_value)
    e = safe_str(evidence_span)

    if not v:
        return False

    # 明显的“业务/技术/产品”提示词，优先判定为 core
    for kw in PRODUCT_CORE_HINTS:
        if kw.lower() in v.lower() or kw.lower() in e.lower():
            return False

    # 太短且没有上下文增强，通常更像品牌/项目名
    if len(v) <= 6 and (not e or e == v):
        return True

    # 长度不长，且 evidence_span 没有提供业务说明，也偏品牌名
    if len(v) <= 8 and e == v:
        return True

    return False


def build_group_texts(stock_name: str, facts: List[StockFact]) -> Tuple[Dict[str, str], Dict[str, List[int]]]:
    grouped_values: Dict[str, List[str]] = defaultdict(list)
    grouped_ids: Dict[str, List[int]] = defaultdict(list)

    product_core_values: List[str] = []
    product_core_ids: List[int] = []
    product_brand_values: List[str] = []
    product_brand_ids: List[int] = []

    for f in facts:
        group = GROUP_MAP.get(f.fact_type)
        if not group:
            continue

        merged_text = merge_fact_text(f)
        if not merged_text:
            continue

        # product 特殊拆分：核心产品/技术 vs 品牌/项目名
        if group == "product":
            if f.fact_type == "product" and is_product_brand_like(f.fact_value, f.evidence_span):
                product_brand_values.append(merged_text)
                product_brand_ids.append(f.id)
            else:
                product_core_values.append(merged_text)
                product_core_ids.append(f.id)
            continue

        grouped_values[group].append(merged_text)
        grouped_ids[group].append(f.id)

    group_texts = {
        "main_business_text": "；".join(unique_keep_order(grouped_values["main_business"][:8])),
        "product_text": "；".join(unique_keep_order(product_core_values[:10])),
        "brand_text": "；".join(unique_keep_order(product_brand_values[:10])),
        "order_text": "；".join(unique_keep_order(grouped_values["order"][:8])),
        "relation_text": "；".join(unique_keep_order(grouped_values["relation"][:8])),
        "logic_text": "；".join(unique_keep_order(grouped_values["logic"][:8])),
    }

    grouped_ids["product_core"] = product_core_ids
    grouped_ids["product_brand"] = product_brand_ids

    return group_texts, grouped_ids


def build_profile_text(stock_name: str, group_texts: Dict[str, str], include_order: bool = True) -> str:
    """
    主 embedding 文本：
    - 保留：主营业务 / 核心产品与技术 / 订单合作 / 逻辑角色
    - 移除：relation_text（关系噪声）
    - 移除：brand_text（品牌噪声）
    """
    parts = [f"股票: {stock_name}"]

    main_business_text = safe_str(group_texts.get("main_business_text"))
    product_text = safe_str(group_texts.get("product_text"))
    order_text = safe_str(group_texts.get("order_text"))
    logic_text = safe_str(group_texts.get("logic_text"))

    if main_business_text:
        parts.append(f"{GROUP_LABELS['main_business_text']}: {main_business_text}")
    if product_text:
        parts.append(f"{GROUP_LABELS['product_text']}: {product_text}")
    if include_order and order_text:
        parts.append(f"{GROUP_LABELS['order_text']}: {order_text}")
    if logic_text:
        parts.append(f"{GROUP_LABELS['logic_text']}: {logic_text}")

    return "\n".join(parts)


def build_evidence_json(
    facts: List[StockFact],
    grouped_ids: Dict[str, List[int]],
    group_texts: Dict[str, str],
) -> Dict[str, Any]:
    primary_fact_count = sum(1 for f in facts if f.fact_type in PRIMARY_TYPES)

    fact_preview = []
    for f in facts[:20]:
        fact_preview.append(
            {
                "fact_id": f.id,
                "fact_type": f.fact_type,
                "fact_value": f.fact_value,
                "source": f.source,
                "confidence": f.confidence,
                "source_id": f.source_id,
                "evidence_span": f.evidence_span,
            }
        )

    return {
        "version": "1.1",
        "fact_groups": {
            "main_business": grouped_ids.get("main_business", []),
            "product_core": grouped_ids.get("product_core", []),
            "product_brand": grouped_ids.get("product_brand", []),
            "order": grouped_ids.get("order", []),
            "relation": grouped_ids.get("relation", []),
            "logic": grouped_ids.get("logic", []),
        },
        "group_texts": {
            "main_business_text": group_texts.get("main_business_text", ""),
            "product_text": group_texts.get("product_text", ""),
            "brand_text": group_texts.get("brand_text", ""),
            "order_text": group_texts.get("order_text", ""),
            "relation_text": group_texts.get("relation_text", ""),
            "logic_text": group_texts.get("logic_text", ""),
        },
        "fact_count": len(facts),
        "primary_fact_count": primary_fact_count,
        "fact_preview": fact_preview,
    }


def upsert_stock_profile(
    conn,
    stock_id: str,
    stock_name: str,
    profile_text: str,
    group_texts: Dict[str, str],
    evidence_json: Dict[str, Any],
    embedding_vec: List[float],
    embedding_model: str,
) -> None:
    embedding_literal = vector_to_pgvector_literal(embedding_vec)

    sql = f"""
    INSERT INTO stock_profile_ext (
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
        embedding,
        embedding_model,
        embedding_updated_at,
        created_at,
        updated_at
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s,
        {embedding_literal},
        %s,
        now(),
        now(),
        now()
    )
    ON CONFLICT (stock_id) DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        profile_text = EXCLUDED.profile_text,
        main_business_text = EXCLUDED.main_business_text,
        product_text = EXCLUDED.product_text,
        brand_text = EXCLUDED.brand_text,
        order_text = EXCLUDED.order_text,
        relation_text = EXCLUDED.relation_text,
        logic_text = EXCLUDED.logic_text,
        fact_count = EXCLUDED.fact_count,
        primary_fact_count = EXCLUDED.primary_fact_count,
        evidence_json = EXCLUDED.evidence_json,
        embedding = EXCLUDED.embedding,
        embedding_model = EXCLUDED.embedding_model,
        embedding_updated_at = EXCLUDED.embedding_updated_at,
        updated_at = now()
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                stock_id,
                stock_name,
                profile_text,
                group_texts.get("main_business_text"),
                group_texts.get("product_text"),
                group_texts.get("brand_text"),
                group_texts.get("order_text"),
                group_texts.get("relation_text"),
                group_texts.get("logic_text"),
                evidence_json["fact_count"],
                evidence_json["primary_fact_count"],
                json.dumps(evidence_json, ensure_ascii=False),
                embedding_model,
            ),
        )


def rebuild_stock_profiles(
    db_dsn: str,
    model_name: str,
    stock_id: Optional[str] = None,
    limit: int = 0,
    commit_every: int = 100,
    include_order_in_profile: bool = True,
) -> None:
    model = SentenceModel(model_name)

    sample_vec = model.encode("股票画像测试")
    if hasattr(sample_vec, "tolist"):
        sample_vec = sample_vec.tolist()
    vector_dim = len(sample_vec)

    conn = psycopg2.connect(db_dsn)

    try:
        ensure_pgvector_extension(conn)
        ensure_stock_profile_ext_table(conn, vector_dim)

        stock_rows = fetch_stock_rows(conn, stock_id=stock_id)
        if limit > 0:
            stock_rows = stock_rows[:limit]

        total = len(stock_rows)
        done = 0

        for sid, sname in stock_rows:
            facts = fetch_stock_facts(conn, sid)
            if not facts:
                continue

            group_texts, grouped_ids = build_group_texts(sname, facts)
            profile_text = build_profile_text(
                stock_name=sname,
                group_texts=group_texts,
                include_order=include_order_in_profile,
            )
            evidence_json = build_evidence_json(
                facts=facts,
                grouped_ids=grouped_ids,
                group_texts=group_texts,
            )

            embedding_vec = model.encode(profile_text)
            if hasattr(embedding_vec, "tolist"):
                embedding_vec = embedding_vec.tolist()

            upsert_stock_profile(
                conn=conn,
                stock_id=sid,
                stock_name=sname,
                profile_text=profile_text,
                group_texts=group_texts,
                evidence_json=evidence_json,
                embedding_vec=embedding_vec,
                embedding_model=model_name,
            )

            done += 1
            if done % commit_every == 0:
                conn.commit()
                print(f"[INFO] processed={done}/{total}")

        conn.commit()
        print(f"[DONE] rebuilt stock_profile_ext rows: {done}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="从 stocks + stock_facts 聚合并回填 stock_profile_ext（优化版）")
    parser.add_argument("--db-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument(
        "--model-name",
        default="shibing624/text2vec-base-chinese",
        help="embedding 模型名",
    )
    parser.add_argument("--stock-id", default="", help="只重建指定股票，例如 000002")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少只股票")
    parser.add_argument("--commit-every", type=int, default=100, help="每多少只股票提交一次")
    parser.add_argument(
        "--exclude-order-in-profile",
        action="store_true",
        help="若指定，则订单/合作/投资文本也不进入主 embedding",
    )
    args = parser.parse_args()

    rebuild_stock_profiles(
        db_dsn=args.db_dsn,
        model_name=args.model_name,
        stock_id=args.stock_id or None,
        limit=args.limit,
        commit_every=args.commit_every,
        include_order_in_profile=not args.exclude_order_in_profile,
    )


if __name__ == "__main__":
    main()