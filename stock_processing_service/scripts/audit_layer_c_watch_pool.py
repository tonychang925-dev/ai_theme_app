#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg


@dataclass
class AuditRow:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    subject_name: str
    watch_status: str
    watch_score: float
    strong_grade: str
    pool_entry_type: str
    support_type: str
    support_score: float
    gap_hit: bool
    gap_hit_mode: str


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in {"1", "true", "t", "yes", "y"}:
        return True
    if s in {"0", "false", "f", "no", "n"}:
        return False
    return default


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = 'public' AND table_name = $1
        ) AS ok
        """,
        table,
    )
    return bool(row and row["ok"])


async def _table_columns(conn: asyncpg.Connection, table: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {str(r["column_name"]) for r in rows}


async def _fetch_watch_rows_from_recap(conn: asyncpg.Connection, trade_date: date) -> list[AuditRow]:
    cols = await _table_columns(conn, "post_market_recap_snapshot")
    if "recap_doc" in cols:
        history_expr = "COALESCE(p.recap_doc->'strong_watch_history', '[]'::jsonb)"
    elif "payload" in cols:
        # 兼容两种写法：payload.recap_doc.strong_watch_history 或 payload.strong_watch_history
        history_expr = (
            "COALESCE(p.payload->'recap_doc'->'strong_watch_history', "
            "p.payload->'strong_watch_history', '[]'::jsonb)"
        )
    else:
        return []

    rows = await conn.fetch(
        f"""
        SELECT
          p.trade_date::text AS trade_date,
          h
        FROM post_market_recap_snapshot p,
             LATERAL jsonb_array_elements({history_expr}) AS h
        WHERE p.trade_date = $1::date
        """,
        trade_date,
    )

    result: list[AuditRow] = []
    for r in rows:
        h = r["h"]
        if not isinstance(h, dict):
            continue
        result.append(
            AuditRow(
                trade_date=str(r["trade_date"]),
                stock_id=str(h.get("stock_id") or ""),
                stock_name=str(h.get("stock_name") or ""),
                subject_key=str(h.get("subject_key") or ""),
                subject_name=str(h.get("subject_name") or ""),
                watch_status=str(h.get("watch_status") or ""),
                watch_score=_to_float(h.get("watch_score")),
                strong_grade=str(h.get("strong_grade") or ""),
                pool_entry_type=str(h.get("pool_entry_type") or ""),
                support_type=str(h.get("support_type") or ""),
                support_score=_to_float(h.get("support_score")),
                gap_hit=_to_bool(h.get("gap_hit")),
                gap_hit_mode=str(h.get("gap_hit_mode") or ""),
            )
        )
    return result


async def _fetch_watch_rows_from_subject_pool(conn: asyncpg.Connection, trade_date: date) -> list[AuditRow]:
    rows = await conn.fetch(
        """
        SELECT
          trade_date::text AS trade_date,
          stock_id,
          COALESCE(stock_name, '') AS stock_name,
          COALESCE(subject_key, '') AS subject_key,
          ''::text AS subject_name,
          CASE WHEN COALESCE(rank_order, 999) <= 30 THEN 'seed_selected' ELSE 'seed_rejected' END AS watch_status,
          0::numeric AS watch_score,
          ''::text AS strong_grade,
          ''::text AS pool_entry_type,
          ''::text AS support_type,
          0::numeric AS support_score,
          FALSE AS gap_hit,
          ''::text AS gap_hit_mode
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND COALESCE(rank_order, 999) <= 30
        ORDER BY subject_key, rank_order, stock_id
        """,
        trade_date,
    )
    return [
        AuditRow(
            trade_date=str(r["trade_date"]),
            stock_id=str(r["stock_id"]),
            stock_name=str(r["stock_name"]),
            subject_key=str(r["subject_key"]),
            subject_name=str(r["subject_name"]),
            watch_status=str(r["watch_status"]),
            watch_score=_to_float(r["watch_score"]),
            strong_grade=str(r["strong_grade"]),
            pool_entry_type=str(r["pool_entry_type"]),
            support_type=str(r["support_type"]),
            support_score=_to_float(r["support_score"]),
            gap_hit=_to_bool(r["gap_hit"]),
            gap_hit_mode=str(r["gap_hit_mode"]),
        )
        for r in rows
    ]


async def _fetch_identity_map(conn: asyncpg.Connection) -> dict[str, dict[str, Any]]:
    if not await _table_exists(conn, "theme_mainline_identity_registry"):
        return {}

    cols = await _table_columns(conn, "theme_mainline_identity_registry")
    has_trade_date = "trade_date" in cols
    has_updated_at = "updated_at" in cols

    id_col = "identity_status" if "identity_status" in cols else "''::text AS identity_status"
    main_col = "is_main_theme" if "is_main_theme" in cols else "FALSE AS is_main_theme"
    rv_col = "rule_version" if "rule_version" in cols else "''::text AS rule_version"

    if has_trade_date:
        sql = f"""
        SELECT DISTINCT ON (subject_key)
          COALESCE(subject_key, '') AS subject_key,
          {id_col} AS identity_status,
          {main_col} AS is_main_theme,
          {rv_col} AS rule_version
        FROM theme_mainline_identity_registry
        ORDER BY subject_key, trade_date DESC
        """
    elif has_updated_at:
        sql = f"""
        SELECT DISTINCT ON (subject_key)
          COALESCE(subject_key, '') AS subject_key,
          {id_col} AS identity_status,
          {main_col} AS is_main_theme,
          {rv_col} AS rule_version
        FROM theme_mainline_identity_registry
        ORDER BY subject_key, updated_at DESC
        """
    else:
        sql = f"""
        SELECT
          COALESCE(subject_key, '') AS subject_key,
          {id_col} AS identity_status,
          {main_col} AS is_main_theme,
          {rv_col} AS rule_version
        FROM theme_mainline_identity_registry
        """

    rows = await conn.fetch(sql)
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        sk = str(r["subject_key"])
        out[sk] = {
            "identity_status": str(r.get("identity_status") or ""),
            "is_main_theme": _to_bool(r.get("is_main_theme")),
            "rule_version": str(r.get("rule_version") or ""),
        }
    return out


async def _fetch_cycle_map(conn: asyncpg.Connection, trade_date: date) -> dict[str, dict[str, Any]]:
    if not await _table_exists(conn, "theme_cycle_judgement_v2"):
        return {}
    cols = await _table_columns(conn, "theme_cycle_judgement_v2")

    def col(name: str, fallback: str) -> str:
        return name if name in cols else fallback

    sql = f"""
    SELECT
      COALESCE(subject_key, '') AS subject_key,
      {col('final_cycle_state', "''::text")} AS final_cycle_state,
      {col('final_mainline_alive', 'FALSE')} AS final_mainline_alive,
      {col('mainline_strength_score', '0::numeric')} AS mainline_strength_score,
      {col('repair_score', '0::numeric')} AS repair_score,
      {col('divergence_score', '0::numeric')} AS divergence_score,
      {col('fade_watch_score', '0::numeric')} AS fade_watch_score,
      {col('fade_confirmed_score', '0::numeric')} AS fade_confirmed_score
    FROM theme_cycle_judgement_v2
    WHERE trade_date = $1::date
    """
    rows = await conn.fetch(sql, trade_date)
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        sk = str(r["subject_key"])
        out[sk] = {
            "final_cycle_state": str(r.get("final_cycle_state") or ""),
            "final_mainline_alive": _to_bool(r.get("final_mainline_alive")),
            "mainline_strength_score": _to_float(r.get("mainline_strength_score")),
            "repair_score": _to_float(r.get("repair_score")),
            "divergence_score": _to_float(r.get("divergence_score")),
            "fade_watch_score": _to_float(r.get("fade_watch_score")),
            "fade_confirmed_score": _to_float(r.get("fade_confirmed_score")),
        }
    return out


async def _fetch_subject_day_stats(conn: asyncpg.Connection, trade_date: date) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
          COALESCE(subject_key, '') AS subject_key,
          COUNT(*) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS subject_limit_up_count,
          COUNT(*) FILTER (
            WHERE COALESCE(limit_up, FALSE) = TRUE
               OR COALESCE(is_leader, FALSE) = TRUE
               OR COALESCE(rank_order, 999) <= 3
               OR COALESCE(pct_chg, 0) >= 7.0
          ) AS subject_strong_count
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
        GROUP BY subject_key
        """,
        trade_date,
    )
    return {
        str(r["subject_key"]): {
            "subject_limit_up_count": int(r["subject_limit_up_count"] or 0),
            "subject_strong_count": int(r["subject_strong_count"] or 0),
        }
        for r in rows
    }


