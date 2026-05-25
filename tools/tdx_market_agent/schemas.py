"""TDX Market Agent 响应模型."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(TZ_CN).isoformat()


def health_response() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "tdx_market_agent",
        "source": "tdx_mootdx",
        "time": _now(),
    }


def quote_response(stock_id: str, system_stock_id: str, raw: dict) -> dict[str, Any]:
    return {
        "source": "tdx_mootdx",
        "stock_id": stock_id,
        "system_stock_id": system_stock_id,
        "ts": _now(),
        "data_type": "quote",
        "fields": {
            "price": raw.get("price"),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "last_close": raw.get("last_close"),
            "amount": raw.get("amount"),
            "vol": raw.get("vol"),
            "servertime": raw.get("servertime"),
            "bid1": raw.get("bid1"), "ask1": raw.get("ask1"),
            "bid_vol1": raw.get("bid_vol1"), "ask_vol1": raw.get("ask_vol1"),
            "bid2": raw.get("bid2"), "ask2": raw.get("ask2"),
            "bid_vol2": raw.get("bid_vol2"), "ask_vol2": raw.get("ask_vol2"),
            "bid3": raw.get("bid3"), "ask3": raw.get("ask3"),
            "bid_vol3": raw.get("bid_vol3"), "ask_vol3": raw.get("ask_vol3"),
            "bid4": raw.get("bid4"), "ask4": raw.get("ask4"),
            "bid_vol4": raw.get("bid_vol4"), "ask_vol4": raw.get("ask_vol4"),
            "bid5": raw.get("bid5"), "ask5": raw.get("ask5"),
            "bid_vol5": raw.get("bid_vol5"), "ask_vol5": raw.get("ask_vol5"),
        },
        "raw": raw,
    }


def minute_response(stock_id: str, system_stock_id: str, rows: list[dict]) -> dict[str, Any]:
    return {
        "source": "tdx_mootdx",
        "stock_id": stock_id,
        "system_stock_id": system_stock_id,
        "ts": _now(),
        "data_type": "minute",
        "row_count": len(rows),
        "rows": [
            {
                "minute_index": int(r.get("index", i)),
                "price": r.get("price"),
                "vol": r.get("vol"),
                "volume": r.get("volume"),
            }
            for i, r in enumerate(rows)
        ],
    }


def bars_response(
    stock_id: str, system_stock_id: str, rows: list[dict], frequency: int, offset: int,
) -> dict[str, Any]:
    result_rows = []
    for r in rows:
        bar_time = _build_bar_time(r)
        result_rows.append({
            "bar_time": bar_time,
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "close": r.get("close"),
            "vol": r.get("vol"),
            "amount": r.get("amount"),
            "year": r.get("year"),
            "month": r.get("month"),
            "day": r.get("day"),
            "hour": r.get("hour"),
            "minute": r.get("minute"),
        })

    return {
        "source": "tdx_mootdx",
        "stock_id": stock_id,
        "system_stock_id": system_stock_id,
        "ts": _now(),
        "data_type": "bars",
        "frequency": frequency,
        "offset": offset,
        "row_count": len(result_rows),
        "rows": result_rows,
    }


def _build_bar_time(row: dict) -> str:
    """从 year/month/day/hour/minute 字段生成 ISO 时间字符串."""
    try:
        y = int(row.get("year") or 0)
        m = int(row.get("month") or 0)
        d = int(row.get("day") or 0)
        h = int(row.get("hour") or 0)
        mi = int(row.get("minute") or 0)
        if y > 2000 and m > 0 and d > 0:
            return datetime(y, m, d, h, mi, 0, tzinfo=TZ_CN).isoformat()
    except (ValueError, TypeError):
        pass
    return _now()
