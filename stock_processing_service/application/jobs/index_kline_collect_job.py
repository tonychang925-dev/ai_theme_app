"""PR-13D: IndexKlineCollectJob — 采集大盘指数日K + 技术分析落库。

可被采集控制台勾选触发，也可独立运行。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

INDEX_CONFIG = {
    "000001": {"name": "上证指数", "market": "1"},
    "399001": {"name": "深证成指", "market": "0"},
    "399006": {"name": "创业板指", "market": "0"},
    "000300": {"name": "沪深300", "market": "1"},
    "000905": {"name": "中证500", "market": "1"},
    "000852": {"name": "中证1000", "market": "1"},
    "000688": {"name": "科创50", "market": "1"},
}

DEFAULT_INDICES = ["000001", "399001", "399006", "000300", "000905", "000852"]


@dataclass
class IndexCollectResult:
    trade_date: str
    collected_count: int = 0
    technical_count: int = 0
    total_count: int = 0
    missing_indices: list[str] = None
    source: str = "akshare"
    diagnostics: dict[str, Any] = None

    def __post_init__(self):
        self.missing_indices = self.missing_indices or []
        self.diagnostics = self.diagnostics or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": len(self.missing_indices) == 0,
            "trade_date": self.trade_date,
            "collected_count": self.collected_count,
            "technical_count": self.technical_count,
            "total_count": self.total_count,
            "missing_indices": self.missing_indices,
            "source": self.source,
            "diagnostics": self.diagnostics,
        }


def _to_decimal(val) -> Decimal:
    if val is None or (isinstance(val, float) and (val != val)):
        return Decimal("0")
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


class IndexKlineCollectJob:
    """Collect index daily K-line and compute technical analysis."""

    def __init__(self, pool=None) -> None:
        self._pool = pool

    async def collect(
        self,
        *,
        trade_date: date | None = None,
        indices: list[str] | None = None,
        lookback_days: int = 120,
        force: bool = False,
    ) -> IndexCollectResult:
        indices = indices or DEFAULT_INDICES
        td = trade_date or date.today()

        if self._pool is None:
            return IndexCollectResult(
                trade_date=td.isoformat(),
                missing_indices=indices,
                diagnostics={"error": "no_db_pool"},
            )

        missing: list[str] = []
        collected = 0
        technical = 0

        # Support both Pool and Connection
        pool_obj = self._pool
        if hasattr(pool_obj, 'acquire'):
            conn = await pool_obj.acquire()
            release = True
        else:
            conn = pool_obj
            release = False

        try:
            for code in indices:
                cfg = INDEX_CONFIG.get(code, {"name": code, "market": "1"})
                try:
                    # ── 1. Fetch K-line from akshare ──
                    import akshare as ak
                    symbol = f"sh{code}" if cfg["market"] == "1" else f"sz{code}"
                    df = await asyncio.to_thread(ak.stock_zh_index_daily, symbol=symbol)

                    if df is None or df.empty:
                        missing.append(code)
                        continue

                    rows_written = 0
                    for _, row in df.iterrows():
                        row_date = row["date"]
                        if hasattr(row_date, "to_pydatetime"):
                            row_date = row_date.date()
                        elif hasattr(row_date, "date"):
                            row_date = row_date.date()

                        close_v = float(row["close"] or 0)
                        pre_close_v = float(row.get("pre_close", 0) or 0)
                        pct = ((close_v - pre_close_v) / pre_close_v * 100) if pre_close_v else 0.0

                        await conn.execute(
                            """INSERT INTO index_daily_kline
                               (index_code, index_name, market, trade_date, open, high, low, close, pre_close, pct_chg, volume, amount, source)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                               ON CONFLICT (index_code, market, trade_date) DO UPDATE SET
                                 index_name=$2, open=$5, high=$6, low=$7, close=$8,
                                 pre_close=$9, pct_chg=$10, volume=$11, amount=$12, updated_at=now()""",
                            code, cfg["name"], cfg["market"], row_date,
                            float(row["open"] or 0), float(row["high"] or 0),
                            float(row["low"] or 0), close_v,
                            pre_close_v, round(pct, 2),
                            float(row.get("volume", 0) or 0),
                            float(row.get("amount", 0) or 0),
                            "akshare",
                        )
                        rows_written += 1

                    if rows_written > 0:
                        collected += 1

                    # ── 2. Compute technical analysis ──
                    kline_rows = await conn.fetch(
                        """SELECT trade_date, open, high, low, close, volume, pct_chg
                           FROM index_daily_kline
                           WHERE index_code = $1 AND trade_date <= $2::date
                           ORDER BY trade_date DESC LIMIT $3""",
                        code, td, lookback_days,
                    )
                    if not kline_rows:
                        continue

                    kline_list = [dict(r) for r in reversed(kline_rows)]
                    tech = self._compute_technical(code, cfg["name"], td, kline_list)

                    await conn.execute(
                        """INSERT INTO index_technical_daily
                           (trade_date, index_code, index_name, trend_state, trend_score,
                            above_ma5, above_ma10, above_ma20, above_ma60,
                            ma5, ma10, ma20, ma60, ma_structure, support_level, resistance_level,
                            support_score, pressure_score, macd_state, volume_pattern,
                            break_support, near_pressure, risk_flags_json, diagnostics_json)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23::jsonb,$24::jsonb)
                           ON CONFLICT (trade_date, index_code) DO UPDATE SET
                             index_name=$3, trend_state=$4, trend_score=$5,
                             above_ma5=$6, above_ma10=$7, above_ma20=$8, above_ma60=$9,
                             ma5=$10, ma10=$11, ma20=$12, ma60=$13, ma_structure=$14,
                             support_level=$15, resistance_level=$16,
                             support_score=$17, pressure_score=$18, macd_state=$19,
                             volume_pattern=$20, break_support=$21, near_pressure=$22,
                             risk_flags_json=$23::jsonb, diagnostics_json=$24::jsonb,
                             updated_at=now()""",
                        td, code, cfg["name"],
                        tech["trend_state"], tech["trend_score"],
                        tech["above_ma5"], tech["above_ma10"], tech["above_ma20"], tech["above_ma60"],
                        tech["ma5"], tech["ma10"], tech["ma20"], tech["ma60"],
                        tech["ma_structure"],
                        tech["support_level"], tech["resistance_level"],
                        tech["support_score"], tech["pressure_score"],
                        tech["macd_state"], tech["volume_pattern"],
                        tech["break_support"], tech["near_pressure"],
                        json.dumps(tech.get("risk_flags", [])),
                        json.dumps(tech.get("diagnostics", {})),
                    )
                    technical += 1

                except Exception as e:
                    logger.warning(f"Index collect failed for {code}: {e}")
                    missing.append(code)
        finally:
            if release:
                await pool_obj.release(conn)

        return IndexCollectResult(
            trade_date=td.isoformat(),
            collected_count=collected,
            technical_count=technical,
            total_count=len(indices),
            missing_indices=missing,
            source="akshare",
            diagnostics={},
        )

    def _compute_technical(
        self, code: str, name: str, td: date, klines: list[dict]
    ) -> dict[str, Any]:
        """Compute technical indicators from K-line data."""
        if len(klines) < 5:
            return _empty_technical()

        closes = [_to_decimal(r["close"]) for r in klines]
        highs = [_to_decimal(r["high"]) for r in klines]
        lows = [_to_decimal(r["low"]) for r in klines]
        volumes = [_to_decimal(r.get("volume", 0)) for r in klines]

        latest = closes[-1]
        pre = closes[-2] if len(closes) >= 2 else latest

        # ── MA ──
        def _sma(values: list[Decimal], n: int) -> Decimal:
            if len(values) < n:
                return Decimal("0")
            return sum(values[-n:]) / Decimal(str(n))

        ma5 = _sma(closes, 5)
        ma10 = _sma(closes, 10)
        ma20 = _sma(closes, 20)
        ma60 = _sma(closes, 60)

        above_ma5 = latest > ma5
        above_ma10 = latest > ma10
        above_ma20 = latest > ma20
        above_ma60 = ma60 > 0 and latest > ma60

        mas_above = [above_ma5, above_ma10, above_ma20, above_ma60]
        if all(mas_above):
            ma_structure = "bullish"
        elif any(mas_above) and not all(mas_above):
            ma_structure = "mixed"
        else:
            ma_structure = "bearish"

        # ── Support / Resistance ──
        support = float(min(lows[-20:] if len(lows) >= 20 else lows))
        resistance = float(max(highs[-20:] if len(highs) >= 20 else highs))
        break_support = float(latest) < support
        near_pressure = float(latest) > float(resistance) * 0.97
        support_score = max(0.0, min(100.0, (float(latest) - support) / max(float(latest), 0.01) * 200))
        pressure_score = max(0.0, min(100.0, (resistance - float(latest)) / max(float(resistance), 0.01) * 100))

        # ── MACD ──
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        dif = ema12 - ema26
        dea = _dea(closes)  # 9-day EMA of DIF
        macd_hist = (dif - dea) * Decimal("2")

        if dif > Decimal("0"):
            macd_state = "above_zero_bullish" if macd_hist > 0 else "above_zero_weakening"
        else:
            macd_state = "below_zero_bearish" if macd_hist < 0 else "below_zero_weak_rebound"

        # ── Volume ──
        vol_5d = sum(volumes[-5:]) / Decimal("5") if len(volumes) >= 5 else Decimal("0")
        vol_20d = sum(volumes[-20:]) / Decimal("20") if len(volumes) >= 20 else Decimal("0")
        vol_ratio = float(vol_5d / vol_20d) if vol_20d > 0 else 1.0
        if vol_ratio > 2.0:
            volume_pattern = "spike_high"
        elif vol_ratio > 1.3:
            volume_pattern = "expanding"
        elif vol_ratio < 0.5:
            volume_pattern = "shrinking_significantly"
        elif vol_ratio < 0.85:
            volume_pattern = "shrinking"
        else:
            volume_pattern = "normal"

        # ── Trend ──
        trend_score = 50.0
        if above_ma20:
            trend_score += 20.0
        else:
            trend_score -= 20.0
        if float(ma5) > float(ma20):
            trend_score += 10.0
        if float(ma10) > float(ma20):
            trend_score += 10.0
        if vol_ratio > 1.3:
            trend_score += 10.0
        trend_score = max(0.0, min(100.0, trend_score))

        if above_ma20 and trend_score >= 58:
            trend_state = "bullish_trend"
        elif not above_ma20 and trend_score <= 35:
            trend_state = "bearish_trend"
        elif not above_ma20 and vol_ratio < 0.85 and near_pressure:
            trend_state = "downtrend_rebound"
        else:
            trend_state = "neutral_box"

        # ── Risk flags ──
        risk_flags = []
        if not above_ma5:
            risk_flags.append("跌破MA5")
        if not above_ma20:
            risk_flags.append("跌破MA20")
        if not above_ma60 and ma60 > 0:
            risk_flags.append("跌破MA60")
        if break_support:
            risk_flags.append("破支撑位")
        if near_pressure:
            risk_flags.append("临近压力位")
        if vol_ratio < 0.5:
            risk_flags.append("大幅缩量")
        if vol_ratio < 0.85:
            risk_flags.append("缩量")
        if trend_state == "bearish_trend":
            risk_flags.append("空头趋势")
        if trend_state == "downtrend_rebound":
            risk_flags.append("弱反抽")

        return {
            "trend_state": trend_state,
            "trend_score": round(trend_score, 1),
            "above_ma5": above_ma5,
            "above_ma10": above_ma10,
            "above_ma20": above_ma20,
            "above_ma60": above_ma60,
            "ma5": float(ma5),
            "ma10": float(ma10),
            "ma20": float(ma20),
            "ma60": float(ma60),
            "ma_structure": ma_structure,
            "support_level": round(support, 2),
            "resistance_level": round(resistance, 2),
            "support_score": round(support_score, 1),
            "pressure_score": round(pressure_score, 1),
            "macd_state": macd_state,
            "volume_pattern": volume_pattern,
            "break_support": break_support,
            "near_pressure": near_pressure,
            "risk_flags": risk_flags,
            "diagnostics": {
                "latest_close": float(latest),
                "prev_close": float(pre),
                "vol_ratio_5d": round(vol_ratio, 2),
                "lookback_bars": len(klines),
            },
        }


def _empty_technical() -> dict[str, Any]:
    return {
        "trend_state": "unknown", "trend_score": 0.0,
        "above_ma5": False, "above_ma10": False, "above_ma20": False, "above_ma60": False,
        "ma5": 0, "ma10": 0, "ma20": 0, "ma60": 0,
        "ma_structure": "unknown",
        "support_level": 0, "resistance_level": 0,
        "support_score": 0, "pressure_score": 0,
        "macd_state": "unknown", "volume_pattern": "unknown",
        "break_support": False, "near_pressure": False,
        "risk_flags": ["数据不足"],
        "diagnostics": {"error": "insufficient_data"},
    }


def _ema(values: list[Decimal], n: int) -> Decimal:
    if len(values) < n:
        return sum(values) / Decimal(str(max(len(values), 1)))
    k = Decimal("2") / Decimal(str(n + 1))
    result = sum(values[:n]) / Decimal(str(n))
    for v in values[n:]:
        result = v * k + result * (Decimal("1") - k)
    return result


def _dea(closes: list[Decimal]) -> Decimal:
    """9-period EMA of DIF values."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif_vals = []
    for i in range(max(12, 26) - 1, len(closes)):
        e12 = _ema(closes[:i+1], 12)
        e26 = _ema(closes[:i+1], 26)
        dif_vals.append(e12 - e26)
    if not dif_vals:
        return Decimal("0")
    return _ema(dif_vals, 9)
