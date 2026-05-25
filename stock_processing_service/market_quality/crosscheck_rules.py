"""P1-D 双源校验规则引擎.

Status:
  OK             — price_diff_pct <= 0.3%
  WARN           — 0.3% < price_diff_pct <= 1.0%
  CRITICAL       — price_diff_pct > 1.0%
  MISSING_SOURCE — 任一源无数据
  STALE_SOURCE   — 任一源延迟 > 30s
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

TZ_CN = timezone(timedelta(hours=8))
_MAX_STALE_SECONDS = 30.0
_PRICE_WARN_THRESHOLD = 0.3   # %
_PRICE_CRIT_THRESHOLD = 1.0   # %


def evaluate(
    stock_id: str,
    jyhf: dict[str, Any] | None,
    tdx: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """评估双源行情一致性.

    返回:
      {
        "stock_id": "002361.SZ",
        "jyhf_ts": datetime or None,
        "tdx_ts": datetime or None,
        "jyhf_price": float or None,
        "tdx_price": float or None,
        "price_diff": float or None,
        "price_diff_pct": float or None,
        "jyhf_pct_chg": float or None,
        "tdx_pct_chg": float or None,
        "pct_chg_diff": float or None,
        "jyhf_amount": float or None,
        "tdx_amount": float or None,
        "amount_diff_pct": float or None,
        "jyhf_vol": float or None,
        "tdx_vol": float or None,
        "vol_diff_pct": float or None,
        "jyhf_delay_seconds": float or None,
        "tdx_delay_seconds": float or None,
        "crosscheck_status": str,
        "severity": str,
        "reason": str,
        "raw": dict,
      }
    """
    if now is None:
        now = datetime.now(TZ_CN)

    result: dict[str, Any] = {
        "stock_id": stock_id,
        "jyhf_ts": None,
        "tdx_ts": None,
        "jyhf_price": None,
        "tdx_price": None,
        "price_diff": None,
        "price_diff_pct": None,
        "jyhf_pct_chg": None,
        "tdx_pct_chg": None,
        "pct_chg_diff": None,
        "jyhf_amount": None,
        "tdx_amount": None,
        "amount_diff_pct": None,
        "jyhf_vol": None,
        "tdx_vol": None,
        "vol_diff_pct": None,
        "jyhf_delay_seconds": None,
        "tdx_delay_seconds": None,
        "crosscheck_status": "MISSING_SOURCE",
        "severity": "warning",
        "reason": "",
        "raw": {},
    }

    # ── 缺失检测 ──
    if jyhf is None and tdx is None:
        result["crosscheck_status"] = "MISSING_SOURCE"
        result["severity"] = "critical"
        result["reason"] = "both_sources_missing"
        return result

    if jyhf is None:
        result["crosscheck_status"] = "MISSING_SOURCE"
        result["severity"] = "critical"
        result["reason"] = "jyhf_missing"
        if tdx is not None:
            result["tdx_ts"] = _to_dt(tdx.get("ts"))
            result["tdx_price"] = _safe_float(tdx.get("price"))
            result["tdx_pct_chg"] = _safe_float(tdx.get("pct_chg"))
            result["tdx_amount"] = _safe_float(tdx.get("amount"))
            result["tdx_vol"] = _safe_float(tdx.get("vol"))
        return result

    if tdx is None:
        result["crosscheck_status"] = "MISSING_SOURCE"
        result["severity"] = "critical"
        result["reason"] = "tdx_missing"
        result["jyhf_ts"] = _to_dt(jyhf.get("ts"))
        result["jyhf_price"] = _safe_float(jyhf.get("price"))
        result["jyhf_pct_chg"] = _safe_float(jyhf.get("pct_chg"))
        result["jyhf_amount"] = _safe_float(jyhf.get("amount"))
        result["jyhf_vol"] = _safe_float(jyhf.get("vol"))
        return result

    # ── 填充原始数据 ──
    jyhf_ts = _to_dt(jyhf.get("ts"))
    tdx_ts = _to_dt(tdx.get("ts"))
    jyhf_price = _safe_float(jyhf.get("price"))
    tdx_price = _safe_float(tdx.get("price"))

    result["jyhf_ts"] = jyhf_ts
    result["tdx_ts"] = tdx_ts
    result["jyhf_price"] = jyhf_price
    result["tdx_price"] = tdx_price
    result["jyhf_pct_chg"] = _safe_float(jyhf.get("pct_chg"))
    result["tdx_pct_chg"] = _safe_float(tdx.get("pct_chg"))
    result["jyhf_amount"] = _safe_float(jyhf.get("amount"))
    result["tdx_amount"] = _safe_float(tdx.get("amount"))
    result["jyhf_vol"] = _safe_float(jyhf.get("vol"))
    result["tdx_vol"] = _safe_float(tdx.get("vol"))
    result["raw"] = {"jyhf": {k: str(v) for k, v in jyhf.items()}, "tdx": {k: str(v) for k, v in tdx.items()}}

    # ── 延迟 ──
    if jyhf_ts:
        result["jyhf_delay_seconds"] = (now - jyhf_ts).total_seconds()
    if tdx_ts:
        result["tdx_delay_seconds"] = (now - tdx_ts).total_seconds()

    # ── 过期检测 ──
    jyhf_stale = result["jyhf_delay_seconds"] is not None and result["jyhf_delay_seconds"] > _MAX_STALE_SECONDS
    tdx_stale = result["tdx_delay_seconds"] is not None and result["tdx_delay_seconds"] > _MAX_STALE_SECONDS
    if jyhf_stale and tdx_stale:
        result["crosscheck_status"] = "STALE_SOURCE"
        result["severity"] = "critical"
        result["reason"] = "both_sources_stale"
        return result
    if jyhf_stale:
        result["crosscheck_status"] = "STALE_SOURCE"
        result["severity"] = "warning"
        result["reason"] = f"jyhf_stale_{result['jyhf_delay_seconds']:.0f}s"
        return result
    if tdx_stale:
        result["crosscheck_status"] = "STALE_SOURCE"
        result["severity"] = "warning"
        result["reason"] = f"tdx_stale_{result['tdx_delay_seconds']:.0f}s"
        return result

    # ── 价差 ──
    if jyhf_price and tdx_price and jyhf_price != 0:
        result["price_diff"] = round(float(jyhf_price - tdx_price), 4)
        result["price_diff_pct"] = round(abs(float(jyhf_price - tdx_price) / float(jyhf_price)) * 100, 6)

    # ── 涨跌幅差 ──
    if result["jyhf_pct_chg"] is not None and result["tdx_pct_chg"] is not None:
        result["pct_chg_diff"] = round(abs(float(result["jyhf_pct_chg"]) - float(result["tdx_pct_chg"])), 4)

    # ── 成交额/成交量差（仅记录，不做强判定）──
    if result["jyhf_amount"] and result["tdx_amount"] and result["jyhf_amount"] != 0:
        result["amount_diff_pct"] = round(
            abs(float(result["jyhf_amount"]) - float(result["tdx_amount"])) / float(result["jyhf_amount"]) * 100, 6,
        )
    if result["jyhf_vol"] and result["tdx_vol"] and result["jyhf_vol"] != 0:
        result["vol_diff_pct"] = round(
            abs(float(result["jyhf_vol"]) - float(result["tdx_vol"])) / float(result["jyhf_vol"]) * 100, 6,
        )

    # ── 判定 ──
    diff_pct = result["price_diff_pct"]
    if diff_pct is not None:
        if diff_pct <= _PRICE_WARN_THRESHOLD:
            result["crosscheck_status"] = "OK"
            result["severity"] = "info"
            result["reason"] = "price_diff_ok"
        elif diff_pct <= _PRICE_CRIT_THRESHOLD:
            result["crosscheck_status"] = "WARN"
            result["severity"] = "warning"
            result["reason"] = f"price_diff_{diff_pct:.2f}pct"
        else:
            result["crosscheck_status"] = "CRITICAL"
            result["severity"] = "critical"
            result["reason"] = f"price_diff_{diff_pct:.2f}pct_gt_1pct"

    return result


def _safe_float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (ValueError, TypeError):
        return None


def _to_dt(value) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
