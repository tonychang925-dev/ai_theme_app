#!/usr/bin/env python3
"""
从 subject_children_staging 反灌 subject_stock_map。

当前策略保持保守：
- 仅使用 children 快照中显式提供的 lead_stock_id / lead_stock_name
- 仅为 child_subject_key 建立直接 leader 映射
- 不对父节点做扩散推断
"""

import asyncio
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
    )


async def load_rows(manager: PostgresDatabaseManager) -> int:
    sql = """
    INSERT INTO subject_stock_map (
        subject_key,
        stock_id,
        name,
        pct_chg,
        sort,
        top,
        reason,
        remark,
        source_type,
        confidence,
        evidence_json
    )
    SELECT
        scs.child_subject_key AS subject_key,
        scs.lead_stock_id AS stock_id,
        COALESCE(scs.lead_stock_name, s.name) AS name,
        scs.pct_chg,
        1 AS sort,
        TRUE AS top,
        'derived from subject_children_staging lead stock' AS reason,
        scs.child_name AS remark,
        'jyhf_children' AS source_type,
        0.95 AS confidence,
        jsonb_build_object(
            'evidence_source', 'subject_children_staging',
            'parent_subject_key', scs.parent_subject_key,
            'child_subject_key', scs.child_subject_key,
            'child_name', scs.child_name,
            'lead_stock_id', scs.lead_stock_id,
            'lead_stock_name', scs.lead_stock_name,
            'stock_count', scs.stock_count,
            'pct_chg', scs.pct_chg,
            'source_type', scs.source_type
        ) AS evidence_json
    FROM (
        SELECT DISTINCT ON (child_subject_key, lead_stock_id)
            parent_subject_key,
            child_subject_key,
            child_name,
            lead_stock_id,
            lead_stock_name,
            pct_chg,
            stock_count,
            source_type
        FROM subject_children_staging
        WHERE lead_stock_id IS NOT NULL
          AND child_subject_key IS NOT NULL
        ORDER BY child_subject_key, lead_stock_id, depth ASC, sort ASC NULLS LAST
    ) scs
    LEFT JOIN stocks s
      ON s.stock_id = scs.lead_stock_id
    ON CONFLICT (subject_key, stock_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        pct_chg = EXCLUDED.pct_chg,
        sort = EXCLUDED.sort,
        top = EXCLUDED.top,
        reason = EXCLUDED.reason,
        remark = EXCLUDED.remark,
        source_type = EXCLUDED.source_type,
        confidence = EXCLUDED.confidence,
        evidence_json = EXCLUDED.evidence_json,
        updated_at = NOW()
    """
    async with manager.pool.acquire() as conn:
        result = await conn.execute(sql)
    try:
        return int(result.split()[-1])
    except Exception:
        return 0


async def main() -> int:
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        count = await load_rows(manager)
        print(f"[OK] loaded subject_stock_map from children rows={count}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
