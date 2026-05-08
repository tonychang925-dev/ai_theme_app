#!/usr/bin/env python3
"""固定样本新旧链 A/B 对比回归测试。

样本:
  1. 神剑股份 2026-04-07
  2. 联德股份 2026-04-15
  3. 维科技术 2026-04-22 ~ 2026-04-24
  4. 独立强势股样本（从4/15日池中选non-confirmed-mainline的股票）
  5. 退潮反例（fade_confirmed subject下的股票）
  6. 一日游反例（one_day_tour subject下的股票）

对比维度:
  - Layer C seed_rows 是否一致
  - watch_score / pool_entry_type / watch_status 是否一致
  - candidate_promoted 是否一致
  - D1 candidates 是否一致
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.domain.services.strong_stock_tracking_service import (
    BoardSnapshot,
    CycleSnapshot,
    PatternSnapshot,
    PositionSnapshot,
    StrongStockTrackingService,
)
from stock_processing_service.domain.services.kline_support_scorer import KlineSupportScorer
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.contracts.dto import SubjectStockPoolDTO, StockBarDTO


@dataclass
class SampleResult:
    label: str
    trade_date: date
    stock_id: str
    stock_name: str
    # Old chain (from DB history)
    old_in_seed: bool = False
    old_watch_status: str = ""
    old_watch_score: str = ""
    old_pool_entry_type: str = ""
    old_candidate_level: str = ""
    old_candidate_score: str = ""
    # New chain (computed)
    new_in_seed: bool = False
    new_watch_status: str = ""
    new_watch_score: float = 0.0
    new_pool_entry_type: str = ""
    new_support_type: str = ""
    new_support_score: float = 0.0
    new_d1_level: str = ""
    new_d1_score: float = 0.0
    # Diff
    seed_match: bool = False
    pool_entry_match: bool = False
    d1_match: bool = False
    notes: list[str] = field(default_factory=list)


SAMPLE_SPECS = [
    # 主线样本
    {"label": "神剑", "date": date(2026, 4, 7), "stock_id": "002361.SZ", "stock_name": "神剑股份"},
    {"label": "联德", "date": date(2026, 4, 15), "stock_id": "605060.SH", "stock_name": "联德股份"},
    # 维科 续命链
    {"label": "维科", "date": date(2026, 4, 22), "stock_id": "600152.SH", "stock_name": "维科技术"},
    {"label": "维科", "date": date(2026, 4, 23), "stock_id": "600152.SH", "stock_name": "维科技术"},
    {"label": "维科", "date": date(2026, 4, 24), "stock_id": "600152.SH", "stock_name": "维科技术"},
]


async def init_gateway():
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False
    return await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)


async def run_regression() -> list[SampleResult]:
    gw = await init_gateway()
    adapter = StockReadGatewayAdapter(db_gateway=gw)
    tracking = StrongStockTrackingService()
    scorer = KlineSupportScorer()
    results: list[SampleResult] = []

    for spec in SAMPLE_SPECS:
        td = spec["date"]
        sid = spec["stock_id"]
        label = f"{spec['label']}_{td.isoformat()}"
        sname = spec["stock_name"]

        r = SampleResult(label=label, trade_date=td, stock_id=sid, stock_name=sname)

        # ── 旧链数据 ──
        async with gw._client.pool.acquire() as conn:
            old_seed = await conn.fetch(
                """SELECT stock_id FROM subject_stock_daily_snapshot
                   WHERE trade_date IN (
                       SELECT DISTINCT trade_date FROM subject_stock_daily_snapshot
                       WHERE trade_date <= $1::date ORDER BY trade_date DESC LIMIT 7
                   ) AND stock_id = $2 LIMIT 1""",
                td, sid,
            )
            r.old_in_seed = len(old_seed) > 0

            old_pool = await conn.fetchrow(
                """SELECT watch_status, watch_score, pool_entry_type
                   FROM strong_stock_watch_history
                   WHERE stock_id = $1 AND trade_date = $2""",
                sid, td,
            )
            if old_pool:
                r.old_watch_status = str(old_pool["watch_status"] or "")
                r.old_watch_score = str(old_pool["watch_score"] or "")
                r.old_pool_entry_type = str(old_pool["pool_entry_type"] or "")
                # 旧链D1：formal/observe_only + active/weakening = D1候选
                old_entry = str(old_pool["pool_entry_type"] or "")
                old_status = str(old_pool["watch_status"] or "")
                if old_entry in {"formal", "observe_only"} and old_status in {"active", "weakening"}:
                    r.old_candidate_level = old_entry
                    r.old_candidate_score = str(old_pool["watch_score"] or "")

        # ── 新链计算 ──
        seed_raw = await adapter.get_strong_watch_seed_rows(td, 7)
        seed_cands = tracking.build_seed_candidates(seed_raw)
        r.new_in_seed = any(sid in s.stock_id for s in seed_cands)

        all_subj = sorted({s.subject_key for s in seed_cands if s.subject_key})
        all_ids = [s.stock_id for s in seed_cands if s.stock_id]

        identities = await adapter.get_mainline_identity_by_subject_keys(all_subj, td)
        cycles = await adapter.get_mainline_cycle_by_subject_keys(all_subj, td)
        evidence_raw = await adapter.get_subject_cycle_evidence_daily(td, subject_keys=all_subj)
        board_stats = await adapter.get_subject_board_stats(td)
        positions = await adapter.get_stock_position_judgement(td, all_ids)
        patterns = await adapter.get_stock_pattern_judgement(td, all_ids)
        bars = await adapter.get_stock_daily_bars(td, all_ids)
        prior = await adapter.get_prior_stock_daily_snapshots(td, 7, all_ids)
        history_bars = await adapter.get_stock_daily_bars_range(td - timedelta(days=90), td, all_ids)

        id_by_subj = {x.subject_key: x for x in identities}
        cyc_by_subj = {x.subject_key: x for x in cycles}
        ev_by_subj = {str(row.get("subject_key", "")): dict(row) for row in evidence_raw}
        board_by_subj = {str(row.get("subject_key", "")): dict(row) for row in board_stats}
        bar_by_stock = {b.stock_id: b for b in bars}

        watch_results = []
        for c in seed_cands:
            cyc = cyc_by_subj.get(c.subject_key)
            cycle_snap = CycleSnapshot(
                final_cycle_state=str(getattr(cyc, "final_cycle_state", "") or ""),
                effective_mainline_alive=not bool(getattr(cyc, "fade_confirmed", False) if cyc else False),
                fade_watch=bool(getattr(cyc, "fade_watch", False)) if cyc else False,
                fade_confirmed=bool(getattr(cyc, "fade_confirmed", False)) if cyc else False,
                mainline_strength_score=float(getattr(cyc, "mainline_strength_score", 0) or 0) if cyc else 0.0,
                event_continuity_score=float((ev_by_subj.get(c.subject_key, {})).get("event_continuity_score", 0) or 0),
            )
            bd = board_by_subj.get(c.subject_key, {})
            board_snap = BoardSnapshot(
                subject_limit_up_count=int(bd.get("subject_limit_up_count", 0)),
                subject_strong_count=int(bd.get("subject_strong_count", 0)),
            )
            pd = next((dict(rr) for rr in positions if c.stock_id in str(rr.get("stock_id", ""))), {})
            ptd = next((dict(rr) for rr in patterns if c.stock_id in str(rr.get("stock_id", ""))), {})
            pl = ptd.get("pattern_labels")
            if isinstance(pl, str):
                try: pl = json.loads(pl)
                except Exception: pl = []
            pat_snap = PatternSnapshot(
                pattern_labels=[str(x) for x in (pl or [])],
                volume_pattern_status=str(ptd.get("volume_pattern_status", "")),
                breakout_status=str(ptd.get("breakout_status", "")),
                pullback_status=str(ptd.get("pullback_status", "")),
            )
            pos_snap = PositionSnapshot(
                position_label=str(pd.get("position_label", "")),
                ma_alignment_status=str(pd.get("ma_alignment_status", "")),
                trend_strength_score=float(pd.get("trend_strength_score", 0) or 0),
            )
            bar = bar_by_stock.get(c.stock_id) or StockBarDTO(
                trade_date=td, stock_id=c.stock_id, stock_name=c.stock_name,
                open_price=0, high_price=0, low_price=0, close_price=0,
                pre_close=0, pct_chg=0, volume=0, amount=0,
                limit_up_price=0, limit_down_price=0,
            )
            sp = [p for p in prior if p.stock_id == c.stock_id]
            sh = [h for h in history_bars if h.stock_id == c.stock_id]
            sup = scorer.score(stock_id=c.stock_id, current_bar=bar, prior_rows=sp, history_bars=sh)
            wr = tracking.score_watch_row(c, cycle=cycle_snap, board=board_snap, support_result=sup, pos=pos_snap, pattern=pat_snap)
            watch_results.append(wr)

        target_wr = next((wr for wr in watch_results if sid in wr.stock_id), None)
        if target_wr:
            r.new_watch_status = target_wr.watch_status
            r.new_watch_score = target_wr.watch_score
            r.new_pool_entry_type = target_wr.pool_entry_type
            r.new_support_type = str(target_wr.support_type or "")
            r.new_support_score = target_wr.support_score

        # D1 candidates
        pool_dtos = []
        for wr in watch_results:
            if not tracking.is_candidate_eligible(watch_status=wr.watch_status, pool_entry_type=wr.pool_entry_type):
                continue
            if not wr.stock_id:
                continue
            pool_dtos.append(SubjectStockPoolDTO(
                trade_date=td, subject_key=wr.subject_key, subject_name=wr.theme_name,
                stock_id=wr.stock_id, stock_name=wr.stock_name, pool_rank=None,
                metadata={
                    "candidate_source": "strong_watch_pool",
                    "watch_score": str(wr.watch_score), "watch_status": wr.watch_status,
                    "pool_entry_type": wr.pool_entry_type, "strong_grade": wr.strong_grade,
                    "support_type": str(wr.support_type or ""), "support_level": str(wr.support_level or ""),
                    "support_score": str(wr.support_score), "role_tags": wr.labels,
                    "eligible_for_candidate": True,
                    "recent_limit_up_count": wr.labels.get("recent_limit_up_count", 0),
                    "is_leader": wr.labels.get("is_dragon_head", False),
                },
            ))
        w2s = W2SCandidateService()
        candidates = w2s.build_candidates(bars=list(bar_by_stock.values()), pool_rows=pool_dtos, prior_rows=[])
        all_c = getattr(w2s, "all_candidates", candidates)
        target_d1 = next((c for c in all_c if sid in c.stock_id), None)
        if target_d1:
            r.new_d1_level = str(getattr(target_d1, "candidate_level", ""))
            r.new_d1_score = float(getattr(target_d1, "candidate_score", 0))

        # ── Diff判定 ──
        r.seed_match = r.old_in_seed == r.new_in_seed
        r.pool_entry_match = (
            (r.old_pool_entry_type in {"formal", "observe_only"}) ==
            (r.new_pool_entry_type in {"formal", "observe_only"})
        )
        old_d1_hit = r.old_candidate_level not in {"", "reject", "REJECT"}
        new_d1_hit = r.new_d1_level not in {"", "reject", "REJECT"}
        r.d1_match = old_d1_hit == new_d1_hit

        if not r.seed_match:
            r.notes.append(f"seed mismatch: old={r.old_in_seed} new={r.new_in_seed}")
        if not r.pool_entry_match:
            r.notes.append(f"pool_entry mismatch: old={r.old_pool_entry_type} new={r.new_pool_entry_type}")
        if not r.d1_match:
            r.notes.append(f"D1 mismatch: old={r.old_candidate_level}/{r.old_candidate_score} new={r.new_d1_level}/{r.new_d1_score:.0f}")

        results.append(r)

    # ── 独立强势股样本（从4/15中选non-confirmed-mainline入池的股票）──
    td15 = date(2026, 4, 15)
    async with gw._client.pool.acquire() as conn:
        indie_rows = await conn.fetch(
            """SELECT h.stock_id, h.stock_name, h.watch_status, h.watch_score, h.pool_entry_type
               FROM strong_stock_watch_history h
               WHERE h.trade_date = $1
                 AND h.pool_entry_type IN ('formal', 'observe_only')
                 AND h.watch_status IN ('active', 'weakening')
                 AND NOT EXISTS (
                     SELECT 1 FROM theme_mainline_identity_registry mr
                     WHERE mr.subject_key = h.subject_key
                       AND mr.is_main_theme = TRUE
                       AND mr.identity_status = 'confirmed'
                 )
               LIMIT 3""",
            td15,
        )
        for row in indie_rows:
            sid = str(row["stock_id"])
            r = SampleResult(
                label=f"indie_{sid}", trade_date=td15, stock_id=sid,
                stock_name=str(row["stock_name"]),
                old_watch_status=str(row["watch_status"]),
                old_watch_score=str(row["watch_score"]),
                old_pool_entry_type=str(row["pool_entry_type"]),
            )
            seed_raw = await adapter.get_strong_watch_seed_rows(td15, 7)
            r.new_in_seed = any(sid in str(s.get("stock_id", "")) for s in seed_raw)
            r.seed_match = r.new_in_seed
            if not r.new_in_seed:
                r.notes.append("独立强势股未进入新链种子")
            results.append(r)

    # ── 退潮反例 ──
    async with gw._client.pool.acquire() as conn:
        fade_subj = await conn.fetchval(
            "SELECT subject_key FROM theme_cycle_judgement_v2 WHERE trade_date = $1 AND fade_confirmed = TRUE LIMIT 1",
            td15,
        )
        if fade_subj:
            fade_stocks = await conn.fetch(
                "SELECT stock_id, stock_name FROM subject_stock_daily_snapshot WHERE trade_date = $1 AND subject_key = $2 LIMIT 3",
                td15, fade_subj,
            )
            for row in fade_stocks:
                sid = str(row["stock_id"])
                r = SampleResult(
                    label=f"fade_{sid}", trade_date=td15, stock_id=sid,
                    stock_name=str(row["stock_name"]),
                )
                seed_raw = await adapter.get_strong_watch_seed_rows(td15, 7)
                r.new_in_seed = any(sid in str(s.get("stock_id", "")) for s in seed_raw)
                if r.new_in_seed:
                    r.notes.append(f"退潮subject {fade_subj} 下的股票居然进入了种子池")
                results.append(r)

    # ── 一日游反例 ──
    async with gw._client.pool.acquire() as conn:
        tour_subj = await conn.fetchval(
            "SELECT subject_key FROM theme_mainline_identity_registry WHERE evidence_json->>'one_day_tour_flag' = 'true' LIMIT 1"
        )
        if not tour_subj:
            tour_subj = await conn.fetchval(
                "SELECT subject_key FROM theme_cycle_evidence_daily WHERE trade_date = $1 LIMIT 1", td15
            )
        if tour_subj:
            tour_stocks = await conn.fetch(
                "SELECT stock_id, stock_name FROM subject_stock_daily_snapshot WHERE trade_date = $1 AND subject_key = $2 LIMIT 3",
                td15, tour_subj,
            )
            for row in tour_stocks:
                sid = str(row["stock_id"])
                r = SampleResult(
                    label=f"tour_{sid}", trade_date=td15, stock_id=sid,
                    stock_name=str(row["stock_name"]),
                )
                seed_raw = await adapter.get_strong_watch_seed_rows(td15, 7)
                r.new_in_seed = any(sid in str(s.get("stock_id", "")) for s in seed_raw)
                if r.new_in_seed:
                    r.notes.append(f"一日游subject {tour_subj} 下的股票进入了种子池")
                results.append(r)

    await gw.close()
    return results


def print_report(results: list[SampleResult]) -> None:
    """格式化输出对比报告。"""
    print("=" * 100)
    print("新旧链 Layer C/D 固定样本回归对比报告")
    print("=" * 100)

    # 分类统计
    mainline = [r for r in results if r.label.startswith(("神剑", "联德", "维科"))]
    indie = [r for r in results if r.label.startswith("indie_")]
    fade = [r for r in results if r.label.startswith("fade_")]
    tour = [r for r in results if r.label.startswith("tour_")]

    print(f"\n样本: 主线={len(mainline)} 独立强势={len(indie)} 退潮反例={len(fade)} 一日游反例={len(tour)}")

    # 主线样本详情
    print("\n── 主线样本 ──")
    print(f"{'样本':<16} {'日期':<12} {'股票':<12} {'旧seed':<8} {'新seed':<8} {'旧C状态':<24} {'新C状态':<24} {'旧D1':<16} {'新D1':<16} {'匹配':<8}")
    print("-" * 100)
    for r in mainline:
        old_c = f"{r.old_watch_status}/{r.old_pool_entry_type}/{r.old_watch_score}"
        new_c = f"{r.new_watch_status}/{r.new_pool_entry_type}/{r.new_watch_score:.0f}"
        old_d1 = f"{r.old_candidate_level}/{r.old_candidate_score}"
        new_d1 = f"{r.new_d1_level}/{r.new_d1_score:.0f}" if r.new_d1_level else "-"
        match_str = "✅" if (r.seed_match and r.pool_entry_match and r.d1_match) else "❌"
        print(f"{r.label:<16} {str(r.trade_date):<12} {r.stock_name:<12} {str(r.old_in_seed):<8} {str(r.new_in_seed):<8} {old_c:<24} {new_c:<24} {old_d1:<16} {new_d1:<16} {match_str:<8}")
        if r.notes:
            for n in r.notes:
                print(f"  ⚠️  {n}")

    # 独立强势股
    print(f"\n── 独立强势股样本（无confirmed mainline）──")
    for r in indie:
        ok = "✅ 种子中" if r.new_in_seed else "❌ 缺失"
        print(f"  {r.stock_id:<14} {r.stock_name:<10} {ok}")
        if r.notes:
            for n in r.notes:
                print(f"    {n}")

    # 退潮反例
    print(f"\n── 退潮反例（fade_confirmed subject下的股票不应入围）──")
    for r in fade:
        ok = "❌ 异常入围" if r.new_in_seed else "✅ 已过滤"
        print(f"  {r.stock_id:<14} {r.stock_name:<10} {ok}")
        if r.notes:
            for n in r.notes:
                print(f"    {n}")

    # 一日游反例
    print(f"\n── 一日游反例（one_day_tour subject下的股票不应入围）──")
    for r in tour:
        ok = "❌ 异常入围" if r.new_in_seed else "✅ 已过滤"
        print(f"  {r.stock_id:<14} {r.stock_name:<10} {ok}")
        if r.notes:
            for n in r.notes:
                print(f"    {n}")

    # 总统计
    seed_ok = sum(1 for r in mainline if r.seed_match)
    pool_ok = sum(1 for r in mainline if r.pool_entry_match)
    d1_ok = sum(1 for r in mainline if r.d1_match)
    print(f"\n── 主样本通过率 ──")
    print(f"  seed匹配: {seed_ok}/{len(mainline)}")
    print(f"  pool_entry匹配: {pool_ok}/{len(mainline)}")
    print(f"  D1匹配: {d1_ok}/{len(mainline)}")
    print(f"  退潮过滤: {sum(1 for r in fade if not r.new_in_seed)}/{len(fade)}")
    print(f"  一日游过滤: {sum(1 for r in tour if not r.new_in_seed)}/{len(tour)}")


if __name__ == "__main__":
    results = asyncio.run(run_regression())
    print_report(results)
