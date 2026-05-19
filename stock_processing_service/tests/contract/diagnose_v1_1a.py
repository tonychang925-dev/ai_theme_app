"""
v1.1a_data_readiness — Diagnostic Script
==========================================
Investigate two bottlenecks without DB changes:
  1. A-layer coverage: why 96→10?
  2. D1 strong_history: what field values fail?

Usage: python stock_processing_service/tests/contract/diagnose_v1_1a.py
"""

from __future__ import annotations

import asyncio, os, sys
from collections import Counter
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")
TRADE_DATE = date(2026, 5, 15)  # most recent date from seed_funnel


async def diagnose_a_layer():
    """Diagnose why 96 after_subject_key_filter → 10 after_a_layer_check."""
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    print("\n" + "=" * 70)
    print("  DIAGNOSIS 1: A-LAYER COVERAGE (96 → 10)")
    print("=" * 70)

    # Get the 96 rows (after subject_key filter)
    rows = await c.execute_query("""
        SELECT b.stock_id, b.stock_name, b.subject_key, b.theme_name,
               b.leader_role_proxy, b.prior7_limitup_days
        FROM strong_stock_daily_feature b
        WHERE b.trade_date=$1 AND b.leader_role_proxy!='unknown'
          AND b.prior7_limitup_days>=1
          AND b.subject_key IS NOT NULL AND btrim(b.subject_key) <> ''
    """, (TRADE_DATE,))
    total = len(rows)
    print(f"\n  Total with subject_key: {total}")

    # Check which subject_keys exist in subject_daily_feature
    subjects = [str(r['subject_key']).strip() for r in rows]
    subject_set = set(subjects)

    a_rows = await c.execute_query(
        "SELECT DISTINCT subject_key FROM subject_daily_feature WHERE trade_date=$1 AND rule_version='subject_feature_from_rank_v0.1'",
        (TRADE_DATE,))
    a_set = {str(r['subject_key']) for r in a_rows}
    print(f"  A-layer subjects (subject_daily_feature): {len(a_set)}")

    matched = subject_set & a_set
    missed = subject_set - a_set
    print(f"  Matched: {len(matched)}")
    print(f"  Missed:  {len(missed)}")

    # Top 50 missed samples
    print(f"\n  --- Top 50 A-layer MISS samples ---")
    print(f"  {'stock_id':<15} {'subject_key':<30} {'theme_name':<25} {'leader_role':<18}")
    print(f"  {'─'*15} {'─'*30} {'─'*25} {'─'*18}")
    count = 0
    for r in rows:
        sk = str(r['subject_key']).strip()
        if sk in missed:
            print(f"  {str(r['stock_id']):<15} {sk:<30} {str(r.get('theme_name',''))[:25]:<25} {str(r.get('leader_role_proxy','')):<18}")
            count += 1
            if count >= 50:
                break

    # Check subject_key variants: bizKey / root_subject_key / any alternate columns
    print(f"\n  --- subject_daily_feature cols for spot check ---")
    if missed:
        sample_sk = list(missed)[0]
        sample_rows = await c.execute_query(
            "SELECT * FROM subject_daily_feature WHERE subject_key=$1 LIMIT 1",
            (sample_sk,))
        if sample_rows:
            print(f"  Sample key '{sample_sk}' EXISTS in subject_daily_feature (but not for {TRADE_DATE})")
            cols = list(sample_rows[0].keys())
            print(f"  Available columns: {cols}")
        else:
            print(f"  Sample key '{sample_sk}' NOT FOUND anywhere in subject_daily_feature")

    # Check if strong_stock_daily_feature has alternate subject key fields
    b_cols = await c.execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name='strong_stock_daily_feature' ORDER BY ordinal_position"
    )
    b_col_names = [r['column_name'] for r in b_cols]
    print(f"\n  strong_stock_daily_feature columns: {b_col_names}")
    subject_like_cols = [c for c in b_col_names if 'subject' in c.lower() or 'biz' in c.lower() or 'key' in c.lower()]
    print(f"  Subject-like columns: {subject_like_cols}")

    # Check subject_daily_feature columns too
    a_cols = await c.execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name='subject_daily_feature' ORDER BY ordinal_position"
    )
    a_col_names = [r['column_name'] for r in a_cols]
    print(f"\n  subject_daily_feature columns: {a_col_names}")

    # What does subject_daily_feature cover?
    a_counts = await c.execute_query(
        "SELECT COUNT(*) as n, COUNT(DISTINCT subject_key) as distinct_sk FROM subject_daily_feature WHERE trade_date=$1",
        (TRADE_DATE,))
    print(f"\n  subject_daily_feature on {TRADE_DATE}: {a_counts[0]['n']} rows, {a_counts[0]['distinct_sk']} distinct subjects")

    # Check rank table if available
    try:
        rank_check = await c.execute_query(
            "SELECT COUNT(*) as n, COUNT(DISTINCT subject_key) as sk FROM subject_daily_rank WHERE trade_date=$1",
            (TRADE_DATE,))
        print(f"  subject_daily_rank on {TRADE_DATE}: {rank_check[0]['n']} rows, {rank_check[0]['sk']} distinct subjects")
    except Exception:
        print(f"  subject_daily_rank: table does not exist or query failed")

    # Check subject_key overlap between strong_stock and subject_daily_feature
    b_all = await c.execute_query(
        "SELECT DISTINCT subject_key FROM strong_stock_daily_feature WHERE trade_date=$1",
        (TRADE_DATE,))
    b_all_set = {str(r['subject_key']) for r in b_all if r['subject_key']}
    print(f"\n  strong_stock_daily_feature distinct subjects on {TRADE_DATE}: {len(b_all_set)}")
    print(f"  Overlap with A-layer: {len(b_all_set & a_set)}/{len(b_all_set)}")

    await gw.close()
    return {"total": total, "matched": len(matched), "missed": len(missed), "a_set_size": len(a_set)}


