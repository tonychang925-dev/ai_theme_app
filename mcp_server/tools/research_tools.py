"""M3.2.7.2a Research MCP Tools — fail-closed on as_of, factual evidence only.

READ-ONLY. All as_of gated. No Workbench opinion in factual tools.
Case001: only 2026-07-14 supported. Other dates → unavailable.
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

SUPPORTED_AS_OF = "2026-07-14"


def _strength_dist(ctx: dict) -> dict:
    """Build strength distribution from raw_metrics."""
    strengths = []
    for t in ctx.get("themes", []):
        rm = t.get("raw_metrics", {}) or {}
        s = rm.get("mainline_strength_score")
        if s is not None:
            strengths.append(float(s))
    if not strengths:
        return {"count": 0}
    return {
        "count": len(strengths),
        "min": min(strengths),
        "max": max(strengths),
        "below_0_4": sum(1 for s in strengths if s < 0.4),
        "above_0_6": sum(1 for s in strengths if s >= 0.6),
        "above_0_8": sum(1 for s in strengths if s >= 0.8),
    }


def _with_exchange_suffix(code: str) -> str:
    """Add exchange suffix for stock_data_test.stock_daily_snapshot.stock_id."""
    if "." in code:
        return code
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    return f"{code}.SZ"


def _fetch_stock_bars(stock_code: str, as_of: str, sessions: int) -> list | None:
    """Fetch up to N trading bars from DB. Returns None on failure."""
    import os as _os, asyncpg, asyncio
    from datetime import date as _date

    dsn = _os.environ.get("STOCK_DB_DSN", "")
    if not dsn:
        return None

    db_code = _with_exchange_suffix(stock_code)
    try:
        async def _fetch():
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch("""
                    SELECT trade_date, open_price, high_price, low_price,
                           close_price, pre_close, volume, amount
                    FROM stock_daily_snapshot
                    WHERE stock_id = $1 AND trade_date <= $2::date
                    ORDER BY trade_date DESC LIMIT $3
                """, db_code, _date.fromisoformat(as_of), sessions)
                return list(reversed(rows))
            finally:
                await conn.close()
        return asyncio.run(_fetch())
    except Exception:
        return None


def _above_ma5_direct(built_bars: list, n: int = 5) -> bool:
    """Check if last close is above MA5. Uses _build_bars dict format."""
    closes = [b["close"] for b in built_bars[-n:]]
    if len(closes) < n:
        return False
    ma5 = sum(closes) / n
    return closes[-1] > ma5


def _guard_as_of(as_of: str) -> dict | None:
    """Only SUPPORTED_AS_OF is available for historical replay.
    Future dates, previous dates → unavailable (never latest fallback).
    """
    if as_of != SUPPORTED_AS_OF:
        return {
            "status": "unavailable",
            "reason": f"Historical artifact only for {SUPPORTED_AS_OF}, requested={as_of}",
        }
    return None


# ── Stock History ───────────────────────────────────────────────────────────

def market_stock_history(stock_code: str, as_of: str, lookback_sessions: int = 5) -> dict:
    guard = _guard_as_of(as_of)
    if guard:
        return {**guard, "tool": "market_stock_history",
                "stock_code": stock_code, "as_of": as_of}

    import os as _os
    dsn = _os.environ.get("STOCK_DB_DSN", "")
    if not dsn:
        return {
            "status": "unavailable",
            "tool": "market_stock_history",
            "stock_code": stock_code, "as_of": as_of,
            "reason": "STOCK_DB_DSN not configured",
        }

    db_code = _with_exchange_suffix(stock_code)

    try:
        import asyncpg, asyncio
        from datetime import date as _date

        async def _fetch():
            conn = await asyncpg.connect(dsn)
            try:
                # P0-1: exact trading-session LIMIT (not calendar days)
                rows = await conn.fetch("""
                    SELECT trade_date, open_price, high_price, low_price,
                           close_price, pre_close, volume, amount
                    FROM stock_daily_snapshot
                    WHERE stock_id = $1
                    AND trade_date <= $2::date
                    ORDER BY trade_date DESC
                    LIMIT $3
                """, db_code, _date.fromisoformat(as_of), lookback_sessions)
                return list(reversed(rows))
            finally:
                await conn.close()

        rows = asyncio.run(_fetch())
    except Exception as e:
        return {
            "status": "unavailable",
            "tool": "market_stock_history",
            "stock_code": stock_code, "as_of": as_of,
            "reason": f"DB query failed: {type(e).__name__}: {e}",
        }

    if len(rows) < lookback_sessions:
        return {
            "status": "partial",
            "source_kind": "objective_stock_history",
            "stock_code": stock_code,
            "as_of": as_of,
            "requested_sessions": lookback_sessions,
            "actual_sessions": len(rows),
            "reason": f"only {len(rows)} bars available (requested {lookback_sessions})",
            "bars": _build_bars(rows),
        }

    bars = _build_bars(rows)
    metrics = _compute_metrics(bars)

    return {
        "status": "live",
        "source_kind": "objective_stock_history",
        "stock_code": stock_code,
        "as_of": as_of,
        "requested_sessions": lookback_sessions,
        "actual_sessions": len(bars),
        "bars": bars,
        **metrics,
        "provenance": {
            "source": "stock_data_test.stock_daily_snapshot",
            "max_trade_date": str(rows[-1]["trade_date"]),
            "future_rows_used": False,
            "rule_version": "stock-metrics.v1",
        },
    }


def _build_bars(rows) -> list:
    return [{
        "trade_date": str(r["trade_date"]),
        "open": float(r["open_price"]), "high": float(r["high_price"]),
        "low": float(r["low_price"]), "close": float(r["close_price"]),
        "pre_close": float(r["pre_close"]),
        "volume": float(r["volume"]), "amount": float(r["amount"]),
        "pct_chg": round((float(r["close_price"]) / float(r["pre_close"]) - 1) * 100, 2)
            if float(r["pre_close"]) else None,
    } for r in rows]


def _compute_metrics(bars: list) -> dict:
    closes = [b["close"] for b in bars]
    last_close = closes[-1]
    # P0-1: true 5-session cumulative return (last_close / first pre_close - 1)
    first_pre_close = bars[0]["pre_close"]
    total_return = round((last_close / first_pre_close - 1), 4) if first_pre_close else 0

    # P0-2: true max drawdown (running peak → trough, close-based)
    running_peak = 0.0
    max_dd = 0.0
    for b in bars:
        running_peak = max(running_peak, b["close"])
        dd = b["close"] / running_peak - 1 if running_peak else 0
        max_dd = min(max_dd, dd)

    # Volume trend: compare first half vs second half
    mid = len(bars) // 2
    v1 = sum(b["volume"] for b in bars[:mid]) / max(mid, 1)
    v2 = sum(b["volume"] for b in bars[mid:]) / max(len(bars) - mid, 1)
    if v2 > v1 * 1.3:
        vol_trend = "elevated"
    elif v2 < v1 * 0.7:
        vol_trend = "contracting"
    else:
        vol_trend = "normal"

    # P0-3: key-level from moving averages + prior session close
    ma5 = sum(closes[-5:]) / min(len(closes), 5)
    above_ma5 = last_close > ma5
    prior_session_close = bars[-2]["close"] if len(bars) >= 2 else last_close
    above_prior_session_close = last_close > prior_session_close
    limit_up_flag = bars[-1].get("pct_chg", 0) and bars[-1]["pct_chg"] >= 9.9
    # NOTE: "prior limit-up close" support level (from StrategyCard) requires
    # scanning history for last 涨停日, not just prior session. Not implemented.

    if above_ma5 and limit_up_flag:
        key_state = "intact_limit_up"
    elif above_ma5:
        key_state = "intact"
    elif last_close > ma5 * 0.97:
        key_state = "testing"
    else:
        key_state = "broken"

    return {
        "total_return": total_return,
        "max_drawdown_from_peak": round(max_dd, 4),
        "volume_trend": vol_trend,
        "key_level_status": {
            "state": key_state,
            "levels": {
                "ma5": round(ma5, 2),
                "close_vs_ma5": round(last_close / ma5, 4) if ma5 else None,
            },
            "tests": {
                "above_ma5": above_ma5,
                "above_prior_session_close": above_prior_session_close,
                "limit_up_flag": limit_up_flag,
            },
            "_note": "prior_limit_up_close support level (StrategyCard) not yet implemented — scanning for last 涨停 close TBD.",
            "rule_version": "key-level.v1",
        },
    }


def market_stock_auction(stock_code: str, as_of: str) -> dict:
    guard = _guard_as_of(as_of)
    if guard:
        return {**guard, "tool": "market_stock_auction",
                "stock_code": stock_code, "as_of": as_of}

    return {
        "status": "unavailable",
        "tool": "market_stock_auction",
        "stock_code": stock_code, "as_of": as_of,
        "reason": "auction archive not available for historical dates",
        "data_status": "DATA_UNAVAILABLE",
    }


# ── Theme Constituents (factual only — no opinions) ────────────────────────

def market_theme_constituents(subject_key: str, as_of: str) -> dict:
    guard = _guard_as_of(as_of)
    if guard:
        return {**guard, "tool": "market_theme_constituents",
                "subject_key": subject_key, "as_of": as_of}

    try:
        import json
        from pathlib import Path

        base = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
        universe = json.loads(
            (base / "outcomes" / "baseline_universe.json").read_text(encoding="utf-8")
        )
        subject = universe["subjects"].get(subject_key)
        if not subject:
            return {"status": "unavailable", "tool": "market_theme_constituents",
                    "subject_key": subject_key, "as_of": as_of,
                    "reason": f"subject_key {subject_key} not in frozen 7/14 baseline"}

        constits = subject.get("constituent_codes", [])
        leaders = subject.get("leader_codes", [])

        # Fetch real stock bars for all constituents
        stock_metrics = {}
        t0_date = None
        prev_date = None
        for code in constits:
            bars = _fetch_stock_bars(code, as_of, 6)  # 6 bars = 5 trailing + T0
            if bars and len(bars) >= 2:
                built = _build_bars(bars)
                bar_5d = built[-5:] if len(built) >= 5 else built
                first_pre = bar_5d[0]["pre_close"]
                last_close = bar_5d[-1]["close"]
                ret_5d = (last_close / first_pre - 1) if first_pre else 0

                t0_bar = built[-1]
                prev_bar = built[-2]
                t0_date = t0_bar["trade_date"]
                prev_date = prev_bar["trade_date"]
                t0_pct = t0_bar["pct_chg"] or 0
                t0_limit_up = t0_pct >= 9.9
                t0_above_ma5 = _above_ma5_direct(built, 5)

                prev_pct = prev_bar["pct_chg"] or 0
                # Prev session MA5: compute from bars 0..-2 (exclude T0)
                prev_built = built[:-1]
                prev_above_ma5 = _above_ma5_direct(prev_built, 5) if len(prev_built) >= 5 else False

                stock_metrics[code] = {
                    "return_5d": round(ret_5d, 4),
                    "return_5d_pct": round(ret_5d * 100, 2),
                    "t0_pct_chg": t0_pct,
                    "t0_limit_up": t0_limit_up,
                    "t0_above_ma5": t0_above_ma5,
                    "prev_pct_chg": prev_pct,
                    "prev_above_ma5": prev_above_ma5,
                    "leader_flag": code in leaders,
                }

        if not stock_metrics:
            return {"status": "partial", "tool": "market_theme_constituents",
                    "subject_key": subject_key, "as_of": as_of,
                    "reason": "no stock history data for any constituent"}

        # Peer relative strength ranking
        ranked = sorted(stock_metrics.items(), key=lambda x: x[1]["return_5d"], reverse=True)
        peer_relative_strength = {
            "window_sessions": 5,
            "ranking": [
                {"stock_code": code, "return_5d": m["return_5d"],
                 "return_5d_pct": m["return_5d_pct"], "rank": i + 1,
                 "leader_flag": m["leader_flag"]}
                for i, (code, m) in enumerate(ranked)
            ],
            "dispersion": {
                "max_min_spread": round(
                    ranked[0][1]["return_5d"] - ranked[-1][1]["return_5d"], 4) if len(ranked) >= 2 else 0,
            },
        }

        # Emerging leaders: non-leader codes with top 2 return
        non_leaders = [(c, m) for c, m in ranked if not m["leader_flag"]]
        emerging_leaders = [
            {"stock_code": c, "return_5d_pct": m["return_5d_pct"],
             "candidate_status": "candidate", "note": "top return among non-leaders"}
            for c, m in non_leaders[:1]
        ]

        # Current breadth (T0)
        t0_count = len(stock_metrics)
        t0_limit_up_count = sum(1 for m in stock_metrics.values() if m["t0_limit_up"])
        t0_above_ma5_count = sum(1 for m in stock_metrics.values() if m["t0_above_ma5"])
        t0_positive_count = sum(1 for m in stock_metrics.values() if m["t0_pct_chg"] > 0)

        current_breadth = {
            "trade_date": t0_date,
            "constituent_count": t0_count,
            "limit_up_count": t0_limit_up_count,
            "limit_up_ratio": round(t0_limit_up_count / t0_count, 2) if t0_count else 0,
            "above_ma5_count": t0_above_ma5_count,
            "above_ma5_ratio": round(t0_above_ma5_count / t0_count, 2) if t0_count else 0,
            "positive_count": t0_positive_count,
            "positive_ratio": round(t0_positive_count / t0_count, 2) if t0_count else 0,
        }

        # Breadth change: compute prev-session using bars[-2] data
        prev_positive = sum(1 for m in stock_metrics.values() if m.get("prev_pct_chg", 0) > 0)
        prev_limit_up = sum(1 for m in stock_metrics.values()
                          if m.get("prev_pct_chg", 0) >= 9.9)
        # prev MA5: use bars 0..-2 (exclude last bar)
        prev_above_ma5 = sum(1 for m in stock_metrics.values() if m.get("prev_above_ma5", False))
        bt = stock_metrics  # alias for readability
        breadth_change = {
            "from_trade_date": prev_date,
            "to_trade_date": t0_date,
            "from": {
                "positive_count": prev_positive,
                "positive_ratio": round(prev_positive / t0_count, 2) if t0_count else 0,
                "limit_up_count": prev_limit_up,
                "limit_up_ratio": round(prev_limit_up / t0_count, 2) if t0_count else 0,
                "above_ma5_count": prev_above_ma5,
                "above_ma5_ratio": round(prev_above_ma5 / t0_count, 2) if t0_count else 0,
            },
            "to": {
                "positive_count": t0_positive_count,
                "positive_ratio": current_breadth["positive_ratio"],
                "limit_up_count": t0_limit_up_count,
                "limit_up_ratio": current_breadth["limit_up_ratio"],
                "above_ma5_count": t0_above_ma5_count,
                "above_ma5_ratio": current_breadth["above_ma5_ratio"],
            },
            "delta": {
                "positive_ratio": round(current_breadth["positive_ratio"] - round(prev_positive / t0_count, 2), 2) if t0_count else 0,
                "limit_up_ratio": round(current_breadth["limit_up_ratio"] - round(prev_limit_up / t0_count, 2), 2) if t0_count else 0,
            },
        }

        return {
            "status": "live",
            "source_kind": "objective_constituent_universe",
            "subject_key": subject_key,
            "as_of": as_of,
            "constituent_codes": constits,
            "constituent_count": len(constits),
            "leader_codes": leaders,
            "peer_relative_strength": peer_relative_strength,
            "current_breadth": current_breadth,
            "breadth_change": breadth_change,
            "emerging_leaders": emerging_leaders,
            "stock_metrics": stock_metrics,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "unavailable", "tool": "market_theme_constituents",
                "subject_key": subject_key, "as_of": as_of,
                "reason": f"export failed: {type(e).__name__}: {e}"}


# ── Theme Capital ───────────────────────────────────────────────────────────

def market_theme_capital(subject_key: str, as_of: str) -> dict:
    guard = _guard_as_of(as_of)
    if guard:
        return {**guard, "tool": "market_theme_capital",
                "subject_key": subject_key, "as_of": as_of}

    return {
        "status": "unavailable",
        "tool": "market_theme_capital",
        "subject_key": subject_key, "as_of": as_of,
        "reason": "historical capital flow data not yet linked",
        "data_status": "pending_ingestion",
    }


# ── Market Regime (objective context — NOT Workbench opinion) ───────────────

def market_regime_read(as_of: str) -> dict:
    guard = _guard_as_of(as_of)
    if guard:
        return {**guard, "tool": "market_regime_read", "as_of": as_of}

    try:
        import json
        from pathlib import Path

        base = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
        # Read OBJECTIVE market_context (not workbench_review)
        ctx = json.loads((base / "market_context.json").read_text(encoding="utf-8"))

        # P0-2: Derive regime from RAW strength metrics (NOT stage_signal)
        themes = ctx.get("themes", [])
        dist = _strength_dist(ctx)
        total = dist.get("count", 0)
        if total == 0:
            regime = "unknown"
        else:
            above_06 = dist.get("above_0_6", 0)
            below_04 = dist.get("below_0_4", 0)
            above_08 = dist.get("above_0_8", 0)

            if above_08 / total > 0.3:
                regime = "strength_dominant"
            elif above_06 / total > 0.5:
                regime = "strength_active"
            elif below_04 / total > 0.7:
                regime = "weak_dominant"
            else:
                regime = "mixed_repair"

        return {
            "status": "live",
            "source_kind": "objective_market_facts",
            "as_of": as_of,
            "facts": {
                "theme_count": total,
                "strength_distribution": _strength_dist(ctx),
            },
            "derived": {
                "regime_assessment": {
                    "value": regime,
                    "provenance_kind": "engine_derived",
                    "rule_version": "market-regime.v1",
                    "note": "Derived from raw mainline_strength_score distribution. Provenance: market_context.json (f90721c). ZERO stage_signal used.",
                },
            },
            "data_note": "Facts from frozen market_context (f90721c). Derived regime is engine output, not objective truth.",
        }
    except Exception:
        return {
            "status": "unavailable",
            "tool": "market_regime_read",
            "as_of": as_of,
            "reason": "market_context read error",
        }


__all__ = [
    "market_stock_history",
    "market_stock_auction",
    "market_theme_constituents",
    "market_theme_capital",
    "market_regime_read",
]
