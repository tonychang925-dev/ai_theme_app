"""
UniverseBuilder 覆盖策略分析脚本

对比修改前后 (old 一刀切 blocked vs new 四场景分类) 的 UniverseBuilder 输出分布。

用法:
  PG_HOST=localhost PG_PORT=5432 PG_DATABASE=stock_data_test \
  python -m stock_processing_service.tests.replay._universe_coverage_analyzer \
    --trade-date 2026-04-07

  PG_HOST=localhost PG_PORT=5432 PG_DATABASE=stock_data_test \
  python -m stock_processing_service.tests.replay._universe_coverage_analyzer \
    --trade-date 2026-04-15

  # 输出 JSON 到文件
  PG_HOST=localhost PG_PORT=5432 PG_DATABASE=stock_data_test \
  python -m stock_processing_service.tests.replay._universe_coverage_analyzer \
    --trade-date 2026-04-07 --output tmp/universe_analysis_2026-04-07.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional


# ── 模拟 Old UniverseBuilder 逻辑 (一刀切 blocked) ──

def old_build_universe(
    pool_rows: list[dict],
    identities_by_subject: dict[str, dict],
    cycles_by_subject: dict[str, dict],
) -> dict[str, Any]:
    """旧逻辑: identity is None or cycle is None → blocked"""
    formal: list[str] = []
    observe: list[str] = []
    blocked: list[str] = []
    blocked_reasons: dict[str, str] = {}

    for row in pool_rows:
        subject_key = str(row.get("subject_key") or "")
        stock_id = str(row.get("stock_id") or "")
        if not subject_key:
            blocked.append(stock_id)
            blocked_reasons[stock_id] = "missing_subject_key"
            continue

        identity = identities_by_subject.get(subject_key)
        cycle = cycles_by_subject.get(subject_key)

        # 旧逻辑: 一刀切
        if identity is None or cycle is None:
            blocked.append(stock_id)
            if identity is None and cycle is None:
                blocked_reasons[stock_id] = "missing_identity_and_cycle"
            elif identity is None:
                blocked_reasons[stock_id] = "missing_identity"
            else:
                blocked_reasons[stock_id] = "missing_cycle"
            continue

        # 有 identity 和 cycle，正常判定
        identity_confirmed = (
            str(identity.get("identity_status", "")).lower() == "confirmed"
            and bool(identity.get("is_main_theme", False))
        )
        cycle_alive = bool(cycle.get("final_mainline_alive", False))

        if identity_confirmed and cycle_alive:
            formal.append(stock_id)
        else:
            observe.append(stock_id)

    return {
        "formal": formal,
        "observe": observe,
        "blocked": blocked,
        "blocked_reasons": blocked_reasons,
    }


# ── 模拟 New UniverseBuilder 逻辑 (四场景分类) ──

# 与 strong_watch_universe.py 保持一致
_INFERRED_CYCLE_STATE = "unknown"
_INFERRED_MAINLINE_ALIVE = False


def new_build_universe(
    pool_rows: list[dict],
    identities_by_subject: dict[str, dict],
    cycles_by_subject: dict[str, dict],
) -> dict[str, Any]:
    """新逻辑: 四场景分类"""
    formal: list[str] = []
    observe: list[str] = []
    blocked: list[str] = []
    blocked_reasons: dict[str, str] = {}
    cycle_sources: dict[str, str] = {}  # subject_key → 'db' | 'inferred'
    details: dict[str, dict] = {}

    for row in pool_rows:
        subject_key = str(row.get("subject_key") or "")
        stock_id = str(row.get("stock_id") or "")
        if not subject_key:
            blocked.append(stock_id)
            blocked_reasons[stock_id] = "missing_subject_key"
            details[stock_id] = {"universe_status": "blocked", "universe_reason": "missing_subject_key"}
            continue

        identity = identities_by_subject.get(subject_key)
        cycle = cycles_by_subject.get(subject_key)
        cycle_source = "db"

        # 场景 1: identity + cycle 都缺失 → blocked
        if identity is None and cycle is None:
            blocked.append(stock_id)
            blocked_reasons[stock_id] = "missing_identity_and_cycle"
            details[stock_id] = {"universe_status": "blocked", "universe_reason": "missing_identity_and_cycle"}
            continue

        # 场景 2: identity 缺失但 cycle 存在 → blocked (罕见边界)
        if identity is None:
            blocked.append(stock_id)
            blocked_reasons[stock_id] = "missing_identity"
            details[stock_id] = {
                "universe_status": "blocked",
                "universe_reason": "missing_identity",
                "cycle_present": True,
            }
            continue

        # identity 存在, 处理 cycle 缺失
        if cycle is None:
            identity_confirmed_prelim = (
                str(identity.get("identity_status", "")).lower() == "confirmed"
                and bool(identity.get("is_main_theme", False))
            )
            if identity_confirmed_prelim:
                # 场景 3: B层覆盖缺口 → observe (推断 cycle)
                cycle = {
                    "final_cycle_state": _INFERRED_CYCLE_STATE,
                    "final_mainline_alive": _INFERRED_MAINLINE_ALIVE,
                }
                cycle_source = "inferred"
            else:
                # 场景 4: identity 非主线 + cycle 缺失 → blocked
                blocked.append(stock_id)
                blocked_reasons[stock_id] = "identity_not_mainline_and_cycle_missing"
                details[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "identity_not_mainline_and_cycle_missing",
                }
                continue

        # 正常主线判定
        identity_confirmed = (
            str(identity.get("identity_status", "")).lower() == "confirmed"
            and bool(identity.get("is_main_theme", False))
        )
        cycle_alive = bool(cycle.get("final_mainline_alive", False))

        if identity_confirmed and cycle_alive:
            formal.append(stock_id)
            details[stock_id] = {
                "universe_status": "formal",
                "universe_reason": "identity_confirmed_and_cycle_alive",
                "cycle_source": cycle_source,
            }
        else:
            observe.append(stock_id)
            details[stock_id] = {
                "universe_status": "observe",
                "universe_reason": "identity_or_cycle_not_formal",
                "cycle_source": cycle_source,
            }

        cycle_sources[stock_id] = cycle_source

    return {
        "formal": formal,
        "observe": observe,
        "blocked": blocked,
        "blocked_reasons": blocked_reasons,
        "cycle_sources": cycle_sources,
        "details": details,
    }


# ── DB 查询 ──


async def query_db(trade_date_str: str) -> dict[str, Any]:
    """从 stock_data_test 数据库查询三层数据。"""
    import asyncpg

    pg_host = os.getenv("PG_HOST", "localhost")
    pg_port = int(os.getenv("PG_PORT", "5432"))
    pg_database = os.getenv("PG_DATABASE", "stock_data_test")
    pg_user = os.getenv("PG_USERNAME", "postgres")
    pg_password = os.getenv("PG_PASSWORD", "")

    conn = await asyncpg.connect(
        host=pg_host,
        port=pg_port,
        database=pg_database,
        user=pg_user,
        password=pg_password,
    )

    try:
        trade_date_obj = date.fromisoformat(trade_date_str)

        # 1. 查询 subject_stock_daily_snapshot (新链 pool 真源)
        # 使用与 get_subject_stock_pool_by_trade_date() 相同的查询逻辑
        pool_rows = await conn.fetch(
            """
            WITH base AS (
                SELECT
                    s.trade_date,
                    s.subject_key,
                    s.subject_name,
                    s.stock_id,
                    COALESCE(NULLIF(s.stock_name, ''), m.stock_name) AS stock_name,
                    s.rank_order AS rank_order_raw,
                    COALESCE(s.close_price, m.close_price) AS close_price,
                    COALESCE(s.pct_chg, m.pct_chg) AS pct_chg,
                    s.limit_up AS limit_up_raw,
                    s.is_leader AS is_leader_raw
                FROM subject_stock_daily_snapshot s
                LEFT JOIN LATERAL (
                  SELECT stock_name, close_price, pct_chg
                  FROM stock_daily_snapshot m
                  WHERE m.trade_date = s.trade_date
                    AND m.stock_id = s.stock_id
                    AND m.source_name LIKE 'tushare%'
                  ORDER BY CASE WHEN m.source_name = 'tushare' THEN 0 ELSE 1 END, m.updated_at DESC NULLS LAST
                  LIMIT 1
                ) m ON TRUE
                WHERE s.trade_date = $1::date
                  AND COALESCE(s.stock_id, '') <> ''
            ),
            ranked AS (
                SELECT
                    trade_date,
                    subject_key,
                    subject_name,
                    stock_id,
                    stock_name,
                    COALESCE(
                        rank_order_raw,
                        DENSE_RANK() OVER (
                            PARTITION BY subject_key
                            ORDER BY pct_chg DESC NULLS LAST, stock_id
                        )
                    ) AS rank_order,
                    close_price,
                    pct_chg,
                    COALESCE(limit_up_raw, (pct_chg >= 9.5), FALSE) AS limit_up,
                    COALESCE(
                        is_leader_raw,
                        (
                            COALESCE(
                                rank_order_raw,
                                DENSE_RANK() OVER (
                                    PARTITION BY subject_key
                                    ORDER BY pct_chg DESC NULLS LAST, stock_id
                                )
                            ) <= 1
                        ),
                        FALSE
                    ) AS is_leader
                FROM base
            )
            SELECT
                trade_date,
                subject_key,
                subject_name,
                stock_id,
                stock_name,
                rank_order AS pool_rank,
                close_price,
                pct_chg,
                limit_up,
                is_leader
            FROM ranked
            ORDER BY subject_key, rank_order ASC, stock_id
            """,
            trade_date_obj,
        )
        pool_list = [dict(r) for r in pool_rows]
        print(f"[DB] subject_stock_daily_snapshot (pool): {len(pool_list)} rows")

        # 获取所有 distinct subject_keys
        all_subject_keys = sorted({str(r["subject_key"]) for r in pool_rows if r["subject_key"]})
        print(f"[DB] distinct subject_keys: {len(all_subject_keys)}")

        # 2. 查询 theme_mainline_identity_registry
        identity_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (subject_key)
                subject_key,
                COALESCE(identity_status, '') AS identity_status,
                COALESCE(is_main_theme, FALSE) AS is_main_theme,
                first_confirmed_date,
                last_review_date,
                COALESCE(rule_version, '') AS rule_version
            FROM theme_mainline_identity_registry
            WHERE subject_key = ANY($1::text[])
              AND (
                last_review_date IS NULL
                OR last_review_date <= $2::date
              )
              AND (
                first_confirmed_date IS NULL
                OR first_confirmed_date <= $2::date
              )
            ORDER BY subject_key, last_review_date DESC NULLS LAST, updated_at DESC NULLS LAST
            """,
            all_subject_keys,
            trade_date_obj,
        )
        identity_list = [dict(r) for r in identity_rows]
        print(f"[DB] theme_mainline_identity_registry: {len(identity_list)} rows (matched)")

        # 3. 查询 theme_cycle_judgement_v2
        # 先检查表是否存在
        table_check = await conn.fetch(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'theme_cycle_judgement_v2'
            )
            """
        )
        table_exists = table_check[0]["exists"]

        cycle_list: list[dict] = []
        if table_exists:
            # 检测表中实际存在的列（该表在不同环境中列可能不同）
            cols = await conn.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'theme_cycle_judgement_v2'
                """
            )
            col_set = {str(r["column_name"]) for r in cols}

            def _col(name: str, fallback: str) -> str:
                return name if name in col_set else fallback

            cycle_sql = f"""
                SELECT trade_date, subject_key,
                       {_col('final_cycle_state', "''::text")} AS final_cycle_state,
                       {_col('final_mainline_alive', 'FALSE')} AS final_mainline_alive,
                       {_col('confidence_score', '0::numeric')} AS transition_confidence,
                       {_col('mainline_strength_score', '0::numeric')} AS mainline_strength_score,
                       {_col('fade_watch_score', '0::numeric')} AS fade_watch_score,
                       {_col('fade_confirmed_score', '0::numeric')} AS fade_confirmed_score
                FROM theme_cycle_judgement_v2
                WHERE trade_date = $1::date
                  AND subject_key = ANY($2::text[])
                ORDER BY subject_key
                """
            cycle_rows = await conn.fetch(
                cycle_sql,
                trade_date_obj,
                all_subject_keys,
            )
            cycle_list = [dict(r) for r in cycle_rows]
            print(f"[DB] theme_cycle_judgement_v2: {len(cycle_list)} rows (matched, table_exists={table_exists})")
        else:
            print(f"[DB] theme_cycle_judgement_v2: table does not exist")

        return {
            "pool_rows": pool_list,
            "all_subject_keys": all_subject_keys,
            "identity_rows": identity_list,
            "cycle_rows": cycle_list,
            "cycle_table_exists": table_exists,
        }

    finally:
        await conn.close()


