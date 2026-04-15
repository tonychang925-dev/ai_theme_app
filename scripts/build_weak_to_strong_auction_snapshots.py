#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List

import asyncpg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill pre_market_auction_snapshot for weak-to-strong candidates.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument(
        "--dsn",
        default=os.getenv("POSTGRES_DSN", "postgresql://postgres:zxbzj~925@localhost:5432/stock_data_test"),
        help="Postgres DSN",
    )
    parser.add_argument("--max-candidates", type=int, default=200, help="Max candidates to process")
    parser.add_argument("--proxy-ratio", type=float, default=0.04, help="Auction amount proxy ratio vs daily amount")
    return parser.parse_args()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _candidate_last_minute_ratio(candidate_type: str, pct_chg: float) -> float:
    base = {
        "dragon_repair": 0.36,
        "subdragon_repair": 0.32,
        "bad_limit_repair": 0.29,
        "upper_shadow_repair": 0.24,
        "strong_trend_repair": 0.27,
        "generic_repair": 0.22,
    }.get(candidate_type, 0.22)
    if pct_chg > 1.5:
        base += 0.03
    if pct_chg < -2.0:
        base -= 0.02
    return max(0.15, min(base, 0.45))


def _stability_score(pct_chg: float, candidate_type: str) -> float:
    score = 84.0 - abs(pct_chg) * 2.2
    if candidate_type in {"dragon_repair", "subdragon_repair"}:
        score += 6.0
    if candidate_type == "bad_limit_repair":
        score -= 4.0
    return max(35.0, min(score, 95.0))


