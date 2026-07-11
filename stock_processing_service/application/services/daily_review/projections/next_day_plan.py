"""Next Day Plan projection — PR2.3b.

Chapter 6 only describes tomorrow's plan:

  - scenario
  - watch_themes
  - watch_stocks
  - confirmation_signals
  - invalidation_signals
  - forbidden_actions

It consumes existing playbook/emotion/engine plan data and does not infer new
trading decisions.
"""

from __future__ import annotations

from typing import Any

from ..policies.merge_policy import resolve_plan


def project_next_day_plan(
    *,
    engine_report: dict[str, Any] | None = None,
    snapshot_emotion: dict[str, Any] | None = None,
    snapshot_playbook: dict[str, Any] | None = None,
    builder_watchlist_reviews: list[dict[str, Any]] | None = None,
    builder_post_market_setup_plan: dict[str, Any] | None = None,
    builder_trading_principle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the next_day_plan block from approved plan sources."""
    engine = engine_report or {}
    emotion = snapshot_emotion or {}
    playbook = snapshot_playbook or {}
    setup_plan = builder_post_market_setup_plan or _dict(engine.get("post_market_setup_plan"))
    trading_principle = builder_trading_principle or _dict(engine.get("trading_principle"))
    decision_v2 = _dict(engine.get("post_market_decision_v2"))

    watch_stocks = _build_watch_stocks(
        watchlist_reviews=builder_watchlist_reviews,
        setup_plan=setup_plan,
        decision_v2=decision_v2,
    )

    scenario = resolve_plan(
        analyst_value=_override_final(playbook.get("scenario")),
        playbook_value=_first_text(
            playbook.get("scenario"),
            playbook.get("market_scenario"),
            playbook.get("summary"),
        ),
        engine_value=_first_text(emotion.get("tomorrow_outlook")),
        legacy_value=_first_text(trading_principle.get("main_strategy")),
    )

    confirmation_signals = _unique_texts(
        _override_list(playbook.get("confirmation_signals"))
        or _as_list(playbook.get("confirmation_signals"))
        or _as_list(emotion.get("tomorrow_watchpoints"))
    )
    invalidation_signals = _unique_texts(
        _override_list(playbook.get("invalidation_signals"))
        or _as_list(playbook.get("invalidation_signals"))
        or _collect_from_watch_stocks(watch_stocks, "invalidation_signals")
    )
    forbidden_actions = _unique_texts(
        _override_list(playbook.get("forbidden_actions"))
        or _as_list(playbook.get("forbidden_actions"))
        or _as_list(emotion.get("tomorrow_forbidden"))
        or _as_list(trading_principle.get("forbidden_actions"))
    )

    return {
        "scenario": scenario or "",
        "watch_themes": _build_watch_themes(watch_stocks),
        "watch_stocks": watch_stocks,
        "confirmation_signals": confirmation_signals,
        "invalidation_signals": invalidation_signals,
        "forbidden_actions": forbidden_actions,
        "principles": _build_principles(trading_principle, playbook),
        "playbook": _compact_playbook(playbook),
    }


# ── private helpers ──


def _build_watch_stocks(
    *,
    watchlist_reviews: list[dict[str, Any]] | None,
    setup_plan: dict[str, Any],
    decision_v2: dict[str, Any],
) -> list[dict[str, Any]]:
    stocks: dict[str, dict[str, Any]] = {}
    for row in _list_of_dicts(watchlist_reviews):
        _merge_watch_row(_ensure_stock(stocks, row), row, tag="watchlist")

    for row in _extract_setup_items(setup_plan):
        _merge_watch_row(_ensure_stock(stocks, row), row, tag="one_to_two")

    for row in _list_of_dicts(decision_v2.get("next_day_focus_stocks")):
        _merge_watch_row(_ensure_stock(stocks, row), row, tag="focus")
    for row in _list_of_dicts(decision_v2.get("weak_to_strong_d1_reviews")):
        _merge_watch_row(_ensure_stock(stocks, row), row, tag="d1")

    rows = [stock for stock in stocks.values() if stock.get("stock_code") or stock.get("stock_name")]
    rows.sort(key=lambda item: (int(item.get("priority") or 9999), str(item.get("stock_name") or item.get("stock_code") or "")))
    return rows


def _ensure_stock(stocks: dict[str, dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    code = _stock_code(row)
    if not code:
        code = f"__unknown__:{len(stocks)}"
    if code not in stocks:
        stocks[code] = {
            "stock_code": "" if code.startswith("__unknown__:") else code,
            "stock_name": _first_text(row.get("stock_name"), row.get("name")),
            "subject_key": _first_text(row.get("subject_key"), row.get("theme_subject_key")),
            "theme_name": _first_text(row.get("theme_name"), row.get("subject_name"), row.get("resolved_theme_name")),
            "tags": [],
            "priority": row.get("priority") or row.get("rank_order") or row.get("rank"),
            "action": "",
            "confirmation_signals": [],
            "invalidation_signals": [],
            "reason": "",
        }
    entity = stocks[code]
    if not entity.get("stock_name"):
        entity["stock_name"] = _first_text(row.get("stock_name"), row.get("name"))
    if not entity.get("subject_key"):
        entity["subject_key"] = _first_text(row.get("subject_key"), row.get("theme_subject_key"))
    if not entity.get("theme_name"):
        entity["theme_name"] = _first_text(row.get("theme_name"), row.get("subject_name"), row.get("resolved_theme_name"))
    return entity


def _merge_watch_row(entity: dict[str, Any], row: dict[str, Any], *, tag: str) -> None:
    _append_unique(entity.setdefault("tags", []), tag)
    _set_first(entity, "priority", row.get("priority") or row.get("rank_order") or row.get("rank"))
    _set_first(entity, "watch_level", row.get("watch_level") or row.get("candidate_level") or row.get("category") or row.get("role_label"))
    _set_first(entity, "action", row.get("action") or row.get("next_day_action") or row.get("plan_status"))
    _set_first(entity, "reason", row.get("reason") or row.get("rank_reason") or row.get("catalyst"))

    tomorrow_plan = _dict(row.get("tomorrow_plan"))
    confirmations = (
        _as_list(row.get("buy_condition"))
        + _as_list(row.get("flags"))
        + _as_list(tomorrow_plan.get("confirmation_triggers"))
        + _as_list(tomorrow_plan.get("auction_watch"))
    )
    invalidations = _as_list(row.get("give_up_conditions")) + _as_list(row.get("invalidation_plan"))
    for item in confirmations:
        _append_unique(entity.setdefault("confirmation_signals", []), item)
    for item in invalidations:
        _append_unique(entity.setdefault("invalidation_signals", []), item)
    if tomorrow_plan.get("expected_behavior") and not entity.get("action"):
        entity["action"] = tomorrow_plan.get("expected_behavior")


def _extract_setup_items(setup_plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not setup_plan:
        return []
    if isinstance(setup_plan.get("items"), list):
        return _list_of_dicts(setup_plan.get("items"))
    one_to_two = _dict(setup_plan.get("one_to_two"))
    if isinstance(one_to_two.get("items"), list):
        return _list_of_dicts(one_to_two.get("items"))
    return []


def _build_watch_themes(watch_stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for stock in watch_stocks:
        subject_key = _first_text(stock.get("subject_key"), stock.get("theme_name"))
        theme_name = _first_text(stock.get("theme_name"), subject_key)
        if not subject_key and not theme_name:
            continue
        key = subject_key or theme_name
        row = by_key.setdefault(key, {"subject_key": subject_key, "theme_name": theme_name, "stock_count": 0, "stocks": []})
        row["stock_count"] += 1
        _append_unique(row["stocks"], stock.get("stock_code") or stock.get("stock_name"))
    return sorted(by_key.values(), key=lambda item: (-int(item.get("stock_count") or 0), str(item.get("theme_name") or "")))


def _build_principles(trading_principle: dict[str, Any], playbook: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty({
        "allow_trade": trading_principle.get("allow_trade"),
        "market_mode": trading_principle.get("market_mode"),
        "position_limit": trading_principle.get("position_limit"),
        "main_strategy": resolve_plan(
            analyst_value=_override_final(playbook.get("main_strategy")),
            playbook_value=playbook.get("main_strategy"),
            engine_value=trading_principle.get("main_strategy"),
        ),
        "allowed_actions": _as_list(trading_principle.get("allowed_actions")),
        "risk_notes": _as_list(trading_principle.get("risk_notes")),
        "no_trade_reasons": _as_list(trading_principle.get("no_trade_reasons")),
    })


def _compact_playbook(playbook: dict[str, Any]) -> dict[str, Any]:
    if not playbook:
        return {}
    allowed = {
        "scenario",
        "market_scenario",
        "summary",
        "main_strategy",
        "confirmation_signals",
        "invalidation_signals",
        "forbidden_actions",
        "position_plan",
        "risk_control",
    }
    return {k: v for k, v in playbook.items() if k in allowed and v not in (None, "", [], {})}


def _collect_from_watch_stocks(stocks: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for stock in stocks:
        values.extend(_as_list(stock.get(key)))
    return _unique_texts(values)


def _override_final(value: Any) -> Any:
    if isinstance(value, dict) and value.get("override") is True:
        return value.get("final_value") or value.get("analyst_value")
    return None


def _override_list(value: Any) -> list[str]:
    final = _override_final(value)
    return _as_list(final)


def _stock_code(row: dict[str, Any]) -> str:
    raw = _first_text(row.get("stock_code"), row.get("stock_id"), row.get("code"))
    if not raw:
        return ""
    if "." in raw:
        left, right = raw.split(".", 1)
        return f"{left}.{right.upper()}"
    return raw


def _set_first(target: dict[str, Any], key: str, value: Any) -> None:
    if target.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
        target[key] = value


def _append_unique(target: list[Any], value: Any) -> None:
    text = _first_text(value)
    if text and text not in target:
        target.append(text)


def _unique_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        _append_unique(result, value)
    return result


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", {}, []):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}
