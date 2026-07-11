"""Capital Evidence projection — PR2.3a.

Compiles capital evidence into three fixed layers:

  - market: market-level capital state
  - themes: theme-level capital evidence
  - stocks: stock-level evidence merged by stock_code

The projection only maps and merges existing rows. It does not recalculate
money-flow metrics or infer new capital conclusions.
"""

from __future__ import annotations

from typing import Any


def project_capital_evidence(
    *,
    engine_report: dict[str, Any] | None = None,
    builder_theme_capital_reviews: list[dict[str, Any]] | None = None,
    builder_stock_capital_reviews: list[dict[str, Any]] | None = None,
    builder_money_flow_reviews: list[dict[str, Any]] | None = None,
    builder_dragon_tiger_reviews: list[dict[str, Any]] | None = None,
    builder_abnormal_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build capital_evidence from already computed evidence rows."""
    engine = engine_report or {}
    evidence_layer = _dict(engine.get("evidence_layer_review"))
    seat_summary = _dict(engine.get("seat_money_summary"))

    stock_capital_rows = _list_of_dicts(builder_stock_capital_reviews)
    money_flow_rows = _list_of_dicts(builder_money_flow_reviews)
    dragon_tiger_rows = _list_of_dicts(builder_dragon_tiger_reviews)
    abnormal_rows = _list_of_dicts(builder_abnormal_reviews)

    stock_entities: dict[str, dict[str, Any]] = {}
    orphan_seats: list[dict[str, Any]] = []

    for row in stock_capital_rows:
        _merge_stock_capital(_ensure_stock(stock_entities, row), row)
    for row in money_flow_rows:
        _merge_money_flow(_ensure_stock(stock_entities, row), row)
    for row in abnormal_rows:
        _merge_abnormal(_ensure_stock(stock_entities, row), row)
    for row in dragon_tiger_rows:
        code = _stock_code(row)
        if not code:
            orphan_seats.append(_compact_seat(row))
            continue
        _merge_dragon_tiger(_ensure_stock(stock_entities, row), row)

    return {
        "market": _build_market_capital(engine, evidence_layer, seat_summary),
        "themes": _build_theme_capital(builder_theme_capital_reviews),
        "stocks": _sorted_stocks(stock_entities),
        "seat_summary": seat_summary,
        "orphan_seats": orphan_seats,
        "evidence_layer": evidence_layer,
        "alignment": _dict(engine.get("evidence_alignment_index")),
        "event_narrative": _first_text(
            engine.get("driver_event_narrative"),
            _dict(engine.get("market_hotspot_narrative")).get("summary"),
        ),
    }


# ── private helpers ──


def _build_market_capital(
    engine: dict[str, Any],
    evidence_layer: dict[str, Any],
    seat_summary: dict[str, Any],
) -> dict[str, Any]:
    active_capital = _dict(engine.get("active_capital"))
    money_flow = _dict(engine.get("money_flow_review"))
    market_summary = _dict(engine.get("market_summary"))
    evidence_diag = _dict(evidence_layer.get("diagnostics"))
    return _drop_none({
        "active_amount": _first_non_empty(
            active_capital.get("active_amount_yi"),
            active_capital.get("active_amount"),
            market_summary.get("active_amount_yi"),
        ),
        "active_ratio": _first_non_empty(
            active_capital.get("active_ratio"),
            market_summary.get("active_ratio"),
        ),
        "state": _first_text(
            active_capital.get("state"),
            money_flow.get("state"),
            money_flow.get("conclusion"),
        ),
        "summary": _first_text(
            money_flow.get("summary"),
            evidence_layer.get("summary"),
            seat_summary.get("summary"),
        ),
        "hot_money_net_buy": seat_summary.get("hot_money_net_buy"),
        "institution_net_buy": seat_summary.get("institution_net_buy"),
        "evidence_count": _sum_ints(
            evidence_diag.get("abnormal_count"),
            evidence_diag.get("money_flow_count"),
            evidence_diag.get("dragon_tiger_count"),
            evidence_diag.get("stock_capital_count"),
        ),
    })


def _build_theme_capital(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    for row in _list_of_dicts(rows):
        subject_key = _first_text(row.get("subject_key"), row.get("theme_subject_key"))
        theme_name = _first_text(row.get("theme_name"), row.get("subject_name"), subject_key)
        if not subject_key and not theme_name:
            continue
        themes.append(_drop_none({
            "subject_key": subject_key,
            "theme_name": theme_name,
            "total_inflow": row.get("total_inflow"),
            "leader_inflow": row.get("leader_inflow"),
            "top3_inflow": row.get("top3_inflow"),
            "inflow_stock_count": row.get("inflow_stock_count"),
            "rank_order": row.get("rank_order"),
            "capital_validation": row.get("capital_validation"),
            "theme_kline": row.get("theme_kline"),
        }))
    themes.sort(key=lambda item: (int(item.get("rank_order") or 9999), str(item.get("theme_name") or "")))
    return themes


def _ensure_stock(
    stocks: dict[str, dict[str, Any]],
    row: dict[str, Any],
) -> dict[str, Any]:
    code = _stock_code(row)
    if not code:
        code = f"__unknown__:{len(stocks)}"
    if code not in stocks:
        stocks[code] = {
            "stock_code": "" if code.startswith("__unknown__:") else code,
            "stock_name": _first_text(row.get("stock_name"), row.get("name")),
            "subject_key": _first_text(row.get("subject_key"), row.get("theme_subject_key")),
            "theme_name": _first_text(row.get("theme_name"), row.get("subject_name"), row.get("resolved_theme_name")),
            "capital_flow": {},
            "dragon_tiger": {},
            "abnormal_signals": [],
            "sources": [],
        }
    entity = stocks[code]
    if not entity.get("stock_name"):
        entity["stock_name"] = _first_text(row.get("stock_name"), row.get("name"))
    if not entity.get("subject_key"):
        entity["subject_key"] = _first_text(row.get("subject_key"), row.get("theme_subject_key"))
    if not entity.get("theme_name"):
        entity["theme_name"] = _first_text(row.get("theme_name"), row.get("subject_name"), row.get("resolved_theme_name"))
    return entity


def _merge_stock_capital(entity: dict[str, Any], row: dict[str, Any]) -> None:
    flow = entity.setdefault("capital_flow", {})
    _set_first(flow, "main_net_inflow", row.get("main_net_inflow") or row.get("amount"))
    _set_first(flow, "active_buy", row.get("active_buy"))
    _set_first(flow, "institution_net", row.get("institution_net") or row.get("institution_net_buy"))
    _set_first(flow, "hot_money_net", row.get("hot_money_net") or row.get("hot_money_net_buy"))
    _set_first(flow, "rank_order", row.get("rank_order") or row.get("rank_in_theme"))
    _set_first(flow, "conclusion", row.get("conclusion") or row.get("description"))
    _append_source(entity, "stock_capital_reviews")


def _merge_money_flow(entity: dict[str, Any], row: dict[str, Any]) -> None:
    flow = entity.setdefault("capital_flow", {})
    _set_first(flow, "main_net_inflow", row.get("main_net_inflow") or row.get("amount"))
    _set_first(flow, "money_flow_tier", row.get("money_flow_tier"))
    _set_first(flow, "role_enhanced", row.get("role_enhanced"))
    _set_first(flow, "institution_signal", row.get("institution_signal"))
    _set_first(flow, "hot_money_signal", row.get("hot_money_signal"))
    _set_first(flow, "dragon_tiger_signal", row.get("dragon_tiger_signal"))
    _set_first(flow, "conclusion", row.get("conclusion") or row.get("description"))
    _append_source(entity, "money_flow_reviews")


def _merge_dragon_tiger(entity: dict[str, Any], row: dict[str, Any]) -> None:
    dt = entity.setdefault("dragon_tiger", {})
    _set_first(dt, "net_buy", row.get("net_buy") or row.get("net_amount"))
    _set_first(dt, "buy_amount", row.get("buy_amount") or row.get("billboard_buy_amount"))
    _set_first(dt, "sell_amount", row.get("sell_amount") or row.get("billboard_sell_amount"))
    _set_first(dt, "seat_type", row.get("seat_type"))
    _set_first(dt, "hot_money_name", row.get("hot_money_name"))
    _set_first(dt, "institution_seat_count", row.get("institution_seat_count"))
    _set_first(dt, "continuous_days", row.get("continuous_days"))
    _set_first(dt, "reason", row.get("reason"))
    _set_first(dt, "side_summary", row.get("side_summary"))
    seat_summary = row.get("seat_summary")
    if seat_summary:
        dt["seat_summary"] = seat_summary
    _append_source(entity, "dragon_tiger_reviews")


def _merge_abnormal(entity: dict[str, Any], row: dict[str, Any]) -> None:
    signal = _drop_none({
        "title": row.get("title"),
        "score": row.get("score") or row.get("abnormal_score") or row.get("abnormal_composite_score"),
        "labels": row.get("labels") or row.get("abnormal_labels"),
        "volume_ratio": row.get("volume_ratio"),
        "turnover_rate": row.get("turnover_rate"),
        "conclusion": row.get("conclusion") or row.get("description") or row.get("reason"),
    })
    if signal:
        entity.setdefault("abnormal_signals", []).append(signal)
    _append_source(entity, "abnormal_reviews")


def _compact_seat(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_none({
        "stock_name": _first_text(row.get("stock_name"), row.get("name")),
        "theme_name": _first_text(row.get("theme_name"), row.get("subject_name"), row.get("resolved_theme_name")),
        "net_buy": row.get("net_buy") or row.get("net_amount"),
        "buy_amount": row.get("buy_amount") or row.get("billboard_buy_amount"),
        "sell_amount": row.get("sell_amount") or row.get("billboard_sell_amount"),
        "seat_type": row.get("seat_type"),
        "reason": row.get("reason"),
    })


def _sorted_stocks(stocks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entity in stocks.values():
        entity["capital_flow"] = _drop_none(entity.get("capital_flow") or {})
        entity["dragon_tiger"] = _drop_none(entity.get("dragon_tiger") or {})
        rows.append(entity)
    rows.sort(
        key=lambda item: (
            int(_dict(item.get("capital_flow")).get("rank_order") or 9999),
            str(item.get("stock_name") or item.get("stock_code") or ""),
        )
    )
    return rows


def _stock_code(row: dict[str, Any]) -> str:
    raw = _first_text(row.get("stock_code"), row.get("stock_id"), row.get("code"))
    if not raw:
        return ""
    code = raw.strip()
    if "." in code:
        left, right = code.split(".", 1)
        return f"{left}.{right.upper()}"
    return code


def _append_source(entity: dict[str, Any], source: str) -> None:
    sources = entity.setdefault("sources", [])
    if source not in sources:
        sources.append(source)


def _set_first(target: dict[str, Any], key: str, value: Any) -> None:
    if target.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
        target[key] = value


def _drop_none(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None and v != "" and v != [] and v != {}}


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


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _sum_ints(*values: Any) -> int:
    total = 0
    for value in values:
        try:
            total += int(value or 0)
        except (TypeError, ValueError):
            continue
    return total
