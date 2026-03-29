#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
import_jyhf_gate_profile_v2.py

优化版本：
- 并发读取 gate
- gate schema 校验
- 批量 upsert
- terms 数量限制
- tsvector 搜索索引
- 导入进度条
- 导入日志
"""

import os
import sys
import json
import argparse
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_STRONG = 20
MAX_WEAK = 40
MAX_NEG = 20


# =========================
# DB config
# =========================
def get_postgres_config():
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=10
    )


# =========================
# utils
# =========================
def read_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def parse_optional_datetime(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except Exception:
        return None


# =========================
# gate validation
# =========================
def validate_gate(gate: Dict[str, Any]) -> bool:
    if not isinstance(gate, dict):
        return False

    if not isinstance(gate.get("must"), list):
        return False

    if not isinstance(gate.get("should"), list):
        return False

    if not isinstance(gate.get("not"), list):
        return False

    if not gate.get("strategy_type"):
        return False

    return True


# =========================
# text utils
# =========================
def dedup_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = str(x).strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def normalize_terms(items: List[str]) -> List[str]:
    return dedup_keep_order(items)


# =========================
# gate -> profile
# =========================
def flatten_dimension_terms(dimensions):
    out = []
    if not isinstance(dimensions, dict):
        return out

    for v in dimensions.values():
        if isinstance(v, list):
            out.extend(v)

    return out


def build_search_profile(subject_name, subject_desc, gate):

    concept = gate.get("concept", "")
    semantic_type = gate.get("semantic_type", "")
    strategy_type = gate.get("strategy_type", "")

    dimensions = gate.get("dimensions", {})

    must = gate.get("must", [])
    should = gate.get("should", [])
    not_terms = gate.get("not", [])

    dim_terms = flatten_dimension_terms(dimensions)

    strong_terms = normalize_terms(must + ([concept] if concept else []))[:MAX_STRONG]

    weak_terms = normalize_terms(should + dim_terms)[:MAX_WEAK]

    negative_terms = normalize_terms(not_terms)[:MAX_NEG]

    parts = [
        subject_name,
        subject_desc,
        concept,
        semantic_type,
        strategy_type,
        *strong_terms,
        *weak_terms
    ]

    search_text = " ".join(dedup_keep_order(parts))

    return {
        "concept": concept,
        "semantic_type": semantic_type,
        "strategy_type": strategy_type,
        "dimensions": dimensions,
        "strong_terms": strong_terms,
        "weak_terms": weak_terms,
        "negative_terms": negative_terms,
        "search_text": search_text
    }


# =========================
# schema
# =========================
async def ensure_schema(conn):

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS theme_gate_profile (
        subject_key varchar(80) PRIMARY KEY,
        source_system varchar(50),

        concept text,
        semantic_type varchar(80),
        strategy_type varchar(30),

        ontology_json jsonb,
        gate_json jsonb,

        must_terms jsonb,
        should_terms jsonb,
        not_terms jsonb,

        strong_terms jsonb,
        weak_terms jsonb,
        negative_terms jsonb,

        search_text text,
        search_vector tsvector,

        quality varchar(20),
        generated_at timestamp,

        created_at timestamp default now(),
        updated_at timestamp default now()
    )
    """)

    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_theme_gate_profile_search_vector
    ON theme_gate_profile
    USING GIN(search_vector)
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS gate_import_log(
        id SERIAL PRIMARY KEY,
        subject_key varchar(80),
        action varchar(20),
        quality varchar(20),
        imported_at timestamp default now()
    )
    """)


# =========================
# load gate files
# =========================
def load_gate_files(subject_ids, gate_dir):

    paths = [gate_dir / f"{sid}_gate.json" for sid in subject_ids]

    def load(path):
        return path.stem.replace("_gate", ""), read_json(path)

    results = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        for sid, gate in ex.map(load, paths):
            if gate:
                results[sid] = gate

    return results


# =========================
# subject list
# =========================
def load_subject_ids(path):
    rows = read_jsonl(path)

    ids = []
    for r in rows:
        sid = r.get("subjectId") or r.get("subject_id") or r.get("id")
        if sid:
            ids.append(str(sid))

    return ids


# =========================
# main
# =========================
async def main():

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="theme_data_complete")
    ap.add_argument("--gate-dir", default="subject_gates")
    ap.add_argument("--subject", type=str)
    args = ap.parse_args()

    data_root = Path(args.data_root)
    gate_dir = Path(args.gate_dir)

    subject_list_file = data_root / "lists" / "full_theme_list.jsonl"

    subject_ids = load_subject_ids(subject_list_file)

    if args.subject:
        subject_ids = [args.subject]

    logger.info(f"读取 subject 数: {len(subject_ids)}")

    logger.info("并发加载 gate 文件")

    gate_map = load_gate_files(subject_ids, gate_dir)

    logger.info(f"发现 gate 文件: {len(gate_map)}")

    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)

    await manager.connect()

    try:

        async with manager.pool.acquire() as conn:

            await ensure_schema(conn)

            rows = []

            for sid, gate in tqdm(gate_map.items(), desc="处理 gate"):

                if not validate_gate(gate):
                    continue

                subject_name = gate.get("concept", "")
                subject_desc = ""

                profile = build_search_profile(subject_name, subject_desc, gate)

                ontology_json = json.dumps({
                    "concept": profile["concept"],
                    "semantic_type": profile["semantic_type"],
                    "strategy_type": profile["strategy_type"],
                    "dimensions": profile["dimensions"]
                }, ensure_ascii=False)

                gate_json = json.dumps(gate, ensure_ascii=False)

                must_terms = json.dumps(gate.get("must", []), ensure_ascii=False)
                should_terms = json.dumps(gate.get("should", []), ensure_ascii=False)
                not_terms = json.dumps(gate.get("not", []), ensure_ascii=False)

                strong_terms = json.dumps(profile["strong_terms"], ensure_ascii=False)
                weak_terms = json.dumps(profile["weak_terms"], ensure_ascii=False)
                negative_terms = json.dumps(profile["negative_terms"], ensure_ascii=False)

                generated_at = parse_optional_datetime(gate.get("generated_at"))

                rows.append((
                    sid,
                    profile["concept"],
                    profile["semantic_type"],
                    profile["strategy_type"],
                    ontology_json,
                    gate_json,
                    must_terms,
                    should_terms,
                    not_terms,
                    strong_terms,
                    weak_terms,
                    negative_terms,
                    profile["search_text"],
                    gate.get("quality", "unknown"),
                    generated_at
                ))

            logger.info(f"准备写入 {len(rows)} 条")

            await conn.executemany("""
            INSERT INTO theme_gate_profile(
                subject_key,source_system,
                concept,semantic_type,strategy_type,
                ontology_json,gate_json,
                must_terms,should_terms,not_terms,
                strong_terms,weak_terms,negative_terms,
                search_text,quality,generated_at,
                search_vector,
                created_at,updated_at
            )
            VALUES(
                $1,'jyhf',
                $2,$3,$4,
                $5::jsonb,$6::jsonb,
                $7::jsonb,$8::jsonb,$9::jsonb,
                $10::jsonb,$11::jsonb,$12::jsonb,
                $13,$14,$15,
                to_tsvector('simple',$13),
                NOW(),NOW()
            )
            ON CONFLICT(subject_key)
            DO UPDATE SET
                concept=EXCLUDED.concept,
                semantic_type=EXCLUDED.semantic_type,
                strategy_type=EXCLUDED.strategy_type,
                ontology_json=EXCLUDED.ontology_json,
                gate_json=EXCLUDED.gate_json,
                must_terms=EXCLUDED.must_terms,
                should_terms=EXCLUDED.should_terms,
                not_terms=EXCLUDED.not_terms,
                strong_terms=EXCLUDED.strong_terms,
                weak_terms=EXCLUDED.weak_terms,
                negative_terms=EXCLUDED.negative_terms,
                search_text=EXCLUDED.search_text,
                search_vector=EXCLUDED.search_vector,
                quality=EXCLUDED.quality,
                updated_at=NOW()
            """, rows)

            logger.info("gate 导入完成")

    finally:
        await manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())