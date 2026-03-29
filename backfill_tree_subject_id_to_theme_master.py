#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
给 theme_master.tags 批量回填 tree_subject_id（L1 subject_id）

原则：
- 不推翻现有架构
- 使用现有 financial_categories + theme_master 的层级关系
- 对每个 jyhf 叶子题材，根据 category_path / category1_code 回填 tree_subject_id
- tree_subject_id = L1 的 subject_id

运行：
单题材测试：
python backfill_tree_subject_id_to_theme_master.py --subject 9024302

全量：
python backfill_tree_subject_id_to_theme_master.py
"""

import os
import sys
import json
import argparse
import asyncio
import logging
from typing import Dict, Any, Optional, List

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PREFIX = "JYHF_"


# =========================
# DB Config
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
# Helpers
# =========================
def code_to_subject_id(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = str(code).strip()
    if code.startswith(PREFIX):
        return code[len(PREFIX):]
    return None


# =========================
# DB Reads
# =========================
async def fetch_theme_master_rows(conn, subject: Optional[str] = None) -> List[Dict[str, Any]]:
    if subject:
        rows = await conn.fetch("""
            SELECT id, code, name, source_id, tags, category1_code, category2_code, category_path
            FROM theme_master
            WHERE source_system = 'jyhf'
              AND (source_id = $1 OR code = $2)
        """, str(subject), f"{PREFIX}{subject}")
    else:
        rows = await conn.fetch("""
            SELECT id, code, name, source_id, tags, category1_code, category2_code, category_path
            FROM theme_master
            WHERE source_system = 'jyhf'
        """)
    return [dict(r) for r in rows]


async def fetch_financial_categories_rows(conn) -> List[Dict[str, Any]]:
    rows = await conn.fetch("""
        SELECT category_code, source_id, category_level, parent_code, full_path
        FROM financial_categories
        WHERE source_system = 'jyhf'
    """)
    return [dict(r) for r in rows]


# =========================
# Core Logic
# =========================
def build_category_index(fc_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(r["category_code"]): r for r in fc_rows if r.get("category_code")}


def infer_tree_subject_id(theme_row: Dict[str, Any], fc_idx: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """
    tree_subject_id = L1 的 subject_id
    优先级：
    1. category_path[0]
    2. category1_code
    """
    category_path = theme_row.get("category_path") or []
    category1_code = theme_row.get("category1_code")

    l1_code = None
    if isinstance(category_path, list) and len(category_path) >= 1:
        l1_code = category_path[0]
    elif category1_code:
        l1_code = category1_code

    if not l1_code:
        return None

    l1_row = fc_idx.get(str(l1_code))
    if l1_row and l1_row.get("source_id") is not None:
        return str(l1_row["source_id"])

    return code_to_subject_id(l1_code)


async def update_theme_master_tags(conn, row_id: int, tags_obj: Dict[str, Any]):
    tags_json = json.dumps(tags_obj, ensure_ascii=False)
    await conn.execute("""
        UPDATE theme_master
        SET tags = $2::jsonb,
            updated_at = NOW()
        WHERE id = $1
    """, row_id, tags_json)


# =========================
# Main
# =========================
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", type=str, help="仅测试一个叶子题材 subject_id")
    args = ap.parse_args()

    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            theme_rows = await fetch_theme_master_rows(conn, args.subject)
            fc_rows = await fetch_financial_categories_rows(conn)
            fc_idx = build_category_index(fc_rows)

            logger.info(f"读取 theme_master(jyhf): {len(theme_rows)}")
            logger.info(f"读取 financial_categories(jyhf): {len(fc_rows)}")

            updated = 0
            skipped_no_l1 = 0
            skipped_same = 0

            for row in theme_rows:
                tree_subject_id = infer_tree_subject_id(row, fc_idx)
                if not tree_subject_id:
                    skipped_no_l1 += 1
                    continue

                tags = row.get("tags") or {}
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = {}
                if not isinstance(tags, dict):
                    tags = {}

                current = str(tags.get("tree_subject_id") or "").strip()
                if current == tree_subject_id:
                    skipped_same += 1
                    continue

                tags["tree_subject_id"] = tree_subject_id
                await update_theme_master_tags(conn, row["id"], tags)
                updated += 1

            stats = {
                "updated": updated,
                "skipped_no_l1": skipped_no_l1,
                "skipped_same": skipped_same,
                "total": len(theme_rows),
            }
            logger.info("==== 回填统计 ====")
            logger.info(json.dumps(stats, ensure_ascii=False, indent=2))

    finally:
        await manager.disconnect()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())