#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
对比 full_theme_list.jsonl 与本地数据库中的 theme_master / financial_categories
找出缺失题材，并输出分类统计。

用途：
1. 找出哪些久赢恒丰题材已进入 theme_master
2. 找出哪些只进入 financial_categories
3. 找出哪些两边都没有
4. 辅助判断是不是“只有 L1 / 非叶子 / 数据不全 / 历史导入不一致”导致未入库

运行示例：
python audit_jyhf_subject_coverage.py \
  --list-file full_theme_list.jsonl \
  --out-dir tmp/jyhf_audit
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple

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
    rows = []
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception as e:
                logger.warning(f"跳过无法解析的第 {line_no} 行: {e}")
    return rows


def extract_subject_list(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    兼容 full_theme_list.jsonl 常见字段
    """
    out = []
    for row in rows:
        sid = (
            row.get("subjectId")
            or row.get("subject_id")
            or row.get("bizKey")
            or row.get("id")
        )
        if sid is None:
            continue

        item = {
            "subject_id": str(sid),
            "name": row.get("name") or row.get("subjectName") or "",
            "type": row.get("type"),
            "level": row.get("level"),
            "parent_id": row.get("parentId") or row.get("parent_subject_key"),
            "ancestors": row.get("ancestors"),
            "raw": row,
        }
        out.append(item)
    return out


# =========================
# 数据库读取
# =========================
async def fetch_theme_master_jyhf(conn) -> List[Dict[str, Any]]:
    rows = await conn.fetch("""
        SELECT id, name, code, source_system, source_id, theme_type, status,
               category1_code, category2_code, category3_code, category_path
        FROM theme_master
        WHERE source_system = 'jyhf'
    """)
    return [dict(r) for r in rows]


async def fetch_financial_categories_jyhf(conn) -> List[Dict[str, Any]]:
    rows = await conn.fetch("""
        SELECT id, category_code, category_name, source_system, source_id,
               category_level, parent_code, full_path
        FROM financial_categories
        WHERE source_system = 'jyhf'
    """)
    return [dict(r) for r in rows]


async def fetch_staging_jyhf(conn) -> List[Dict[str, Any]]:
    """
    staging 可能不存在，做容错
    """
    try:
        rows = await conn.fetch("""
            SELECT subject_key, name, level, parent_subject_key, ancestors, full_name
            FROM jyhf_subject_node_staging
        """)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"读取 jyhf_subject_node_staging 失败，忽略 staging 对比: {e}")
        return []


# =========================
# 核对逻辑
# =========================
def build_theme_master_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx = {}
    for r in rows:
        sid = str(r.get("source_id") or "").strip()
        code = str(r.get("code") or "").strip()

        if sid:
            idx[sid] = r
        elif code.startswith(PREFIX):
            idx[code[len(PREFIX):]] = r
    return idx


def build_financial_categories_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx = {}
    for r in rows:
        sid = str(r.get("source_id") or "").strip()
        code = str(r.get("category_code") or "").strip()

        if sid:
            idx[sid] = r
        elif code.startswith(PREFIX):
            idx[code[len(PREFIX):]] = r
    return idx


def build_staging_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx = {}
    for r in rows:
        sid = str(r.get("subject_key") or "").strip()
        if sid:
            idx[sid] = r
    return idx


def infer_possible_reason(
    subject: Dict[str, Any],
    tm_hit: bool,
    fc_hit: bool,
    staging_hit: bool,
) -> str:
    """
    粗略原因推断，只做审计辅助，不做绝对判断
    """
    level = subject.get("level")
    parent_id = subject.get("parent_id")
    ancestors = subject.get("ancestors")

    if tm_hit and not fc_hit:
        return "已作为题材对象导入 theme_master"
    if fc_hit and not tm_hit:
        return "仅作为分类节点导入 financial_categories（可能被旧逻辑视为非叶子）"
    if tm_hit and fc_hit:
        return "同时存在于题材表和分类表（需检查是否混合节点）"

    # 两边都缺失
    if not staging_hit:
        return "主数据缺失：当前 staging 中也不存在，可能是旧快照不一致或未进入主数据导入链路"

    if level == 1 and not parent_id:
        return "可能是只有 L1 的节点，旧规则未作为叶子题材导入"
    if level in (1, 2) and ancestors in (None, "", "0"):
        return "层级/路径信息不完整，可能导致旧导入逻辑跳过"
    return "存在于 staging 但未进入主表，需检查叶子/非叶子判定或导入规则"


def classify_subjects(
    full_subjects: List[Dict[str, Any]],
    theme_idx: Dict[str, Dict[str, Any]],
    fc_idx: Dict[str, Dict[str, Any]],
    staging_idx: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    result = {
        "in_theme_master_only": [],
        "in_financial_categories_only": [],
        "in_both": [],
        "missing_in_both": [],
    }

    for subj in full_subjects:
        sid = subj["subject_id"]
        theme_row = theme_idx.get(sid)
        fc_row = fc_idx.get(sid)
        staging_row = staging_idx.get(sid)

        item = {
            "subject_id": sid,
            "name": subj.get("name"),
            "type": subj.get("type"),
            "level": subj.get("level"),
            "parent_id": subj.get("parent_id"),
            "ancestors": subj.get("ancestors"),
            "in_theme_master": bool(theme_row),
            "in_financial_categories": bool(fc_row),
            "in_staging": bool(staging_row),
            "theme_master_row": theme_row,
            "financial_categories_row": fc_row,
            "staging_row": staging_row,
        }
        item["possible_reason"] = infer_possible_reason(
            subj,
            tm_hit=bool(theme_row),
            fc_hit=bool(fc_row),
            staging_hit=bool(staging_row),
        )

        if theme_row and fc_row:
            result["in_both"].append(item)
        elif theme_row:
            result["in_theme_master_only"].append(item)
        elif fc_row:
            result["in_financial_categories_only"].append(item)
        else:
            result["missing_in_both"].append(item)

    return result


def summarize(classified: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    summary = {
        "in_theme_master_only": len(classified["in_theme_master_only"]),
        "in_financial_categories_only": len(classified["in_financial_categories_only"]),
        "in_both": len(classified["in_both"]),
        "missing_in_both": len(classified["missing_in_both"]),
    }

    # 对缺失原因做个简单统计
    reason_counter = {}
    for item in classified["missing_in_both"] + classified["in_financial_categories_only"]:
        reason = item.get("possible_reason") or "unknown"
        reason_counter[reason] = reason_counter.get(reason, 0) + 1

    summary["reason_breakdown"] = reason_counter
    return summary


def write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# =========================
# main
# =========================
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-file", required=True, help="full_theme_list.jsonl 路径")
    ap.add_argument("--out-dir", default="tmp/jyhf_audit", help="输出目录")
    args = ap.parse_args()

    list_file = Path(args.list_file)
    out_dir = Path(args.out_dir)

    full_rows = read_jsonl(list_file)
    full_subjects = extract_subject_list(full_rows)
    logger.info(f"full_theme_list 共读取题材 {len(full_subjects)} 个")

    config = get_postgres_config()
    manager = PostgresDatabaseManager(config)
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        async with manager.pool.acquire() as conn:
            theme_rows = await fetch_theme_master_jyhf(conn)
            fc_rows = await fetch_financial_categories_jyhf(conn)
            staging_rows = await fetch_staging_jyhf(conn)

            logger.info(f"theme_master(jyhf) = {len(theme_rows)}")
            logger.info(f"financial_categories(jyhf) = {len(fc_rows)}")
            logger.info(f"jyhf_subject_node_staging = {len(staging_rows)}")

            theme_idx = build_theme_master_index(theme_rows)
            fc_idx = build_financial_categories_index(fc_rows)
            staging_idx = build_staging_index(staging_rows)

            classified = classify_subjects(
                full_subjects=full_subjects,
                theme_idx=theme_idx,
                fc_idx=fc_idx,
                staging_idx=staging_idx,
            )
            summary = summarize(classified)

            logger.info("==== SUMMARY ====")
            logger.info(json.dumps(summary, ensure_ascii=False, indent=2))

            # 输出文件
            write_json(out_dir / "summary.json", summary)
            write_jsonl(out_dir / "in_theme_master_only.jsonl", classified["in_theme_master_only"])
            write_jsonl(out_dir / "in_financial_categories_only.jsonl", classified["in_financial_categories_only"])
            write_jsonl(out_dir / "in_both.jsonl", classified["in_both"])
            write_jsonl(out_dir / "missing_in_both.jsonl", classified["missing_in_both"])

            # 再额外输出一个重点排查文件：只关心缺失项
            focus_rows = classified["in_financial_categories_only"] + classified["missing_in_both"]
            write_jsonl(out_dir / "focus_missing_or_category_only.jsonl", focus_rows)

            logger.info(f"审计结果已输出到: {out_dir}")

    finally:
        await manager.disconnect()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())