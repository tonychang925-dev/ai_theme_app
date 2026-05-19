"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.2a — Auction Data Readiness                                           ║
║  Date: 2026-05-19                                                          ║
║  Purpose: Check pre_market_auction_snapshot coverage for v2.0 candidates   ║
╚══════════════════════════════════════════════════════════════════════════════╝

Input:  w2s_signal_validation_v1_1b + w2s_candidate_rebuild
Output: v2_2a_auction_data_readiness_*.json

Checks:
  1. How many candidates can match auction_snapshot on T+1
  2. real_auction (timeline) coverage
  3. proxy_auction (single_point) coverage
  4. missing rate
  5. Per-date coverage
  6. Per-stock coverage

Data source classification:
  - real_auction:      source_trace->>'record_mode' = 'timeline_enhanced'
                       OR shape_features contains 'timeline_enhanced'
  - daily_open_proxy:  source_trace->>'record_mode' = 'single_point'
                       OR shape_features contains 'single_point_snapshot'
  - missing:           no row in pre_market_auction_snapshot for T+1

Usage: python stock_processing_service/tests/contract/run_v2_2a_auction_data_readiness.py
"""

from __future__ import annotations

import asyncio, json, os, sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


def classify_auction_source(row: dict[str, Any] | None) -> str:
    """Classify a pre_market_auction_snapshot row into data source category."""
    if row is None:
        return "missing"

    source_trace = row.get("source_trace") or {}
    if isinstance(source_trace, str):
        try:
            source_trace = json.loads(source_trace)
        except Exception:
            source_trace = {}

    shape_features = row.get("shape_features") or []
    if isinstance(shape_features, str):
        try:
            shape_features = json.loads(shape_features)
        except Exception:
            shape_features = []

    record_mode = str(source_trace.get("record_mode") or "")
    source_version = str(row.get("source_version") or "")

    # Timeline data = real auction
    if record_mode == "timeline_enhanced":
        return "real_auction"
    if "timeline_enhanced" in shape_features:
        return "real_auction"
    if "timeline" in source_version:
        return "real_auction"

    # Single point = daily open proxy
    if record_mode == "single_point":
        return "daily_open_proxy"
    if "single_point_snapshot" in shape_features or "result_only_mode" in shape_features:
        return "daily_open_proxy"

    # Has data but can't classify precisely — check if it has meaningful data
    auction_open_pct = row.get("auction_open_pct")
    auction_amount = row.get("auction_amount")
    if auction_open_pct is not None or (auction_amount and float(auction_amount) > 0):
        return "daily_open_proxy"  # conservative: treat as proxy

    return "missing"


async def main():
    print(f"\n{'='*70}")
    print(f"  v2.2a AUCTION DATA READINESS")
    print(f"  Checking pre_market_auction_snapshot coverage for v2.0 candidates")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ── Load v2.0 candidates ──
    signals = await c.execute_query("""
        SELECT v.trade_date, v.stock_id, v.stock_name,
               v.is_win_3d, v.is_win_5d, v.loss_over_5pct,
               v.next_3d_return, v.next_5d_return,
               c.support_type, c.support_strength, c.pool_entry_type,
               c.candidate_score, c.weak_type, c.candidate_type
        FROM w2s_signal_validation_v1_1b v
        JOIN w2s_candidate_rebuild c ON v.trade_date=c.trade_date AND v.stock_id=c.stock_id
        WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
        ORDER BY v.trade_date, v.stock_id
    """)

    for s in signals:
        td = s["trade_date"]
        if isinstance(td, str):
            s["trade_date"] = date.fromisoformat(td)

    print(f"  Candidates loaded: {len(signals)}")

    # ── Get trading calendar (all unique dates from candidates) ──
    all_trade_dates = sorted({s["trade_date"] for s in signals})
    min_date = all_trade_dates[0]
    max_date = all_trade_dates[-1]

    # ── Compute T+1 for each candidate ──
    # Build T+1 mapping: for each trade_date, what is the next trading day?
    next_trade_date_map: dict[date, date] = {}
    for i, td in enumerate(all_trade_dates):
        if i + 1 < len(all_trade_dates):
            next_trade_date_map[td] = all_trade_dates[i + 1]

    # ── Load all auction snapshots in range ──
    auction_rows = await c.execute_query(
        """SELECT trade_date, stock_id, auction_open_price, auction_open_pct,
                  auction_volume, auction_amount, pre_close,
                  last_minute_amount, last_minute_ratio,
                  prev_day_max_intraday_amount, carry_ratio,
                  price_path_stability_score, is_red_zone,
                  has_end_spike, has_end_drop,
                  shape_features, source_version, source_trace, rule_version
           FROM pre_market_auction_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           ORDER BY trade_date, stock_id""",
        (min_date, max_date + timedelta(days=10)),
    )

    # Build auction lookup: (trade_date, stock_id) -> row
    auction_lookup: dict[tuple[date, str], dict] = {}
    for r in auction_rows:
        td = r["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        auction_lookup[(td, str(r["stock_id"]))] = r

    print(f"  Auction snapshots loaded: {len(auction_rows)}")
    print(f"  Unique auction dates: {len({r['trade_date'] for r in auction_rows})}")
    print(f"  Unique auction stocks: {len({r['stock_id'] for r in auction_rows})}")

    # ── Match each candidate to T+1 auction ──
    source_counts: dict[str, int] = defaultdict(int)
    per_date: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_stock: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    matched_details: list[dict] = []
    skipped_no_next_day = 0

    for s in signals:
        td = s["trade_date"]
        sid = str(s["stock_id"])

        t1_date = next_trade_date_map.get(td)
        if t1_date is None:
            skipped_no_next_day += 1
            continue

        auction_row = auction_lookup.get((t1_date, sid))
        source = classify_auction_source(auction_row)

        source_counts[source] += 1
        date_key = td.isoformat()
        per_date[date_key][source] += 1
        per_stock[sid][source] += 1

        if auction_row:
            matched_details.append({
                "trade_date": td.isoformat(),
                "stock_id": sid,
                "t1_date": t1_date.isoformat(),
                "auction_source": source,
                "auction_open_pct": float(auction_row.get("auction_open_pct") or 0),
                "price_path_stability_score": float(auction_row.get("price_path_stability_score") or 0),
                "has_end_drop": bool(auction_row.get("has_end_drop")),
                "has_end_spike": bool(auction_row.get("has_end_spike")),
                "is_red_zone": bool(auction_row.get("is_red_zone")),
                "record_mode": (
                    (json.loads(auction_row["source_trace"]).get("record_mode")
                     if isinstance(auction_row.get("source_trace"), str) else
                     (auction_row.get("source_trace") or {}).get("record_mode"))
                    if auction_row.get("source_trace") else ""
                ),
            })
        else:
            matched_details.append({
                "trade_date": td.isoformat(),
                "stock_id": sid,
                "t1_date": t1_date.isoformat(),
                "auction_source": "missing",
                "auction_open_pct": None,
                "price_path_stability_score": None,
                "has_end_drop": None,
                "has_end_spike": None,
                "is_red_zone": None,
                "record_mode": "",
            })

    total = len(signals) - skipped_no_next_day

    # ── PRINT REPORT ──
    print(f"\n{'─'*70}")
    print(f"  1. OVERALL COVERAGE")
    print(f"{'─'*70}")
    print(f"  Total signals (with T+1): {total}")
    print(f"  Skipped (no next trading day): {skipped_no_next_day}")
    print()
    for src in ["real_auction", "daily_open_proxy", "missing"]:
        cnt = source_counts.get(src, 0)
        pct = cnt / total * 100 if total else 0
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"  {src:<20} {cnt:>5} ({pct:>5.1f}%)  {bar}")

    # ── 2. Per-date coverage ──
    print(f"\n{'─'*70}")
    print(f"  2. PER-DATE COVERAGE")
    print(f"{'─'*70}")
    print(f"  {'Date':<14} {'Signals':>7} {'real':>5} {'proxy':>5} {'missing':>7} {'real%':>7} {'proxy%':>7} {'miss%':>7}")

    dates_sorted = sorted(per_date.keys())
    for dk in dates_sorted:
        stats = per_date[dk]
        n = sum(stats.values())
        r = stats.get("real_auction", 0)
        p = stats.get("daily_open_proxy", 0)
        m = stats.get("missing", 0)
        print(f"  {dk:<14} {n:>7} {r:>5} {p:>5} {m:>7} {r/n*100:>6.1f}% {p/n*100:>6.1f}% {m/n*100:>6.1f}%")

    # ── 3. Per-stock top repeaters coverage ──
    print(f"\n{'─'*70}")
    print(f"  3. STOCK COVERAGE (stocks with >=3 signals)")
    print(f"{'─'*70}")

    stock_summary = []
    for sid, stats in per_stock.items():
        n = sum(stats.values())
        if n >= 3:
            r = stats.get("real_auction", 0)
            p = stats.get("daily_open_proxy", 0)
            stock_summary.append((sid, n, r, p, r / n, (r + p) / n))

    stock_summary.sort(key=lambda x: -x[1])
    print(f"  {'Stock':<14} {'N':>4} {'real':>5} {'proxy':>5} {'real%':>7} {'any%':>7}")
    for sid, n, r, p, rpct, apct in stock_summary[:20]:
        print(f"  {sid:<14} {n:>4} {r:>5} {p:>5} {rpct:>6.1f}% {apct:>6.1f}%")

    total_stocks = len(per_stock)
    stocks_with_real = sum(1 for sid, stats in per_stock.items() if stats.get("real_auction", 0) > 0)
    stocks_with_any = sum(1 for sid, stats in per_stock.items() if stats.get("real_auction", 0) + stats.get("daily_open_proxy", 0) > 0)
    print(f"\n  Total unique stocks: {total_stocks}")
    print(f"  Stocks with real_auction: {stocks_with_real} ({stocks_with_real/total_stocks*100:.1f}%)")
    print(f"  Stocks with any auction data: {stocks_with_any} ({stocks_with_any/total_stocks*100:.1f}%)")

    # ── 4. Auction quality for matched rows ──
    real_rows = [d for d in matched_details if d["auction_source"] == "real_auction"]
    proxy_rows = [d for d in matched_details if d["auction_source"] == "daily_open_proxy"]

    print(f"\n{'─'*70}")
    print(f"  4. AUCTION QUALITY (matched rows)")
    print(f"{'─'*70}")

    if real_rows:
        has_drop = sum(1 for r in real_rows if r.get("has_end_drop"))
        has_spike = sum(1 for r in real_rows if r.get("has_end_spike"))
        red_zone = sum(1 for r in real_rows if r.get("is_red_zone"))
        print(f"  real_auction ({len(real_rows)} rows):")
        print(f"    has_end_drop:  {has_drop} ({has_drop/len(real_rows)*100:.1f}%)")
        print(f"    has_end_spike: {has_spike} ({has_spike/len(real_rows)*100:.1f}%)")
        print(f"    is_red_zone:   {red_zone} ({red_zone/len(real_rows)*100:.1f}%)")
        stability_scores = [r["price_path_stability_score"] for r in real_rows if r.get("price_path_stability_score") is not None]
        if stability_scores:
            print(f"    stability_score: min={min(stability_scores):.1f} med={sorted(stability_scores)[len(stability_scores)//2]:.1f} max={max(stability_scores):.1f}")
    else:
        print(f"  real_auction: 0 rows — NO REAL AUCTION DATA")

    if proxy_rows:
        print(f"  daily_open_proxy ({len(proxy_rows)} rows): single-point data only")
    else:
        print(f"  daily_open_proxy: 0 rows")

    # ── 5. CONCLUSION ──
    print(f"\n{'='*70}")
    print(f"  READINESS CONCLUSIONS")
    print(f"{'='*70}")

    real_pct = source_counts.get("real_auction", 0) / total * 100 if total else 0
    proxy_pct = source_counts.get("daily_open_proxy", 0) / total * 100 if total else 0
    missing_pct = source_counts.get("missing", 0) / total * 100 if total else 0

    conclusions = {
        "total_signals": total,
        "real_auction_count": source_counts.get("real_auction", 0),
        "real_auction_pct": round(real_pct, 2),
        "daily_open_proxy_count": source_counts.get("daily_open_proxy", 0),
        "daily_open_proxy_pct": round(proxy_pct, 2),
        "missing_count": source_counts.get("missing", 0),
        "missing_pct": round(missing_pct, 2),
        "unique_auction_dates": len({r["trade_date"] for r in auction_rows}),
        "unique_auction_stocks": len({r["stock_id"] for r in auction_rows}),
        "stocks_with_real_auction": stocks_with_real,
        "stocks_with_any_auction": stocks_with_any,
        "total_unique_stocks": total_stocks,
        "recommendation": "",
    }

    print(f"  real_auction:      {conclusions['real_auction_count']}/{total} ({real_pct:.1f}%)")
    print(f"  daily_open_proxy:  {conclusions['daily_open_proxy_count']}/{total} ({proxy_pct:.1f}%)")
    print(f"  missing:           {conclusions['missing_count']}/{total} ({missing_pct:.1f}%)")

    if real_pct >= 30:
        conclusions["recommendation"] = "GO: real_auction coverage sufficient for v2.2 full implementation"
        print(f"\n  → GO: real_auction coverage >= 30%. Proceed with v2.2b AuctionConfirmationService.")
    elif real_pct >= 10:
        conclusions["recommendation"] = "PARTIAL: real_auction exists but limited. Build framework with real_auction + proxy separation. Do proxy-grouped validation."
        print(f"\n  → PARTIAL: real_auction coverage {real_pct:.1f}%. Build framework but separate real vs proxy.")
    elif proxy_pct >= 40:
        conclusions["recommendation"] = "PROXY_ONLY: No meaningful real_auction. Build framework with daily_open_proxy only. Mark all results as proxy."
        print(f"\n  → PROXY_ONLY: Build framework with daily_open_proxy. Results must be labeled proxy.")
    else:
        conclusions["recommendation"] = "BLOCKED: Insufficient auction data. Prioritize data collection before v2.2."
        print(f"\n  → BLOCKED: Insufficient auction data. Prioritize data collection.")

    # ── Save report ──
    report = {
        "phase": "v2.2a_auction_data_readiness",
        "timestamp": datetime.now().isoformat(),
        "overall": {
            "total_signals": total,
            "skipped_no_next_day": skipped_no_next_day,
            "source_counts": dict(source_counts),
            "source_pcts": {
                "real_auction": round(real_pct, 2),
                "daily_open_proxy": round(proxy_pct, 2),
                "missing": round(missing_pct, 2),
            },
        },
        "per_date": {
            dk: {
                "signals": sum(per_date[dk].values()),
                "real_auction": per_date[dk].get("real_auction", 0),
                "daily_open_proxy": per_date[dk].get("daily_open_proxy", 0),
                "missing": per_date[dk].get("missing", 0),
            }
            for dk in dates_sorted
        },
        "stock_coverage": {
            "total_unique": total_stocks,
            "with_real_auction": stocks_with_real,
            "with_any_auction": stocks_with_any,
            "top_repeaters": [
                {"stock_id": sid, "n": n, "real": r, "proxy": p}
                for sid, n, r, p, _, _ in stock_summary[:20]
            ],
        },
        "auction_quality": {
            "real_auction_rows": len(real_rows),
            "proxy_rows": len(proxy_rows),
            "has_end_drop_count": sum(1 for r in real_rows if r.get("has_end_drop")),
            "has_end_spike_count": sum(1 for r in real_rows if r.get("has_end_spike")),
            "is_red_zone_count": sum(1 for r in real_rows if r.get("is_red_zone")),
        },
        "conclusions": conclusions,
    }

    out_path = Path(__file__).parent / f"v2_2a_auction_data_readiness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")

    await gw.close()
    return report


if __name__ == "__main__":
    asyncio.run(main())
