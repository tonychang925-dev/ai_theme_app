from __future__ import annotations

from typing import Any


class SeatMoneySnapshotAdapter:
    """Build recap-level seat money facts from explicit seat sources only."""

    source = "post_market_recap_snapshot.seat_money_summary"

    def build(self, recap_doc: dict[str, Any]) -> dict[str, Any]:
        context = recap_doc.get("report_context") if isinstance(recap_doc.get("report_context"), dict) else {}
        dragon_rows = _dict_list(context.get("dragon_tiger"))
        hot_money_rows = _dict_list(context.get("hot_money_activities"))

        institution_rows = [_institution_row(row) for row in dragon_rows]
        institution_rows = [row for row in institution_rows if row["stock_id"] or row["stock_name"]]
        institution_rows.sort(key=lambda item: (-float(item.get("net_buy") or 0), str(item.get("stock_name") or "")))

        hot_money_grouped = _group_hot_money_rows(hot_money_rows)
        if not hot_money_grouped:
            hot_money_grouped = _group_hot_money_from_dragon_rows(dragon_rows)

        hot_money_buy_rows = [
            bucket for bucket in hot_money_grouped.values() if bucket.get("buy_entries")
        ]
        hot_money_sell_rows = [
            bucket for bucket in hot_money_grouped.values() if bucket.get("sell_entries")
        ]
        hot_money_buy_rows.sort(key=lambda item: (-float(item.get("net_buy") or 0), str(item.get("hot_money_name") or "")))
        hot_money_sell_rows.sort(key=lambda item: (float(item.get("net_buy") or 0), str(item.get("hot_money_name") or "")))

        institution_buy_rows = [row for row in institution_rows if float(row.get("net_buy") or 0) >= 0][:20]
        institution_sell_rows = [
            row
            for row in sorted(institution_rows, key=lambda item: (float(item.get("net_buy") or 0), str(item.get("stock_name") or "")))
            if float(row.get("net_buy") or 0) <= 0
        ][:20]

        institution_sum = sum(float(row.get("net_buy") or 0) for row in institution_rows)
        hot_money_sum = sum(float(row.get("net_buy") or 0) for row in hot_money_grouped.values())
        has_structured_source = bool(dragon_rows or hot_money_rows)
        return {
            "summary": _summary(institution_buy_rows, hot_money_buy_rows, has_structured_source),
            "cohesion": _cohesion(institution_rows, hot_money_grouped, institution_sum, hot_money_sum),
            "institution_net_buy": institution_sum,
            "hot_money_net_buy": hot_money_sum,
            "institution_buy_rows": institution_buy_rows,
            "institution_sell_rows": institution_sell_rows,
            "hot_money_buy_rows": hot_money_buy_rows[:20],
            "hot_money_sell_rows": hot_money_sell_rows[:20],
            "institution_top_buys": institution_buy_rows[:3],
            "institution_top_sells": institution_sell_rows[:3],
            "hot_money_top_buys": hot_money_buy_rows[:3],
            "hot_money_top_sells": hot_money_sell_rows[:3],
            "theme_rows": [],
            "diagnostics": {
                "source": "structured" if has_structured_source else "none",
                "source_tables": ["dragon_tiger_object", "hot_money_trading_activity"],
                "dragon_tiger_row_count": len(dragon_rows),
                "hot_money_activity_row_count": len(hot_money_rows),
                "institution_row_count": len(institution_rows),
                "hot_money_seat_count": len(hot_money_grouped),
            },
        }


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _institution_row(row: dict[str, Any]) -> dict[str, Any]:
    buy_amount = _float(row.get("buy_amount") or row.get("billboard_buy_amount"))
    sell_amount = _float(row.get("sell_amount") or row.get("billboard_sell_amount"))
    net_buy = _float(row.get("net_buy") or row.get("net_amount") or row.get("net_buy_amount"))
    if net_buy is None and buy_amount is not None and sell_amount is not None:
        net_buy = buy_amount - sell_amount
    return {
        "stock_id": _text(row.get("stock_id") or row.get("stock_code")),
        "stock_name": _text(row.get("stock_name")),
        "theme_name": _text(row.get("theme_name") or row.get("resolved_theme_name")),
        "buy_seat_count": _int(row.get("institution_seat_count")),
        "sell_seat_count": None,
        "institution_buy_amount": buy_amount,
        "institution_sell_amount": sell_amount,
        "net_buy": net_buy or 0.0,
        "reason": _text(row.get("reason") or row.get("lhb_reason") or row.get("list_reason")),
        "seat_summary": row.get("seat_summary") if isinstance(row.get("seat_summary"), list) else [],
    }


