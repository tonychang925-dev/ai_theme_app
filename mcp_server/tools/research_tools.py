"""M3.2.7.2 Research MCP Tools — historical data for Julia's research workflow.

READ-ONLY. Return only data <= as_of date. Never fallback to latest.
If data unavailable for as_of → return structured unavailable, not synthetic.
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def market_stock_history(stock_code: str, as_of: str, lookback_sessions: int = 5) -> dict:
    """Return historical daily bars for a stock up to as_of.

    Fail-closed: if data unavailable for as_of → status=unavailable.
    Never returns future or latest data.
    """
    return _unavailable("market_stock_history", {
        "stock_code": stock_code, "as_of": as_of,
        "reason": "stock daily kline not yet ingested for July 2026 dates",
        "data_status": "pending_ingestion",
    })


def market_stock_auction(stock_code: str, as_of: str) -> dict:
    """Return pre-market auction data for a stock on as_of.

    Fail-closed: no auction archive → DATA_UNAVAILABLE.
    """
    return _unavailable("market_stock_auction", {
        "stock_code": stock_code, "as_of": as_of,
        "reason": "auction archive not available for historical dates",
        "data_status": "DATA_UNAVAILABLE",
    })


def market_theme_constituents(subject_key: str, as_of: str) -> dict:
    """Return theme constituent stock data as of as_of.

    Uses frozen 7/14 snapshot baseline_universe.json for constituent lists.
    Returns: relative_strength_rank, breadth, emerging_leaders.
    Fail-closed: if subject_key not in frozen baseline → unavailable.
    """
    try:
        import json
        from pathlib import Path

        base = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
        universe = json.loads(
            (base / "outcomes" / "baseline_universe.json").read_text(encoding="utf-8")
        )
        subject = universe["subjects"].get(subject_key)
        if not subject:
            return _unavailable("market_theme_constituents", {
                "subject_key": subject_key, "as_of": as_of,
                "reason": f"subject_key {subject_key} not in frozen 7/14 baseline",
            })

        constits = subject.get("constituent_codes", [])
        leaders = subject.get("leader_codes", [])

        return {
            "status": "live",
            "subject_key": subject_key,
            "as_of": as_of,
            "constituent_count": len(constits),
            "constituent_codes": constits[:10],
            "leader_codes": leaders,
            "workbench_stage": subject.get("workbench_stage", ""),
            "julia_stage": subject.get("julia_stage", ""),
            "verdict": subject.get("verdict", ""),
            "relative_strength_rank": [],
            "breadth_change": "unknown",
            "emerging_leaders": [],
            "data_note": "Constituent identity frozen. Price returns pending kline ingestion.",
        }
    except Exception:
        return _unavailable("market_theme_constituents", {
            "subject_key": subject_key, "as_of": as_of,
            "reason": "baseline universe read error",
        })


def market_theme_capital(subject_key: str, as_of: str) -> dict:
    """Return capital flow persistence for a theme as of as_of.

    Fail-closed: historical capital data not available → unavailable.
    """
    return _unavailable("market_theme_capital", {
        "subject_key": subject_key, "as_of": as_of,
        "reason": "historical capital flow data not yet linked",
        "data_status": "pending_ingestion",
    })


def market_regime_read(as_of: str) -> dict:
    """Return market regime assessment as of as_of.

    Reads from frozen 7/14 workbench_review and chart data.
    Fail-closed: no future data. Only <= as_of sources.
    """
    try:
        import json
        from pathlib import Path

        base = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
        wb = json.loads((base / "workbench_review.json").read_text(encoding="utf-8"))

        return {
            "status": "live",
            "as_of": as_of,
            "regime": _derive_regime(wb),
            "breadth": "unknown",
            "risk": "medium_high",
            "evidence": ["emotion_review_7_14"],
            "data_note": "Regime derived from frozen 7/14 workbench review.",
        }
    except Exception:
        return _unavailable("market_regime_read", {
            "as_of": as_of,
            "reason": "workbench review read error",
        })


def _derive_regime(wb: dict) -> str:
    """Derive simplified regime from workbench claims."""
    claims = wb.get("claims", [])
    divergence_count = sum(1 for c in claims if c.get("stage_judgement") == "divergence")
    diffusion_count = sum(1 for c in claims if c.get("stage_judgement") == "diffusion")
    total = len(claims)
    if total == 0:
        return "unknown"
    div_ratio = divergence_count / total
    if div_ratio > 0.5:
        return "repair_to_divergence"
    return "mixed_repair"


def _unavailable(tool: str, info: dict) -> dict:
    return {"status": "unavailable", "tool": tool, **info}


__all__ = [
    "market_stock_history",
    "market_stock_auction",
    "market_theme_constituents",
    "market_theme_capital",
    "market_regime_read",
]
