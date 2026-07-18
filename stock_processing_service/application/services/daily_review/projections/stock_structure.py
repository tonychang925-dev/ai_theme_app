"""Stock Structure projection — PR2.2b.

Implements stock entity merge by stock_code across multiple sources:

  stocks_by_code = merge(
      strong_stock_reviews,         # builder: today's role assessment
      post_market_decision_v2,      # engine: strong stock pool reviews
      post_market_setup_plan,       # engine: 1-to-2 candidates
  )

For each unique stock, produce one entity with aggregated roles.
Display optimization is deferred to PR4 (frontend).

Key principle: Chapter 4 describes TODAY only (who led, who was mid-cap, who was eliminated).
Tomorrow watch/1-to-2 goes to Chapter 6 (Next Day Plan).
"""

from __future__ import annotations

from typing import Any


def project_stock_structure(
    *,
    engine_report: dict[str, Any],
    builder_strong_stock_reviews: list[dict[str, Any]] | None = None,
    builder_watchlist_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build stock_structure via entity merge by stock_code.

    Args:
        engine_report: Full engine report (has post_market_decision_v2, post_market_setup_plan).
        builder_strong_stock_reviews: strong_stock_reviews from builder.
        builder_watchlist_reviews: watchlist_reviews from builder (for role context only).

    Returns:
        {stocks: [...], groups: {leaders: [...], mid_cap: [...], frontline: [...], eliminated: [...]}}
    """
    strong_stocks = builder_strong_stock_reviews or []
    decision_v2 = engine_report.get("post_market_decision_v2") or {}

    # ── Step 1: Collect all stock entities by stock_code ──
    stocks_by_code: dict[str, dict[str, Any]] = {}

    # Source A: strong_stock_reviews (builder) — today's role assessment
    for ss in strong_stocks:
        code = _normalize_stock_code(ss.get("stock_code", ""))
        if not code:
            continue
        if code not in stocks_by_code:
            stocks_by_code[code] = _new_stock_entity(code)
        entity = stocks_by_code[code]
        _merge_strong_stock(entity, ss)

    # Source B: post_market_decision_v2.strong_stock_pool_reviews (engine)
    pool_reviews = decision_v2.get("strong_stock_pool_reviews") or []
    for pr in pool_reviews:
        code = _normalize_stock_code(pr.get("stock_code", pr.get("stock_id", "")))
        if not code or code in stocks_by_code:
            # If already in stocks_by_code from strong_stock_reviews, skip
            # (strong_stock_reviews is the richer source)
            continue
        stocks_by_code[code] = _new_stock_entity(code)
        _merge_pool_review(stocks_by_code[code], pr)

    # ── Step 2: Build groups by today's role ──
    leaders: list[str] = []
    mid_cap: list[str] = []
    frontline: list[str] = []
    eliminated: list[str] = []

    for code, entity in stocks_by_code.items():
        role = entity.get("today_role", "")
        if role == "LEADER":
            leaders.append(code)
        elif role == "MID_CAP":
            mid_cap.append(code)
        elif role == "FRONTLINE":
            frontline.append(code)
        elif role == "ELIMINATED":
            eliminated.append(code)
        elif role == "WATCH":
            frontline.append(code)
        else:
            frontline.append(code)

    return {
        "stocks": list(stocks_by_code.values()),
        "groups": {
            "leaders": leaders,
            "mid_cap": mid_cap,
            "frontline": frontline,
            "eliminated": eliminated,
        },
    }


# ── private helpers ──


def _normalize_stock_code(raw: str) -> str:
    """Normalize stock code: strip whitespace, uppercase suffix."""
    code = str(raw).strip()
    if not code or code == "None":
        return ""
    # Ensure .SZ/.SH suffix is uppercase
    if "." in code:
        parts = code.split(".")
        code = f"{parts[0]}.{parts[1].upper()}"
    return code


def _new_stock_entity(code: str) -> dict[str, Any]:
    """Create a new stock entity dict."""
    return {
        "stock_code": code,
        "stock_name": "",
        "today_role": "",
        "theme_name": "",
        "subject_key": "",
        "scores": {},
        "capital": {},
        "today_status": "",
        "source": [],
    }


def _merge_strong_stock(entity: dict[str, Any], ss: dict[str, Any]) -> None:
    """Merge strong_stock_reviews row into entity."""
    # Name (first source wins)
    if not entity["stock_name"]:
        entity["stock_name"] = str(ss.get("stock_name", ""))
    if not entity["theme_name"]:
        entity["theme_name"] = str(ss.get("theme_name", ""))
    if not entity["subject_key"]:
        entity["subject_key"] = str(ss.get("subject_key", ""))

    # Role mapping
    role_raw = str(ss.get("role", ""))
    role = role_raw.upper()
    role_label = str(ss.get("role_label", ""))
    if role in ("LEADER", "DRAGON", "龙头"):
        entity["today_role"] = "LEADER"
    elif role in ("SUB_DRAGON", "POTENTIAL_LEADER", "潜在龙头"):
        entity["today_role"] = "FRONTLINE"
    elif role in ("MID_CAP", "中军"):
        entity["today_role"] = "MID_CAP"
    elif role in ("REJECT", "ELIMINATED", "淘汰"):
        entity["today_role"] = "ELIMINATED"
    elif role_label in ("龙头", "LEADER"):
        entity["today_role"] = "LEADER"
    elif role_label in ("淘汰", "REJECT"):
        entity["today_role"] = "ELIMINATED"
    elif not entity["today_role"]:
        entity["today_role"] = "WATCH"

    # Scores (keep the ones that matter for formal review, per Matrix)
    entity["scores"] = {
        "composite": _first_non_empty(ss.get("composite_score"), ss.get("watch_score")),
        "capital": _first_non_empty(ss.get("capital_score"), ss.get("money_flow_score")),
        "structure": _first_non_empty(ss.get("structure_score"), ss.get("support_score")),
        "leading": _first_non_empty(ss.get("leading_score"), ss.get("mainline_strength_score")),
        "purity": ss.get("purity_score"),
        "resilience": ss.get("resilience_score"),
    }

    # Capital data from money_flow
    mf = ss.get("money_flow") or {}
    entity["capital"] = {
        "main_net_inflow": _first_non_empty(mf.get("main_net_inflow"), ss.get("main_net_inflow")),
        "money_flow_tier": _first_non_empty(mf.get("money_flow_tier"), ss.get("money_flow_tier"), ""),
        "role_enhanced": _first_non_empty(mf.get("role_enhanced"), ss.get("role_enhanced"), ""),
    }

    # Today status from kline/llm
    kline = ss.get("kline") or {}
    llm = ss.get("llm") or {}
    evidence = ss.get("evidence") or {}
    entity["today_status"] = (
        str(kline.get("position_label", ""))
        or str(kline.get("pattern_summary", ""))
        or str(llm.get("judgement", ""))
        or str(ss.get("watch_status", ""))
        or str(ss.get("cycle_state", ""))
        or str(evidence.get("position_label", ""))
    )
    entity["rationale"] = ss.get("rationale", "")
    entity["rejection_reason"] = ss.get("rejection_reason")

    if "strong_stock_reviews" not in entity["source"]:
        entity["source"].append("strong_stock_reviews")


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _merge_pool_review(entity: dict[str, Any], pr: dict[str, Any]) -> None:
    """Merge pool review into entity (engine fallback)."""
    if not entity["stock_name"]:
        entity["stock_name"] = str(pr.get("stock_name", ""))
    if not entity["theme_name"]:
        entity["theme_name"] = str(pr.get("theme_name", ""))
    if not entity["today_role"]:
        role = str(pr.get("role", "")).upper()
        if role in ("LEADER",):
            entity["today_role"] = "LEADER"
        else:
            entity["today_role"] = "WATCH"
    if "pool_reviews" not in entity["source"]:
        entity["source"].append("pool_reviews")
