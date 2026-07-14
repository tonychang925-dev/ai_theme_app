"""PR4.2.34e — Stock Identity Normalizer.

Maps various stock code formats to canonical Tushare format (6-digit.SZ/SH).
  - DB raw: "603019", "000021"
  - Tushare: "603019.SH", "000021.SZ"
  - Sina: "sz000021"
  - With prefix: "SH603019"

All internal matching should go through this normalizer to avoid the
identity mismatch that caused 国产算力 theme to have 0 matched stocks.
"""

from __future__ import annotations

SH_PREFIXES = ("6", "9", "5")  # 上海交易所


def to_db_code(ts_code: str) -> str:
    """Tushare format → DB 6-digit format: '603019.SH' → '603019'."""
    return ts_code.split(".")[0].strip()


def to_ts_code(db_code: str) -> str:
    """DB 6-digit format → Tushare format: '603019' → '603019.SH'."""
    code = db_code.strip()
    if "." in code:
        return code  # already has exchange suffix
    if code.startswith(SH_PREFIXES):
        return f"{code}.SH"
    return f"{code}.SZ"


def to_canonical(raw: str) -> str:
    """Any format → canonical Tushare format."""
    text = raw.strip().upper()
    # Strip known prefixes
    for prefix in ("SZ", "SH", "BJ"):
        if text.startswith(prefix):
            text = text[2:]
            break
    # Strip exchange suffix if present
    if "." in text:
        text = text.split(".")[0]
    # Re-apply correct exchange suffix
    if text.startswith(SH_PREFIXES):
        return f"{text}.SH"
    return f"{text}.SZ"


def normalize_for_matching(raw: str) -> str:
    """Strip to 6-digit format for cross-table matching."""
    return raw.strip().split(".")[0].lstrip("SZ").lstrip("SH").lstrip("BJ")
