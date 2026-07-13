"""Normalize stock rows into the ReviewDocument stock contract."""

from __future__ import annotations

from typing import Any


class StockDocumentNormalizer:
    """Map internal strong stock rows to public ReviewDocument stock objects."""

    def normalize_many(self, rows: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.normalize(row) for row in rows if isinstance(row, dict)]

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        code = _text(row.get("code") or row.get("stock_code") or row.get("stock_id"))
        name = _stock_name(row, code)
        themes = _themes(row)
        height = _first(row, "height", "board_height")

        stock = {
            "code": code,
            "name": name,
            "themes": themes,
            "role": _text(row.get("role")),
            "height": height,
        }
        if name is None or not themes:
            stock["quality"] = "DEGRADED"
        return stock


def _stock_name(row: dict[str, Any], code: str) -> str | None:
    name = _text(row.get("name") or row.get("stock_name"))
    if not name or name == code:
        return None
    return name


def _themes(row: dict[str, Any]) -> list[dict[str, Any]]:
    existing = row.get("themes")
    if isinstance(existing, list):
        themes = [_theme_from_mapping(item) for item in existing if isinstance(item, dict)]
        return [item for item in themes if item]

    key = _text(row.get("theme_key") or row.get("subject_key"))
    name = _text(row.get("theme_name"))
    if _is_independent_marker(key) or _is_independent_marker(name) or not name:
        return []

    theme: dict[str, Any] = {"name": name}
    if key:
        theme["key"] = key
    return [theme]


def _theme_from_mapping(item: dict[str, Any]) -> dict[str, Any]:
    key = _text(item.get("key") or item.get("theme_key") or item.get("subject_key"))
    name = _text(item.get("name") or item.get("theme_name"))
    if _is_independent_marker(key) or _is_independent_marker(name) or not name:
        return {}
    theme: dict[str, Any] = {"name": name}
    if key:
        theme["key"] = key
    return theme


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_independent_marker(value: str) -> bool:
    return value == "__independent__"
