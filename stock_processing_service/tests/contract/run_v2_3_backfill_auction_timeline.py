"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.3 — Backfill Auction Timeline from Existing Snapshot Data             ║
║  Date: 2026-05-19                                                          ║
║  Purpose: Convert single_point_snapshot → synthetic timeline → features  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Pipeline:
  pre_market_auction_snapshot (single_point)
    → pre_market_auction_timeline_raw (synthetic point at 09:25)
    → pre_market_auction_feature (computed features)

Only processes stocks in w2s_candidate_rebuild (v2.0 candidates).
NOT full market.

Usage: python stock_processing_service/tests/contract/run_v2_3_backfill_auction_timeline.py
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


async def main():
    print(f"\n{'='*70}")
    print(f"  v2.3 — BACKFILL AUCTION TIMELINE + FEATURES")
    print(f"  Source: pre_market_auction_snapshot (single_point)")
    print(f"  Target: pre_market_auction_timeline_raw + pre_market_auction_feature")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ── Import domain service ──
    from stock_processing_service.domain.services.auction_timeline_feature_builder import (
        AuctionTimelineFeatureBuilder,
        TimelinePoint,
    )

    builder = AuctionTimelineFeatureBuilder()

    # ── Step 1: Get candidate stock set ──
    cand_stocks = await c.execute_query(
        """SELECT DISTINCT stock_id
           FROM w2s_candidate_rebuild
           WHERE rule_version = 'w2s_v1.0_usecase_replay'"""
    )
    target_stocks = {str(r["stock_id"]) for r in cand_stocks}
    print(f"  Candidate stocks (target scope): {len(target_stocks)}")

    # Also add code-only aliases for matching
    target_aliases = set(target_stocks)
    for sid in list(target_stocks):
        code = sid.split(".", 1)[0] if "." in sid else sid
        target_aliases.add(code)

    # ── Step 2: Load snapshot data for candidate dates ──
    date_range = await c.execute_query(
        """SELECT MIN(next_trade_date) AS min_date, MAX(next_trade_date) AS max_date
           FROM w2s_candidate_rebuild
           WHERE rule_version = 'w2s_v1.0_usecase_replay'"""
    )
    min_date = date_range[0]["min_date"]
    max_date = date_range[0]["max_date"]
    if isinstance(min_date, str):
        min_date = date.fromisoformat(min_date)
    if isinstance(max_date, str):
        max_date = date.fromisoformat(max_date)

    snapshots = await c.execute_query(
        """SELECT trade_date, stock_id, stock_name,
                  auction_open_price, pre_close, auction_open_pct,
                  auction_volume, auction_amount,
                  last_minute_amount, last_minute_ratio,
                  prev_day_max_intraday_amount, carry_ratio,
                  price_path_stability_score,
                  is_red_zone, has_end_spike, has_end_drop,
                  shape_features, source_type, source_version,
                  source_trace, source_trace_id, rule_version
           FROM pre_market_auction_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           ORDER BY trade_date, stock_id""",
        (min_date, max_date + timedelta(days=5)),
    )

    print(f"  Snapshots loaded: {len(snapshots)}")

    # ── Also load prev_day_max_intraday_amount from daily bars ──
    # (pre_market_auction_snapshot already has this field)

    # ── Step 3: Filter to candidate stocks & build timeline ──
    raw_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    stats: dict[str, int] = defaultdict(int)

    for snap in snapshots:
        td = snap["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        sid = str(snap["stock_id"])

        # Filter: only candidate stocks
        code = sid.split(".", 1)[0] if "." in sid else sid
        if sid not in target_aliases and code not in target_aliases:
            stats["skipped_not_candidate"] += 1
            continue

        # Parse shape_features and source_trace
        shape_features = snap.get("shape_features") or []
        if isinstance(shape_features, str):
            try: shape_features = json.loads(shape_features)
            except Exception: shape_features = []

        source_trace = snap.get("source_trace") or {}
        if isinstance(source_trace, str):
            try: source_trace = json.loads(source_trace)
            except Exception: source_trace = {}

        open_pct = float(snap.get("auction_open_pct") or 0)
        open_price = float(snap.get("auction_open_price") or 0)
        amount = float(snap.get("auction_amount") or 0)
        volume = float(snap.get("auction_volume") or 0)

        data_mode = "synthetic_single_point"

        # ── Build raw timeline rows ──
        # Synthetic: one point at 09:25 from the snapshot
        timeline_point = {
            "snapshot_time": "09:25:00",
            "indicative_open_price": open_price,
            "indicative_open_pct": open_pct,
            "matched_volume": volume,
            "matched_amount": amount,
            "bid_price": None,
            "ask_price": None,
            "bid_volume": None,
            "ask_volume": None,
        }

        raw_rows.append({
            "trade_date": td,
            "stock_id": sid,
            "snapshot_time": "09:25:00",
            "indicative_open_price": open_price,
            "indicative_open_pct": open_pct,
            "matched_volume": volume,
            "matched_amount": amount,
            "bid_price": None,
            "ask_price": None,
            "bid_volume": None,
            "ask_volume": None,
            "source_name": "tushare",
            "source_api": "stk_auction",
            "data_mode": data_mode,
            "raw_payload": json.dumps({
                "source": "pre_market_auction_snapshot",
                "source_trace_id": snap.get("source_trace_id", ""),
                "original_shape_features": shape_features,
            }),
            "source_trace": json.dumps({
                "migration": "v2.3_synthetic_from_single_point",
                "original_source_version": snap.get("source_version", ""),
                "original_source_type": snap.get("source_type", ""),
                "original_record_mode": source_trace.get("record_mode", ""),
            }),
        })

        stats["raw_rows_created"] += 1

        # ── Build features ──
        point = TimelinePoint(
            snapshot_time="09:25:00",
            indicative_price=open_price,
            indicative_open_pct=open_pct,
            matched_volume=volume,
            matched_amount=amount,
        )

        prev_day_max = float(snap.get("prev_day_max_intraday_amount") or 0)
        stability_from_snap = float(snap.get("price_path_stability_score") or 0)
        has_drop = bool(snap.get("has_end_drop") or False)
        has_spike = bool(snap.get("has_end_spike") or False)
        is_red = bool(snap.get("is_red_zone") or False)
        last_ratio = float(snap.get("last_minute_ratio") or 0)

        feature = builder.build(
            trade_date=td,
            stock_id=sid,
            points=[point],
            prev_day_max_intraday_amount=prev_day_max,
            stock_name=str(snap.get("stock_name") or ""),
            subject_key="",
            theme_name="",
            source_trace={
                "backfill": "v2.3_synthetic_from_snapshot",
                "original_stability": stability_from_snap,
                "original_has_end_drop": has_drop,
                "original_has_end_spike": has_spike,
                "original_is_red_zone": is_red,
            },
        )

        # Override with original snapshot values where available
        if stability_from_snap > 0:
            feature.price_stability_score = stability_from_snap
        if has_drop:
            feature.has_end_drop = True
            feature.tail_drop_risk = 0.85
            if feature.auction_pattern == "stable":
                feature.auction_pattern = "tail_drop"
        if has_spike:
            feature.has_end_spike = True
            if feature.auction_pattern in {"stable", "tail_drop"}:
                feature.auction_pattern = "tail_lift" if not has_drop else feature.auction_pattern
        if is_red:
            feature.is_red_zone = True
        if last_ratio > 0 and feature.last_minute_volume_ratio == 0:
            feature.last_minute_volume_ratio = last_ratio
        if "single_point_snapshot" not in feature.shape_features:
            feature.shape_features.append("single_point_snapshot")

        feature_rows.append({
            "trade_date": td,
            "stock_id": sid,
            "stock_name": str(snap.get("stock_name") or ""),
            "subject_key": "",
            "theme_name": "",
            "open_pct_0925": feature.open_pct_0925,
            "price_trend_0920_0925": feature.price_trend_0920_0925,
            "price_stability_score": feature.price_stability_score,
            "last_minute_price_change": feature.last_minute_price_change,
            "last_minute_volume_ratio": feature.last_minute_volume_ratio,
            "last_minute_grab_score": feature.last_minute_grab_score,
            "tail_drop_risk": feature.tail_drop_risk,
            "auction_volume_ratio": feature.auction_volume_ratio,
            "auction_pattern": feature.auction_pattern,
            "shape_features": json.dumps(feature.shape_features),
            "is_red_zone": feature.is_red_zone,
            "has_end_spike": feature.has_end_spike,
            "has_end_drop": feature.has_end_drop,
            "data_status": feature.data_status,
            "timeline_points_count": feature.timeline_points_count,
            "timeline_points": json.dumps(feature.timeline_points_snapshot),
            "rule_version": feature.rule_version,
            "source_trace": json.dumps(feature.source_trace),
        })
        stats["feature_rows_created"] += 1

    print(f"\n  Stats:")
    for k, v in sorted(stats.items()):
        print(f"    {k}: {v}")

    # ── Step 4: Write raw rows ──
    if raw_rows:
        raw_written = 0
        for r in raw_rows:
            try:
                await c.execute_query("""
                    INSERT INTO pre_market_auction_timeline_raw (
                        trade_date, stock_id, snapshot_time,
                        indicative_open_price, indicative_open_pct,
                        matched_volume, matched_amount,
                        bid_price, ask_price, bid_volume, ask_volume,
                        source_name, source_api, data_mode,
                        raw_payload, source_trace)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
                            $12,$13,$14,$15::jsonb,$16::jsonb)
                    ON CONFLICT (trade_date, stock_id, snapshot_time) DO NOTHING
                """, (
                    r["trade_date"], r["stock_id"], r["snapshot_time"],
                    r["indicative_open_price"], r["indicative_open_pct"],
                    r["matched_volume"], r["matched_amount"],
                    r["bid_price"], r["ask_price"],
                    r["bid_volume"], r["ask_volume"],
                    r["source_name"], r["source_api"], r["data_mode"],
                    r["raw_payload"], r["source_trace"],
                ))
                raw_written += 1
            except Exception as e:
                print(f"    ⚠ raw write error: {e}")

        print(f"\n  Raw rows written: {raw_written}/{len(raw_rows)}")

    # ── Step 5: Write feature rows ──
    if feature_rows:
        feat_written = 0
        for r in feature_rows:
            try:
                await c.execute_query("""
                    INSERT INTO pre_market_auction_feature (
                        trade_date, stock_id, stock_name, subject_key, theme_name,
                        open_pct_0925, price_trend_0920_0925,
                        price_stability_score, last_minute_price_change,
                        last_minute_volume_ratio, last_minute_grab_score,
                        tail_drop_risk, auction_volume_ratio,
                        auction_pattern, shape_features,
                        is_red_zone, has_end_spike, has_end_drop,
                        data_status, timeline_points_count, timeline_points,
                        rule_version, source_trace)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                            $14,$15::jsonb,$16,$17,$18,
                            $19,$20,$21::jsonb,$22,$23::jsonb)
                    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                        open_pct_0925 = EXCLUDED.open_pct_0925,
                        price_stability_score = EXCLUDED.price_stability_score,
                        data_status = EXCLUDED.data_status,
                        timeline_points_count = EXCLUDED.timeline_points_count,
                        timeline_points = EXCLUDED.timeline_points,
                        source_trace = EXCLUDED.source_trace
                """, (
                    r["trade_date"], r["stock_id"], r["stock_name"],
                    r["subject_key"], r["theme_name"],
                    r["open_pct_0925"], r["price_trend_0920_0925"],
                    r["price_stability_score"], r["last_minute_price_change"],
                    r["last_minute_volume_ratio"], r["last_minute_grab_score"],
                    r["tail_drop_risk"], r["auction_volume_ratio"],
                    r["auction_pattern"], r["shape_features"],
                    r["is_red_zone"], r["has_end_spike"], r["has_end_drop"],
                    r["data_status"], r["timeline_points_count"], r["timeline_points"],
                    r["rule_version"], r["source_trace"],
                ))
                feat_written += 1
            except Exception as e:
                print(f"    ⚠ feature write error: {e}")

        print(f"  Feature rows written: {feat_written}/{len(feature_rows)}")

    print(f"\n{'='*70}")
    print(f"  BACKFILL COMPLETE")
    print(f"{'='*70}\n")

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
