#!/usr/bin/env python3
"""新链 A/B/C 层回放验证脚本。

模拟每日盘后复盘流程：Cycle → Identity → State → StrongWatch。
使用新链 Job 直接调用，不依赖 SPS API 或旧链脚本。
"""
from __future__ import annotations

import asyncio, os, sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("IDENTITY_LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
os.environ.setdefault("IDENTITY_LLM_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))
os.environ.setdefault("IDENTITY_LLM_MODEL", "deepseek-chat")

from database_service.config import get_config
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_processing_service.infrastructure.gateway_adapters.db_theme_data_gateway import DBThemeDataGateway
from stock_processing_service.infrastructure.gateway_adapters.db_stock_object_gateway import DBStockObjectGateway
from stock_processing_service.application.jobs.build_cycle_judgement_job import BuildCycleJudgementJob
from stock_processing_service.application.jobs.build_identity_job import BuildIdentityJob
from stock_processing_service.application.jobs.build_mainline_state_job import BuildMainlineStateJob
from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob


class _NoopEventPort:
    async def publish_stock_processing_event(self, event): return "ok"

class _NoopIdempotencyPort:
    async def acquire_job_idempotency(self, **kwargs): return True
    async def is_job_completed(self, *args, **kwargs): return False
    async def mark_job_completed(self, *args, **kwargs): return None


def trading_days(start: date, end: date) -> list[date]:
    return [d for d in ((start + timedelta(days=i)) for i in range((end - start).days + 1))
            if d.weekday() < 5]


async def process_date(db, td: date, theme_gw, stock_gw, ep, ip) -> dict:
    batch = f"replay_{td.isoformat().replace('-', '')}"
    trace = f"replay_{td.isoformat()}"

    # B: Cycle
    cycle = BuildCycleJudgementJob(read_port=theme_gw, write_port=stock_gw)
    cr = await cycle.execute(trade_date=td, batch_id=batch, trace_id=trace)
    print(f"  [B-cycle] {cr.status} rows={cr.affected_rows} u={cr.metrics.get('tracked_subjects','?')}")

    # A: Identity
    identity = BuildIdentityJob(read_port=theme_gw, write_port=stock_gw, event_port=ep, idempotency_port=ip)
    ir = await identity.execute(trade_date=td, snapshot_version="replay.v1", batch_id=batch, trace_id=trace)
    print(f"  [A-identity] {ir.status} rows={ir.affected_rows} u={ir.metrics.get('universe_subject_count','?')}")

    # B: State
    state = BuildMainlineStateJob(read_port=theme_gw, write_port=stock_gw)
    sr = await state.execute(trade_date=td, batch_id=batch, trace_id=trace)
    print(f"  [B-state] {sr.status} rows={sr.affected_rows}")

    # C: Strong Watch (via BuildPostMarketRecapJob)
    recap = BuildPostMarketRecapJob(
        read_port=theme_gw, write_port=stock_gw, event_port=ep, idempotency_port=ip,
        identity_job=None, mainline_state_job=None, cycle_judgement_job=None,
    )
    rr = await recap.execute(trade_date=td, snapshot_version="replay_c.v1",
                              batch_id=batch, trace_id=trace, lookback_days=7)
    c_total = await db.pool.fetchval(
        "SELECT COUNT(*) FROM strong_stock_watch_history WHERE trade_date = $1", td)
    c_pool = await db.pool.fetchval(
        "SELECT COUNT(*) FILTER (WHERE watch_status IN ('active','weakening')) FROM strong_stock_watch_history WHERE trade_date = $1", td)
    print(f"  [C-watch] {rr.status} in_pool={c_pool} total={c_total}")

    return {"cycle": cr, "identity": ir, "state": sr, "recap": rr}


async def verify_results(db, days: list[date]):
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    print("\n--- Identity rows per date ---")
    for td in days:
        cnt = await db.pool.fetchval(
            "SELECT COUNT(*) FROM theme_mainline_identity_registry WHERE source_trade_date = $1", td)
        print(f"  {td}: {cnt}")

    print("\n--- 9064628 inheritance ---")
    rows = await db.pool.fetch(
        "SELECT source_trade_date, is_main_theme, identity_status FROM theme_mainline_identity_registry "
        "WHERE subject_key = '9064628' ORDER BY source_trade_date")
    for r in rows:
        s = "✅" if r["is_main_theme"] else "❌"
        print(f"  {r['source_trade_date']}: {r['identity_status']} {s}")

    print("\n--- Cycle ---")
    for td in days:
        t = await db.pool.fetchval("SELECT COUNT(*) FROM theme_cycle_judgement_v2 WHERE trade_date = $1", td)
        a = await db.pool.fetchval("SELECT COUNT(*) FROM theme_cycle_judgement_v2 WHERE trade_date = $1 AND final_mainline_alive", td)
        print(f"  {td}: total={t} alive={a}")

    print("\n--- Strong Watch ---")
    for td in days:
        t = await db.pool.fetchval("SELECT COUNT(*) FROM strong_stock_watch_history WHERE trade_date = $1", td)
        p = await db.pool.fetchval("SELECT COUNT(*) FILTER (WHERE watch_status IN ('active','weakening')) FROM strong_stock_watch_history WHERE trade_date = $1", td)
        print(f"  {td}: total={t} in_pool={p}")

    print("\n--- Identity status distribution ---")
    rows = await db.pool.fetch(
        "SELECT identity_status, COUNT(*) as cnt FROM theme_mainline_identity_registry "
        "WHERE source_trade_date BETWEEN $1 AND $2 GROUP BY identity_status ORDER BY cnt DESC",
        days[0], days[-1])
    for r in rows:
        print(f"  {r['identity_status']}: {r['cnt']}")

    print("\n--- Upgrade trigger ---")
    cnt = await db.pool.fetchval(
        "SELECT COUNT(*) FROM theme_mainline_identity_registry "
        "WHERE source_trade_date BETWEEN $1 AND $2 AND rule_version LIKE '%upgrade_trigger%'",
        days[0], days[-1])
    print(f"  upgrade_trigger: {cnt}")


async def main():
    sd = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 4, 16)
    ed = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 4, 30)
    days = trading_days(sd, ed)
    print(f"Replay {len(days)} days: {sd} → {ed}\n")

    config = get_config()
    db = PostgresDatabaseManager(config)
    await db.connect()
    tg = DBThemeDataGateway(db)
    sg = DBStockObjectGateway(db)
    ep = _NoopEventPort()
    ip = _NoopIdempotencyPort()

    # Prerequisite
    await db.pool.execute("DELETE FROM theme_mainline_identity_registry WHERE subject_key = '9064628'")
    await db.pool.execute(
        "INSERT INTO theme_mainline_identity_registry (subject_key, theme_name, is_main_theme, identity_status, "
        "first_seen_date, first_confirmed_date, last_review_date, source_trade_date, rule_is_main_theme, rule_version, llm_applied) "
        "VALUES ('9064628', 'Micro LED CPO', true, 'confirmed', '2026-04-16', '2026-04-16', '2026-04-16', '2026-04-16', "
        "true, 'mainline_identity_registry.v5_cluster_compensation', true)")
    print("Prerequisite: 9064628 confirmed on 4/16\n")

    for td in days:
        print(f"=== {td.isoformat()} ===")
        await process_date(db, td, tg, sg, ep, ip)

    await verify_results(db, days)


if __name__ == "__main__":
    asyncio.run(main())