def _int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def _group_hot_money_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        seat_name = _text(row.get("hot_money_name") or row.get("seat_name"))
        if not seat_name:
            continue
        entry = _hot_money_entry(row)
        bucket = grouped.setdefault(seat_name, _hot_money_bucket(seat_name))
        bucket["net_buy"] = float(bucket["net_buy"] or 0) + float(entry["net_amount"] or 0)
        if _text(row.get("side")) == "卖出":
            bucket["sell_net"] = float(bucket["sell_net"] or 0) + float(entry["net_amount"] or 0)
            bucket["sell_entries"].append(entry)
        else:
            bucket["buy_net"] = float(bucket["buy_net"] or 0) + float(entry["net_amount"] or 0)
            bucket["buy_entries"].append(entry)
    return _sort_hot_money_entries(grouped)


def _group_hot_money_from_dragon_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        seat_name = _text(row.get("hot_money_name") or row.get("famous_seat") or row.get("seat_name"))
        seat_type = _text(row.get("seat_type") or row.get("seat_category") or row.get("seat_role"))
        if not seat_name and seat_type not in {"HOT_MONEY", "MIXED"}:
            continue
        if not seat_name:
            seat_name = _text(row.get("stock_name"))
        if not seat_name:
            continue
        entry = _hot_money_entry(row)
        bucket = grouped.setdefault(seat_name, _hot_money_bucket(seat_name))
        bucket["net_buy"] = float(bucket["net_buy"] or 0) + float(entry["net_amount"] or 0)
        if float(entry["net_amount"] or 0) < 0:
            bucket["sell_net"] = float(bucket["sell_net"] or 0) + float(entry["net_amount"] or 0)
            bucket["sell_entries"].append(entry)
        else:
            bucket["buy_net"] = float(bucket["buy_net"] or 0) + float(entry["net_amount"] or 0)
            bucket["buy_entries"].append(entry)
    return _sort_hot_money_entries(grouped)


def _hot_money_bucket(seat_name: str) -> dict[str, Any]:
    return {
        "hot_money_name": seat_name,
        "buy_entries": [],
        "sell_entries": [],
        "buy_net": 0.0,
        "sell_net": 0.0,
        "net_buy": 0.0,
    }


def _hot_money_entry(row: dict[str, Any]) -> dict[str, Any]:
    buy_amount = _float(row.get("buy_amount") or row.get("billboard_buy_amount"))
    sell_amount = _float(row.get("sell_amount") or row.get("billboard_sell_amount"))
    net_amount = _float(row.get("net_amount") or row.get("net_buy") or row.get("net_buy_amount"))
    if net_amount is None and buy_amount is not None and sell_amount is not None:
        net_amount = buy_amount - sell_amount
    return {
        "stock_id": _text(row.get("stock_id") or row.get("stock_code")),
        "stock_name": _text(row.get("stock_name")),
        "theme_name": _text(row.get("theme_name") or row.get("resolved_theme_name")),
        "subject_key": _text(row.get("subject_key")),
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "net_amount": net_amount or 0.0,
        "reason": _text(row.get("reason") or row.get("lhb_reason") or row.get("list_reason")),
        "rank_order": _int(row.get("rank_order")),
        "is_theme_leader": bool(row.get("is_theme_leader") or row.get("is_leader")),
        "style_tags": row.get("style_tags") if isinstance(row.get("style_tags"), list) else [],
    }


def _sort_hot_money_entries(grouped: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for bucket in grouped.values():
        bucket["buy_entries"] = sorted(
            bucket["buy_entries"],
            key=lambda item: (-float(item.get("net_amount") or 0), str(item.get("stock_name") or "")),
        )[:3]
        bucket["sell_entries"] = sorted(
            bucket["sell_entries"],
            key=lambda item: (float(item.get("net_amount") or 0), str(item.get("stock_name") or "")),
        )[:3]
    return grouped


def _cohesion(
    institution_rows: list[dict[str, Any]],
    hot_money_grouped: dict[str, dict[str, Any]],
    institution_sum: float,
    hot_money_sum: float,
) -> str:
    if institution_rows and hot_money_grouped:
        return "同向" if (institution_sum >= 0) == (hot_money_sum >= 0) else "分歧"
    return "未知"


def _summary(
    institution_buy_rows: list[dict[str, Any]],
    hot_money_buy_rows: list[dict[str, Any]],
    has_structured_source: bool,
) -> str:
    if not has_structured_source:
        return "暂无结构化机构席位/游资数据"
    institution_text = "、".join(
        row["stock_name"] for row in institution_buy_rows[:3] if row.get("stock_name")
    ) or "暂无机构重点"
    hot_money_text = "、".join(
        row["hot_money_name"] for row in hot_money_buy_rows[:3] if row.get("hot_money_name")
    ) or "暂无游资重点"
    return f"机构关注 {institution_text}，游资关注 {hot_money_text}。"
