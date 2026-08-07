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

    # Add exchange suffix for DB lookup
    db_code = _with_exchange_suffix(stock_code)

    try:
        import asyncpg, asyncio

        async def _fetch():
            conn = await asyncpg.connect(
                "postgresql://postgres:zxbzj~925@localhost/stock_data_test")
            try:
                from datetime import date as _date
                rows = await conn.fetch("""
                    SELECT trade_date, open_price, high_price, low_price,
                           close_price, pre_close, volume, amount
                    FROM stock_daily_snapshot
                    WHERE stock_id = $1
                    AND trade_date >= $2::date - ($3 || ' days')::interval
                    AND trade_date <= $2::date
                    ORDER BY trade_date
                """, db_code, _date.fromisoformat(as_of), str(lookback_sessions + 5))
                return rows
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

    if not rows:
        return {
            "status": "unavailable",
            "tool": "market_stock_history",
            "stock_code": stock_code, "as_of": as_of,
            "reason": f"no data for {db_code} in lookback window",
        }

    # Build OHLCV bars
    bars = [{
        "trade_date": str(r["trade_date"]),
        "open": float(r["open_price"]), "high": float(r["high_price"]),
        "low": float(r["low_price"]), "close": float(r["close_price"]),
        "pre_close": float(r["pre_close"]),
        "volume": float(r["volume"]), "amount": float(r["amount"]),
    } for r in rows]

    # Derive metrics
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    first_close = closes[0]
    last_close = closes[-1]
    total_return = (last_close / first_close - 1) if first_close else 0

    peak = max(highs)
    dd_from_peak = (last_close / peak - 1) if peak else 0

    # Volume trend: compare first half vs second half
    mid = len(bars) // 2
    vol_first = sum(b["volume"] for b in bars[:mid]) / max(mid, 1)
    vol_second = sum(b["volume"] for b in bars[mid:]) / max(len(bars) - mid, 1)
    if vol_second > vol_first * 1.3:
        vol_trend = "elevated"
    elif vol_second < vol_first * 0.7:
        vol_trend = "contracting"
    else:
        vol_trend = "normal"

    # Key level: is close near session high?
    last_bar = bars[-1]
    close_vs_high = last_bar["close"] / last_bar["high"] if last_bar["high"] else 1
    if close_vs_high > 0.98:
        key_level = "intact"
    elif close_vs_high > 0.95:
        key_level = "testing"
    else:
        key_level = "broken"

    return {
        "status": "live",
        "source_kind": "objective_stock_history",
        "stock_code": stock_code,
        "db_code": db_code,
        "as_of": as_of,
        "lookback_sessions": lookback_sessions,
        "bar_count": len(bars),
        "bars": bars,
        "total_return": round(total_return, 4),
        "max_drawdown_from_peak": round(dd_from_peak, 4),
        "volume_trend": vol_trend,
        "key_level_status": key_level,
        "provenance": {
            "source": "stock_data_test.stock_daily_snapshot",
            "max_trade_date": str(rows[-1]["trade_date"]),
            "future_rows_used": False,
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
            return {
                "status": "unavailable",
                "tool": "market_theme_constituents",
                "subject_key": subject_key, "as_of": as_of,
                "reason": f"subject_key {subject_key} not in frozen 7/14 baseline",
            }

        constits = subject.get("constituent_codes", [])
        leaders = subject.get("leader_codes", [])

        # P0: return full list (not [:10]). P1: add total_count/truncated.
        return {
            "status": "live",
            "source_kind": "objective_constituent_universe",
            "subject_key": subject_key,
            "as_of": as_of,
            "constituent_codes": constits,
            "constituent_count": len(constits),
            "leader_codes": leaders,
            "leader_count": len(leaders),
            # P0: NO workbench_stage, julia_stage, or verdict in factual evidence
            "data_note": "Constituent identity frozen from 7/14 baseline_universe. Price returns pending kline ingestion.",
        }
    except Exception:
        return {
            "status": "unavailable",
            "tool": "market_theme_constituents",
            "subject_key": subject_key, "as_of": as_of,
            "reason": "baseline universe read error",
        }


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
