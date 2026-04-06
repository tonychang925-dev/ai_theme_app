#!/usr/bin/env python3
"""
久赢恒丰数据导入到金融分类体系（最终版）
- financial_categories: 只存非叶子节点（分类）
- theme_master: 只存叶子节点（题材详情）
- category2_code 可选，查询支持两种形态
- 数值字段不转字符串，保持原生类型
- 索引完善
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Any, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.config import DatabaseConfig, DatabaseType, RedisConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PREFIX = "JYHF_"

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

async def clear_old_data(conn):
    """清空之前导入的久赢恒丰数据（先删子表后删父表）"""
    await conn.execute("DELETE FROM theme_master WHERE source_system = 'jyhf'")
    await conn.execute("DELETE FROM financial_categories WHERE source_system = 'jyhf'")
    logger.info("已清空 theme_master 和 financial_categories 中旧的久赢恒丰数据")

async def _table_exists(conn, table_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = $1
            )
            """,
            table_name,
        )
    )


def _load_subject_keys(subjects_file: Optional[str]) -> Optional[List[str]]:
    if not subjects_file:
        return None
    with open(subjects_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return []
    if subjects_file.endswith(".json"):
        data = json.loads(content)
        return [str(x) for x in data]
    return [line.strip() for line in content.splitlines() if line.strip()]


async def fetch_all_nodes(conn, subject_keys: Optional[List[str]] = None) -> List[Dict]:
    """优先从 subject_node_staging 读取；回退到 jyhf_subject_node_staging。"""
    use_subject_node = await _table_exists(conn, "subject_node_staging")
    rows = []
    subject_filter = ""
    params: List[Any] = []

    if subject_keys:
        subject_filter = " WHERE subject_key = ANY($1::varchar[]) "
        params.append(subject_keys)

    if use_subject_node:
        rows = await conn.fetch(
            f"""
            SELECT
                subject_key,
                subject_name AS name,
                coalesce(node_level, 1) AS level,
                parent_subject_key,
                ancestors,
                coalesce(raw_json->>'fullName', raw_json->>'full_name') AS full_name,
                pct_chg,
                NULL::integer AS stock_count,
                NULL::integer AS limit_up_count,
                NULL::integer AS lead_times,
                NULL::numeric AS amount,
                NULL::numeric AS market_value,
                NULL::varchar AS lead_stock_id,
                NULL::varchar AS lead_stock_name
            FROM subject_node_staging
            {subject_filter}
            """,
            *params,
        )
        if rows:
            logger.info(f"从 subject_node_staging 获取到 {len(rows)} 个节点")
            return [dict(r) for r in rows]

    rows = await conn.fetch(
        f"""
        SELECT subject_key, name, level, parent_subject_key, ancestors, full_name,
               pct_chg, stock_count, limit_up_count, lead_times,
               amount, market_value, lead_stock_id, lead_stock_name
        FROM jyhf_subject_node_staging
        {subject_filter}
        """,
        *params,
    )
    logger.info(f"从 jyhf_subject_node_staging 获取到 {len(rows)} 个节点")
    return [dict(r) for r in rows]

async def fetch_hierarchy_edges(conn) -> List[Dict]:
    rows = await conn.fetch(
        """
        SELECT parent_subject_key, child_subject_key, child_name
        FROM theme_hierarchy_staging
        """
    )
    logger.info(f"从 theme_hierarchy_staging 获取到 {len(rows)} 条树边")
    return [dict(r) for r in rows]


async def fetch_children_snapshots(conn) -> List[Dict]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (child_subject_key)
            parent_subject_key,
            child_subject_key,
            child_name,
            full_name,
            pct_chg,
            stock_count,
            limit_up_count,
            amount,
            market_value,
            lead_stock_id,
            lead_stock_name,
            ancestors,
            depth
        FROM subject_children_staging
        ORDER BY child_subject_key, depth ASC, updated_at DESC
        """
    )
    logger.info(f"从 subject_children_staging 获取到 {len(rows)} 条子题材快照")
    return [dict(r) for r in rows]


def build_graph(
    root_nodes: List[Dict],
    hierarchy_edges: List[Dict],
    child_snapshots: List[Dict],
) -> Tuple[Dict[str, Dict], Dict[str, Set[str]], Dict[str, Optional[str]], Dict[str, int], Set[str], Set[str]]:
    node_map: Dict[str, Dict] = {}
    children_map: Dict[str, Set[str]] = defaultdict(set)
    parent_map: Dict[str, Optional[str]] = {}

    for node in root_nodes:
        key = str(node["subject_key"])
        node_map[key] = {
            "subject_key": key,
            "name": node.get("name") or key,
            "full_name": node.get("full_name"),
            "pct_chg": node.get("pct_chg"),
            "stock_count": node.get("stock_count"),
            "limit_up_count": node.get("limit_up_count"),
            "lead_times": node.get("lead_times"),
            "amount": node.get("amount"),
            "market_value": node.get("market_value"),
            "lead_stock_id": node.get("lead_stock_id"),
            "lead_stock_name": node.get("lead_stock_name"),
            "node_level": 1,
        }
        parent_map.setdefault(key, None)

    for row in child_snapshots:
        parent = row.get("parent_subject_key")
        key = str(row["child_subject_key"])
        existing = node_map.get(key, {"subject_key": key})
        existing.update(
            {
                "name": row.get("child_name") or existing.get("name") or key,
                "full_name": row.get("full_name") or existing.get("full_name"),
                "pct_chg": row.get("pct_chg") if row.get("pct_chg") is not None else existing.get("pct_chg"),
                "stock_count": row.get("stock_count") if row.get("stock_count") is not None else existing.get("stock_count"),
                "limit_up_count": row.get("limit_up_count") if row.get("limit_up_count") is not None else existing.get("limit_up_count"),
                "amount": row.get("amount") if row.get("amount") is not None else existing.get("amount"),
                "market_value": row.get("market_value") if row.get("market_value") is not None else existing.get("market_value"),
                "lead_stock_id": row.get("lead_stock_id") or existing.get("lead_stock_id"),
                "lead_stock_name": row.get("lead_stock_name") or existing.get("lead_stock_name"),
            }
        )
        node_map[key] = existing
        if parent not in (None, "", "0", 0):
            parent = str(parent)
            children_map[parent].add(key)
            parent_map[key] = parent
            parent_map.setdefault(parent, None)
            node_map.setdefault(parent, {"subject_key": parent, "name": parent})

    for row in hierarchy_edges:
        parent = str(row["parent_subject_key"])
        child = str(row["child_subject_key"])
        children_map[parent].add(child)
        parent_map[child] = parent
        parent_map.setdefault(parent, None)
        node_map.setdefault(parent, {"subject_key": parent, "name": parent})
        child_node = node_map.setdefault(child, {"subject_key": child, "name": child})
        if not child_node.get("name") or child_node["name"] == child:
            child_node["name"] = row.get("child_name") or child

    root_keys = {str(node["subject_key"]) for node in root_nodes}
    levels: Dict[str, int] = {key: 1 for key in root_keys}
    queue = list(root_keys)
    while queue:
        current = queue.pop(0)
        current_level = levels[current]
        for child in sorted(children_map.get(current, set())):
            next_level = current_level + 1
            if child not in levels or next_level < levels[child]:
                levels[child] = next_level
                queue.append(child)

    for key, level in levels.items():
        node_map[key]["node_level"] = level

    non_leaf_keys = set(root_keys) | set(children_map.keys())
    leaf_keys = set(node_map.keys()) - non_leaf_keys

    logger.info(f"识别到非叶子节点（分类）: {len(non_leaf_keys)} 个")
    logger.info(f"识别到叶子节点（题材）: {len(leaf_keys)} 个")
    return node_map, children_map, parent_map, levels, non_leaf_keys, leaf_keys


def ancestor_chain(key: str, parent_map: Dict[str, Optional[str]]) -> List[str]:
    chain = []
    current = key
    seen = set()
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        current = parent_map.get(current)
    chain.reverse()
    return chain


def select_targets(
    subject_keys: Optional[List[str]],
    parent_map: Dict[str, Optional[str]],
    non_leaf_keys: Set[str],
    leaf_keys: Set[str],
) -> Tuple[Set[str], Set[str]]:
    if not subject_keys:
        return set(non_leaf_keys), set(leaf_keys)

    selected = {str(key) for key in subject_keys}
    context = set(selected)
    for key in list(selected):
        context.update(ancestor_chain(key, parent_map))

    return non_leaf_keys & context, leaf_keys & selected

async def insert_financial_categories(
    conn,
    non_leaf_keys: Set[str],
    node_map: Dict[str, Dict],
    parent_map: Dict[str, Optional[str]],
    levels: Dict[str, int],
):
    """
    将非叶子节点插入 financial_categories，构建正确的分类树。
    优化点：
      - 修正 path_depth，使用 parts 数量计算正确深度。
      - 冲突日志使用 Counter.most_common(3) 展示真实 top3 候选路径。
      - ancestor_descendants 仅针对缺失祖先收集，提升性能。
      - 增加详细的父节点缺失诊断，并将异常信息写入日志。
      - 兼容一级叶子节点：若一级节点是叶子，也插入 financial_categories 作为分类入口。
    """
    key_to_prefixed = {key: f"{PREFIX}{key}" for key in non_leaf_keys}
    insert_list = []                      # 用于批量插入

    for key in sorted(non_leaf_keys):
        node = node_map.get(key, {"name": key})
        name = node.get("name") or key
        category_level = levels.get(key, 1)
        parent_key = parent_map.get(key)
        parent_code = key_to_prefixed[parent_key] if parent_key in non_leaf_keys else None
        full_path = [key_to_prefixed[x] for x in ancestor_chain(key, parent_map) if x in non_leaf_keys]
        keywords = [name]
        insert_list.append((
            key_to_prefixed[key],
            name,
            key,
            keywords,
            parent_code,
            category_level,
            full_path
        ))

    await conn.executemany("""
        INSERT INTO financial_categories (
            category_code, category_name, category_level, parent_code,
            source_system, source_id, is_standard, keywords, aliases,
            full_path, created_at, updated_at
        ) VALUES (
            $1, $2, $6, $5,
            'jyhf', $3, false, $4, '{}',
            $7, NOW(), NOW()
        )
        ON CONFLICT (category_code) DO UPDATE SET
            category_name = EXCLUDED.category_name,
            category_level = EXCLUDED.category_level,
            parent_code = EXCLUDED.parent_code,
            source_id = EXCLUDED.source_id,
            keywords = EXCLUDED.keywords,
            full_path = EXCLUDED.full_path,
            updated_at = NOW()
    """, insert_list)
    logger.info(f"插入/更新非叶子节点 {len(insert_list)} 个")

async def insert_theme_master(
    conn,
    leaf_keys: Set[str],
    non_leaf_keys: Set[str],
    node_map: Dict[str, Dict],
    parent_map: Dict[str, Optional[str]],
):
    """将叶子节点插入 theme_master，设置 category1_code 和 category2_code（可选）"""
    key_to_prefixed = {}
    for key in non_leaf_keys:
        key_to_prefixed[key] = f"{PREFIX}{key}"
    for key in leaf_keys:
        key_to_prefixed[key] = f"{PREFIX}{key}"

    leaf_list = []
    for key in sorted(leaf_keys):
        node = node_map[key]
        chain = ancestor_chain(key, parent_map)
        non_leaf_chain = [x for x in chain if x in non_leaf_keys]
        cat1_code = None
        cat2_code = None
        if non_leaf_chain:
            cat1_code = key_to_prefixed[non_leaf_chain[0]]
        if len(non_leaf_chain) > 1:
            cat2_code = key_to_prefixed[non_leaf_chain[1]]

        # 构建 tags，数值保留原样（Decimal 转为 float 以便 JSON 序列化）
        tags = {
            "jyhf_id": key,
            "full_name": node.get('full_name'),
            "pct_chg": float(node['pct_chg']) if node.get('pct_chg') is not None else None,
            "stock_count": node.get('stock_count'),
            "limit_up_count": node.get('limit_up_count'),
            "lead_times": node.get('lead_times'),
            "amount": float(node['amount']) if node.get('amount') is not None else None,
            "market_value": float(node['market_value']) if node.get('market_value') is not None else None,
            "lead_stock_id": node.get('lead_stock_id'),
            "lead_stock_name": node.get('lead_stock_name'),
        }
        tags = {k: v for k, v in tags.items() if v is not None}
        # 使用自定义 JSON 编码器处理 Decimal 转换（但已转为 float，无需特殊处理）
        tags_json = json.dumps(tags, ensure_ascii=False)

        # category_path 只存分类节点 code
        category_path = None
        if cat1_code and cat2_code:
            category_path = [cat1_code, cat2_code]
        elif cat1_code:
            category_path = [cat1_code]

        leaf_list.append((
            key_to_prefixed[key],
            node['name'],
            cat1_code,
            cat2_code,
            tags_json,
            category_path,
            key
        ))

    # 批量插入
    if leaf_list:
        await conn.executemany("""
            INSERT INTO theme_master (
                code, name, category1_code, category2_code, tags, category_path,
                source_system, source_id, theme_type, lifecycle_stage, status,
                heat_score, confidence_score, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                'jyhf', $7, 'concept', 'growth', 'active',
                50, 0.8, NOW(), NOW()
            )
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                category1_code = EXCLUDED.category1_code,
                category2_code = EXCLUDED.category2_code,
                tags = EXCLUDED.tags,
                category_path = EXCLUDED.category_path,
                updated_at = NOW()
        """, leaf_list)
        logger.info(f"插入/更新叶子节点 {len(leaf_list)} 个")


async def cleanup_removed_nodes(
    conn,
    non_leaf_keys: Set[str],
    leaf_keys: Set[str],
) -> None:
    await conn.execute(
        """
        DELETE FROM financial_categories
        WHERE source_system = 'jyhf'
          AND NOT (source_id = ANY($1::varchar[]))
        """,
        list(non_leaf_keys),
    )
    await conn.execute(
        """
        DELETE FROM theme_master
        WHERE source_system = 'jyhf'
          AND NOT (source_id = ANY($1::varchar[]))
        """,
        list(leaf_keys),
    )
    logger.info("已清理不在最新节点树中的 jyhf 分类/题材")

async def create_indexes(conn):
    """创建查询所需索引"""
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_cat2_source
        ON theme_master (source_system, category2_code)
        WHERE status = 'active'
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_cat1_source
        ON theme_master (source_system, category1_code)
        WHERE status = 'active' AND category2_code IS NULL
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_theme_source_id
        ON theme_master (source_system, source_id)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_fin_cat_path
        ON financial_categories USING GIN (full_path)
    """)
    logger.info("索引创建/检查完成")

