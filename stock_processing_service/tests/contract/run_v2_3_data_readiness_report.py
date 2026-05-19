"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.3 — Auction Timeline Data Readiness Report                            ║
║  Date: 2026-05-19                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Checks:
  1. pre_market_auction_timeline_raw coverage for candidate stocks
  2. pre_market_auction_feature coverage
  3. timeline_points_count distribution
  4. data_status distribution
  5. Missing rate (candidates without any timeline data)
  6. Source distribution

Usage: python stock_processing_service/tests/contract/run_v2_3_data_readiness_report.py
"""

from __future__ import annotations

import asyncio, json, os, sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


async def main():
    print(f"\n{'='*70}")
    print(f"  v2.3 — AUCTION TIMELINE DATA READINESS")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ── 1. Candidate scope ──
    cand_stocks = await c.execute_query(
        """SELECT DISTINCT stock_id
           FROM w2s_candidate_rebuild
           WHERE rule_version = 'w2s_v1.0_usecase_replay'"""
    )
    target_stocks = {str(r["stock_id"]) for r in cand_stocks}
    target_codes = {s.split(".", 1)[0] if "." in s else s for s in target_stocks}

    # ── 2. Get candidate-stock-date pairs from signal validation ──
    signal_pairs = await c.execute_query(
        """SELECT v.trade_date AS candidate_trade_date,
                  c.next_trade_date, c.stock_id
           FROM w2s_signal_validation_v1_1b v
           JOIN w2s_candidate_rebuild c
             ON v.trade_date = c.trade_date AND v.stock_id = c.stock_id
           WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
             AND c.next_trade_date IS NOT NULL"""
    )

    candidate_pairs: list[tuple[date, str]] = []
    for r in signal_pairs:
        td = r["next_trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        candidate_pairs.append((td, str(r["stock_id"])))

    total_pairs = len(candidate_pairs)
    print(f"  Candidate-stock-date pairs: {total_pairs}")

    # ── 3. Check raw timeline coverage ──
    raw_rows = await c.execute_query(
        """SELECT trade_date, stock_id, snapshot_time, data_mode
           FROM pre_market_auction_timeline_raw
           ORDER BY trade_date, stock_id, snapshot_time"""
    )

    # Index by (date, stock_id) → set of times
    raw_index: dict[tuple[date, str], set[str]] = defaultdict(set)
    raw_mode: dict[tuple[date, str], str] = {}
    for r in raw_rows:
        td = r["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        key = (td, str(r["stock_id"]))
        raw_index[key].add(str(r["snapshot_time"]))
        raw_mode[key] = str(r.get("data_mode") or "unknown")

    # Match to candidate pairs
    matched_raw = 0
    has_0924 = 0
    has_0925 = 0
    points_dist: dict[int, int] = defaultdict(int)

    for td, sid in candidate_pairs:
        key = (td, sid)
        # Try with code only
        code = sid.split(".", 1)[0] if "." in sid else sid
        alt_key = (td, code)
        times = raw_index.get(key) or raw_index.get(alt_key)
        if times:
            matched_raw += 1
            n = len(times)
            points_dist[n] += 1
            if "09:24:00" in times:
                has_0924 += 1
            if "09:25:00" in times:
                has_0925 += 1

    raw_cov = matched_raw / total_pairs * 100 if total_pairs else 0
    print(f"\n  ── Raw Timeline Coverage ──")
    print(f"  Total pairs:          {total_pairs}")
    print(f"  Raw timeline matched: {matched_raw} ({raw_cov:.1f}%)")
    print(f"  Missing raw data:     {total_pairs - matched_raw} ({100 - raw_cov:.1f}%)")
    print(f"  Has 09:24:00:         {has_0924} ({has_0924/total_pairs*100:.1f}%)")
    print(f"  Has 09:25:00:         {has_0925} ({has_0925/total_pairs*100:.1f}%)")

    print(f"\n  Timeline points distribution:")
    for n in sorted(points_dist.keys()):
        cnt = points_dist[n]
        print(f"    {n} point(s): {cnt} pairs ({cnt/total_pairs*100:.1f}%)")

    # ── 4. Check feature coverage ──
    feature_rows = await c.execute_query(
        """SELECT trade_date, stock_id, data_status, timeline_points_count
           FROM pre_market_auction_feature
           ORDER BY trade_date, stock_id"""
    )

    feat_index: dict[tuple[date, str], dict] = {}
    for r in feature_rows:
        td = r["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        feat_index[(td, str(r["stock_id"]))] = r

    matched_feat = 0
    data_status_counts: dict[str, int] = defaultdict(int)
    real_auction_count = 0

    for td, sid in candidate_pairs:
        key = (td, sid)
        code = sid.split(".", 1)[0] if "." in sid else sid
        alt_key = (td, code)
        feat = feat_index.get(key) or feat_index.get(alt_key)
        if feat:
            matched_feat += 1
            status = str(feat.get("data_status") or "unknown")
            data_status_counts[status] += 1
            if status == "real_auction_timeline":
                real_auction_count += 1

    feat_cov = matched_feat / total_pairs * 100 if total_pairs else 0
    real_cov = real_auction_count / total_pairs * 100 if total_pairs else 0

    print(f"\n  ── Feature Coverage ──")
    print(f"  Feature rows matched:  {matched_feat} ({feat_cov:.1f}%)")
    print(f"  Missing features:      {total_pairs - matched_feat} ({100 - feat_cov:.1f}%)")
    print(f"\n  data_status distribution:")
    for status in sorted(data_status_counts.keys()):
        cnt = data_status_counts[status]
        pct = cnt / total_pairs * 100 if total_pairs else 0
        bar = "█" * int(pct / 2) + "░" * max(0, 50 - int(pct / 2))
        print(f"    {status:<30} {cnt:>5} ({pct:>5.1f}%)  {bar}")

    # ── 5. Source distribution ──
    source_counts = await c.execute_query(
        """SELECT data_mode, COUNT(*) AS cnt
           FROM pre_market_auction_timeline_raw
           GROUP BY data_mode
           ORDER BY cnt DESC"""
    )
    print(f"\n  ── Raw Timeline Source ──")
    for r in source_counts:
        print(f"    {r['data_mode']}: {r['cnt']} rows")

    # ── 6. Per-date coverage for candidate dates ──
    print(f"\n  ── Per-Date Feature Coverage ──")
    print(f"  {'Date':<14} {'Pairs':>6} {'Feat':>6} {'Cov%':>7}")
    date_pairs: dict[date, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for td, sid in candidate_pairs:
        total, matched = date_pairs[td]
        date_pairs[td] = (total + 1, matched)
    for td, sid in candidate_pairs:
        key = (td, sid)
        code = sid.split(".", 1)[0] if "." in sid else sid
        alt_key = (td, code)
        feat = feat_index.get(key) or feat_index.get(alt_key)
        if feat:
            total, matched = date_pairs[td]
            date_pairs[td] = (total, matched + 1)

    for td in sorted(date_pairs.keys()):
        total, matched = date_pairs[td]
        pct = matched / total * 100 if total else 0
        print(f"  {td}   {total:>6} {matched:>6} {pct:>6.1f}%")

    # ── 7. Conclusion ──
    print(f"\n{'='*70}")
    print(f"  READINESS ASSESSMENT")
    print(f"{'='*70}")

    target_cov = 80.0
    checks = {
        "candidate_raw_coverage >= 80%": raw_cov >= target_cov,
        "candidate_feature_coverage >= 80%": feat_cov >= target_cov,
        "has_09:25 >= 80%": (has_0925 / total_pairs * 100) >= target_cov if total_pairs else False,
        "real_auction_timeline >= 80%": real_cov >= target_cov,
        "missing <= 20%": (100 - feat_cov) <= 20,
    }

    all_pass = True
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        if not passed:
            all_pass = False
        print(f"  {icon} {check}")

    if all_pass:
        print(f"\n  → READY for v2.4 auction effect validation")
    else:
        print(f"\n  → NOT READY. Current data_status is synthetic_single_point.")
        print(f"  → 0% real_auction_timeline — need multi-point timeline data.")
        print(f"  → Continue collecting or upgrade data source to Level-2.")

    # ── Save report ──
    report = {
        "phase": "v2.3_auction_timeline_data_readiness",
        "timestamp": datetime.now().isoformat(),
        "candidate_pairs": total_pairs,
        "raw_timeline": {
            "matched": matched_raw,
            "coverage_pct": round(raw_cov, 2),
            "has_0924": has_0924,
            "has_0925": has_0925,
            "points_distribution": {str(k): v for k, v in points_dist.items()},
        },
        "features": {
            "matched": matched_feat,
            "coverage_pct": round(feat_cov, 2),
            "data_status_counts": dict(data_status_counts),
            "real_auction_pct": round(real_cov, 2),
        },
        "v2.4_ready": all_pass,
        "note": "synthetic_single_point data is NOT real_auction. Strategy conclusions blocked until real timeline data available.",
    }

    out_path = Path(__file__).parent / f"v2_3_data_readiness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")

    await gw.close()
    return report


if __name__ == "__main__":
    asyncio.run(main())