# ── 统计分析 ──


def analyze(db_data: dict[str, Any]) -> dict[str, Any]:
    """运行 old vs new UniverseBuilder 并输出对比统计。"""
    pool_rows = db_data["pool_rows"]
    identity_rows = db_data["identity_rows"]
    cycle_rows = db_data["cycle_rows"]
    all_subject_keys = db_data["all_subject_keys"]

    # 构建 lookup dict
    identities_by_subject: dict[str, dict] = {
        str(r["subject_key"]): r for r in identity_rows
    }
    cycles_by_subject: dict[str, dict] = {
        str(r["subject_key"]): r for r in cycle_rows
    }

    # ── 运行 old 逻辑 ──
    old_result = old_build_universe(pool_rows, identities_by_subject, cycles_by_subject)

    # ── 运行 new 逻辑 ──
    new_result = new_build_universe(pool_rows, identities_by_subject, cycles_by_subject)

    # ── 分析 identity 分布 ──
    identity_status_dist: dict[str, int] = {}
    identity_main_theme_count = 0
    for r in identity_rows:
        st = str(r.get("identity_status", "")).lower() or "empty"
        identity_status_dist[st] = identity_status_dist.get(st, 0) + 1
        if bool(r.get("is_main_theme", False)):
            identity_main_theme_count += 1

    # ── 分析 cycle 分布 ──
    cycle_state_dist: dict[str, int] = {}
    cycle_alive_count = 0
    for r in cycle_rows:
        st = str(r.get("final_cycle_state", "")).lower() or "empty"
        cycle_state_dist[st] = cycle_state_dist.get(st, 0) + 1
        if bool(r.get("final_mainline_alive", False)):
            cycle_alive_count += 1

    # ── 关键: 已确认主线 + 缺 cycle 的 subject_keys ──
    confirmed_mainline_no_cycle: list[str] = []
    confirmed_mainline_with_cycle: list[str] = []
    for sk in all_subject_keys:
        identity = identities_by_subject.get(sk)
        cycle = cycles_by_subject.get(sk)
        if identity and str(identity.get("identity_status", "")).lower() == "confirmed" and bool(identity.get("is_main_theme", False)):
            if cycle is None:
                confirmed_mainline_no_cycle.append(sk)
            else:
                confirmed_mainline_with_cycle.append(sk)

    # ── 新旧 blocked 差异 (迁移的 stock_ids) ──
    old_blocked_set = set(old_result["blocked"])
    new_blocked_set = set(new_result["blocked"])
    migrated_blocked_to_observe = old_blocked_set - new_blocked_set
    newly_blocked = new_blocked_set - old_blocked_set

    # 按 reason 分类 old blocked
    old_blocked_reason_dist: dict[str, int] = {}
    for reason in old_result["blocked_reasons"].values():
        old_blocked_reason_dist[reason] = old_blocked_reason_dist.get(reason, 0) + 1

    new_blocked_reason_dist: dict[str, int] = {}
    for reason in new_result["blocked_reasons"].values():
        new_blocked_reason_dist[reason] = new_blocked_reason_dist.get(reason, 0) + 1

    # ── 按 subject_key 维度统计 (去重) ──
    # 每个 subject_key 可能有多只股票，按 subject_key 聚合统计
    subject_universe_status: dict[str, str] = {}  # subject_key → formal|observe|blocked
    subject_cycle_source: dict[str, str] = {}  # subject_key → db|inferred (仅 new logic)

    # New logic subject-level status (取第一个 row 的 status)
    for row in pool_rows:
        sk = str(row.get("subject_key") or "")
        sid = str(row.get("stock_id") or "")
        if sk and sk not in subject_universe_status:
            detail = new_result["details"].get(sid, {})
            subject_universe_status[sk] = detail.get("universe_status", "blocked")
            subject_cycle_source[sk] = detail.get("cycle_source", "n/a")

    # Old logic subject-level status
    old_subject_status: dict[str, str] = {}
    for row in pool_rows:
        sk = str(row.get("subject_key") or "")
        sid = str(row.get("stock_id") or "")
        if sk and sk not in old_subject_status:
            if sid in old_blocked_set:
                old_subject_status[sk] = "blocked"
            elif sid in set(old_result["observe"]):
                old_subject_status[sk] = "observe"
            else:
                old_subject_status[sk] = "formal"

    # Subject 级别迁移统计
    subject_migrated = {
        sk for sk in all_subject_keys
        if old_subject_status.get(sk) == "blocked" and subject_universe_status.get(sk) != "blocked"
    }

    # 迁移的 subject 明细
    migration_details: list[dict] = []
    for sk in sorted(subject_migrated):
        identity = identities_by_subject.get(sk, {})
        migration_details.append({
            "subject_key": sk,
            "old_status": old_subject_status.get(sk),
            "new_status": subject_universe_status.get(sk),
            "cycle_source": subject_cycle_source.get(sk),
            "identity_status": identity.get("identity_status", "n/a"),
            "is_main_theme": identity.get("is_main_theme", False),
        })

    # ── 构建输出 ──
    return {
        "meta": {
            "trade_date": db_data["pool_rows"][0]["trade_date"] if db_data["pool_rows"] else "unknown",
            "total_pool_rows": len(pool_rows),
            "distinct_subject_keys": len(all_subject_keys),
            "identity_hit": len(identity_rows),
            "identity_coverage_pct": round(len(identity_rows) / max(len(all_subject_keys), 1) * 100, 1),
            "cycle_hit": len(cycle_rows),
            "cycle_coverage_pct": round(len(cycle_rows) / max(len(all_subject_keys), 1) * 100, 1),
            "cycle_table_exists": db_data["cycle_table_exists"],
        },
        "identity_distribution": {
            "by_status": identity_status_dist,
            "is_main_theme_count": identity_main_theme_count,
            "confirmed_mainline_no_cycle_count": len(confirmed_mainline_no_cycle),
            "confirmed_mainline_with_cycle_count": len(confirmed_mainline_with_cycle),
            "confirmed_mainline_no_cycle_keys": confirmed_mainline_no_cycle[:20],  # 前 20 个
        },
        "cycle_distribution": {
            "by_state": cycle_state_dist,
            "alive_count": cycle_alive_count,
        },
        "old_logic": {
            "formal_count": len(old_result["formal"]),
            "observe_count": len(old_result["observe"]),
            "blocked_count": len(old_result["blocked"]),
            "blocked_reason_distribution": old_blocked_reason_dist,
            "subject_level": {
                "formal": sum(1 for v in old_subject_status.values() if v == "formal"),
                "observe": sum(1 for v in old_subject_status.values() if v == "observe"),
                "blocked": sum(1 for v in old_subject_status.values() if v == "blocked"),
            },
        },
        "new_logic": {
            "formal_count": len(new_result["formal"]),
            "observe_count": len(new_result["observe"]),
            "blocked_count": len(new_result["blocked"]),
            "blocked_reason_distribution": new_blocked_reason_dist,
            "inferred_cycle_count": sum(1 for v in new_result["cycle_sources"].values() if v == "inferred"),
            "db_cycle_count": sum(1 for v in new_result["cycle_sources"].values() if v == "db"),
            "subject_level": {
                "formal": sum(1 for v in subject_universe_status.values() if v == "formal"),
                "observe": sum(1 for v in subject_universe_status.values() if v == "observe"),
                "blocked": sum(1 for v in subject_universe_status.values() if v == "blocked"),
            },
        },
        "migration": {
            "stocks_migrated_blocked_to_observe": len(migrated_blocked_to_observe),
            "stocks_newly_blocked": len(newly_blocked),
            "subjects_migrated": len(subject_migrated),
            "subject_migration_details": migration_details[:30],  # 前 30 个
            "sample_migrated_stock_ids": sorted(migrated_blocked_to_observe)[:20],
        },
        "delta": {
            "formal_delta": len(new_result["formal"]) - len(old_result["formal"]),
            "observe_delta": len(new_result["observe"]) - len(old_result["observe"]),
            "blocked_delta": len(new_result["blocked"]) - len(old_result["blocked"]),
            "subject_formal_delta": (
                sum(1 for v in subject_universe_status.values() if v == "formal")
                - sum(1 for v in old_subject_status.values() if v == "formal")
            ),
            "subject_observe_delta": (
                sum(1 for v in subject_universe_status.values() if v == "observe")
                - sum(1 for v in old_subject_status.values() if v == "observe")
            ),
            "subject_blocked_delta": (
                sum(1 for v in subject_universe_status.values() if v == "blocked")
                - sum(1 for v in old_subject_status.values() if v == "blocked")
            ),
        },
    }


