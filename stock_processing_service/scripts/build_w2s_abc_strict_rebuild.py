"""
Phase -1: Strict A/B/C → D Layer Reconstruction
================================================
Rebuilds weak_to_strong_candidate_pool from raw daily bar data
following the architecture document data flow:

  stock_daily_snapshot (raw bars)
    ↓
  C层: stock_structure_daily_feature (weak_type, support)
  + B层: strong_stock_daily_feature (leader, prior7)
  + A层: subject_daily_feature (mainline)
    ↓
  D层: weak_to_strong_candidate_pool (BuildWeakToStrongCandidateUseCase logic)

STRICT MODE: only uses T-day and prior data. No future data.
"""

from __future__ import annotations

import asyncio, json, logging, os, sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("strict_rebuild")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")
START_DATE = date(2026, 2, 15)
END_DATE = date(2026, 5, 15)
STRICT_RULE_VERSION = "weak_to_strong_candidate.v4_strict_rebuild"


async def get_trading_days(c) -> list[date]:
    """Get all trading days in range from stock_daily_snapshot."""
    rows = await c.execute_query(
        "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
        (START_DATE, END_DATE),
    )
    return [r["trade_date"] for r in rows]


async def load_daily_bars(c, trade_date: date) -> dict[str, dict]:
    """Load all daily bars for a trade date."""
    rows = await c.execute_query(
        "SELECT DISTINCT ON (stock_id) stock_id, stock_name, open_price, high_price, low_price, close_price, pre_close, pct_chg, volume, amount FROM stock_daily_snapshot WHERE trade_date = $1 AND source_name LIKE 'tushare%'",
        (trade_date,),
    )
    return {str(r["stock_id"]): r for r in rows}


async def compute_prior7_features(c, stock_id: str, trade_date: date, all_bars: dict[date, dict[str, dict]]) -> tuple[int, int, float]:
    """Compute prior7_limitup_days and prior7_strong_days from prior bar data.

    Only looks at bars with trade_date < current date (strict: no future data).
    """
    trading_days = sorted([d for d in all_bars if d < trade_date], reverse=True)[:7]
    limitup_days = 0
    strong_days = 0
    prev_day_pct = 0.0
    prev_day_limit_up = False

    for i, td in enumerate(trading_days):
        bar = all_bars[td].get(stock_id)
        if bar is None:
            continue
        pct = float(bar.get("pct_chg") or 0)
        if i == 0:
            prev_day_pct = pct
            prev_day_limit_up = pct >= 9.5
        if pct >= 9.5:
            limitup_days += 1
        if pct >= 5.0:
            strong_days += 1

    return limitup_days, strong_days, prev_day_pct, prev_day_limit_up


def detect_support(bar: dict, prev_bar: dict | None) -> tuple[str, float]:
    """Detect support type and strength from daily bar data.

    Simplified but directionally correct:
    - gap_support: today's low > yesterday's high (gap up)
    - prev_low_support: today's low near yesterday's low
    - ma_support: today's low near 5-day average (approximated)
    """
    low = float(bar.get("low_price") or 0)
    close = float(bar.get("close_price") or 0)
    pre_close = float(bar.get("pre_close") or 0)

    if prev_bar:
        prev_high = float(prev_bar.get("high_price") or 0)
        prev_low = float(prev_bar.get("low_price") or 0)
        prev_close = float(prev_bar.get("close_price") or 0)

        # Gap support: gap up, today's low stayed above yesterday's high
        if low > prev_high * 0.98:
            return "gap_support", min(90.0, 50.0 + (low - prev_high) / prev_high * 500)

        # Previous low support: today's low near yesterday's low
        dist_to_prev_low = abs(low - prev_low) / prev_low if prev_low > 0 else 999
        if dist_to_prev_low < 0.02:
            return "previous_low", 80.0 - dist_to_prev_low * 500

        # Platform support: today's close near yesterday's close
        dist_to_prev_close = abs(close - prev_close) / prev_close if prev_close > 0 else 999
        if dist_to_prev_close < 0.03:
            return "platform_support", 60.0 - dist_to_prev_close * 500

    # MA support (approximate): today's low near pre_close
    dist_to_pre = abs(low - pre_close) / pre_close if pre_close > 0 else 999
    if dist_to_pre < 0.03:
        return "ma_support", 55.0 - dist_to_pre * 500

    # No clear support detected
    if low < pre_close * 0.93:
        return "none", 20.0

    return "weak_support", 40.0


