from __future__ import annotations


def normalize_stock_id(raw: str) -> str:
    """统一证券代码格式为 000001.SZ / 600000.SH / 430001.BJ。"""
    value = (raw or "").strip().upper()
    if not value:
        return ""

    if "." in value:
        code, suffix = value.split(".", 1)
        if len(code) == 6 and code.isdigit() and suffix in {"SZ", "SH", "BJ"}:
            return f"{code}.{suffix}"
        value = code

    if len(value) != 6 or not value.isdigit():
        return ""

    if value.startswith(("60", "68")):
        suffix = "SH"
    elif value.startswith(("43", "83", "87")):
        suffix = "BJ"
    else:
        suffix = "SZ"

    return f"{value}.{suffix}"
