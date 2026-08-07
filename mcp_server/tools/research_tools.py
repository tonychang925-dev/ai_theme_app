"""M3.2.7.2a Research MCP Tools — fail-closed on as_of, factual evidence only.

READ-ONLY. All as_of gated. No Workbench opinion in factual tools.
Case001: only 2026-07-14 supported. Other dates → unavailable.
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

SUPPORTED_AS_OF = "2026-07-14"


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

    return {
        "status": "unavailable",
        "tool": "market_stock_history",
        "stock_code": stock_code, "as_of": as_of,
        "reason": "stock daily kline not yet ingested for July 2026 dates",
        "data_status": "pending_ingestion",
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

        # Derive regime from objective theme signals
        themes = ctx.get("themes", [])
        total = len(themes)
        if total == 0:
            regime = "unknown"
        else:
            # Count derived_stage_signal distribution from objective context
            stages = {}
            for t in themes:
                ds = t.get("derived_signals", {})
                stage = ds.get("stage_signal", {}).get("value", "unknown")
                stages[stage] = stages.get(stage, 0) + 1

            div_ratio = stages.get("divergence", 0) / total
            ferm_ratio = stages.get("fermentation", 0) / total
            acc_ratio = stages.get("acceleration", 0) / total

            if div_ratio > 0.5:
                regime = "divergence_dominant"
            elif ferm_ratio > 0.3:
                regime = "fermentation_active"
            elif acc_ratio > 0.05:
                regime = "mixed_with_acceleration"
            else:
                regime = "mixed_repair"

        return {
            "status": "live",
            "source_kind": "objective_market_context",
            "as_of": as_of,
            "regime": regime,
            "stage_distribution": stages,
            "theme_count": total,
            "evidence": ["market_context_via_stage_signal_distribution"],
            "data_note": "Regime derived from objective market_context (frozen f90721c). NOT from workbench_review.",
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
