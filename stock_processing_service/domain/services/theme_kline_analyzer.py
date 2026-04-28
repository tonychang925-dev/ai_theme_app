from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ThemeKlineResult:
    one_day_tour_kline_flag: bool
    kline_support_hold: bool
    platform_breakout_flag: bool
    platform_breakout_strength: float
    ema10: float
    ema20: float
    rsi14: float
    bb_lower: float
    close_last: float
    retrace_ratio_5d: float
    ta_backend: str


class ThemeKlineAnalyzer:
    """题材 K 线形态分析器。

    1:1 复刻生产 build_mainline_identity_registry.py
    _analyze_theme_kline_shape_open_source() (L95-199).

    输入：题材近 N 交易日涨跌幅序列（时间升序，单位 %）。
    输出：one_day_tour_kline_flag / kline_support_hold / platform_breakout_flag。
    """

    @staticmethod
    def _finite_float(value: Any, default: float = 0.0) -> float:
        try:
            v = float(value)
        except Exception:
            return default
        return v if math.isfinite(v) else default

    def analyze(self, pct_series: list[float]) -> ThemeKlineResult:
        if not pct_series or len(pct_series) < 8:
            return ThemeKlineResult(
                ta_backend="none",
                kline_support_hold=False,
                one_day_tour_kline_flag=False,
                platform_breakout_flag=False,
                platform_breakout_strength=0.0,
                ema10=0.0,
                ema20=0.0,
                rsi14=0.0,
                bb_lower=0.0,
                close_last=0.0,
                retrace_ratio_5d=0.0,
            )

        # 用涨跌幅重建题材"合成收盘价"曲线（基准100）
        closes: list[float] = []
        c = 100.0
        for p in pct_series:
            c *= max(0.01, 1.0 + float(p) / 100.0)
            closes.append(c)

        backend = "none"
        ema10 = ema20 = rsi14 = bb_lower = 0.0
        close_last = self._finite_float(closes[-1], 0.0)
        retrace_ratio_5d = 0.0
        one_day_tour_kline_flag = False
        kline_support_hold = False
        platform_breakout_flag = False
        platform_breakout_strength = 0.0

        try:
            import pandas as pd

            close_s = pd.Series(closes, dtype="float64")
            pct_s = pd.Series(pct_series, dtype="float64")

            try:
                import pandas_ta as pta

                backend = "pandas_ta"
                ema10 = self._finite_float(pta.ema(close_s, length=10).iloc[-1], close_last)
                if len(close_s) >= 20:
                    ema20 = self._finite_float(pta.ema(close_s, length=20).iloc[-1], ema10)
                else:
                    ema20 = self._finite_float(pta.ema(close_s, length=10).iloc[-1], ema10)
                rsi14 = self._finite_float(pta.rsi(close_s, length=14).iloc[-1], 50.0) if len(close_s) >= 14 else 50.0
                bb = pta.bbands(close_s, length=20, std=2.0)
                if bb is not None and "BBL_20_2.0" in bb.columns:
                    bb_lower = self._finite_float(bb["BBL_20_2.0"].iloc[-1], 0.0)
            except Exception:
                from ta.momentum import RSIIndicator
                from ta.trend import EMAIndicator
                from ta.volatility import BollingerBands

                backend = "ta"
                ema10 = self._finite_float(
                    EMAIndicator(close_s, window=10).ema_indicator().iloc[-1], close_last
                )
                ema20 = self._finite_float(
                    EMAIndicator(close_s, window=min(20, max(10, len(close_s)))).ema_indicator().iloc[-1],
                    ema10,
                )
                rsi14 = self._finite_float(
                    RSIIndicator(close_s, window=min(14, max(6, len(close_s)))).rsi().iloc[-1], 50.0
                )
                if len(close_s) >= 20:
                    bb_lower = self._finite_float(
                        BollingerBands(close_s, window=20, window_dev=2).bollinger_lband().iloc[-1], 0.0
                    )

            # ── 一日游形态：单日冲高后5日内显著回撤且失守短均 ──
            spike = float(pct_s.max())
            spike_idx = int(pct_s.idxmax())
            window_end = min(len(close_s) - 1, spike_idx + 5)
            if window_end > spike_idx and close_s.iloc[spike_idx] > 0:
                min_after = float(close_s.iloc[spike_idx : window_end + 1].min())
                retrace_ratio_5d = max(
                    0.0,
                    (float(close_s.iloc[spike_idx]) - min_after) / float(close_s.iloc[spike_idx]),
                )
            one_day_tour_kline_flag = bool(
                spike >= 7.0
                and retrace_ratio_5d >= 0.08
                and close_last < ema10 * 0.99
                and rsi14 < 48.0
            )

            # ── 支撑未破：收盘未明显跌破中期均线/布林下轨，且非极弱RSI ──
            support_floor = max(ema20 * 0.98, bb_lower * 0.97 if bb_lower > 0 else 0.0)
            kline_support_hold = bool(close_last >= support_floor and rsi14 >= 35.0)

            # ── 平台突破：近20日大区间压缩后，当前收盘有效突破前高 ──
            if len(close_s) >= 22:
                prev_high_20 = float(close_s.shift(1).rolling(20).max().iloc[-1])
                prev_low_20 = float(close_s.shift(1).rolling(20).min().iloc[-1])
                range_ratio_20 = (prev_high_20 - prev_low_20) / prev_high_20 if prev_high_20 > 0 else 0.0
                breakout_ratio = (close_last - prev_high_20) / prev_high_20 if prev_high_20 > 0 else 0.0
                platform_breakout_flag = bool(
                    range_ratio_20 <= 0.18 and breakout_ratio >= 0.01 and close_last > ema20
                )
                if platform_breakout_flag:
                    platform_breakout_strength = min(
                        100.0, breakout_ratio * 1000.0 + (0.18 - range_ratio_20) * 120.0
                    )
        except Exception:
            pass

        return ThemeKlineResult(
            ta_backend=backend,
            kline_support_hold=kline_support_hold,
            one_day_tour_kline_flag=one_day_tour_kline_flag,
            platform_breakout_flag=platform_breakout_flag,
            platform_breakout_strength=round(self._finite_float(platform_breakout_strength, 0.0), 4),
            ema10=round(self._finite_float(ema10, 0.0), 4),
            ema20=round(self._finite_float(ema20, 0.0), 4),
            rsi14=round(self._finite_float(rsi14, 0.0), 4),
            bb_lower=round(self._finite_float(bb_lower, 0.0), 4),
            close_last=round(self._finite_float(close_last, 0.0), 4),
            retrace_ratio_5d=round(self._finite_float(retrace_ratio_5d, 0.0), 4),
        )
