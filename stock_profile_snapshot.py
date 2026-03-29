#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import psycopg2
import psycopg2.extras


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def load_stage1_candidate_stock_ids(stage1_json_path: str) -> List[str]:
    """从 Stage1 输出中提取候选股票 stock_id 列表"""
    with open(stage1_json_path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    stock_ids: List[str] = []
    seen = set()
    for event_block in rows:
        for root in event_block.get("root_theme_candidates") or []:
            for stock in root.get("root_stocks") or []:
                sid = safe_str(stock.get("stock_id"))
                if sid and sid not in seen:
                    seen.add(sid)
                    stock_ids.append(sid)
    return stock_ids


def fetch_stock_profile_map(conn, stock_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """从 stocks 表查询股票静态底座"""
    if not stock_ids:
        return {}

    sql = """
    SELECT stock_id, name AS stock_name, remark, detail_html
    FROM stocks
    WHERE stock_id = ANY(%s)
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_ids,))
        rows = list(cur.fetchall())

    return {
        safe_str(r["stock_id"]): {
            "stock_id": safe_str(r["stock_id"]),
            "stock_name": safe_str(r.get("stock_name")),
            "profile_text": "",  # 可留空或从 stock_profile_ext 补充
            "remark": safe_str(r.get("remark")),
            "detail_html_text": safe_str(r.get("detail_html")),
        }
        for r in rows
    }


def fetch_stock_lightspots_map(conn, stock_ids: List[str]) -> Dict[str, List[str]]:
    """从 stock_lightspots 表聚合 lightspots"""
    if not stock_ids:
        return {}

    sql = """
    SELECT stock_id, content
    FROM stock_lightspots
    WHERE stock_id = ANY(%s)
    ORDER BY stock_id, lightspot_id
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (stock_ids,))
        rows = list(cur.fetchall())

    out: Dict[str, List[str]] = {}
    for r in rows:
        sid = safe_str(r["stock_id"])
        content = safe_str(r.get("content"))
        if not sid or not content:
            continue
        out.setdefault(sid, []).append(content)
    return out


def build_stock_profile_snapshot(db_dsn: str, stage1_json_path: str, out_path: str) -> None:
    """导出 stock_profile_snapshot.json"""
    stock_ids = load_stage1_candidate_stock_ids(stage1_json_path)
    print(f"[INFO] stage1 candidate stock ids: {len(stock_ids)}")

    conn = psycopg2.connect(db_dsn)
    try:
        profile_map = fetch_stock_profile_map(conn, stock_ids)
        lightspots_map = fetch_stock_lightspots_map(conn, stock_ids)
    finally:
        conn.close()

    snapshot: Dict[str, Dict[str, Any]] = {}
    for sid in stock_ids:
        base = profile_map.get(sid, {
            "stock_id": sid,
            "stock_name": "",
            "profile_text": "",
            "remark": "",
            "detail_html_text": "",
        })
        lightspots = lightspots_map.get(sid, [])
        snapshot[sid] = {
            "stock_id": sid,
            "stock_name": safe_str(base.get("stock_name")),
            "profile_text": safe_str(base.get("profile_text")),
            "remark": safe_str(base.get("remark")),
            "detail_html_text": safe_str(base.get("detail_html_text")),
            "lightspots": lightspots,
        }

    Path(out_path).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] wrote: {out_path}")


if __name__ == "__main__":
    build_stock_profile_snapshot(
        db_dsn="postgresql://postgres:你的密码@127.0.0.1:5432/stock_data_test",
        stage1_json_path="root_stock_stage1_candidates_one.json",
        out_path="stock_profile_snapshot.json",
    )