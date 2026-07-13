from __future__ import annotations

from typing import Any


class CapitalSnapshotAdapter:
    """Project seat money summary into draft capital state."""

    @staticmethod
    def directions_from_seat_money(seat_money_summary: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        if not isinstance(seat_money_summary, dict):
            return {"institution": [], "hot_money": []}
        return {
            "institution": [
                _institution_direction(row)
                for row in _dict_list(seat_money_summary.get("institution_buy_rows"))
                if _direction_name(row)
            ],
            "hot_money": [
                _hot_money_direction(row)
                for row in _dict_list(seat_money_summary.get("hot_money_buy_rows"))
                if _hot_money_name(row) and _hot_money_theme_name(row)
            ],
        }


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _direction_name(row: dict[str, Any]) -> str:
    return _text(row.get("theme_name") or row.get("stock_name"))


def _hot_money_name(row: dict[str, Any]) -> str:
    return _text(row.get("hot_money_name"))


def _hot_money_theme_name(row: dict[str, Any]) -> str:
    entries = _dict_list(row.get("buy_entries"))
    first = entries[0] if entries else {}
    return _text(first.get("theme_name"))


def _institution_direction(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme_name": _direction_name(row),
        "stock_name": _text(row.get("stock_name")),
        "net_buy": row.get("net_buy"),
        "source": "post_market_recap_snapshot.seat_money_summary.institution_buy_rows",
    }


def _hot_money_direction(row: dict[str, Any]) -> dict[str, Any]:
    entries = _dict_list(row.get("buy_entries"))
    return {
        "theme_name": _hot_money_theme_name(row),
        "hot_money_name": _hot_money_name(row),
        "net_buy": row.get("net_buy"),
        "entries": entries,
        "source": "post_market_recap_snapshot.seat_money_summary.hot_money_buy_rows",
    }
