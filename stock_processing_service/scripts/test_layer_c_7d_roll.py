#!/usr/bin/env python3
"""Layer C 7日滚动测试 — 联德股份 (605060.SH) 4/7-4/15.

每天运行：种子查询 → Domain过滤 → 打印结果
验证：池大小合理（~30-80），联德出现在池中且保持到4/15。
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

# Setup path
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

TRADE_DATES = [
    date(2026, 4, 7),
    date(2026, 4, 8),
    date(2026, 4, 9),
    date(2026, 4, 10),
    date(2026, 4, 13),
    date(2026, 4, 14),
    date(2026, 4, 15),
]
TARGET_STOCK = "605060.SH"
TARGET_NAME = "联德股份"


async def main() -> None:
    # ── 初始化 Gateway ──
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")
    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    adapter = StockReadGatewayAdapter(db_gateway=gw)
    tracking = StrongStockTrackingService()
    support_scorer = KlineSupportScorer()

    # ── 累计跟踪池（模拟 old chain strong_stock_watch_pool 的持久化）──
    # key: stock_id, value: last_seen_date 和最新结果
    persistent_pool: dict[str, dict] = {}

    print("=" * 100)
    print(f"Layer C 7日滚动测试 — 目标: {TARGET_NAME} ({TARGET_STOCK})")
    print("=" * 100)

    for td in TRADE_DATES:
        print(f"\n{'─' * 80}")
        print(f"📅 {td.isoformat()}")

        # ── Step 1: 种子查询 ──
        seed_raw = await adapter.get_strong_watch_seed_rows(td, lookback_days=7)
        seed_candidates = tracking.build_seed_candidates(seed_raw)

        # ── Step 2: 预取评分数据 ──
        all_subject_keys = sorted({s.subject_key for s in seed_candidates if s.subject_key})
        stock_ids_for_scoring = [s.stock_id for s in seed_candidates]

        # 也加入 persistent_pool 中的股票
        persistent_ids = [sid for sid in persistent_pool if sid not in {s.stock_id for s in seed_candidates}]
        all_scoring_ids = stock_ids_for_scoring + persistent_ids

        identities_raw = await adapter.get_mainline_identity_by_subject_keys(all_subject_keys, td)
        cycles_raw = await adapter.get_mainline_cycle_by_subject_keys(all_subject_keys, td)
        board_raw = await adapter.get_subject_board_stats(td)
        pos_raw = await adapter.get_stock_position_judgement(td, all_scoring_ids)
        pat_raw = await adapter.get_stock_pattern_judgement(td, all_scoring_ids)
        bars_raw = await adapter.get_stock_daily_bars(td, all_scoring_ids)
        prior_raw = await adapter.get_prior_stock_daily_snapshots(td, lookback_days=7, stock_ids=all_scoring_ids)

        id_by_subj = {x.subject_key: x for x in identities_raw}
        cyc_by_subj = {x.subject_key: x for x in cycles_raw}
        board_by_subj = {str(r.get("subject_key", "")): dict(r) for r in board_raw}
        pos_by_stock = {str(r.get("stock_id", "")): dict(r) for r in pos_raw}
        pat_by_stock = {str(r.get("stock_id", "")): dict(r) for r in pat_raw}
        bar_by_stock = {b.stock_id: b for b in bars_raw}

        # ── Step 3: 评分所有种子 ──
        results = []
        for s in seed_candidates:
            cyc = cyc_by_subj.get(s.subject_key)
            ident = id_by_subj.get(s.subject_key)
            is_main = getattr(ident, "is_main_theme", False) if ident else False
            id_status = getattr(ident, "identity_status", "") if ident else ""

            cycle_snap = CycleSnapshot(
                final_cycle_state=str(getattr(cyc, "final_cycle_state", "") or ""),
                # 设计文档第309行/第2226行: final_mainline_alive = not fade_confirmed
                # 这是周期状态判定（是否硬退潮确认），不是主线身份确认
                effective_mainline_alive=bool(
                    not (getattr(cyc, "fade_confirmed", False) if cyc else False)
                ),
                fade_watch=bool(getattr(cyc, "fade_watch", False)) if cyc else False,
                fade_confirmed=bool(getattr(cyc, "fade_confirmed", False)) if cyc else False,
                mainline_strength_score=float(getattr(cyc, "mainline_strength_score", 0) or 0) if cyc else 0.0,
                event_continuity_score=0.0,
            )

            bd = board_by_subj.get(s.subject_key, {})
            board_snap = BoardSnapshot(
                subject_limit_up_count=int(bd.get("subject_limit_up_count") or 0),
                subject_strong_count=int(bd.get("subject_strong_count") or 0),
            )

            pos_d = pos_by_stock.get(s.stock_id, {})
            pos_snap = PositionSnapshot(
                position_label=str(pos_d.get("position_label") or ""),
                ma_alignment_status=str(pos_d.get("ma_alignment_status") or ""),
                trend_strength_score=float(pos_d.get("trend_strength_score") or 0.0),
            )

            pat_d = pat_by_stock.get(s.stock_id, {})
            pl = pat_d.get("pattern_labels")
            if isinstance(pl, str):
                import json
                try: pl = json.loads(pl)
                except Exception: pl = []
            pat_snap = PatternSnapshot(
                pattern_labels=[str(x) for x in (pl or [])],
                volume_pattern_status=str(pat_d.get("volume_pattern_status") or ""),
                breakout_status=str(pat_d.get("breakout_status") or ""),
                pullback_status=str(pat_d.get("pullback_status") or ""),
            )

            bar = bar_by_stock.get(s.stock_id)
            from stock_processing_service.contracts.dto import StockBarDTO
            if bar is None:
                bar = StockBarDTO(trade_date=td, stock_id=s.stock_id, stock_name=s.stock_name,
                                  open_price=0, high_price=0, low_price=0, close_price=0,
                                  pre_close=0, pct_chg=0, volume=0, amount=0)

            sup = support_scorer.score(stock_id=s.stock_id, current_bar=bar, prior_rows=prior_raw)

            r = tracking.score_watch_row(s, cycle=cycle_snap, board=board_snap,
                                         support_result=sup, pos=pos_snap, pattern=pat_snap)
            results.append(r)
            if r.stock_id:
                persistent_pool[r.stock_id] = {"last_date": td, "result": r}

        # ── Step 4: 输出统计 ──
        formal = [r for r in results if r.pool_entry_type == "formal"]
        observe = [r for r in results if r.pool_entry_type == "observe_only"]
        rejected = [r for r in results if r.pool_entry_type == "reject"]
        active = [r for r in results if r.watch_status == "active"]
        weakening = [r for r in results if r.watch_status == "weakening"]
        removed = [r for r in results if r.watch_status == "removed"]

        # 检查联德
        liande_results = [r for r in results if TARGET_STOCK in r.stock_id or TARGET_NAME in r.stock_name]

        print(f"  种子输入: {len(seed_raw)} → Domain过滤后: {len(results)}")
        print(f"  formal={len(formal)} observe_only={len(observe)} rejected={len(rejected)}")
        print(f"  active={len(active)} weakening={len(weakening)} removed={len(removed)}")
        print(f"  持久池累计: {len(persistent_pool)}")

        if liande_results:
            for lr in liande_results:
                print(f"  ✅ 联德股份: stock_id={lr.stock_id} status={lr.watch_status} "
                      f"entry={lr.pool_entry_type} score={lr.watch_score:.1f} "
                      f"grade={lr.strong_grade} broken={lr.broken_board} "
                      f"reason={lr.removed_reason or 'N/A'}")
                print(f"     labels: recent_limit_up={lr.labels.get('recent_limit_up_count')} "
                      f"is_dragon={lr.labels.get('is_dragon_head')} "
                      f"current_flag={lr.labels.get('current_flag_today')} "
                      f"board_effect={lr.labels.get('board_effect_confirmed')}")
        else:
            print(f"  ❌ 联德股份: 未出现在今日种子中!")
            # 检查是否在持久池中
            liande_pool = {k: v for k, v in persistent_pool.items() if TARGET_STOCK in k or TARGET_NAME in str(v)}
            if liande_pool:
                for k, v in liande_pool.items():
                    lr = v["result"]
                    print(f"     (在持久池中: {k} status={lr.watch_status} entry={lr.pool_entry_type} "
                          f"score={lr.watch_score:.1f} last={v['last_date']})")

    # ── 最终汇总 ──
    print(f"\n{'=' * 100}")
    print("汇总")
    print(f"{'=' * 100}")
    for td in TRADE_DATES:
        pool_on_date = {k: v for k, v in persistent_pool.items() if v["last_date"] <= td}
        liande_in_pool = {k: v for k, v in pool_on_date.items() if TARGET_STOCK in k}
        status_str = ""
        if liande_in_pool:
            for k, v in liande_in_pool.items():
                lr = v["result"]
                status_str = f"✅ {lr.watch_status}/{lr.pool_entry_type} score={lr.watch_score:.1f} grade={lr.strong_grade}"
        else:
            status_str = "❌ 不在池中"
        print(f"  {td.isoformat()}: 池中股票={len(pool_on_date)} | 联德: {status_str}")

    print(f"\n最终持久池 ({TRADE_DATES[-1]}) 总结:")
    final_pool = [(k, v["result"]) for k, v in persistent_pool.items()]
    final_pool.sort(key=lambda x: x[1].watch_score, reverse=True)
    print(f"  formal: {sum(1 for _, r in final_pool if r.pool_entry_type == 'formal')}")
    print(f"  observe_only: {sum(1 for _, r in final_pool if r.pool_entry_type == 'observe_only')}")
    print(f"  reject: {sum(1 for _, r in final_pool if r.pool_entry_type == 'reject')}")
    print(f"  active: {sum(1 for _, r in final_pool if r.watch_status == 'active')}")
    print(f"  weakening: {sum(1 for _, r in final_pool if r.watch_status == 'weakening')}")
    print(f"  removed: {sum(1 for _, r in final_pool if r.watch_status == 'removed')}")

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
