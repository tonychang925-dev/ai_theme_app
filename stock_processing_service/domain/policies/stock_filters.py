from __future__ import annotations


def is_excluded_stock(stock_code: str) -> bool:
    """Exclude ST and 688-prefixed symbols for strong-stock tracking."""
    code = (stock_code or "").strip().upper()
    if not code:
        return True
    if code.startswith("688"):
        return True
    return False
