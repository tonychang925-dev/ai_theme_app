#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Dict, List, Sequence, Tuple

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


@dataclass
class ClusterRule:
    name: str
    keywords: Sequence[str]


CLUSTER_RULES: List[ClusterRule] = [
    ClusterRule("并购重组链", ("重组", "并购", "借壳", "资产注入", "并表")),
    ClusterRule("低空经济链", ("低空经济", "低空", "无人机", "eVTOL", "通航")),
    ClusterRule("中东重建链", ("以伊重建", "中东重建", "以色列", "伊朗", "战后重建", "重建")),
    ClusterRule("光通信链", ("光通信", "CPO", "光纤", "光模块", "光缆", "光芯片", "光互连", "硅光")),
    ClusterRule(
        "商业航天链",
        (
            "商业航天",
            "卫星互联网",
            "卫星",
            "星链",
            "航天",
            "航天国家队",
            "航天材料",
            "太空",
            "太空机器人",
            "太空旅游",
            "太空算力",
            "太空光伏",
            "火箭",
            "火箭发射",
            "可回收火箭",
            "海上火箭回收",
            "蓝箭航天",
            "商业航天8大IPO",
            "广州商业航天",
            "SpaceX",
            "spacex",
            "安徽商业航天",
        ),
    ),
    ClusterRule("算力链", ("算力", "数据中心", "液冷", "英伟达", "GPU", "AIDC", "服务器")),
    ClusterRule("半导体链", ("半导体", "存储芯片", "芯片", "PCB", "封装", "光刻")),
    ClusterRule("AI应用链", ("AI助手", "AI医疗", "Token经济", "Seedance", "算电协同", "变压器")),
    ClusterRule("地产建材链", ("房地产", "地产", "建材", "建筑", "城中村", "基建")),
    ClusterRule("化工材料链", ("化工", "化工涨价", "电子布", "染料", "金刚石", "新材料", "纤维")),
    ClusterRule("周期资源链", ("钢铁", "煤炭", "有色", "铜", "铝", "稀土", "贵金属")),
    ClusterRule("消费主题链", ("宠物经济", "旅游", "生猪", "消费", "折叠屏", "家电")),
    ClusterRule("医药链", ("创新药", "医药", "医疗", "生物")),
    ClusterRule("能源链", ("电力", "燃气", "煤炭", "油气", "风电", "光伏", "锂电")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="输出主线题材簇聚合视图")
    parser.add_argument("--trade-date", help="交易日 YYYY-MM-DD；不传则取 registry 最新复核日")
    parser.add_argument("--include-observed", action="store_true", help="是否展示簇内 observed 成员")
    parser.add_argument("--top-members", type=int, default=6, help="每个簇最多展示成员数量")
    return parser.parse_args()


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _assign_cluster(theme_name: str) -> str:
    normalized = (theme_name or "").strip()
    normalized_lower = normalized.lower()
    for rule in CLUSTER_RULES:
        if any((k in normalized) or (k.lower() in normalized_lower) for k in rule.keywords):
            return rule.name
    return "未归类"


async def _connect() -> asyncpg.Connection:
    cfg = StockServiceConfig()
    return await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )


async def _resolve_trade_date(conn: asyncpg.Connection, requested: str | None) -> date:
    if requested:
        return _parse_date(requested)
    row = await conn.fetchrow("SELECT MAX(last_review_date) AS d FROM theme_mainline_identity_registry")
    if not row or not row["d"]:
        raise RuntimeError("theme_mainline_identity_registry 无可用数据")
    return row["d"]


async def _fetch_rows(conn: asyncpg.Connection, trade_date: date) -> List[asyncpg.Record]:
    sql = """
    SELECT
        subject_key,
        theme_name,
        identity_status,
        is_main_theme,
        rule_is_main_theme,
        llm_is_main_theme,
        composite_score
    FROM theme_mainline_identity_registry
    WHERE last_review_date = $1
    ORDER BY composite_score DESC NULLS LAST, subject_key
    """
    return await conn.fetch(sql, trade_date)


def _group_rows(rows: Sequence[asyncpg.Record]) -> Dict[str, List[asyncpg.Record]]:
    grouped: Dict[str, List[asyncpg.Record]] = {}
    for r in rows:
        cname = _assign_cluster(str(r.get("theme_name") or ""))
        grouped.setdefault(cname, []).append(r)
    return grouped


def _cluster_sort_key(item: Tuple[str, List[asyncpg.Record]]) -> Tuple[int, float]:
    _, rows = item
    confirmed = sum(1 for r in rows if str(r.get("identity_status") or "") == "confirmed")
    top_score = max(float(r.get("composite_score") or 0.0) for r in rows) if rows else 0.0
    return (-confirmed, -top_score)


def _print_cluster_view(
    grouped: Dict[str, List[asyncpg.Record]],
    include_observed: bool,
    top_members: int,
) -> None:
    print("=== 主线簇视图 ===")
    items = sorted(grouped.items(), key=_cluster_sort_key)
    for cname, rows in items:
        confirmed_rows = [r for r in rows if str(r.get("identity_status") or "") == "confirmed"]
        observed_rows = [r for r in rows if str(r.get("identity_status") or "") != "confirmed"]
        if not confirmed_rows and not include_observed:
            continue
        status = "主线簇" if confirmed_rows else "观察簇"
        top_score = max(float(r.get("composite_score") or 0.0) for r in rows)
        print(
            f"[CLUSTER] {cname} | status={status} | "
            f"confirmed={len(confirmed_rows)} observed={len(observed_rows)} top_score={top_score:.2f}"
        )

        show_rows = confirmed_rows + observed_rows if include_observed else confirmed_rows
        for r in show_rows[: max(1, int(top_members))]:
            print(
                "  - "
                f"{r['subject_key']} {r['theme_name']} "
                f"status={r['identity_status']} "
                f"score={float(r.get('composite_score') or 0.0):.2f} "
                f"rule={bool(r.get('rule_is_main_theme'))} "
                f"llm={r.get('llm_is_main_theme')}"
            )


async def main_async() -> int:
    args = parse_args()
    conn = await _connect()
    try:
        trade_date = await _resolve_trade_date(conn, args.trade_date)
        rows = await _fetch_rows(conn, trade_date)
        print(f"[INFO] trade_date={trade_date.isoformat()} total_rows={len(rows)}")
        grouped = _group_rows(rows)
        _print_cluster_view(grouped, include_observed=bool(args.include_observed), top_members=int(args.top_members))
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
