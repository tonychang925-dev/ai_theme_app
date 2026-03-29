#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
将单个久赢恒丰题材的 detail / gate / knowledge jsonl 落库到本地 PostgreSQL

落库目标：
1. subject_detail                -> 原始 detail_html + reason_short
2. theme_gate_profile            -> gate / ontology / search profile
3. theme_knowledge_block         -> core / related / signal / event blocks

先测试单题材：
    python import_single_subject_knowledge.py --subject 9063417

测试通过后可批量：
    python import_single_subject_knowledge.py --list-file full_theme_list.jsonl --limit 20
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PREFIX = "JYHF_"


# =========================
# 数据库配置
# =========================
def get_postgres_config():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
    database = os.getenv("POSTGRES_DATABASE", "stock_data_test")

    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=host,
        postgres_port=port,
        postgres_database=database,
        postgres_username=user,
        postgres_password=password,
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=10
    )


# =========================
# 文件读取
# =========================
def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
    return rows


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# =========================
# 辅助函数
# =========================
def dedup_keep_order(items: List[str]) -> List[str]:
    out = []
    seen = set()
    for x in items:
        x = str(x or "").strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def normalize_terms(items: List[str], max_len: int = 24) -> List[str]:
    cleaned = []
    for x in dedup_keep_order(items):
        if len(x) > max_len:
            continue
        cleaned.append(x)
    return cleaned


def flatten_dimension_terms(dimensions: Dict[str, Any]) -> List[str]:
    out = []
    if not isinstance(dimensions, dict):
        return out
    for _, vals in dimensions.items():
        if isinstance(vals, list):
            out.extend([str(v).strip() for v in vals if str(v).strip()])
    return out


def build_search_profile(
    theme_name: str,
    theme_description: str,
    gate_json: Dict[str, Any]
) -> Dict[str, Any]:
    """
    以 gate 为唯一真源，派生：
    - strong_terms
    - weak_terms
    - negative_terms
    - search_text
    """
    concept = str(gate_json.get("concept", "") or "").strip()
    semantic_type = str(gate_json.get("semantic_type", "") or "").strip()
    strategy_type = str(gate_json.get("strategy_type", "") or "").strip()
    dimensions = gate_json.get("dimensions", {}) or {}

    must_terms = [str(x).strip() for x in gate_json.get("must", []) or []]
    should_terms = [str(x).strip() for x in gate_json.get("should", []) or []]
    not_terms = [str(x).strip() for x in gate_json.get("not", []) or []]
    dimension_terms = flatten_dimension_terms(dimensions)

    # 强词：must 为主 + concept
    strong_terms = normalize_terms(
        must_terms + ([concept] if concept else []),
        max_len=24
    )

    # 弱词：should + dimensions
    weak_terms = normalize_terms(
        should_terms + dimension_terms,
        max_len=24
    )
    strong_set = set(strong_terms)
    weak_terms = [x for x in weak_terms if x not in strong_set]

    # 负词：not
    negative_terms = normalize_terms(not_terms, max_len=24)

    # 聚合 search_text
    parts = []
    for chunk in [
        theme_name,
        theme_description,
        concept,
        semantic_type,
        strategy_type,
        *strong_terms,
        *weak_terms,
    ]:
        chunk = str(chunk or "").strip()
        if chunk:
            parts.append(chunk)

    search_text = " ".join(dedup_keep_order(parts))

    return {
        "concept": concept,
        "semantic_type": semantic_type,
        "strategy_type": strategy_type,
        "strong_terms": strong_terms,
        "weak_terms": weak_terms,
        "negative_terms": negative_terms,
        "search_text": search_text,
        "dimensions": dimensions,
    }


