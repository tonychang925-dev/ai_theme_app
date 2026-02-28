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
import logging
from decimal import Decimal
from collections import Counter
from typing import Dict, List, Set, Tuple, Any

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

async def fetch_all_nodes(conn) -> List[Dict]:
    """从 staging 表获取所有节点数据"""
    rows = await conn.fetch("""
        SELECT subject_key, name, level, parent_subject_key, ancestors, full_name,
               pct_chg, stock_count, limit_up_count, lead_times,
               amount, market_value, lead_stock_id, lead_stock_name
        FROM jyhf_subject_node_staging
    """)
    logger.info(f"从 staging 表获取到 {len(rows)} 个节点")
    return [dict(r) for r in rows]

def identify_non_leaf_and_leaf(node_map: Dict[str, Dict]) -> Tuple[Set[str], Set[str], Dict[str, Set[str]]]:
    """
    识别非叶子节点（分类）和叶子节点（题材）
    返回：
        non_leaf_keys: 所有非叶子节点 key（包括可能缺失的祖先）
        leaf_keys: 所有叶子节点 key
        children_map: 父节点到子节点列表的映射
    """
    # 构建父子关系
    children_map = {}
    all_keys = set(node_map.keys())
    for key, node in node_map.items():
        parent = node.get('parent_subject_key')
        if parent:
            children_map.setdefault(parent, set()).add(key)

    # 从 ancestors 中收集所有可能缺失的祖先
    ancestor_keys = set()
    for node in node_map.values():
        ancestors = node.get('ancestors')
        if ancestors and ancestors != '0':
            for part in ancestors.split(',')[1:]:
                if part.strip():
                    ancestor_keys.add(part.strip())

    # 非叶子节点 = (在 node_map 中有子节点的) ∪ (不在 node_map 中的祖先)
    non_leaf_keys = set()
    for key in all_keys:
        if key in children_map and children_map[key]:
            non_leaf_keys.add(key)
    missing_ancestors = ancestor_keys - all_keys
    non_leaf_keys.update(missing_ancestors)

    # 叶子节点 = 在 node_map 中且不在 non_leaf_keys 中
    leaf_keys = all_keys - non_leaf_keys

    logger.info(f"识别到非叶子节点（分类）: {len(non_leaf_keys)} 个")
    logger.info(f"识别到叶子节点（题材）: {len(leaf_keys)} 个")
    return non_leaf_keys, leaf_keys, children_map

def compute_depth(ancestors: str) -> int:
    """根据 ancestors 计算节点深度（从1开始）"""
    if not ancestors or ancestors == '0':
        return 1
    return len(ancestors.split(','))

