"""M4d: THS EPS forecast client (via akshare).

akshare handles THS auth/cookies internally.  Rate-limited
at the caller level via M3 governance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import akshare as ak


SOURCE_NAME = "ths"
EPS_ENDPOINT = "eps_forecast"


@dataclass(frozen=True)
class EpsForecastResult:
    stock_code: str
    stock_name: str
    year: int
    eps_mean: float | None
    eps_min: float | None
    eps_max: float | None
    analyst_count: int
    industry_avg_eps: float | None
    source_trace_id: str


class ThsEpsClient:
    """THS EPS forecast client — wraps akshare.stock_profit_forecast_ths."""

    def __init__(self, *, source_name: str = SOURCE_NAME) -> None:
        self._source_name = source_name

    async def fetch_forecast(
        self, stock_code: str, trade_date: date, stock_name: str = "",
    ) -> list[EpsForecastResult]:
        """Fetch EPS forecast for a stock. Runs in thread (akshare is sync)."""
        import asyncio

        td_str = trade_date.isoformat()
        try:
            df = await asyncio.to_thread(
                ak.stock_profit_forecast_ths, symbol=stock_code,
            )
        except Exception:
            return []

        if df is None or df.empty:
            return []

        results: list[EpsForecastResult] = []
        for _, row in df.iterrows():
            try:
                year = int(row.get("年度") or 0)
                if year < 2026:
                    continue
                eps_mean = _safe_float(row.get("均值"))
                analysts = int(row.get("预测机构数") or 0)
                results.append(EpsForecastResult(
                    stock_code=stock_code,
                    stock_name=stock_name or str(row.get("股票简称", stock_code)),
                    year=year,
                    eps_mean=eps_mean,
                    eps_min=_safe_float(row.get("最小值")),
                    eps_max=_safe_float(row.get("最大值")),
                    analyst_count=analysts,
                    industry_avg_eps=_safe_float(row.get("行业平均数")),
                    source_trace_id=f"ths_eps:{stock_code}:{year}:{td_str}",
                ))
            except (ValueError, TypeError, KeyError):
                continue
        return results


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
