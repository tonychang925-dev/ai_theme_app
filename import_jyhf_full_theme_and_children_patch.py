#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
根据 full_theme_list.jsonl + children/*.jsonl + theme_hierarchy.jsonl + details/*.jsonl
补齐久赢恒丰本地数据库中的：
1. financial_categories
2. theme_master
3. subject_detail

严格保持现有架构逻辑：
- 没有叶子的节点 -> financial_categories
- 有叶子的父节点 L1/L2 -> financial_categories
- 叶子 L3 -> theme_master
- 有详情文件的题材 -> subject_detail

增强要求：
- 先检查本地文件有效性
- 已存在则跳过
- 输出真实落库统计
- 最后做全量校验，确保应落库数据都已成功落库

关键修正：
- full_theme_list 中“仅存在于索引层、没有 children/hierarchy 关系、ancestors=0 或 level=1”的主干节点，
  视为 financial_categories，而不是 theme_master 叶子。
"""

import os
import sys
import json
import argparse
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set
from collections import defaultdict

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
# 数据模型
# =========================
class Node:
    def __init__(self, node_id: str):
        self.node_id: str = node_id
        self.name: str = ""
        self.full_name: str = ""
        self.level_hint: Optional[int] = None
        self.parent_id: Optional[str] = None
        self.ancestors: Optional[str] = None

        # 来源标记
        self.from_full_list: bool = False
        self.from_children: bool = False
        self.from_hierarchy: bool = False
        self.has_detail: bool = False

        # 衍生属性
        self.children: Set[str] = set()

        # 市场字段（可选，入 tags）
        self.pct_chg = None
        self.stock_count = None
        self.limit_up_count = None
        self.lead_times = None
        self.amount = None
        self.market_value = None
        self.lead_stock_id = None
        self.lead_stock_name = None

    def tags_dict(self) -> Dict[str, Any]:
        x = {
            "jyhf_id": self.node_id,
            "full_name": self.full_name or None,
            "pct_chg": self.pct_chg,
            "stock_count": self.stock_count,
            "limit_up_count": self.limit_up_count,
            "lead_times": self.lead_times,
            "amount": self.amount,
            "market_value": self.market_value,
            "lead_stock_id": self.lead_stock_id,
            "lead_stock_name": self.lead_stock_name,
            "ancestors": self.ancestors,
            "level_hint": self.level_hint,
            "parent_id": self.parent_id,
            "from_full_list": self.from_full_list,
            "from_children": self.from_children,
            "from_hierarchy": self.from_hierarchy,
            "has_detail": self.has_detail,
        }
        return {k: v for k, v in x.items() if v is not None}


# =========================
# 基础文件读取
# =========================
def read_jsonl(path: Path) -> List[Any]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                logger.warning(f"JSONL 解析失败 {path} line={line_no}: {e}")
    return rows


# =========================
# 文件有效性检查
# =========================
def check_local_files(data_root: Path) -> Dict[str, Any]:
    children_dir = data_root / "children"
    lists_dir = data_root / "lists"
    details_dir = data_root / "details"

    full_theme_list = lists_dir / "full_theme_list.jsonl"
    theme_hierarchy = lists_dir / "theme_hierarchy.jsonl"

    result = {
        "children_dir_exists": children_dir.exists(),
        "details_dir_exists": details_dir.exists(),
        "full_theme_list_exists": full_theme_list.exists(),
        "theme_hierarchy_exists": theme_hierarchy.exists(),
        "children_file_count": 0,
        "details_file_count": 0,
        "full_theme_count": 0,
        "hierarchy_count": 0,
    }

    if not result["children_dir_exists"]:
        raise FileNotFoundError(f"缺少目录: {children_dir}")
    if not result["details_dir_exists"]:
        raise FileNotFoundError(f"缺少目录: {details_dir}")
    if not result["full_theme_list_exists"]:
        raise FileNotFoundError(f"缺少文件: {full_theme_list}")
    if not result["theme_hierarchy_exists"]:
        raise FileNotFoundError(f"缺少文件: {theme_hierarchy}")

    result["children_file_count"] = len(list(children_dir.glob("*_children.jsonl")))
    result["details_file_count"] = len(list(details_dir.glob("*_details.jsonl")))
    result["full_theme_count"] = len(read_jsonl(full_theme_list))
    result["hierarchy_count"] = len(read_jsonl(theme_hierarchy))

    logger.info("本地文件检查完成")
    logger.info(json.dumps(result, ensure_ascii=False, indent=2))

    if result["children_file_count"] == 0:
        raise RuntimeError("children 目录中没有任何 *_children.jsonl 文件")
    if result["full_theme_count"] == 0:
        raise RuntimeError("full_theme_list.jsonl 没有有效记录")

    return result


# =========================
# 解析 full_theme_list
# =========================
def parse_full_theme_list(path: Path, only_subject: Optional[str] = None) -> Dict[str, Node]:
    rows = read_jsonl(path)
    node_map: Dict[str, Node] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        sid = row.get("subjectId") or row.get("subject_id") or row.get("bizKey") or row.get("id")
        if sid is None:
            continue
        sid = str(sid)

        if only_subject and sid != only_subject:
            continue

        node = node_map.setdefault(sid, Node(sid))
        node.name = row.get("name") or row.get("subjectName") or node.name
        node.full_name = row.get("full_name") or row.get("fullName") or node.full_name
        lvl = row.get("level")
        if lvl is not None:
            try:
                node.level_hint = int(lvl)
            except Exception:
                pass
        parent_id = row.get("parentId") or row.get("parent_id")
        if parent_id not in (None, "", "0", 0):
            node.parent_id = str(parent_id)
        node.ancestors = row.get("ancestors") or node.ancestors
        node.from_full_list = True

    logger.info(f"full_theme_list 解析完成: {len(node_map)} 个节点")
    return node_map


# =========================
# 解析 children
# children 行格式：
# [id, name, full_name, pct, stock_count, limit_up_count, lead_times, level, null, amount, market_value, lead_stock_id, lead_stock_name, ancestors, [children...]]
# =========================
def parse_child_item(
    item: Any,
    parent_id: Optional[str],
    node_map: Dict[str, Node],
    children_map: Dict[str, Set[str]]
):
    if not isinstance(item, list) or len(item) < 14:
        return

    node_id = str(item[0])
    node = node_map.setdefault(node_id, Node(node_id))
    node.name = item[1] or node.name
    node.full_name = item[2] or node.full_name
    node.pct_chg = item[3]
    node.stock_count = item[4]
    node.limit_up_count = item[5]
    node.lead_times = item[6]
    if item[7] is not None:
        try:
            node.level_hint = int(item[7])
        except Exception:
            pass
    node.amount = item[9]
    node.market_value = item[10]
    node.lead_stock_id = item[11]
    node.lead_stock_name = item[12]
    node.ancestors = item[13] or node.ancestors
    if parent_id:
        node.parent_id = parent_id
        children_map[parent_id].add(node_id)
    node.from_children = True

    nested = item[14] if len(item) > 14 and isinstance(item[14], list) else []
    for child in nested:
        parse_child_item(child, node_id, node_map, children_map)


def parse_children_dir(
    children_dir: Path,
    node_map: Dict[str, Node],
    only_subject: Optional[str] = None
) -> Tuple[Dict[str, Set[str]], Set[str]]:
    children_map: Dict[str, Set[str]] = defaultdict(set)
    parent_file_subjects: Set[str] = set()

    for file in children_dir.glob("*_children.jsonl"):
        subject_id = file.name.replace("_children.jsonl", "")
        if only_subject and subject_id != only_subject:
            continue

        parent_file_subjects.add(subject_id)
        parent_node = node_map.setdefault(subject_id, Node(subject_id))
        parent_node.from_children = True

        rows = read_jsonl(file)
        for row in rows:
            parse_child_item(row, subject_id, node_map, children_map)

    logger.info(f"children 解析完成: 父节点文件 {len(parent_file_subjects)} 个")
    return children_map, parent_file_subjects


# =========================
# 解析 hierarchy，用于关系校验/补边
# {"parent_id": "9025473", "child_id": 9025477, "child_name": "车身"}
# =========================
def parse_theme_hierarchy(
    path: Path,
    node_map: Dict[str, Node],
    children_map: Dict[str, Set[str]],
    only_subject: Optional[str] = None
) -> List[Tuple[str, str]]:
    rows = read_jsonl(path)
    relations = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        parent_id = row.get("parent_id")
        child_id = row.get("child_id")
        child_name = row.get("child_name")

        if parent_id is None or child_id is None:
            continue

        parent_id = str(parent_id)
        child_id = str(child_id)

        if only_subject and parent_id != only_subject and child_id != only_subject:
            continue

        p = node_map.setdefault(parent_id, Node(parent_id))
        c = node_map.setdefault(child_id, Node(child_id))
        if child_name and not c.name:
            c.name = child_name
        c.parent_id = c.parent_id or parent_id
        p.from_hierarchy = True
        c.from_hierarchy = True

        children_map[parent_id].add(child_id)
        relations.append((parent_id, child_id))

    logger.info(f"theme_hierarchy 解析完成: {len(relations)} 条关系")
    return relations


# =========================
# details 扫描
# =========================
def collect_detail_subjects(details_dir: Path) -> Set[str]:
    sids = set()
    for file in details_dir.glob("*_details.jsonl"):
        sid = file.name.replace("_details.jsonl", "")
        sids.add(sid)
    return sids


def read_detail_record(details_dir: Path, subject_id: str) -> Dict[str, Any]:
    path = details_dir / f"{subject_id}_details.jsonl"
    rows = read_jsonl(path)
    if not rows:
        return {
            "subject_key": subject_id,
            "name": "",
            "reason_short": "",
            "detail_html": "",
        }

    def pick(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        id_fields = ["subjectId", "subject_id", "bizKey", "id", "subjectID"]
        sid = None
        for f in id_fields:
            if obj.get(f) is not None:
                sid = str(obj.get(f))
                break
        if sid != str(subject_id):
            return None
        return {
            "subject_key": str(subject_id),
            "name": obj.get("name") or obj.get("subjectName") or "",
            "reason_short": obj.get("reason") or "",
            "detail_html": obj.get("detail") or obj.get("detail_html") or obj.get("content") or "",
        }

    for row in rows:
        if isinstance(row, dict):
            x = pick(row)
            if x:
                return x
            if isinstance(row.get("data"), dict):
                x = pick(row["data"])
                if x:
                    return x

    return {
        "subject_key": subject_id,
        "name": "",
        "reason_short": "",
        "detail_html": "",
    }


# =========================
# 树结构与分类
# =========================
def finalize_children(node_map: Dict[str, Node], children_map: Dict[str, Set[str]]):
    for pid, child_ids in children_map.items():
        p = node_map.setdefault(pid, Node(pid))
        p.children |= set(child_ids)
        for cid in child_ids:
            c = node_map.setdefault(cid, Node(cid))
            c.parent_id = c.parent_id or pid


def is_root_index_node(node: Node) -> bool:
    """
    只存在于 full_theme_list 的主干索引节点，不应视为 theme_master 叶子。
    """
    return (
        node.from_full_list
        and not node.from_children
        and not node.from_hierarchy
        and (node.ancestors in (None, "", "0") or node.level_hint == 1)
    )


def identify_non_leaf_and_leaf(
    node_map: Dict[str, Node]
) -> Tuple[Set[str], Set[str]]:
    non_leaf = set()
    leaf = set()

    for sid, node in node_map.items():
        if node.children or is_root_index_node(node):
            non_leaf.add(sid)
        else:
            leaf.add(sid)

    return non_leaf, leaf


def compute_parent_map(node_map: Dict[str, Node]) -> Dict[str, Optional[str]]:
    return {sid: node.parent_id for sid, node in node_map.items()}


def compute_path_to_root(parent_map: Dict[str, Optional[str]], node_id: str) -> List[str]:
    path = []
    cur = node_id
    visited = set()

    while cur and cur not in visited:
        visited.add(cur)
        path.append(cur)
        cur = parent_map.get(cur)

    path.reverse()
    return path


def classify_leaf_for_theme_master(
    node_id: str,
    parent_map: Dict[str, Optional[str]],
    non_leaf_keys: Set[str]
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    叶子节点映射：
    - L1 / L2 父节点落 financial_categories
    - 叶子 L3 落 theme_master
    返回：
      category1_code, category2_code, category_path
    """
    path = compute_path_to_root(parent_map, node_id)
    category_nodes = [x for x in path[:-1] if x in non_leaf_keys]

    cat1_code = f"{PREFIX}{category_nodes[0]}" if len(category_nodes) >= 1 else None
    cat2_code = f"{PREFIX}{category_nodes[1]}" if len(category_nodes) >= 2 else None

    category_path = []
    if cat1_code:
        category_path.append(cat1_code)
    if cat2_code:
        category_path.append(cat2_code)

    return cat1_code, cat2_code, category_path


# =========================
# 数据库存在性查询
# =========================
async def fetch_existing_financial_categories(conn) -> Set[str]:
    rows = await conn.fetch("""
        SELECT source_id
        FROM financial_categories
        WHERE source_system = 'jyhf' AND source_id IS NOT NULL
    """)
    return {str(r["source_id"]) for r in rows}


async def fetch_existing_theme_master(conn) -> Set[str]:
    rows = await conn.fetch("""
        SELECT source_id
        FROM theme_master
        WHERE source_system = 'jyhf' AND source_id IS NOT NULL
    """)
    return {str(r["source_id"]) for r in rows}


async def fetch_existing_subject_detail(conn) -> Set[str]:
    rows = await conn.fetch("""
        SELECT subject_key FROM subject_detail
    """)
    return {str(r["subject_key"]) for r in rows}


# =========================
# 清理误入 theme_master 的 root 索引节点（可选）
# =========================
async def cleanup_wrong_root_nodes_in_theme_master(conn):
    rows = await conn.fetch("""
        SELECT source_id
        FROM theme_master
        WHERE source_system = 'jyhf'
          AND category1_code IS NULL
          AND category2_code IS NULL
          AND (tags->>'from_full_list') = 'true'
          AND COALESCE(tags->>'from_children', 'false') = 'false'
          AND COALESCE(tags->>'from_hierarchy', 'false') = 'false'
          AND COALESCE(tags->>'ancestors', '0') = '0'
    """)
    ids = [str(r["source_id"]) for r in rows]
    if not ids:
        logger.info("未发现需要清理的误入 theme_master 的 root 索引节点")
        return 0

    await conn.execute("""
        DELETE FROM theme_master
        WHERE source_system = 'jyhf'
          AND category1_code IS NULL
          AND category2_code IS NULL
          AND (tags->>'from_full_list') = 'true'
          AND COALESCE(tags->>'from_children', 'false') = 'false'
          AND COALESCE(tags->>'from_hierarchy', 'false') = 'false'
          AND COALESCE(tags->>'ancestors', '0') = '0'
    """)
    logger.info(f"已清理误入 theme_master 的 root 索引节点: {len(ids)} 个")
    return len(ids)


# =========================
# 确保 subject_detail 增量字段存在
# =========================
async def ensure_subject_detail_columns(conn):
    await conn.execute("""
        ALTER TABLE subject_detail
        ADD COLUMN IF NOT EXISTS reason_short text
    """)
    await conn.execute("""
        ALTER TABLE subject_detail
        ADD COLUMN IF NOT EXISTS is_current boolean DEFAULT true
    """)


# =========================
# 落库
# =========================
async def insert_missing_financial_categories(
    conn,
    node_map: Dict[str, Node],
    non_leaf_keys: Set[str],
    existing_fc: Set[str],
    parent_map: Dict[str, Optional[str]]
) -> Dict[str, int]:
    inserted = 0
    skipped = 0

    rows = []
    for sid in sorted(non_leaf_keys):
        if sid in existing_fc:
            skipped += 1
            continue

        node = node_map[sid]
        path = compute_path_to_root(parent_map, sid)
        category_level = len(path)

        parent_code = None
        if len(path) >= 2:
            parent_code = f"{PREFIX}{path[-2]}"

        full_path = [f"{PREFIX}{x}" for x in path]

        category_name = node.name or node.full_name or f"L_{sid}"
        keywords = [category_name]

        rows.append((
            f"{PREFIX}{sid}",
            category_name,
            category_level,
            parent_code,
            "jyhf",
            sid,
            False,
            keywords,
            [],
            full_path,
        ))

    if rows:
        await conn.executemany("""
            INSERT INTO financial_categories (
                category_code, category_name, category_level, parent_code,
                source_system, source_id, is_standard, keywords, aliases,
                full_path, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7, $8, $9,
                $10, NOW(), NOW()
            )
            ON CONFLICT (category_code) DO NOTHING
        """, rows)
        inserted = len(rows)

    return {"inserted": inserted, "skipped_existing": skipped}


async def insert_missing_theme_master(
    conn,
    node_map: Dict[str, Node],
    leaf_keys: Set[str],
    existing_tm: Set[str],
    parent_map: Dict[str, Optional[str]],
    non_leaf_keys: Set[str]
) -> Dict[str, int]:
    inserted = 0
    skipped = 0

    rows = []
    for sid in sorted(leaf_keys):
        if sid in existing_tm:
            skipped += 1
            continue

        node = node_map[sid]
        cat1_code, cat2_code, category_path = classify_leaf_for_theme_master(
            node_id=sid,
            parent_map=parent_map,
            non_leaf_keys=non_leaf_keys
        )

        tags_json = json.dumps(node.tags_dict(), ensure_ascii=False)

        theme_name = node.name or node.full_name or sid
        description = node.full_name or node.name or ""

        rows.append((
            f"{PREFIX}{sid}",
            theme_name,
            description,
            cat1_code,
            cat2_code,
            tags_json,
            category_path if category_path else None,
            "jyhf",
            sid,
            "concept",
            "growth",
            "active",
            50,
            0.80,
        ))

    if rows:
        await conn.executemany("""
            INSERT INTO theme_master (
                code, name, description, category1_code, category2_code, tags, category_path,
                source_system, source_id, theme_type, lifecycle_stage, status,
                heat_score, confidence_score, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6::jsonb, $7,
                $8, $9, $10, $11, $12,
                $13, $14, NOW(), NOW()
            )
            ON CONFLICT (code) DO NOTHING
        """, rows)
        inserted = len(rows)

    return {"inserted": inserted, "skipped_existing": skipped}


async def insert_missing_subject_detail(
    conn,
    details_dir: Path,
    detail_subject_ids: Set[str],
    existing_sd: Set[str]
) -> Dict[str, int]:
    inserted = 0
    skipped = 0
    empty_detail = 0

    rows = []
    for sid in sorted(detail_subject_ids):
        if sid in existing_sd:
            skipped += 1
            continue

        detail = read_detail_record(details_dir, sid)
        detail_html = detail.get("detail_html", "") or ""
        reason_short = detail.get("reason_short", "") or ""

        if not detail_html:
            empty_detail += 1
            continue

        rows.append((
            sid,
            detail_html,
            reason_short,
            1,
            True,
        ))

    if rows:
        await conn.executemany("""
            INSERT INTO subject_detail (
                subject_key, detail_html, reason_short, detail_version, is_current, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, NOW(), NOW()
            )
            ON CONFLICT (subject_key) DO NOTHING
        """, rows)
        inserted = len(rows)

    return {
        "inserted": inserted,
        "skipped_existing": skipped,
        "empty_detail_skipped": empty_detail,
    }


# =========================
# 全量校验
# =========================
async def validate_all(
    conn,
    expected_fc: Set[str],
    expected_tm: Set[str],
    expected_sd: Set[str]
) -> Dict[str, Any]:
    existing_fc = await fetch_existing_financial_categories(conn)
    existing_tm = await fetch_existing_theme_master(conn)
    existing_sd = await fetch_existing_subject_detail(conn)

    missing_fc = sorted(list(expected_fc - existing_fc))
    missing_tm = sorted(list(expected_tm - existing_tm))
    missing_sd = sorted(list(expected_sd - existing_sd))

    return {
        "expected_financial_categories": len(expected_fc),
        "expected_theme_master": len(expected_tm),
        "expected_subject_detail": len(expected_sd),
        "missing_financial_categories_count": len(missing_fc),
        "missing_theme_master_count": len(missing_tm),
        "missing_subject_detail_count": len(missing_sd),
        "missing_financial_categories": missing_fc[:50],
        "missing_theme_master": missing_tm[:50],
        "missing_subject_detail": missing_sd[:50],
        "ok": len(missing_fc) == 0 and len(missing_tm) == 0 and len(missing_sd) == 0,
    }


# =========================
# 主流程
# =========================
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="theme_data_complete", help="theme_data_complete 根目录")
    ap.add_argument("--subject", type=str, help="仅测试一个主干题材节点，如 9010074")
    ap.add_argument(
        "--cleanup-unmapped-root-leaves",
        action="store_true",
        help="清理之前误插入 theme_master 的 root 索引节点"
    )
    args = ap.parse_args()

    data_root = Path(args.data_root)

    # 1) 本地文件检查
    check_local_files(data_root)

    # 2) 解析数据源
    full_theme_list = data_root / "lists" / "full_theme_list.jsonl"
    theme_hierarchy = data_root / "lists" / "theme_hierarchy.jsonl"
    children_dir = data_root / "children"
    details_dir = data_root / "details"

    node_map = parse_full_theme_list(full_theme_list, only_subject=args.subject)
    children_map, parent_file_subjects = parse_children_dir(children_dir, node_map, only_subject=args.subject)
    parse_theme_hierarchy(theme_hierarchy, node_map, children_map, only_subject=args.subject)

    detail_subject_ids = collect_detail_subjects(details_dir)
    for sid in detail_subject_ids:
        if sid in node_map:
            node_map[sid].has_detail = True

    finalize_children(node_map, children_map)

    non_leaf_keys, leaf_keys = identify_non_leaf_and_leaf(node_map)
    parent_map = compute_parent_map(node_map)

    logger.info(f"节点总数: {len(node_map)}")
    logger.info(f"非叶子节点: {len(non_leaf_keys)}")
    logger.info(f"叶子节点: {len(leaf_keys)}")
    logger.info(f"详情文件数: {len(detail_subject_ids)}")

    # subject_detail 只要求对“存在详情文件且在当前 node_map 中且 detail 非空”的节点补齐
    expected_sd = set()
    for sid in detail_subject_ids:
        if sid not in node_map:
            continue
        detail = read_detail_record(details_dir, sid)
        detail_html = detail.get("detail_html", "") or ""
        if detail_html.strip():
            expected_sd.add(sid)

    # 3) 数据库连接
    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            await ensure_subject_detail_columns(conn)

            if args.cleanup_unmapped_root_leaves:
                await cleanup_wrong_root_nodes_in_theme_master(conn)

            existing_fc = await fetch_existing_financial_categories(conn)
            existing_tm = await fetch_existing_theme_master(conn)
            existing_sd = await fetch_existing_subject_detail(conn)

            logger.info(f"当前库中 financial_categories(jyhf): {len(existing_fc)}")
            logger.info(f"当前库中 theme_master(jyhf): {len(existing_tm)}")
            logger.info(f"当前库中 subject_detail: {len(existing_sd)}")

            # 4) 落库
            fc_stats = await insert_missing_financial_categories(
                conn=conn,
                node_map=node_map,
                non_leaf_keys=non_leaf_keys,
                existing_fc=existing_fc,
                parent_map=parent_map,
            )

            tm_stats = await insert_missing_theme_master(
                conn=conn,
                node_map=node_map,
                leaf_keys=leaf_keys,
                existing_tm=existing_tm,
                parent_map=parent_map,
                non_leaf_keys=non_leaf_keys,
            )

            sd_stats = await insert_missing_subject_detail(
                conn=conn,
                details_dir=details_dir,
                detail_subject_ids=expected_sd,
                existing_sd=existing_sd,
            )

            stats = {
                "financial_categories": fc_stats,
                "theme_master": tm_stats,
                "subject_detail": sd_stats,
            }

            logger.info("==== 落库统计 ====")
            logger.info(json.dumps(stats, ensure_ascii=False, indent=2))

            # 5) 全量校验
            validation = await validate_all(
                conn=conn,
                expected_fc=non_leaf_keys,
                expected_tm=leaf_keys,
                expected_sd=expected_sd,
            )

            logger.info("==== 最终校验 ====")
            logger.info(json.dumps(validation, ensure_ascii=False, indent=2))

            if not validation["ok"]:
                raise RuntimeError(
                    "全量校验失败：仍有缺失数据未落库，请根据 missing_* 列表排查。"
                )

            logger.info("全部补齐成功，且全量校验通过。")

    finally:
        await manager.disconnect()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())