async def insert_financial_categories(conn, non_leaf_keys: Set[str], node_map: Dict[str, Dict], children_map: Dict[str, Set[str]]):
    """
    将非叶子节点插入 financial_categories，构建正确的分类树。
    优化点：
      - 修正 path_depth，使用 parts 数量计算正确深度。
      - 冲突日志使用 Counter.most_common(3) 展示真实 top3 候选路径。
      - ancestor_descendants 仅针对缺失祖先收集，提升性能。
      - 增加详细的父节点缺失诊断，并将异常信息写入日志。
      - 兼容一级叶子节点：若一级节点是叶子，也插入 financial_categories 作为分类入口。
    """
    # ---------- 1. 识别缺失祖先 ----------
    missing_ancestors = set(non_leaf_keys) - set(node_map.keys())

    # ---------- 2. 收集所有非叶子节点的候选路径，并同时收集缺失祖先的名称片段 ----------
    node_candidate_paths = {}   # key -> list of path strings
    ancestor_name_parts = {}    # 仅对缺失祖先：key -> list of name parts

    for node in node_map.values():
        ancestors = node.get('ancestors')
        if not ancestors or ancestors == '0':
            continue
        parts = ancestors.split(',')
        # 记录路径
        for i in range(1, len(parts)):
            current = parts[i]
            if current in non_leaf_keys:
                path = ','.join(parts[:i+1])
                node_candidate_paths.setdefault(current, []).append(path)

        # 为缺失祖先收集名称片段
        full = node.get('full_name')
        if full and '-' in full:
            name_part = full.split('-')[0].strip()
            for j in range(1, len(parts)):
                anc = parts[j]
                if anc in missing_ancestors:
                    ancestor_name_parts.setdefault(anc, []).append(name_part)

    logger.info(f"为 {len(node_candidate_paths)} 个非叶子节点收集到候选路径，缺失祖先 {len(missing_ancestors)} 个")

    # ---------- 3. 为每个节点选择最佳路径 ----------
    from collections import Counter

    def path_depth(p: str) -> int:
        """返回路径深度（去掉0后的节点个数）"""
        return len(p.split(',')) - 1

    selected_paths = {}          # key -> best_path
    path_conflicts = []           # 记录多路径冲突的节点

    for key, paths in node_candidate_paths.items():
        cnt = Counter(paths)
        if len(cnt) == 1:
            selected_paths[key] = paths[0]
            continue
        # 按深度降序、出现次数降序、字典序升序（保证稳定）
        best = max(cnt.items(), key=lambda x: (path_depth(x[0]), x[1], -x[0]))
        selected_paths[key] = best[0]
        top3 = dict(cnt.most_common(3))
        path_conflicts.append((key, len(cnt), top3))

    if path_conflicts:
        logger.warning(f"存在 {len(path_conflicts)} 个节点有多个候选路径，已选择最优路径，示例（前10）：")
        for key, total, top3 in path_conflicts[:10]:
            logger.warning(f"  节点 {key}: 共 {total} 条路径，主要候选: {top3}")

    # ---------- 4. 处理缺失祖先的名称 ----------
    from collections import Counter as NameCounter
    missing_names = {}
    for key in missing_ancestors:
        parts = ancestor_name_parts.get(key, [])
        if parts:
            # 取最常见的名称片段
            missing_names[key] = NameCounter(parts).most_common(1)[0][0]
        else:
            missing_names[key] = f"L_{key}"
            logger.warning(f"缺失祖先 {key} 无法从后代推断名称，使用 {missing_names[key]}")

    # ---------- 5. 准备插入数据，同时收集诊断信息 ----------
    key_to_prefixed = {key: f"{PREFIX}{key}" for key in non_leaf_keys}
    insert_list = []                      # 用于批量插入
    parent_missing_report = []             # 记录父节点缺失的详细情况
    parent_not_in_nonleaf = []             # 记录父节点不在 non_leaf_keys 的情况

    for key in non_leaf_keys:
        best_path = selected_paths.get(key)
        if best_path is None:
            # 该节点从未在任何 ancestors 中出现，作为孤立根处理
            category_level = 1
            parent_code = None
            full_path = [key_to_prefixed[key]]
            # 名称推断
            if key in node_map:
                node = node_map[key]
                name = node['name']
                full_name = node.get('full_name')
                if full_name and '-' in full_name:
                    name = full_name.split('-')[0].strip()
            else:
                name = missing_names.get(key, f"L_{key}")
        else:
            parts = best_path.split(',')
            # parts = ['0', 'id1', 'id2', ..., key]
            category_level = len(parts) - 1
            if len(parts) >= 3:
                parent_key = parts[-2]
                # 检查父节点是否属于非叶子
                if parent_key in non_leaf_keys:
                    parent_code = key_to_prefixed[parent_key]
                else:
                    parent_code = None
                    parent_not_in_nonleaf.append((key, parent_key))
                    logger.warning(f"节点 {key} 的父节点 {parent_key} 不在 non_leaf_keys 中，将置为根")
            else:
                parent_code = None
            # 生成 full_path
            full_path = [key_to_prefixed[pid] for pid in parts[1:]]
            # 名称推断（同上有 node_map 则用节点信息，否则用 missing_names）
            if key in node_map:
                node = node_map[key]
                name = node['name']
                full_name = node.get('full_name')
                if full_name and '-' in full_name:
                    name = full_name.split('-')[0].strip()
            else:
                name = missing_names.get(key, f"L_{key}")

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

    # 输出诊断报告
    if parent_not_in_nonleaf:
        logger.warning(f"共有 {len(parent_not_in_nonleaf)} 个节点的父节点不在 non_leaf_keys 中，示例: {parent_not_in_nonleaf[:10]}")

    # ---------- 6. 批量插入 ----------
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

async def insert_theme_master(conn, leaf_keys: Set[str], non_leaf_keys: Set[str], node_map: Dict[str, Dict]):
    """将叶子节点插入 theme_master，设置 category1_code 和 category2_code（可选）"""
    key_to_prefixed = {}
    for key in non_leaf_keys:
        key_to_prefixed[key] = f"{PREFIX}{key}"
    for key in leaf_keys:
        key_to_prefixed[key] = f"{PREFIX}{key}"

    leaf_list = []
    for key in leaf_keys:
        node = node_map[key]
        ancestors = node.get('ancestors', '')
        # 解析路径中的非叶子节点
        cat1_code = None
        cat2_code = None
        if ancestors and ancestors != '0':
            parts = ancestors.split(',')
            # 从前往后找第一个属于非叶子集合的作为 L1，第二个作为 L2（如果存在）
            found_l1 = False
            for part in parts[1:]:  # 跳过0
                if part in non_leaf_keys:
                    if not found_l1:
                        cat1_code = key_to_prefixed[part]
                        found_l1 = True
                    else:
                        cat2_code = key_to_prefixed[part]
                        break  # 只取最近的两级
        else:
            logger.warning(f"叶子节点 {key} 无 ancestors 信息")

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

async def main():
    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            # 清空旧数据
            await clear_old_data(conn)

            # 获取所有节点
            nodes = await fetch_all_nodes(conn)
            node_map = {node['subject_key']: node for node in nodes}

            # 识别非叶子和叶子节点
            non_leaf_keys, leaf_keys, children_map = identify_non_leaf_and_leaf(node_map)

            # 插入 financial_categories（非叶子）
            await insert_financial_categories(conn, non_leaf_keys, node_map, children_map)

            # 插入 theme_master（叶子）
            await insert_theme_master(conn, leaf_keys, non_leaf_keys, node_map)

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