def compute_weak_type(pct_chg: float, prev_day_pct: float, prev_day_limit_up: bool) -> tuple[str, float]:
    """Classify weak type from BuildWeakToStrongCandidateUseCase logic."""
    if prev_day_limit_up and pct_chg < 0:
        return "bad_limit_up", min(100.0, abs(pct_chg) * 12.0 + 20.0)
    if pct_chg <= -5.0:
        return "big_negative_line", min(100.0, abs(pct_chg) * 10.0)
    if -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
        return "upper_shadow", 55.0
    if pct_chg <= -1.0:
        return "high_open_low_close", min(100.0, abs(pct_chg) * 8.0 + 10.0)
    return "fake_break", 40.0


def compute_candidate_score(
    *,
    is_leader: bool,
    recent_limit_up_count: int,
    rank_order: int,
    weak_intensity: float,
    support_strength: float,
    mainline_strength_score: float,
    fade_watch: bool,
    pct_chg: float,
    prev_day_pct: float,
) -> float:
    """Replicate BuildWeakToStrongCandidateUseCase candidate_score logic."""
    score = 45.0
    if is_leader:
        score += 18.0
    score += min(recent_limit_up_count * 4.0, 12.0)
    if rank_order <= 3:
        score += 8.0
    score += min(weak_intensity * 0.08, 8.0)
    score += min(support_strength * 0.1, 9.0)

    # day_weak_score
    if pct_chg < -4.0:
        score += 20.0
    elif pct_chg < -2.0:
        score += 16.0
    elif pct_chg < -1.0:
        score += 10.0
    else:
        score += 6.0

    # prev_day_weak_score
    if prev_day_pct < -3.0:
        score += 10.0
    elif prev_day_pct < -1.5:
        score += 8.0
    elif prev_day_pct < 0:
        score += 5.0

    score += min(mainline_strength_score * 0.08, 8.0)

    # fade_watch penalty
    if fade_watch:
        if mainline_strength_score >= 75.0:
            score -= 4.0
        elif mainline_strength_score >= 60.0:
            score -= 8.0
        else:
            score -= 12.0

    return max(0.0, min(score, 100.0))