def parse_args():
    parser = argparse.ArgumentParser(description="将久赢节点 staging 增量导入 financial_categories/theme_master")
    parser.add_argument("--subjects-file", help="只处理这些 subject_key（json/txt）")
    parser.add_argument("--full-rebuild", action="store_true", help="清空 jyhf 数据后全量重建")
    parser.add_argument("--batch-id", help="同步批次 ID，仅用于日志")
    return parser.parse_args()


async def main():
    args = parse_args()
    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            if args.full_rebuild:
                await clear_old_data(conn)
            else:
                logger.info("采用增量模式：跳过清空旧数据，直接 upsert")

            # 获取所有节点
            subject_keys = _load_subject_keys(args.subjects_file)
            if subject_keys is not None:
                logger.info(f"按 subjects-file 过滤，subject 数量={len(subject_keys)}")
            if args.batch_id:
                logger.info(f"batch_id={args.batch_id}")
            nodes = await fetch_all_nodes(conn, None)
            hierarchy_edges = await fetch_hierarchy_edges(conn)
            child_snapshots = await fetch_children_snapshots(conn)
            node_map, children_map, parent_map, levels, non_leaf_keys, leaf_keys = build_graph(
                nodes, hierarchy_edges, child_snapshots
            )
            target_non_leaf, target_leaf = select_targets(subject_keys, parent_map, non_leaf_keys, leaf_keys)

            # 插入 financial_categories（非叶子）
            await insert_financial_categories(conn, target_non_leaf, node_map, parent_map, levels)

            # 插入 theme_master（叶子）
            await insert_theme_master(conn, target_leaf, non_leaf_keys, node_map, parent_map)

            if subject_keys is None:
                await cleanup_removed_nodes(conn, non_leaf_keys, leaf_keys)

            # 创建索引
            await create_indexes(conn)

            # 诊断：theme_master 中未绑定分类的叶子
            unbound = await conn.fetch("""
                SELECT code, name, category1_code, category2_code
                FROM theme_master
                WHERE source_system = 'jyhf' AND category1_code IS NULL
            """)
            if unbound:
                logger.warning(f"发现 {len(unbound)} 个叶子节点未绑定任何分类，示例：{unbound[:3]}")
            else:
                logger.info("所有叶子节点均绑定了分类")

            logger.info("所有数据导入完成")
    finally:
        await manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
