"""
v1.1a.2_support_audit — Diagnose d1_fail_support (18/21)
==========================================================
Classify each support failure into:
  missing_structure_row / join_mismatch / support_type_none /
  support_strength_low / support_detector_missing_feature / other

Usage: python stock_processing_service/tests/contract/audit_support_v1_1a_2.py
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


async def audit_support():
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    print("=" * 80)
    print("  v1.1a.2 SUPPORT AUDIT")
    print("=" * 80)

    # Get D1 input samples: eligible rows from strong_watch_pool_scored_rebuild
    # that would be fed to build_candidates()
    candidates = await c.execute_query("""
        SELECT p.stock_id, p.stock_name, p.trade_date, p.subject_key, p.theme_name,
               p.watch_score, p.watch_status, p.pool_entry_type, p.strong_grade,
               p.mainline_strength_score, p.cycle_state,
               p.support_type as pool_support_type,
               p.support_strength as pool_support_strength,
               COALESCE(c.pct_chg, 0) as pct_chg,
               COALESCE(c.limit_up, false) as limit_up,
               COALESCE(c.prev_day_limit_up, false) as prev_day_limit_up,
               COALESCE(c.prior7_limitup_days, 0) as prior7_limitup_days,
               COALESCE(c.prior7_strong_days, 0) as prior7_strong_days,
               COALESCE(c.weak_type, '') as weak_type,
               COALESCE(c.weak_type_quality, '') as weak_type_quality,
               COALESCE(c.support_type, '') as c_support_type,
               COALESCE(c.support_strength, 0) as c_support_strength,
               c.stock_id as c_stock_id,
               c.trade_date as c_trade_date
        FROM strong_watch_pool_scored_rebuild p
        LEFT JOIN stock_structure_daily_feature c ON p.stock_id=c.stock_id AND p.trade_date=c.trade_date
        WHERE p.watch_status IN ('active','weakening')
          AND p.pool_entry_type IN ('formal','observe_only')
          AND NOT COALESCE(p.fade_confirmed, false)
        ORDER BY p.watch_score DESC
    """)

    print(f"\n  Total candidates (pass is_candidate_eligible): {len(candidates)}")

    # Classify each candidate
    fail_categories = Counter()
    fail_samples: list[dict] = []

    for r in candidates:
        pct = float(r['pct_chg'] or 0)
        limit_up = bool(r['limit_up'])
        weak_type = str(r.get('weak_type') or '')
        weak_qual = str(r.get('weak_type_quality') or '')

        # Support info from both sources
        pool_sup_type = str(r.get('pool_support_type') or '')
        pool_sup_strength = float(r.get('pool_support_strength') or 0)
        c_sup_type = str(r.get('c_support_type') or '')
        c_sup_strength = float(r.get('c_support_strength') or 0)
        c_stock_id = str(r.get('c_stock_id') or '')
        c_trade_date = str(r.get('c_trade_date') or '')

        # Effective support (what build_candidates sees)
        # build_candidates gets support info from watch_labels_json (pool) and from row-level fields
        # The watch_labels_json has: support_type from pool, support_score from pool
        # The row-level fields have: support_type from C-layer, support_strength from C-layer
        # Both are checked: support_type in {"", "none"} OR support_strength < 45.0

        # Check both sources
        eff_sup_type = c_sup_type if c_sup_type else pool_sup_type
        eff_sup_strength = c_sup_strength if c_sup_strength > 0 else pool_sup_strength

        # Determine failure category
        category = "pass"
        stock_id_pool = str(r['stock_id'])

        # pct_chg gate (not a support issue)
        if pct >= 0 or pct > -1.0:
            category = "pct_gate"

        # Now check support
        elif eff_sup_type in ('', 'none') or eff_sup_strength < 45.0:
            # Sub-classify
            if not c_stock_id:
                category = "missing_structure_row"
            elif c_stock_id != stock_id_pool:
                # Check normalized format
                pool_normalized = stock_id_pool
                c_normalized = c_stock_id
                if pool_normalized.replace('.SZ','').replace('.SH','') == c_normalized.replace('.SZ','').replace('.SH',''):
                    category = "join_suffix_mismatch"
                else:
                    category = "join_id_mismatch"
            elif eff_sup_type in ('', 'none') and eff_sup_strength >= 45.0:
                category = "support_type_none_only"
            elif eff_sup_type not in ('', 'none') and eff_sup_strength < 45.0:
                category = "support_strength_low"
            elif eff_sup_type in ('', 'none') and eff_sup_strength < 45.0:
                category = "support_type_none_and_strength_low"
            else:
                category = "other"
        else:
            # Has support but check strong_history etc
            pass

        fail_categories[category] += 1

        # Keep samples for detailed analysis
        fail_samples.append({
            'stock_id': stock_id_pool,
            'stock_name': str(r.get('stock_name') or ''),
            'trade_date': str(r.get('trade_date') or ''),
            'pct_chg': pct,
            'limit_up': limit_up,
            'weak_type': weak_type,
            'weak_type_quality': weak_qual,
            'pool_support_type': pool_sup_type,
            'pool_support_strength': pool_sup_strength,
            'c_support_type': c_sup_type,
            'c_support_strength': c_sup_strength,
            'eff_support_type': eff_sup_type,
            'eff_support_strength': eff_sup_strength,
            'c_stock_id': c_stock_id,
            'c_trade_date': c_trade_date,
            'category': category,
        })

    print(f"\n  Classification:")
    for cat, count in sorted(fail_categories.items(), key=lambda x: -x[1]):
        print(f"    {cat:<40} {count:>3}")

    # Show ALL fail samples with categorization
    print(f"\n  --- ALL SAMPLES (by category) ---")
    current_cat = None
    for s in sorted(fail_samples, key=lambda x: (x['category'], -x['eff_support_strength'])):
        if s['category'] != current_cat:
            current_cat = s['category']
            print(f"\n  [{current_cat}]")
            print(f"  {'stock_id':<15} {'trade_date':<12} {'pct_chg':>7} {'weak_type':<20} {'supp_type':<18} {'supp_str':>6} {'pool_st':>6} {'c_st':>6} {'c_id'}")

        print(f"  {s['stock_id']:<15} {s['trade_date']:<12} {s['pct_chg']:>7.2f} {s['weak_type']:<20} "
              f"{s['eff_support_type']:<18} {s['eff_support_strength']:>6.1f} "
              f"{s['pool_support_strength']:>6.1f} {s['c_support_strength']:>6.1f} "
              f"{s['c_stock_id'] if s['c_stock_id'] else 'MISSING'}")

    # Check stock_structure_daily_feature table details
    print(f"\n  --- stock_structure_daily_feature table health ---")
    stats = await c.execute_query("SELECT COUNT(*) as n, COUNT(DISTINCT stock_id) as stocks, COUNT(DISTINCT trade_date) as dates FROM stock_structure_daily_feature")
    print(f"  Total rows: {stats[0]['n']}, distinct stocks: {stats[0]['stocks']}, distinct dates: {stats[0]['dates']}")

    # Check support_type distribution
    sup_dist = await c.execute_query("""
        SELECT support_type, COUNT(*) as n, AVG(support_strength)::numeric(8,1) as avg_str
        FROM stock_structure_daily_feature
        GROUP BY support_type ORDER BY n DESC
    """)
    print(f"\n  support_type distribution:")
    for r in sup_dist:
        print(f"    {str(r['support_type']):<25} n={r['n']:>5d}  avg_strength={r['avg_str']}")

    # Check stock_id format consistency
    fmt_check = await c.execute_query("""
        SELECT
            COUNT(*) FILTER (WHERE stock_id LIKE '%.%') as with_suffix,
            COUNT(*) FILTER (WHERE stock_id NOT LIKE '%.%') as without_suffix
        FROM stock_structure_daily_feature
    """)
    print(f"\n  stock_id format (structure table):")
    print(f"    with suffix (000001.SZ): {fmt_check[0]['with_suffix']}, without: {fmt_check[0]['without_suffix']}")

    # Same for strong_watch_pool_scored_rebuild
    pool_fmt = await c.execute_query("""
        SELECT
            COUNT(*) FILTER (WHERE stock_id LIKE '%.%') as with_suffix,
            COUNT(*) FILTER (WHERE stock_id NOT LIKE '%.%') as without_suffix
        FROM strong_watch_pool_scored_rebuild
    """)
    print(f"  stock_id format (rebuild table):")
    print(f"    with suffix (000001.SZ): {pool_fmt[0]['with_suffix']}, without: {pool_fmt[0]['without_suffix']}")

    # Sample mismatched IDs
    mismatch = [s for s in fail_samples if s['category'] in ('join_id_mismatch', 'join_suffix_mismatch', 'missing_structure_row')]
    if mismatch:
        print(f"\n  --- ID mismatch / missing samples (first 10) ---")
        for s in mismatch[:10]:
            print(f"    pool: {s['stock_id']} | structure: {s['c_stock_id'] or 'MISSING'} | trade: {s['trade_date']}")

    await gw.close()
    return fail_samples, fail_categories


if __name__ == "__main__":
    asyncio.run(audit_support())