async def main():
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    try:
        # Step 0: Create C-layer table
        await c.execute_query("""
            CREATE TABLE IF NOT EXISTS stock_structure_daily_feature (
                trade_date DATE NOT NULL,
                stock_id VARCHAR(32) NOT NULL,
                stock_name VARCHAR(64),
                weak_type VARCHAR(64),
                weak_intensity NUMERIC(8,2),
                support_type VARCHAR(64),
                support_strength NUMERIC(8,2),
                gap_not_filled BOOLEAN DEFAULT false,
                rule_version VARCHAR(64) NOT NULL DEFAULT 'stock_structure_v0.1',
                source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (trade_date, stock_id, rule_version)
            )
        """)
        logger.info("C-layer table ready")

        # Load trading days
        trading_days = await get_trading_days(c)
        logger.info("Trading days: %d", len(trading_days))

        # Preload ALL bars for the entire range (for prior7 computation)
        all_bars: dict[date, dict[str, dict]] = {}
        for td in trading_days:
            all_bars[td] = await load_daily_bars(c, td)
        logger.info("Preloaded bars for %d days", len(all_bars))

        # Load B-layer features
        b_layer = {}
        b_rows = await c.execute_query(
            "SELECT * FROM strong_stock_daily_feature WHERE rule_version = 'strong_stock_feature_v0.1'"
        )
        for r in b_rows:
            key = (r["trade_date"], str(r["stock_id"]))
            b_layer[key] = r
        logger.info("B-layer: %d rows loaded", len(b_layer))

        # Load A-layer features
        a_layer = {}
        a_rows = await c.execute_query(
            "SELECT * FROM subject_daily_feature WHERE rule_version = 'subject_feature_v0.1'"
        )
        for r in a_rows:
            key = (r["trade_date"], str(r["subject_key"]))
            a_layer[key] = r
        logger.info("A-layer: %d rows loaded", len(a_layer))

        # Step 1: Build C-layer for each trading day
        c_written = 0
        for td in trading_days:
            bars = all_bars.get(td, {})
            prev_bars = all_bars.get(td - timedelta(days=1), {})
            # Try previous trading day
            if not prev_bars:
                prev_td = sorted([d for d in trading_days if d < td], reverse=True)
                if prev_td:
                    prev_bars = all_bars.get(prev_td[0], {})

            for sid, bar in bars.items():
                pct = float(bar.get("pct_chg") or 0)
                # Only compute C-layer for stocks with meaningful moves
                if pct >= 0:
                    continue

                prev_bar = prev_bars.get(sid)
                supp_type, supp_str = detect_support(bar, prev_bar)
                weak_type, weak_intensity = compute_weak_type(
                    pct, 0.0, False  # prev_day values computed later during D-layer
                )

                try:
                    await c.execute_query("""
                        INSERT INTO stock_structure_daily_feature (trade_date, stock_id, stock_name,
                            weak_type, weak_intensity, support_type, support_strength,
                            rule_version, source_trace)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,'stock_structure_v0.1',
                            jsonb_build_object('method','strict_rebuild','date',$1::text))
                        ON CONFLICT (trade_date, stock_id, rule_version) DO UPDATE SET
                            weak_type = EXCLUDED.weak_type,
                            support_type = EXCLUDED.support_type,
                            support_strength = EXCLUDED.support_strength
                    """, (td, sid, bar.get("stock_name",""), weak_type, str(weak_intensity),
                          supp_type, str(supp_str)))
                    c_written += 1
                except Exception:
                    pass

        c_cnt = await c.execute_query("SELECT COUNT(*) as n FROM stock_structure_daily_feature")
        logger.info("C-layer: %d rows written (total: %d)", c_written, c_cnt[0]["n"])

        # Step 2: Build D-layer (candidates) from A/B/C
        d_written = 0
        gates_hit = {"total": 0, "pct_gate": 0, "history": 0, "prior7": 0, "support": 0, "pass": 0}

        for td in trading_days:
            bars = all_bars.get(td, {})

            for sid, bar in bars.items():
                gates_hit["total"] += 1
                pct = float(bar.get("pct_chg") or 0)

                # Gate 1: pct_chg must be < -1.0
                if pct >= 0.0 or pct > -1.0:
                    gates_hit["pct_gate"] += 1
                    continue

                # Look up B-layer features (strict: trade_date <= current)
                b_feat = b_layer.get((td, sid))
                if b_feat is None:
                    # Try nearest prior date
                    for lookback in range(1, 6):
                        prev_td_candidates = [d for d in trading_days if d <= td]
                        if lookback <= len(prev_td_candidates):
                            lookback_date = prev_td_candidates[-lookback]
                            b_feat = b_layer.get((lookback_date, sid))
                            if b_feat:
                                break
                if b_feat is None:
                    gates_hit["history"] += 1
                    continue

                is_leader = bool(b_feat.get("is_leader") or False)
                recent_limit_up = int(b_feat.get("recent_limit_up_count") or 0)
                rank_order = int(b_feat.get("rank_order") or 999)

                # Gate 2: strong_history
                strong_history = is_leader or recent_limit_up >= 1 or rank_order <= 5
                if not strong_history:
                    gates_hit["history"] += 1
                    continue

                # Compute prior7 features from actual prior bars
                prior7_lim, prior7_str, prev_day_pct, prev_day_limit_up = await compute_prior7_features(
                    c, sid, td, all_bars
                )

                # Gate 3: prior7
                if prior7_lim < 1 or prior7_str < 1:
                    gates_hit["prior7"] += 1
                    continue

                # Look up C-layer for support
                supp_type = "none"
                supp_strength = 0.0
                c_feat = None
                c_rows_check = await c.execute_query(
                    "SELECT * FROM stock_structure_daily_feature WHERE trade_date = $1 AND stock_id = $2 LIMIT 1",
                    (td, sid)
                )
                if c_rows_check:
                    c_feat = c_rows_check[0]
                    supp_type = str(c_feat.get("support_type") or "none")
                    supp_strength = float(c_feat.get("support_strength") or 0)

                # Gate 4: support
                if supp_type in ("", "none") or supp_strength < 45.0:
                    gates_hit["support"] += 1
                    continue

                gates_hit["pass"] += 1

                # Classify weak_type from BuildWeakToStrongCandidateUseCase
                weak_type, weak_intensity = compute_weak_type(pct, prev_day_pct, prev_day_limit_up)

                # Look up A-layer
                subject_key = str(b_feat.get("subject_key") or "")
                a_feat = a_layer.get((td, subject_key))
                mainline_score = float(a_feat.get("mainline_strength_score") or 0) if a_feat else 0.0
                fade_watch = bool(a_feat.get("fade_watch") or False) if a_feat else False
                fade_confirmed = bool(a_feat.get("fade_confirmed") or False) if a_feat else False
                cycle_state = str(a_feat.get("cycle_state") or "unknown") if a_feat else "unknown"

                # Compute candidate score
                score = compute_candidate_score(
                    is_leader=is_leader,
                    recent_limit_up_count=recent_limit_up,
                    rank_order=rank_order,
                    weak_intensity=weak_intensity,
                    support_strength=supp_strength,
                    mainline_strength_score=mainline_score,
                    fade_watch=fade_watch,
                    pct_chg=pct,
                    prev_day_pct=prev_day_pct,
                )

                # weak_type_quality adjustment
                if weak_type == "high_open_low_close":
                    score -= 15.0
                    pool_entry = "observe_only"
                elif weak_type in ("big_negative_line", "bad_limit_up"):
                    pool_entry = "formal"
                else:
                    pool_entry = "formal" if score >= 70 else "observe_only"

                candidate_type = "dragon_repair" if (is_leader and recent_limit_up >= 3) else (
                    "subdragon_repair" if is_leader else "strong_trend_repair"
                )

                # Next trade date
                next_dates = sorted([d for d in trading_days if d > td])
                next_td = next_dates[0] if next_dates else td + timedelta(days=1)

                try:
                    await c.execute_query("""
                        INSERT INTO weak_to_strong_candidate_pool (
                            trade_date, next_trade_date, stock_id, stock_name,
                            subject_key, theme_name, candidate_score, candidate_type, rule_version,
                            weak_type, weak_intensity, is_dragon_head, dragon_head_level,
                            prev_limit_up_count, max_consecutive_limit_up_days,
                            support_type, support_level, support_strength,
                            expected_open_low, expected_open_high, expected_auction_pattern,
                            need_last_minute_grab, need_plate_follow, evidence_json,
                            pool_entry_type, cycle_state, mainline_strength_score, fade_watch, fade_confirmed
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,0,
                            $15,'0',$16,'0','0','',false,false,
                            jsonb_build_object('method','strict_rebuild','prior7_lim',$17,'prior7_str',$18,'prev_day_pct',$19,'prev_day_lim',$20)::jsonb,
                            $21,$22,$23,$24,$25)
                        ON CONFLICT (next_trade_date, stock_id) DO UPDATE SET
                            candidate_score = EXCLUDED.candidate_score,
                            candidate_type = EXCLUDED.candidate_type,
                            weak_type = EXCLUDED.weak_type,
                            pool_entry_type = EXCLUDED.pool_entry_type,
                            rule_version = EXCLUDED.rule_version,
                            evidence_json = EXCLUDED.evidence_json
                    """, (td, next_td, sid, bar.get("stock_name", ""),
                          subject_key, str(b_feat.get("theme_name") or ""),
                          str(score), candidate_type, STRICT_RULE_VERSION,
                          weak_type, str(weak_intensity), is_leader,
                          "dragon" if is_leader else "",
                          recent_limit_up, supp_type, str(supp_strength),
                          prior7_lim, prior7_str, str(prev_day_pct), prev_day_limit_up,
                          pool_entry, cycle_state, str(mainline_score), fade_watch, fade_confirmed))
                    d_written += 1
                except Exception as e:
                    pass

        # Final stats
        logger.info("D-layer gates: total=%d pct=%d history=%d prior7=%d support=%d pass=%d",
                     gates_hit["total"], gates_hit["pct_gate"], gates_hit["history"],
                     gates_hit["prior7"], gates_hit["support"], gates_hit["pass"])

        pool_stats = await c.execute_query(
            "SELECT rule_version, COUNT(*) as n, COUNT(DISTINCT trade_date) as d FROM weak_to_strong_candidate_pool WHERE trade_date >= $1 GROUP BY rule_version ORDER BY n DESC",
            (START_DATE,)
        )
        logger.info("D-layer results:")
        for r in pool_stats:
            logger.info("  %s: N=%d dates=%d", r["rule_version"], r["n"], r["d"])

        await c.execute_query(
            "DELETE FROM weak_to_strong_candidate_pool WHERE rule_version = 'weak_to_strong_candidate.v3_backfill' AND trade_date >= $1",
            (START_DATE,)
        )
        logger.info("Cleaned up v3_backfill entries")

    finally:
        close_fn = getattr(gw, "close", None)
        if callable(close_fn):
            await close_fn()


if __name__ == "__main__":
    asyncio.run(main())
