"""P1-A 标准化器 — API 响应 → 数据模型."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

from stock_processing_service.integrations.jyhf_market.schemas import (
    JyhfIndexQuote, JyhfStockDailyBar, JyhfStockQuote, JyhfSubjectStockQuote,
)

logger = logging.getLogger("sps.jyhf_market.normalizers")
TZ_CN = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(TZ_CN).isoformat()

def _today() -> str:
    return str(date.today())

def _safe_float(value, default=None):
    try:
        return None if value is None else float(value)
    except (ValueError, TypeError):
        return default

def _make_ts(trade_date: str, time_str: str) -> str:
    """Combine YYYY-MM-DD trade_date with HHMMSS time into ISO datetime."""
    try:
        td = date.fromisoformat(trade_date)
        hour = int(time_str[:2]) if len(time_str) >= 2 else 0
        minute = int(time_str[2:4]) if len(time_str) >= 4 else 0
        second = int(time_str[4:6]) if len(time_str) >= 6 else 0
        return datetime(td.year, td.month, td.day, hour, minute, second, tzinfo=TZ_CN).isoformat()
    except (ValueError, IndexError):
        return _now()


def normalize_index_quotes(raw: dict) -> list[JyhfIndexQuote]:
    data = raw.get("data", {})
    if not isinstance(data, dict):
        return []
    results = []
    for code, item in data.items():
        if not isinstance(item, dict):
            continue
        trade_date = str(item.get("trade_date", _today()))
        raw_time = str(item.get("time", ""))
        results.append(JyhfIndexQuote(
            trade_date=trade_date,
            ts=_make_ts(trade_date, raw_time) if raw_time else _now(),
            index_code=str(code),
            index_name=str(item.get("name", "")).strip(),
            current=_safe_float(item.get("close")),
            open=_safe_float(item.get("open")),
            high=_safe_float(item.get("high")),
            low=_safe_float(item.get("low")),
            close=_safe_float(item.get("close")),
            pct_chg=_safe_float(item.get("pctChg")),
            amount=_safe_float(item.get("amount")),
            vol=_safe_float(item.get("vol")),
            raw_json=raw,
        ))
    return results


def normalize_stock_quote(raw: dict, stock_id: str, *, api_stock_id: str | None = None) -> JyhfStockQuote | None:
    d = raw.get("data", {})
    if not isinstance(d, dict) or not d:
        return None
    return JyhfStockQuote(
        trade_date=_today(), ts=_now(), stock_id=stock_id,
        stock_name=str(d.get("name", "")),
        current=_safe_float(d.get("current")),
        open=_safe_float(d.get("open")),
        high=_safe_float(d.get("high")),
        low=_safe_float(d.get("low")),
        close=_safe_float(d.get("close")),
        pct_chg=_safe_float(d.get("pctChg")),
        amount=_safe_float(d.get("amount")),
        vol=_safe_float(d.get("vol")),
        pe=_safe_float(d.get("pe")),
        market_value=_safe_float(d.get("marketValue")),
        limit_up=_safe_float(d.get("limitUp")),
        limit_down=_safe_float(d.get("limitDown")),
        source_endpoint="stock/realtime",
        raw_json=raw,
    )


def normalize_subject_stock_quotes(raw: dict, subject_id: str) -> list[JyhfSubjectStockQuote]:
    rows = raw.get("rows", [])
    if not isinstance(rows, list):
        return []
    results = []
    for rank, row in enumerate(rows, start=1):
        try:
            results.append(JyhfSubjectStockQuote(
                trade_date=str(row[0])[:10] if row[0] else _today(),
                ts=_make_ts(str(row[0])[:10], str(row[1])) if row[1] and row[0] else _now(),
                subject_id=subject_id,
                stock_id=str(row[2]),
                stock_name=str(row[3]) if row[3] else "",
                current=_safe_float(row[7]),
                pct_chg=_safe_float(row[10]),
                amount=_safe_float(row[13]),
                vol=_safe_float(row[12]),
                rank_no=rank,
                raw_json={"row": [str(x) for x in row[:15]]},
            ))
        except (IndexError, ValueError, TypeError):
            continue
    return results


# ── P1-F: one-stock-daily normalizer ──


def _normalize_stock_id(raw: str) -> str:
    """Convert raw stock code to system format: 002795 → 002795.SZ."""
    s = raw.strip().upper()
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        elif s.startswith(("0", "3")):
            return f"{s}.SZ"
        elif s.startswith(("4", "8")):
            return f"{s}.BJ"
        return f"{s}.SZ"
    return s


def _extract_raw_rows(raw: dict) -> list[dict]:
    """Extract row list from raw API response, supporting multiple structures.

    Handles:
      - data.items (list of lists) + data.fields (column names) — JYHF format
      - data.rows (list of dicts)
      - data as a list directly
    """
    data = raw.get("data")
    if not isinstance(data, dict):
        return []
    # Pattern 1: data.items (list of lists) + data.fields
    items = data.get("items")
    fields = data.get("fields")
    if isinstance(items, list) and isinstance(fields, list):
        rows = []
        for item in items:
            if isinstance(item, list):
                row = {}
                for i, fname in enumerate(fields):
                    if i < len(item):
                        row[fname] = item[i]
                rows.append(row)
        return rows
    # Pattern 2: data.rows (list of dicts)
    rows = data.get("rows") or data.get("data") or data.get("list")
    if isinstance(rows, list):
        return rows
    return []


def _parse_trade_date(raw_date: str) -> str:
    """Extract YYYY-MM-DD from various trade_date formats."""
    s = str(raw_date or "").strip()
    if not s:
        return ""
    # Handle YYYYMMDD
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    # Handle YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
    return s[:10] if len(s) >= 10 else s


def normalize_stock_daily_bars(
    raw: dict, stock_id: str, *, api_stock_id: str = "", days: int = 120,
) -> list[JyhfStockDailyBar]:
    """Normalize one-stock-daily response into JyhfStockDailyBar list.

    Args:
        raw: API response dict
        stock_id: system format stock ID (e.g. 002795.SZ)
        api_stock_id: API format stock ID (e.g. 002795)
        days: take most recent N bars

    Returns:
        List of JyhfStockDailyBar sorted by trade_date ascending
    """
    rows = _extract_raw_rows(raw)
    if not rows:
        return []

    bars: list[JyhfStockDailyBar] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        td = _parse_trade_date(item.get("trade_date") or item.get("ts_code") or "")
        if not td:
            continue
        name = str(item.get("stock_name") or item.get("name") or "")
        bars.append(JyhfStockDailyBar(
            trade_date=td,
            stock_id=stock_id,
            api_stock_id=api_stock_id,
            stock_name=name,
            open=_safe_float(item.get("open")),
            high=_safe_float(item.get("high")),
            low=_safe_float(item.get("low")),
            close=_safe_float(item.get("close")),
            pre_close=_safe_float(item.get("pre_close")),
            change=_safe_float(item.get("change")),
            pct_chg=_safe_float(item.get("pct_chg")),
            vol=_safe_float(item.get("vol")),
            amount=_safe_float(item.get("amount")),
            raw_json={k: str(v)[:200] for k, v in item.items()},
        ))

    # Sort by trade_date ascending, take the last `days` entries
    bars.sort(key=lambda b: b.trade_date)
    return bars[-days:] if len(bars) > days else bars
