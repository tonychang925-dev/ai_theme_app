"""PR-11: MarketRegimeFactContextBuilder.

Actively builds market regime fact context from real data sources:
  - akshare index K-line (TDX)
  - market breadth from report_context or estimate
  - mainline_lifecycle_reviews
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MarketRegimeFactContext:
    trade_date: str = ""
    index_kline: list[dict[str, Any]] = field(default_factory=list)
    index_technical_reviews: list[dict[str, Any]] = field(default_factory=list)
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    lifecycle_reviews: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "index_kline_rows": len(self.index_kline),
            "index_technical_reviews": self.index_technical_reviews,
            "market_snapshot": self.market_snapshot,
            "lifecycle_review_count": len(self.lifecycle_reviews),
            "diagnostics": self.diagnostics,
        }


class MarketRegimeFactContextBuilder:
    """Build market regime fact context from real data."""

    def __init__(self, read_port: Any = None) -> None:
        self._read = read_port

    async def build(
        self,
        *,
        trade_date: date,
        report_context: dict[str, Any] | None = None,
        lifecycle_reviews: list[dict[str, Any]] | None = None,
        lookback_days: int = 120,
    ) -> MarketRegimeFactContext:
        td_str = trade_date.isoformat()
        diag: dict[str, Any] = {
            "index_source": "akshare_tdx",
            "market_snapshot_source": "report_context_or_default",
            "missing_sources": [],
        }

        # ── 1. Index K-line: prefer DB, fallback to akshare ──
        index_kline: list[dict[str, Any]] = []
        source = "none"
        try:
            import asyncpg
            conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=5)
            try:
                start = trade_date - __import__("datetime").timedelta(days=lookback_days)
                rows = await conn.fetch(
                    """SELECT trade_date, open, high, low, close, volume
                       FROM index_daily_kline
                       WHERE index_code='000001' AND market='1'
                         AND trade_date BETWEEN $1 AND $2
                       ORDER BY trade_date""",
                    start, trade_date,
                )
                if rows:
                    for r in rows:
                        index_kline.append({
                            "close": float(r["close"] or 0),
                            "high": float(r["high"] or 0),
                            "low": float(r["low"] or 0),
                            "volume": float(r["volume"] or 0),
                            "amount": 0,
                        })
                    source = "db.index_daily_kline"
                    diag["index_rows"] = len(index_kline)
            finally:
                await conn.close()
        except Exception:
            pass

        if not index_kline:
            try:
                import akshare as ak
                df = await asyncio.to_thread(ak.stock_zh_index_daily, symbol="sh000001")
                if df is not None and not df.empty:
                    df = df.tail(lookback_days)
                    for _, row in df.iterrows():
                        index_kline.append({
                            "close": float(row["close"]), "high": float(row["high"]),
                            "low": float(row["low"]), "volume": float(row.get("volume", 0)),
                            "amount": 0,
                        })
                    source = "akshare_tdx_live"
                    diag["index_rows"] = len(index_kline)
                else:
                    diag["missing_sources"].append("index_kline")
            except Exception as exc:
                logger.warning("Index K-line fetch failed: %s", exc)
                diag["missing_sources"].append("index_kline")

        diag["index_source"] = source

        # ── 1b. Read index technical analysis from DB ──
        index_technical_reviews: list[dict[str, Any]] = []
        index_data_ready = False
        index_close_map: dict[str, float] = {}
        try:
            import asyncpg as apg2
            conn2 = await apg2.connect("postgresql://localhost/stock_data_test", timeout=5)
            try:
                close_rows = await conn2.fetch(
                    """SELECT index_code, close
                       FROM index_daily_kline
                       WHERE trade_date = $1::date
                       ORDER BY index_code""",
                    trade_date,
                )
                for r in close_rows:
                    d = dict(r)
                    code = str(d.get("index_code") or "").strip()
                    close = d.get("close")
                    if code and close is not None:
                        try:
                            index_close_map[code] = float(close)
                        except Exception:
                            continue

                td_rows = await conn2.fetch(
                    """SELECT * FROM index_technical_daily
                       WHERE trade_date = $1::date
                       ORDER BY index_code""",
                    trade_date,
                )
                if td_rows:
                    for r in td_rows:
                        index_technical_reviews.append(self._enrich_index_technical_review(dict(r), index_close_map))
                    index_data_ready = True
                    diag["index_technical_count"] = len(index_technical_reviews)
            finally:
                await conn2.close()
        except Exception as e:
            logger.warning("Index technical daily read failed: %s", e)
            diag["index_technical_error"] = str(e)[:100]

        diag["index_data_ready"] = index_data_ready
        if index_data_ready:
            diag["index_data_source"] = "index_technical_daily"
        elif index_kline:
            diag["index_data_source"] = "index_daily_kline_only"

        # ── 2. Market snapshot ──
        market_snapshot: dict[str, Any] = {}
        if report_context:
            market = report_context.get("market", {})
            if isinstance(market, dict):
                market_snapshot = dict(market)
        # Fallback: use reasonable defaults
        if not market_snapshot:
            market_snapshot = {
                "up_count": 2000, "down_count": 3000,
                "limit_up_count": 30, "limit_down_count": 10,
                "relay_sentiment_status": "normal",
                "intraday_fade_status": "normal",
            }
            diag["market_snapshot_source"] = "default_estimate"

        # ── 3. Lifecycle reviews ──
        reviews = lifecycle_reviews or []

        return MarketRegimeFactContext(
            trade_date=td_str,
            index_kline=index_kline,
            index_technical_reviews=index_technical_reviews,
            market_snapshot=market_snapshot,
            lifecycle_reviews=reviews,
            diagnostics=diag,
        )

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    @classmethod
    def _enrich_index_technical_review(
        cls,
        row: dict[str, Any],
        index_close_map: dict[str, float],
    ) -> dict[str, Any]:
        d = dict(row)
        d.pop("id", None)

        # Convert date/time to string
        for k in ("trade_date", "created_at", "updated_at"):
            if k in d and hasattr(d[k], "isoformat"):
                d[k] = d[k].isoformat()

        # Parse JSONB
        for k in ("risk_flags_json", "diagnostics_json"):
            if k in d and isinstance(d[k], str):
                try:
                    d[k] = __import__("json").loads(d[k])
                except Exception:
                    pass
            clean_k = k.replace("_json", "")
            d[clean_k] = d.pop(k, d.get(clean_k, []))

        index_code = str(d.get("index_code") or "").strip()
        close = cls._float_or_none(index_close_map.get(index_code))
        support = cls._float_or_none(d.get("nearest_support_level") or d.get("support_level"))
        resistance = cls._float_or_none(d.get("nearest_resistance_level") or d.get("resistance_level"))

        support_distance = None
        resistance_distance = None
        if close is not None and close > 0 and support is not None:
            support_distance = round((close - support) / close * 100, 2)
        if close is not None and close > 0 and resistance is not None:
            resistance_distance = round((resistance - close) / close * 100, 2)

        support_broken = bool(d.get("break_support")) or bool(
            close is not None and support is not None and close < support
        )
        resistance_broken = bool(
            close is not None and resistance is not None and close > resistance
        )
        near_support = bool(
            support_distance is not None and 0 <= support_distance <= 1.0
        )
        near_resistance = bool(
            resistance_distance is not None and 0 <= resistance_distance <= 2.0
        )

        if support_broken:
            support_status = "support_broken"
        elif near_support:
            support_status = "near_support"
        else:
            support_status = "support_available" if support is not None else "unknown"

        if resistance_broken:
            resistance_status = "resistance_broken"
        elif near_resistance:
            resistance_status = "near_resistance"
        else:
            resistance_status = "resistance_available" if resistance is not None else "unknown"

        trend_state = str(d.get("trend_state") or "")
        above_ma5 = bool(d.get("above_ma5"))
        above_ma10 = bool(d.get("above_ma10"))
        above_ma20 = bool(d.get("above_ma20"))
        macd_state = str(d.get("macd_state") or "")

        warning_level = str(d.get("warning_level") or "").strip() or "normal"
        index_trade_hint = str(d.get("index_trade_hint") or "").strip()
        if not index_trade_hint:
            if support_broken and macd_state in {"below_zero_bearish", "below_zero_weak_rebound"}:
                warning_level = "danger"
                index_trade_hint = "支撑失守且MACD偏弱，禁止主动进攻"
            elif resistance_broken or (near_resistance and not above_ma20):
                warning_level = "warning"
                index_trade_hint = "接近压力位或压力已触及，谨慎追高，等待确认突破"
            elif near_support and not above_ma20:
                warning_level = "watch"
                index_trade_hint = "接近支撑位但趋势未确认，等待止跌信号"
            elif above_ma5 and above_ma10 and above_ma20 and not near_resistance:
                warning_level = "green"
                index_trade_hint = "指数环境相对友好，可跟踪主线修复与前排机会"
            elif trend_state == "downtrend_rebound":
                warning_level = "warning"
                index_trade_hint = "下降通道反抽，优先看核心确认，不追后排"
            else:
                index_trade_hint = "指数环境中性，按主线与市场情绪择机应对"

        d.update({
            "close": close,
            "support_level": support,
            "resistance_level": resistance,
            "nearest_support_level": support,
            "nearest_resistance_level": resistance,
            "support_distance_pct": support_distance,
            "resistance_distance_pct": resistance_distance,
            "support_status": support_status,
            "resistance_status": resistance_status,
            "warning_level": warning_level or "normal",
            "index_trade_hint": index_trade_hint,
        })
        return d
