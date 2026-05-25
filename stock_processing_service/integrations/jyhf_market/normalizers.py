"""P1-A 标准化器 — API 响应 → 数据模型."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

from stock_processing_service.integrations.jyhf_market.schemas import (
    JyhfIndexQuote, JyhfStockQuote, JyhfSubjectStockQuote,
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


def normalize_index_quotes(raw: dict) -> list[JyhfIndexQuote]:
    data = raw.get("data", {})
    if not isinstance(data, dict):
        return []
    results = []
    for code, item in data.items():
        if not isinstance(item, dict):
            continue
        results.append(JyhfIndexQuote(
            trade_date=str(item.get("trade_date", _today())),
            ts=str(item.get("time", _now())),
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


def normalize_stock_quote(raw: dict, stock_id: str) -> JyhfStockQuote | None:
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
                ts=str(row[1]) if row[1] else _now(),
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