def extract_detail_record(subject_id: str, detail_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从 details jsonl 中提取当前题材记录
    """
    sid = str(subject_id)

    def pick_from_obj(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        id_fields = ["subjectId", "subject_id", "bizKey", "biz_key", "id", "subjectID"]
        val = None
        for f in id_fields:
            if obj.get(f) is not None:
                val = str(obj.get(f))
                break
        if val != sid:
            return None

        return {
            "subject_key": sid,
            "name": obj.get("name") or obj.get("subjectName") or sid,
            "reason_short": obj.get("reason") or "",
            "detail_html": obj.get("detail") or obj.get("detail_html") or obj.get("content") or "",
            "source_type": obj.get("type"),
            "source_updated_at": obj.get("updateTime") or obj.get("createTime"),
        }

    for row in detail_rows:
        if not isinstance(row, dict):
            continue
        # 一级对象
        x = pick_from_obj(row)
        if x:
            return x
        # row.data
        if isinstance(row.get("data"), dict):
            x = pick_from_obj(row["data"])
            if x:
                return x

    return {
        "subject_key": sid,
        "name": sid,
        "reason_short": "",
        "detail_html": "",
        "source_type": None,
        "source_updated_at": None,
    }


def convert_block_record(subject_id: str, theme_id: int, block_kind: str, row: Dict[str, Any]) -> Optional[Tuple]:
    """
    将一条知识块 json 转为 theme_knowledge_block 插入 tuple
    """
    if not isinstance(row, dict):
        return None

    block_uid = str(
        row.get("uid")
        or row.get("chunk_id")
        or row.get("source_id")
        or ""
    ).strip()

    title = str(row.get("title") or row.get("context_heading") or "").strip()
    text = str(row.get("text") or "").strip()
    role = str(row.get("role") or "").strip()
    stability = str(row.get("stability") or "").strip()
    source = str(row.get("source") or "").strip()
    source_id = str(row.get("source_id") or "").strip()
    date_hint = str(row.get("date_hint") or "").strip()
    global_order = row.get("global_order")
    order_no = row.get("order")
    raw_json = json.dumps(row, ensure_ascii=False)

    return (
        theme_id,
        str(subject_id),
        block_uid,
        block_kind,
        title,
        text,
        role,
        stability,
        source,
        source_id,
        date_hint,
        global_order,
        order_no,
        raw_json,
    )


# =========================
# 数据库 DDL
# =========================
async def ensure_schema(conn):
    """
    在现有表基础上，新增少量重要表与字段
    """
    # subject_detail 增量字段
    await conn.execute("""
        ALTER TABLE subject_detail
        ADD COLUMN IF NOT EXISTS reason_short text
    """)
    await conn.execute("""
        ALTER TABLE subject_detail
        ADD COLUMN IF NOT EXISTS is_current boolean DEFAULT true
    """)

    # 题材 gate + search profile
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS theme_gate_profile (
            theme_id              integer PRIMARY KEY REFERENCES theme_master(id) ON DELETE CASCADE,
            subject_key           varchar(80),
            concept               text,
            semantic_type         varchar(80),
            strategy_type         varchar(30),
            ontology_json         jsonb NOT NULL DEFAULT '{}'::jsonb,
            gate_json             jsonb NOT NULL DEFAULT '{}'::jsonb,
            must_terms            jsonb NOT NULL DEFAULT '[]'::jsonb,
            should_terms          jsonb NOT NULL DEFAULT '[]'::jsonb,
            not_terms             jsonb NOT NULL DEFAULT '[]'::jsonb,
            strong_terms          jsonb NOT NULL DEFAULT '[]'::jsonb,
            weak_terms            jsonb NOT NULL DEFAULT '[]'::jsonb,
            negative_terms        jsonb NOT NULL DEFAULT '[]'::jsonb,
            search_text           text,
            quality               varchar(20),
            gate_version          integer DEFAULT 1,
            generated_at          timestamp without time zone,
            created_at            timestamp without time zone DEFAULT now(),
            updated_at            timestamp without time zone DEFAULT now()
        )
    """)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_gate_profile_subject_key
        ON theme_gate_profile(subject_key)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_gate_profile_strategy_type
        ON theme_gate_profile(strategy_type)
    """)

    # 知识块表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS theme_knowledge_block (
            id                   bigserial PRIMARY KEY,
            theme_id             integer NOT NULL REFERENCES theme_master(id) ON DELETE CASCADE,
            subject_key          varchar(80) NOT NULL,
            block_uid            varchar(120),
            block_kind           varchar(30) NOT NULL,    -- core / related / signal / event
            title                text,
            content_text         text,
            role                 varchar(50),
            stability            varchar(20),
            source               varchar(50),
            source_id            varchar(120),
            date_hint            varchar(80),
            global_order         integer,
            order_no             integer,
            raw_json             jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at           timestamp without time zone DEFAULT now(),
            updated_at           timestamp without time zone DEFAULT now(),
            UNIQUE(theme_id, block_uid, block_kind)
        )
    """)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_knowledge_block_theme_id
        ON theme_knowledge_block(theme_id)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_knowledge_block_kind
        ON theme_knowledge_block(block_kind)
    """)

    logger.info("schema 检查/创建完成")


# =========================
# 查询 theme_master
# =========================
async def find_theme_record(conn, subject_id: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow("""
        SELECT id, name, code, description, source_system, source_id
        FROM theme_master
        WHERE source_system = 'jyhf' AND source_id = $1
        LIMIT 1
    """, str(subject_id))
    if row:
        return dict(row)

    row = await conn.fetchrow("""
        SELECT id, name, code, description, source_system, source_id
        FROM theme_master
        WHERE code = $1
        LIMIT 1
    """, f"{PREFIX}{subject_id}")
    if row:
        return dict(row)

    return None


# =========================
# subject_detail 落库
# =========================
async def upsert_subject_detail(conn, subject_key: str, detail_html: str, reason_short: str):
    await conn.execute("""
        INSERT INTO subject_detail (
            subject_key, detail_html, reason_short, detail_version, is_current, created_at, updated_at
        ) VALUES (
            $1, $2, $3, 1, true, NOW(), NOW()
        )
        ON CONFLICT (subject_key) DO UPDATE SET
            detail_html = EXCLUDED.detail_html,
            reason_short = EXCLUDED.reason_short,
            is_current = true,
            updated_at = NOW()
    """, subject_key, detail_html or "", reason_short or "")


# =========================
# gate_profile 落库
# =========================
async def upsert_theme_gate_profile(
    conn,
    theme_id: int,
    subject_key: str,
    gate_json: Dict[str, Any],
    profile: Dict[str, Any],
):
    must_terms = json.dumps(gate_json.get("must", []) or [], ensure_ascii=False)
    should_terms = json.dumps(gate_json.get("should", []) or [], ensure_ascii=False)
    not_terms = json.dumps(gate_json.get("not", []) or [], ensure_ascii=False)

    ontology_json = json.dumps({
        "concept": profile.get("concept"),
        "semantic_type": profile.get("semantic_type"),
        "strategy_type": profile.get("strategy_type"),
        "dimensions": profile.get("dimensions", {}),
    }, ensure_ascii=False)

    gate_json_str = json.dumps(gate_json, ensure_ascii=False)
    strong_terms = json.dumps(profile.get("strong_terms", []), ensure_ascii=False)
    weak_terms = json.dumps(profile.get("weak_terms", []), ensure_ascii=False)
    negative_terms = json.dumps(profile.get("negative_terms", []), ensure_ascii=False)

    generated_at = gate_json.get("generated_at")

    await conn.execute("""
        INSERT INTO theme_gate_profile (
            theme_id, subject_key, concept, semantic_type, strategy_type,
            ontology_json, gate_json,
            must_terms, should_terms, not_terms,
            strong_terms, weak_terms, negative_terms,
            search_text, quality, gate_version, generated_at,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6::jsonb, $7::jsonb,
            $8::jsonb, $9::jsonb, $10::jsonb,
            $11::jsonb, $12::jsonb, $13::jsonb,
            $14, $15, 1, $16,
            NOW(), NOW()
        )
        ON CONFLICT (theme_id) DO UPDATE SET
            subject_key    = EXCLUDED.subject_key,
            concept        = EXCLUDED.concept,
            semantic_type  = EXCLUDED.semantic_type,
            strategy_type  = EXCLUDED.strategy_type,
            ontology_json  = EXCLUDED.ontology_json,
            gate_json      = EXCLUDED.gate_json,
            must_terms     = EXCLUDED.must_terms,
            should_terms   = EXCLUDED.should_terms,
            not_terms      = EXCLUDED.not_terms,
            strong_terms   = EXCLUDED.strong_terms,
            weak_terms     = EXCLUDED.weak_terms,
            negative_terms = EXCLUDED.negative_terms,
            search_text    = EXCLUDED.search_text,
            quality        = EXCLUDED.quality,
            gate_version   = EXCLUDED.gate_version,
            generated_at   = EXCLUDED.generated_at,
            updated_at     = NOW()
    """,
    theme_id,
    subject_key,
    profile.get("concept"),
    profile.get("semantic_type"),
    profile.get("strategy_type"),
    ontology_json,
    gate_json_str,
    must_terms,
    should_terms,
    not_terms,
    strong_terms,
    weak_terms,
    negative_terms,
    profile.get("search_text"),
    gate_json.get("quality"),
    generated_at,
    )


# =========================
# 知识块落库
# =========================
async def replace_theme_knowledge_blocks(conn, theme_id: int, subject_id: str, data_dir: Path):
    """
    删除该题材已有知识块后重新导入
    """
    await conn.execute("""
        DELETE FROM theme_knowledge_block WHERE theme_id = $1
    """, theme_id)

    block_specs = [
        ("core", data_dir / "knowledge_core" / f"{subject_id}_knowledge_core.jsonl"),
        ("related", data_dir / "knowledge_related" / f"{subject_id}_knowledge_related.jsonl"),
        ("signal", data_dir / "knowledge_signal" / f"{subject_id}_knowledge_signal.jsonl"),
        ("event", data_dir / "event_feed" / f"{subject_id}_events.jsonl"),
    ]

    insert_rows = []
    for block_kind, path in block_specs:
        rows = read_jsonl(path)
        for row in rows:
            rec = convert_block_record(subject_id, theme_id, block_kind, row)
            if rec:
                insert_rows.append(rec)

    if not insert_rows:
        logger.warning(f"题材 {subject_id} 没有可导入的知识块")
        return

    await conn.executemany("""
        INSERT INTO theme_knowledge_block (
            theme_id, subject_key, block_uid, block_kind,
            title, content_text, role, stability, source, source_id,
            date_hint, global_order, order_no, raw_json,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14::jsonb,
            NOW(), NOW()
        )
    """, insert_rows)

    logger.info(f"题材 {subject_id} 导入知识块 {len(insert_rows)} 条")


# =========================
# 单题材处理
# =========================
async def process_subject(
    conn,
    subject_id: str,
    data_dir: Path,
    gate_dir: Path,
):
    logger.info(f"开始处理题材 {subject_id}")

    theme = await find_theme_record(conn, subject_id)
    if not theme:
        raise RuntimeError(f"theme_master 中找不到 subject_id={subject_id} 对应题材，请先确认已导入 theme_master")

    theme_id = theme["id"]
    theme_name = theme["name"]
    theme_desc = theme.get("description") or ""

    logger.info(f"题材映射成功: theme_id={theme_id}, name={theme_name}")

    # 1) detail
    detail_file = data_dir / "details" / f"{subject_id}_details.jsonl"
    detail_rows = read_jsonl(detail_file)
    detail_obj = extract_detail_record(subject_id, detail_rows)

    await upsert_subject_detail(
        conn=conn,
        subject_key=str(subject_id),
        detail_html=detail_obj.get("detail_html", ""),
        reason_short=detail_obj.get("reason_short", ""),
    )
    logger.info(f"subject_detail 已更新: {subject_id}")

    # 2) gate
    gate_file = gate_dir / f"{subject_id}_gate.json"
    if not gate_file.exists():
        raise RuntimeError(f"gate 文件不存在: {gate_file}")

    gate_json = read_json(gate_file)
    if not gate_json:
        raise RuntimeError(f"gate 文件为空或解析失败: {gate_file}")

    profile = build_search_profile(
        theme_name=theme_name,
        theme_description=theme_desc,
        gate_json=gate_json
    )

    await upsert_theme_gate_profile(
        conn=conn,
        theme_id=theme_id,
        subject_key=str(subject_id),
        gate_json=gate_json,
        profile=profile,
    )
    logger.info(f"theme_gate_profile 已更新: theme_id={theme_id}")

    # 3) 知识块
    await replace_theme_knowledge_blocks(
        conn=conn,
        theme_id=theme_id,
        subject_id=str(subject_id),
        data_dir=data_dir,
    )

    logger.info(f"题材 {subject_id} 处理完成")


# =========================
# 批量列表读取
# =========================
def load_subject_ids_from_list_file(path: Path) -> List[str]:
    if not path.exists():
        return []

    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                sid = obj.get("subjectId") or obj.get("subject_id") or obj.get("bizKey")
                if sid:
                    out.append(str(sid))
            except Exception:
                continue
    return out


# =========================
# main
# =========================
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", type=str, help="单题材 ID")
    ap.add_argument("--list-file", type=str, help="批量题材列表文件")
    ap.add_argument("--limit", type=int, default=0, help="批处理数量限制")
    ap.add_argument("--data-dir", default="theme_data_complete", help="数据目录")
    ap.add_argument("--gate-dir", default="subject_gates", help="gate 文件目录")
    args = ap.parse_args()

    if not args.subject and not args.list_file:
        raise SystemExit("请指定 --subject 或 --list-file")

    data_dir = Path(args.data_dir)
    gate_dir = Path(args.gate_dir)

    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            await ensure_schema(conn)

            if args.subject:
                await process_subject(conn, args.subject, data_dir, gate_dir)
                logger.info("单题材测试导入完成")
                return

            subject_ids = load_subject_ids_from_list_file(Path(args.list_file))
            if args.limit > 0:
                subject_ids = subject_ids[:args.limit]

            logger.info(f"批量处理题材数: {len(subject_ids)}")
            ok = 0
            fail = 0

            for sid in subject_ids:
                try:
                    await process_subject(conn, sid, data_dir, gate_dir)
                    ok += 1
                except Exception as e:
                    fail += 1
                    logger.exception(f"题材 {sid} 导入失败: {e}")

            logger.info(f"批处理完成: ok={ok}, fail={fail}")

    finally:
        await manager.disconnect()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())