async def run(trade_date: str, dsn: str, max_candidates: int, proxy_ratio: float) -> Dict[str, Any]:
    td = datetime.strptime(trade_date, "%Y-%m-%d").date()
    conn = await asyncpg.connect(dsn=dsn)
    try:
        candidates = await conn.fetch(
            """
            SELECT id, stock_id, stock_name, subject_key, theme_name, candidate_type
            FROM weak_to_strong_candidate_pool
            WHERE next_trade_date = $1::date
            ORDER BY candidate_score DESC, id ASC
            LIMIT $2
            """,
            td,
            max(max_candidates, 1),
        )
        if not candidates:
            return {"trade_date": trade_date, "processed": 0, "upserted": 0, "warnings": ["no candidates"]}

        upsert_sql = """
        INSERT INTO pre_market_auction_snapshot (
            trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
            auction_open_price, pre_close, auction_open_pct,
            auction_volume, auction_amount, last_minute_amount, last_minute_ratio,
            prev_day_max_intraday_amount, carry_ratio, price_path_stability_score,
            is_red_zone, has_end_spike, has_end_drop, shape_features,
            source_type, source_trace_id, source_trace, source_version, rule_version, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15, $16,
            $17, $18, $19, $20::jsonb,
            $21, $22, $23::jsonb, $24, $25, NOW()
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            role_label = EXCLUDED.role_label,
            auction_open_price = EXCLUDED.auction_open_price,
            pre_close = EXCLUDED.pre_close,
            auction_open_pct = EXCLUDED.auction_open_pct,
            auction_volume = EXCLUDED.auction_volume,
            auction_amount = EXCLUDED.auction_amount,
            last_minute_amount = EXCLUDED.last_minute_amount,
            last_minute_ratio = EXCLUDED.last_minute_ratio,
            prev_day_max_intraday_amount = EXCLUDED.prev_day_max_intraday_amount,
            carry_ratio = EXCLUDED.carry_ratio,
            price_path_stability_score = EXCLUDED.price_path_stability_score,
            is_red_zone = EXCLUDED.is_red_zone,
            has_end_spike = EXCLUDED.has_end_spike,
            has_end_drop = EXCLUDED.has_end_drop,
            shape_features = EXCLUDED.shape_features,
            source_type = EXCLUDED.source_type,
            source_trace_id = EXCLUDED.source_trace_id,
            source_trace = EXCLUDED.source_trace,
            source_version = EXCLUDED.source_version,
            rule_version = EXCLUDED.rule_version,
            updated_at = NOW()
        """

        upserted = 0
        warnings: List[str] = []
        async with conn.transaction():
            for c in candidates:
                stock_id = str(c["stock_id"])
                stock_code = stock_id.split(".", 1)[0]
                snap = await conn.fetchrow(
                    """
                    SELECT stock_id, stock_name, subject_key, pct_chg, close_price, pre_close, open_price, volume, amount
                    FROM subject_stock_daily_snapshot
                    WHERE trade_date = $1::date
                      AND split_part(stock_id, '.', 1) = $2
                    ORDER BY amount DESC NULLS LAST
                    LIMIT 1
                    """,
                    td,
                    stock_code,
                )
                if not snap:
                    warnings.append(f"snapshot missing: {stock_id}")
                    continue

                prev = await conn.fetchrow(
                    """
                    SELECT close_price, amount
                    FROM subject_stock_daily_snapshot
                    WHERE trade_date < $1::date
                      AND split_part(stock_id, '.', 1) = $2
                    ORDER BY trade_date DESC
                    LIMIT 1
                    """,
                    td,
                    stock_code,
                )

                close_price = _to_float(snap["close_price"], 0.0)
                pre_close = _to_float(snap["pre_close"], 0.0) or _to_float(prev["close_price"], close_price) if prev else _to_float(snap["pre_close"], close_price)
                if pre_close <= 0:
                    pre_close = close_price if close_price > 0 else 1.0
                auction_open_price = _to_float(snap["open_price"], close_price if close_price > 0 else pre_close)
                auction_open_pct = ((auction_open_price - pre_close) / pre_close) * 100.0 if pre_close > 0 else 0.0

                amount = _to_float(snap["amount"], 0.0)
                volume = _to_float(snap["volume"], 0.0)
                auction_amount = max(amount * proxy_ratio, 1_000_000.0)
                auction_volume = max(volume * proxy_ratio, 1_000.0)
                pct_chg = _to_float(snap["pct_chg"], 0.0)
                candidate_type = str(c["candidate_type"] or "generic_repair")
                last_ratio = _candidate_last_minute_ratio(candidate_type, pct_chg)
                last_amount = auction_amount * last_ratio
                prev_max = max(_to_float(prev["amount"], amount) * 0.12 if prev else amount * 0.12, 1_000_000.0)
                carry_ratio = auction_amount / prev_max if prev_max > 0 else 0.0
                stability = _stability_score(pct_chg, candidate_type)
                has_end_spike = last_ratio >= 0.28 and auction_open_pct >= 0
                has_end_drop = auction_open_pct < -1.2
                role_label = "龙头" if candidate_type == "dragon_repair" else ("龙二" if candidate_type == "subdragon_repair" else "强趋势")
                shape_features = []
                if has_end_spike:
                    shape_features.append("tail_upturn")
                if auction_open_pct > 0:
                    shape_features.append("red_zone")
                if stability >= 70:
                    shape_features.append("stable")

                source_trace = {
                    "proxy_mode": "daily_snapshot_based",
                    "proxy_ratio": proxy_ratio,
                    "candidate_type": candidate_type,
                    "pct_chg": pct_chg,
                }
                trace_id = hashlib.md5(
                    f"{trade_date}|{stock_id}|{auction_open_price:.4f}|{auction_amount:.2f}|proxy".encode("utf-8")
                ).hexdigest()[:16]

                await conn.execute(
                    upsert_sql,
                    td,
                    stock_id,
                    str(c["stock_name"] or snap["stock_name"] or stock_id),
                    str(c["subject_key"] or snap["subject_key"] or ""),
                    str(c["theme_name"] or c["subject_key"] or ""),
                    role_label,
                    round(auction_open_price, 4),
                    round(pre_close, 4),
                    round(auction_open_pct, 4),
                    round(auction_volume, 2),
                    round(auction_amount, 2),
                    round(last_amount, 2),
                    round(last_ratio, 4),
                    round(prev_max, 2),
                    round(carry_ratio, 4),
                    round(stability, 4),
                    bool(auction_open_pct > 0),
                    has_end_spike,
                    has_end_drop,
                    json.dumps(shape_features, ensure_ascii=False),
                    "p3.phase3.auction_snapshot.proxy",
                    trace_id,
                    json.dumps(source_trace, ensure_ascii=False),
                    "auction_snapshot.v1.proxy",
                    "auction_snapshot.v1.proxy",
                )
                upserted += 1

        return {
            "trade_date": trade_date,
            "processed": len(candidates),
            "upserted": upserted,
            "warnings": warnings[:20],
        }
    finally:
        await conn.close()


def main() -> int:
    args = parse_args()
    payload = asyncio.run(
        run(
            trade_date=args.trade_date,
            dsn=args.dsn,
            max_candidates=args.max_candidates,
            proxy_ratio=max(min(args.proxy_ratio, 0.2), 0.005),
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