async def _fetch_stock_day_map(conn: asyncpg.Connection, trade_date: date) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
          COALESCE(stock_id, '') AS stock_id,
          COALESCE(stock_name, '') AS stock_name,
          COALESCE(subject_key, '') AS subject_key,
          COALESCE(rank_order, 999) AS rank_order,
          COALESCE(pct_chg, 0) AS pct_chg,
          COALESCE(limit_up, FALSE) AS limit_up,
          COALESCE(is_leader, FALSE) AS is_leader
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
        """,
        trade_date,
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[str(r["stock_id"])] = {
            "stock_name": str(r["stock_name"] or ""),
            "subject_key": str(r["subject_key"] or ""),
            "rank_order": int(r["rank_order"] or 999),
            "pct_chg": _to_float(r["pct_chg"]),
            "limit_up": _to_bool(r["limit_up"]),
            "is_leader": _to_bool(r["is_leader"]),
        }
    return out


async def _fetch_prior7_map(conn: asyncpg.Connection, trade_date: date) -> dict[tuple[str, str], dict[str, int]]:
    start = trade_date - timedelta(days=7)
    rows = await conn.fetch(
        """
        SELECT
          COALESCE(stock_id, '') AS stock_id,
          COALESCE(subject_key, '') AS subject_key,
          COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS prior7_limitup_days,
          COUNT(DISTINCT trade_date) FILTER (
            WHERE COALESCE(limit_up, FALSE) = TRUE
               OR COALESCE(is_leader, FALSE) = TRUE
               OR COALESCE(rank_order, 999) <= 3
               OR COALESCE(pct_chg, 0) >= 7.0
          ) AS prior7_strong_days
        FROM subject_stock_daily_snapshot
        WHERE trade_date < $1::date
          AND trade_date >= $2::date
        GROUP BY stock_id, subject_key
        """,
        trade_date,
        start,
    )
    out: dict[tuple[str, str], dict[str, int]] = {}
    for r in rows:
        out[(str(r["stock_id"]), str(r["subject_key"]))] = {
            "prior7_limitup_days": int(r["prior7_limitup_days"] or 0),
            "prior7_strong_days": int(r["prior7_strong_days"] or 0),
        }
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in headers})


def _make_identity_rows(base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in base_rows:
        out.append(
            {
                "trade_date": r["trade_date"],
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"],
                "subject_key": r["subject_key"],
                "subject_name": r["subject_name"],
                "watch_status": r["watch_status"],
                "watch_score": r["watch_score"],
                "strong_grade": r["strong_grade"],
                "pool_entry_type": r["pool_entry_type"],
                "identity_status": r["identity_status"],
                "is_main_theme": r["is_main_theme"],
                "identity_confirmed_pass": r["identity_confirmed_pass"],
                "identity_rule_version": r["identity_rule_version"],
            }
        )
    return out


def _make_cycle_rows(base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in base_rows:
        out.append(
            {
                "trade_date": r["trade_date"],
                "stock_id": r["stock_id"],
                "subject_key": r["subject_key"],
                "subject_name": r["subject_name"],
                "final_cycle_state": r["final_cycle_state"],
                "final_mainline_alive": r["final_mainline_alive"],
                "state_transition_type": "",
                "cycle_score_mainline_strength": r["mainline_strength_score"],
                "cycle_score_repair": r["repair_score"],
                "cycle_score_divergence": r["divergence_score"],
                "cycle_score_fade_watch": r["fade_watch_score"],
                "cycle_score_fade_confirmed": r["fade_confirmed_score"],
                "cycle_alive_pass": r["cycle_alive_pass"],
            }
        )
    return out


def _make_gate_rows(base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in base_rows:
        out.append(
            {
                "trade_date": r["trade_date"],
                "stock_id": r["stock_id"],
                "stock_name": r["stock_name"],
                "subject_key": r["subject_key"],
                "subject_name": r["subject_name"],
                "limitup_gene_pass": r["limitup_gene_pass"],
                "theme_synergy_pass": r["theme_synergy_pass"],
                "volume_price_health_pass": r["volume_price_health_pass"],
                "structure_health_pass": r["structure_health_pass"],
                "pass_count_4of3": r["pass_count_4of3"],
                "reject_no_limitup_gene": r["reject_no_limitup_gene"],
                "reject_isolated_theme": r["reject_isolated_theme"],
                "reject_break_support_with_heavy_drop": r["reject_break_support_with_heavy_drop"],
                "watch_status": r["watch_status"],
                "watch_score": r["watch_score"],
                "strong_grade": r["strong_grade"],
                "promoted_to_formal": r["promoted_to_formal"],
                "support_type": r["support_type"],
                "support_score": r["support_score"],
                "gap_hit": r["gap_hit"],
                "gap_hit_mode": r["gap_hit_mode"],
                "prior7_limitup_days": r["prior7_limitup_days"],
                "prior7_strong_days": r["prior7_strong_days"],
            }
        )
    return out


async def _audit_one_date(conn: asyncpg.Connection, trade_date: date, out_dir: Path) -> dict[str, Any]:
    source = "recap_strong_watch_history"
    watch_rows = []
    if await _table_exists(conn, "post_market_recap_snapshot"):
        watch_rows = await _fetch_watch_rows_from_recap(conn, trade_date)
    if not watch_rows:
        source = "subject_pool_rank_le_30_seed_proxy"
        watch_rows = await _fetch_watch_rows_from_subject_pool(conn, trade_date)

    identity_map = await _fetch_identity_map(conn)
    cycle_map = await _fetch_cycle_map(conn, trade_date)
    subject_stats = await _fetch_subject_day_stats(conn, trade_date)
    stock_day_map = await _fetch_stock_day_map(conn, trade_date)
    prior7_map = await _fetch_prior7_map(conn, trade_date)

    merged: list[dict[str, Any]] = []
    for w in watch_rows:
        subject_key = w.subject_key or stock_day_map.get(w.stock_id, {}).get("subject_key", "")
        day = stock_day_map.get(w.stock_id, {})

        idt = identity_map.get(subject_key, {})
        cyc = cycle_map.get(subject_key, {})
        sub = subject_stats.get(subject_key, {})
        p7 = prior7_map.get((w.stock_id, subject_key), {"prior7_limitup_days": 0, "prior7_strong_days": 0})

        identity_status = str(idt.get("identity_status") or "")
        is_main_theme = bool(idt.get("is_main_theme") or False)
        identity_confirmed_pass = identity_status.lower() == "confirmed" and is_main_theme

        final_mainline_alive = bool(cyc.get("final_mainline_alive") or False)
        cycle_alive_pass = final_mainline_alive

        pct_chg = _to_float(day.get("pct_chg"), 0.0)
        rank_order = int(day.get("rank_order") or 999)
        limit_up = bool(day.get("limit_up") or False)
        is_leader = bool(day.get("is_leader") or False)

        prior7_limitup_days = int(p7.get("prior7_limitup_days") or 0)
        prior7_strong_days = int(p7.get("prior7_strong_days") or 0)

        subject_limit_up_count = int(sub.get("subject_limit_up_count") or 0)
        subject_strong_count = int(sub.get("subject_strong_count") or 0)

        # 审计口径（v0）：尽量贴近旧链语义，但只使用当前可用字段
        limitup_gene_pass = prior7_limitup_days >= 1
        theme_synergy_pass = final_mainline_alive and (subject_limit_up_count >= 2 or subject_strong_count >= 3)
        volume_price_health_pass = bool(limit_up or pct_chg >= 2.0 or (-5.0 <= pct_chg <= 0.0))
        structure_health_pass = (
            w.support_type in {"gap_support", "previous_low", "prev_low_support", "platform_support", "ma_support"}
            and _to_float(w.support_score) >= 55.0
        )
        pass_count_4of3 = int(limitup_gene_pass) + int(theme_synergy_pass) + int(volume_price_health_pass) + int(structure_health_pass)

        reject_no_limitup_gene = not limitup_gene_pass
        reject_isolated_theme = not theme_synergy_pass
        reject_break_support_with_heavy_drop = (not structure_health_pass) and pct_chg <= -6.0
        promoted_to_formal = w.watch_status in {"active", "weakening_keep", "weakening"}

        merged.append(
            {
                "trade_date": w.trade_date,
                "stock_id": w.stock_id,
                "stock_name": w.stock_name or str(day.get("stock_name") or ""),
                "subject_key": subject_key,
                "subject_name": w.subject_name,
                "watch_status": w.watch_status,
                "watch_score": round(w.watch_score, 6),
                "strong_grade": w.strong_grade,
                "pool_entry_type": w.pool_entry_type,
                "support_type": w.support_type,
                "support_score": round(w.support_score, 4),
                "gap_hit": w.gap_hit,
                "gap_hit_mode": w.gap_hit_mode,
                "identity_status": identity_status,
                "is_main_theme": is_main_theme,
                "identity_confirmed_pass": identity_confirmed_pass,
                "identity_rule_version": str(idt.get("rule_version") or ""),
                "final_cycle_state": str(cyc.get("final_cycle_state") or ""),
                "final_mainline_alive": final_mainline_alive,
                "mainline_strength_score": _to_float(cyc.get("mainline_strength_score")),
                "repair_score": _to_float(cyc.get("repair_score")),
                "divergence_score": _to_float(cyc.get("divergence_score")),
                "fade_watch_score": _to_float(cyc.get("fade_watch_score")),
                "fade_confirmed_score": _to_float(cyc.get("fade_confirmed_score")),
                "cycle_alive_pass": cycle_alive_pass,
                "prior7_limitup_days": prior7_limitup_days,
                "prior7_strong_days": prior7_strong_days,
                "limitup_gene_pass": limitup_gene_pass,
                "theme_synergy_pass": theme_synergy_pass,
                "volume_price_health_pass": volume_price_health_pass,
                "structure_health_pass": structure_health_pass,
                "pass_count_4of3": pass_count_4of3,
                "reject_no_limitup_gene": reject_no_limitup_gene,
                "reject_isolated_theme": reject_isolated_theme,
                "reject_break_support_with_heavy_drop": reject_break_support_with_heavy_drop,
                "promoted_to_formal": promoted_to_formal,
                "rank_order": rank_order,
                "pct_chg": pct_chg,
                "limit_up": limit_up,
                "is_leader": is_leader,
                "subject_limit_up_count": subject_limit_up_count,
                "subject_strong_count": subject_strong_count,
            }
        )

    identity_rows = _make_identity_rows(merged)
    cycle_rows = _make_cycle_rows(merged)
    gate_rows = _make_gate_rows(merged)

    _write_csv(
        out_dir / "layer_c_identity_audit.csv",
        identity_rows,
        [
            "trade_date",
            "stock_id",
            "stock_name",
            "subject_key",
            "subject_name",
            "watch_status",
            "watch_score",
            "strong_grade",
            "pool_entry_type",
            "identity_status",
            "is_main_theme",
            "identity_confirmed_pass",
            "identity_rule_version",
        ],
    )
    _write_csv(
        out_dir / "layer_c_cycle_audit.csv",
        cycle_rows,
        [
            "trade_date",
            "stock_id",
            "subject_key",
            "subject_name",
            "final_cycle_state",
            "final_mainline_alive",
            "state_transition_type",
            "cycle_score_mainline_strength",
            "cycle_score_repair",
            "cycle_score_divergence",
            "cycle_score_fade_watch",
            "cycle_score_fade_confirmed",
            "cycle_alive_pass",
        ],
    )
    _write_csv(
        out_dir / "layer_c_watch_gate_audit.csv",
        gate_rows,
        [
            "trade_date",
            "stock_id",
            "stock_name",
            "subject_key",
            "subject_name",
            "limitup_gene_pass",
            "theme_synergy_pass",
            "volume_price_health_pass",
            "structure_health_pass",
            "pass_count_4of3",
            "reject_no_limitup_gene",
            "reject_isolated_theme",
            "reject_break_support_with_heavy_drop",
            "watch_status",
            "watch_score",
            "strong_grade",
            "promoted_to_formal",
            "support_type",
            "support_score",
            "gap_hit",
            "gap_hit_mode",
            "prior7_limitup_days",
            "prior7_strong_days",
        ],
    )

    kept_pool = [r for r in merged if r["watch_status"] != "removed"]
    summary = {
        "source": source,
        "formal_pool_count": len(kept_pool),
        "identity_fail_count": sum(1 for r in kept_pool if not r["identity_confirmed_pass"]),
        "cycle_alive_fail_count": sum(1 for r in kept_pool if not r["cycle_alive_pass"]),
        "pass_4of3_fail_count": sum(1 for r in kept_pool if r["pass_count_4of3"] < 3),
        "total_rows": len(merged),
    }

    return {
        "summary": summary,
        "rows": merged,
    }


async def _print_samples(conn: asyncpg.Connection, sample_specs: list[str]) -> None:
    if not sample_specs:
        return
    print("\n[Layer C Target Samples]")
    for spec in sample_specs:
        try:
            d, sid = spec.split(":", 1)
            td = _parse_date(d)
            stock_id = sid.strip()
        except Exception:
            print(f"- invalid sample spec: {spec} (expected YYYY-MM-DD:STOCK_ID)")
            continue

        out = await _audit_one_date(conn, td, Path("/tmp/layer_c_sample_tmp"))
        wanted_code = stock_id.split(".", 1)[0]
        rows = [
            r
            for r in out["rows"]
            if str(r["stock_id"]) == stock_id or str(r["stock_id"]).split(".", 1)[0] == wanted_code
        ]
        if not rows:
            print(f"- {spec}: not found in current Layer C source")
            continue

        r = rows[0]
        print(
            f"- {spec}: "
            f"identity_confirmed_pass={r['identity_confirmed_pass']}, "
            f"cycle_alive_pass={r['cycle_alive_pass']}, "
            f"pass_count_4of3={r['pass_count_4of3']}, "
            f"watch_score={r['watch_score']}, strong_grade={r['strong_grade']}, "
            f"watch_status={r['watch_status']}, support_type={r['support_type']}, gap_hit={r['gap_hit']}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Layer-C strong watch pool cleanliness.")
    parser.add_argument("--trade-date", required=True, help="Trade date, e.g. 2026-04-07")
    parser.add_argument("--out-dir", default="tmp/layer_c_audit", help="Output directory for CSV files")
    parser.add_argument(
        "--sample",
        action="append",
        default=["2026-04-07:002361.SZ", "2026-04-15:605060.SH"],
        help="Sample in format YYYY-MM-DD:STOCK_ID; can pass multiple",
    )
    args = parser.parse_args()

    trade_date = _parse_date(args.trade_date)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    )
    try:
        audit = await _audit_one_date(conn, trade_date, out_dir)
        s = audit["summary"]
        print("[Layer C Audit Summary]")
        print(f"trade_date={trade_date.isoformat()}")
        print(f"source={s['source']}")
        print(f"formal_pool_count={s['formal_pool_count']}")
        print(f"identity_fail_count={s['identity_fail_count']}")
        print(f"cycle_alive_fail_count={s['cycle_alive_fail_count']}")
        print(f"pass_4of3_fail_count={s['pass_4of3_fail_count']}")
        print(f"total_rows={s['total_rows']}")
        print(f"csv_dir={out_dir}")

        await _print_samples(conn, args.sample)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
