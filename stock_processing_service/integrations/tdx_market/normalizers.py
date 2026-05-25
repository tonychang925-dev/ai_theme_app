"""TDX 标准化器 — Agent 响应 → 数据模型."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

from stock_processing_service.integrations.tdx_market.schemas import (
    TdxStockQuote, TdxMinuteBar, TdxDailyBar,
)

logger = logging.getLogger("sps.tdx_market.normalizers")
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


def _safe_int(value, default=None):
    try:
        return None if value is None else int(value)
    except (ValueError, TypeError):
        return default


def normalize_quote(raw: dict) -> TdxStockQuote | None:
    """Agent /quote 响应 → TdxStockQuote."""
    fields = raw.get("fields", {})
    if not fields:
        return None

    quote = TdxStockQuote(
        trade_date=_today(),
        ts=raw.get("ts", _now()),
        stock_id=raw.get("stock_id", ""),
        system_stock_id=raw.get("system_stock_id", ""),
        price=_safe_float(fields.get("price")),
        open=_safe_float(fields.get("open")),
        high=_safe_float(fields.get("high")),
        low=_safe_float(fields.get("low")),
        last_close=_safe_float(fields.get("last_close")),
        amount=_safe_float(fields.get("amount")),
        vol=_safe_float(fields.get("vol")),
        servertime=fields.get("servertime"),
        bid1=_safe_float(fields.get("bid1")), ask1=_safe_float(fields.get("ask1")),
        bid_vol1=_safe_int(fields.get("bid_vol1")), ask_vol1=_safe_int(fields.get("ask_vol1")),
        bid2=_safe_float(fields.get("bid2")), ask2=_safe_float(fields.get("ask2")),
        bid_vol2=_safe_int(fields.get("bid_vol2")), ask_vol2=_safe_int(fields.get("ask_vol2")),
        bid3=_safe_float(fields.get("bid3")), ask3=_safe_float(fields.get("ask3")),
        bid_vol3=_safe_int(fields.get("bid_vol3")), ask_vol3=_safe_int(fields.get("ask_vol3")),
        bid4=_safe_float(fields.get("bid4")), ask4=_safe_float(fields.get("ask4")),
        bid_vol4=_safe_int(fields.get("bid_vol4")), ask_vol4=_safe_int(fields.get("ask_vol4")),
        bid5=_safe_float(fields.get("bid5")), ask5=_safe_float(fields.get("ask5")),
        bid_vol5=_safe_int(fields.get("bid_vol5")), ask_vol5=_safe_int(fields.get("ask_vol5")),
        raw_json=raw.get("raw", raw),
    )
    return quote


def normalize_minute(raw: dict) -> list[TdxMinuteBar]:
    """Agent /minute 响应 → list[TdxMinuteBar]."""
    rows = raw.get("rows", [])
    if not rows:
        return []

    stock_id = raw.get("stock_id", "")
    system_stock_id = raw.get("system_stock_id", "")
    ts = raw.get("ts", _now())
    trade_date = _today()

    return [
        TdxMinuteBar(
            trade_date=trade_date,
            ts=ts,
            stock_id=stock_id,
            system_stock_id=system_stock_id,
            minute_index=_safe_int(r.get("minute_index"), 0) or 0,
            price=_safe_float(r.get("price")),
            vol=_safe_float(r.get("vol")),
            volume=_safe_float(r.get("volume")),
            raw_json=r,
        )
        for r in rows
    ]


def normalize_bars(raw: dict) -> list[TdxDailyBar]:
    """Agent /bars 响应 → list[TdxDailyBar]."""
    rows = raw.get("rows", [])
    if not rows:
        return []

    stock_id = raw.get("stock_id", "")
    system_stock_id = raw.get("system_stock_id", "")
    ts = raw.get("ts", _now())
    trade_date = _today()
    frequency = raw.get("frequency", 9)

    return [
        TdxDailyBar(
            trade_date=trade_date,
            ts=ts,
            stock_id=stock_id,
            system_stock_id=system_stock_id,
            bar_time=r.get("bar_time"),
            open=_safe_float(r.get("open")),
            high=_safe_float(r.get("high")),
            low=_safe_float(r.get("low")),
            close=_safe_float(r.get("close")),
            vol=_safe_float(r.get("vol")),
            amount=_safe_float(r.get("amount")),
            frequency=frequency,
            raw_json=r,
        )
        for r in rows
    ]