async def diagnose_d1_fields():
    """Diagnose D1 strong_history failure field values."""
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    print("\n" + "=" * 70)
    print("  DIAGNOSIS 2: D1 STRONG_HISTORY FIELD QUALITY")
    print("=" * 70)

    # Get eligible rows from strong_watch_pool_scored_rebuild
    eligible = await c.execute_query("""
        SELECT p.stock_id, p.stock_name, p.subject_key, p.theme_name,
               p.watch_score, p.watch_status, p.pool_entry_type,
               p.strong_grade, p.mainline_strength_score, p.cycle_state,
               p.support_type, p.support_strength,
               p.recent_limit_up_count, p.hard_gate_pass_count,
               p.fade_watch, p.fade_confirmed,
               COALESCE(c.pct_chg, 0) as pct_chg,
               COALESCE(c.limit_up, false) as limit_up,
               COALESCE(c.prev_day_limit_up, false) as prev_day_limit_up,
               COALESCE(c.prior7_limitup_days, 0) as prior7_limitup_days,
               COALESCE(c.prior7_strong_days, 0) as prior7_strong_days,
               COALESCE(c.weak_type, '') as weak_type,
               COALESCE(c.weak_type_quality, '') as weak_type_quality
        FROM strong_watch_pool_scored_rebuild p
        LEFT JOIN stock_structure_daily_feature c ON p.stock_id=c.stock_id AND p.trade_date=c.trade_date
        WHERE p.watch_status IN ('active','weakening')
          AND p.pool_entry_type IN ('formal','observe_only')
          AND NOT COALESCE(p.fade_confirmed, false)
        ORDER BY p.watch_score DESC NULLS LAST
        LIMIT 30
    """)

    print(f"\n  Total eligible: {len(eligible)}")
    print(f"\n  --- Eligible rows (top 30 by watch_score) ---")
    print(f"  {'stock_id':<15} {'strong_grade':<12} {'pool_entry':<12} {'watch_score':>8} {'recent_lim':>8} {'prior7_lim':>8} {'prior7_str':>8} {'prev_lup':>8} {'pct_chg':>8}")
    print(f"  {'─'*15} {'─'*12} {'─'*12} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    for r in eligible:
        print(f"  {str(r['stock_id']):<15} {str(r['strong_grade']):<12} {str(r['pool_entry_type']):<12} "
              f"{float(r['watch_score'] or 0):>8.1f} {int(r['recent_limit_up_count'] or 0):>8} "
              f"{int(r['prior7_limitup_days'] or 0):>8} {int(r['prior7_strong_days'] or 0):>8} "
              f"{str(r['prev_day_limit_up']):>8} {float(r['pct_chg'] or 0):>8.2f}")

    # Now show what get_w2s_candidate_inputs feeds to build_candidates
    print(f"\n  --- D1 strong_history requirements ---")
    print(f"  strong_history = is_leader OR prev_day_limit_up OR recent_limit_up_count>=1 OR rank_order<=5")
    print(f"  is_leader = strong_grade IN ('S','A')")
    print(f"  rank_order = 999 (hardcoded!)")

    # Check strong_grade distribution
    grades = Counter()
    for r in eligible:
        grades[str(r['strong_grade'])] += 1
    print(f"\n  strong_grade distribution: {dict(grades)}")

    # Count how many WOULD pass with current data if rank_order weren't 999
    passing = 0
    failing = 0
    for r in eligible:
        is_leader = str(r['strong_grade']).upper() in ('S', 'A')
        prev_lup = bool(r['prev_day_limit_up'])
        recent_lim = int(r['recent_limit_up_count'] or 0) >= 1
        rank_in_top = False  # rank_order is always 999
        if is_leader or prev_lup or recent_lim or rank_in_top:
            passing += 1
        else:
            failing += 1
    print(f"\n  strong_history would PASS: {passing}")
    print(f"  strong_history would FAIL: {failing}")

    print(f"\n  --- D1 fail samples with full fields ---")
    print(f"  (showing all fields get_w2s_candidate_inputs passes to build_candidates)")
    count = 0
    for r in eligible:
        is_leader = str(r['strong_grade']).upper() in ('S', 'A')
        prev_lup = bool(r['prev_day_limit_up'])
        recent_lim = int(r['recent_limit_up_count'] or 0)
        p7_lim = int(r['prior7_limitup_days'] or 0)
        p7_str = int(r['prior7_strong_days'] or 0)
        wt = str(r.get('weak_type') or '')
        wtq = str(r.get('weak_type_quality') or '')
        support = str(r.get('support_type') or '')

        strong_hist = is_leader or prev_lup or recent_lim >= 1
        if not strong_hist:
            print(f"\n    stock: {r['stock_id']} | {r['stock_name']}")
            print(f"    is_leader={is_leader} (grade={r['strong_grade']}) | rank_order=999 (hardcoded)")
            print(f"    prev_day_limit_up={prev_lup} | recent_limit_up_count={recent_lim}")
            print(f"    prior7_limitup_days={p7_lim} | prior7_strong_days={p7_str}")
            print(f"    pct_chg={float(r['pct_chg'] or 0):.2f} | weak_type={wt} | weak_type_quality={wtq}")
            print(f"    support_type={support} | support_strength={float(r['support_strength'] or 0):.1f}")
            print(f"    watch_score={float(r['watch_score'] or 0):.1f} | pool_entry_type={r['pool_entry_type']}")
            print(f"    fade_watch={r['fade_watch']} | fade_confirmed={r['fade_confirmed']}")
            print(f"    cycle_state={r['cycle_state']} | mainline_score={float(r['mainline_strength_score'] or 0):.1f}")
            count += 1
            if count >= 10:
                break

    await gw.close()
    return {"eligible": len(eligible), "passing": passing, "failing": failing}


async def main():
    a_result = await diagnose_a_layer()
    d_result = await diagnose_d1_fields()

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  A-layer: {a_result['total']} with sk → {a_result['matched']} matched ({a_result['missed']} missed)")
    print(f"  D1:      {d_result['eligible']} eligible → {d_result['passing']} would pass strong_history ({d_result['failing']} fail)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