# ── CLI ──


def main():
    parser = argparse.ArgumentParser(description="UniverseBuilder 覆盖策略分析")
    parser.add_argument("--trade-date", required=True, help="交易日期 YYYY-MM-DD")
    parser.add_argument("--output", "-o", help="JSON 输出文件路径 (可选)")
    args = parser.parse_args()

    trade_date_str = args.trade_date

    print(f"=" * 60)
    print(f"UniverseBuilder 覆盖策略分析 — {trade_date_str}")
    print(f"=" * 60)

    db_data = asyncio.run(query_db(trade_date_str))

    print()
    result = analyze(db_data)

    # 打印摘要
    meta = result["meta"]
    print(f"\n── 数据概况 ──")
    print(f"  Pool rows:        {meta['total_pool_rows']}")
    print(f"  Distinct subjects: {meta['distinct_subject_keys']}")
    print(f"  Identity hit:     {meta['identity_hit']} ({meta['identity_coverage_pct']}%)")
    print(f"  Cycle hit:        {meta['cycle_hit']} ({meta['cycle_coverage_pct']}%)")

    ident = result["identity_distribution"]
    print(f"\n── Identity 分布 ──")
    for st, cnt in sorted(ident["by_status"].items(), key=lambda x: -x[1]):
        print(f"  {st}: {cnt}")
    print(f"  is_main_theme=True: {ident['is_main_theme_count']}")
    print(f"  confirmed mainline + no cycle: {ident['confirmed_mainline_no_cycle_count']}")
    print(f"  confirmed mainline + with cycle: {ident['confirmed_mainline_with_cycle_count']}")

    cycle = result["cycle_distribution"]
    print(f"\n── Cycle 分布 ──")
    for st, cnt in sorted(cycle["by_state"].items(), key=lambda x: -x[1]):
        print(f"  {st}: {cnt}")
    print(f"  alive_count: {cycle['alive_count']}")

    print(f"\n── Old Logic (一刀切 blocked) ──")
    old = result["old_logic"]
    print(f"  formal:  {old['formal_count']}")
    print(f"  observe: {old['observe_count']}")
    print(f"  blocked: {old['blocked_count']}")
    print(f"  blocked reasons: {old['blocked_reason_distribution']}")
    print(f"  Subject level — formal:{old['subject_level']['formal']} observe:{old['subject_level']['observe']} blocked:{old['subject_level']['blocked']}")

    print(f"\n── New Logic (四场景分类) ──")
    new = result["new_logic"]
    print(f"  formal:  {new['formal_count']}")
    print(f"  observe: {new['observe_count']}")
    print(f"  blocked: {new['blocked_count']}")
    print(f"  blocked reasons: {new['blocked_reason_distribution']}")
    print(f"  inferred cycle: {new['inferred_cycle_count']}")
    print(f"  db cycle:       {new['db_cycle_count']}")
    print(f"  Subject level — formal:{new['subject_level']['formal']} observe:{new['subject_level']['observe']} blocked:{new['subject_level']['blocked']}")

    print(f"\n── Delta (New - Old) ──")
    delta = result["delta"]
    print(f"  formal:  {delta['formal_delta']:+d}")
    print(f"  observe: {delta['observe_delta']:+d}")
    print(f"  blocked: {delta['blocked_delta']:+d}")
    print(f"  (subject) formal:  {delta['subject_formal_delta']:+d}")
    print(f"  (subject) observe: {delta['subject_observe_delta']:+d}")
    print(f"  (subject) blocked: {delta['subject_blocked_delta']:+d}")

    mig = result["migration"]
    print(f"\n── Migration ──")
    print(f"  stocks migrated (blocked→observe): {mig['stocks_migrated_blocked_to_observe']}")
    print(f"  stocks newly blocked:              {mig['stocks_newly_blocked']}")
    print(f"  subjects migrated:                 {mig['subjects_migrated']}")
    if mig["subject_migration_details"]:
        print(f"  First 10 migrated subjects:")
        for d in mig["subject_migration_details"][:10]:
            print(f"    {d['subject_key']}: {d['old_status']}→{d['new_status']} "
                  f"(identity={d['identity_status']}, main_theme={d['is_main_theme']}, "
                  f"cycle_source={d['cycle_source']})")

    # 输出 JSON
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        # 转换 date 等不可序列化类型
        def _serialize(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return str(obj)
            return str(obj)

        json_str = json.dumps(result, indent=2, default=_serialize, ensure_ascii=False)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"\nJSON output written to: {args.output}")


if __name__ == "__main__":
    main()
