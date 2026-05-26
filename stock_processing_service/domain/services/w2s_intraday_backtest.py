"""BT-0/BT-1: 盘中弱转强信号回测引擎 (数据源无关).

基于历史分钟状态层 (intraday_stock_minute_state) 逐分钟回放 P1-I-4 评分器。
严禁使用未来数据 — 每个分钟点只能使用 ≤ 该分钟的数据。

验证 P1-I-4 六维评分是否具有统计预测价值。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

from stock_processing_service.domain.services.intraday_minute_state_builder import calc_vwap

logger = logging.getLogger("sps.w2s_intraday_bt")

TZ_CN = timezone(timedelta(hours=8))

# 收益窗口 (分钟)
RETURN_WINDOWS = [5, 10, 30, 60]


@dataclass
class BacktestSignal:
    minute_ts: str
    stock_id: str
    stock_name: str
    alert_level: str          # A / B / C
    intraday_score: float
    current: float
    vwap: float
    above_vwap_ratio: float
    relative_strength: float
    break_platform: bool
    amount_accel: bool
    score_breakdown: dict[str, float]
    # 未来收益
    ret_5m: float | None = None
    ret_10m: float | None = None
    ret_30m: float | None = None
    ret_60m: float | None = None
    hit_limit_up: bool = False
    fell_below_vwap: bool = False


@dataclass
class BacktestResult:
    signals: list[BacktestSignal]
    total_minutes: int
    stocks_tested: int
    by_level: dict[str, dict] = field(default_factory=dict)


class W2SIntradayBacktest:
    """盘中弱转强回测引擎。"""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 加载 ──

    async def load_minute_series(self, trade_date: str, stock_ids: list[str]) -> dict[str, list[dict]]:
        """加载指定日期所有 stock 的完整分钟序列 (按时间升序)。"""
        if not stock_ids:
            return {}
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        rows = await pool.fetch(
            """SELECT stock_id, stock_name, minute_ts,
                      open, high, low, close, current, pct_chg,
                      amount, vol, amount_delta, vol_delta,
                      vwap, above_vwap,
                      relative_strength_vs_index,
                      platform_high_30m, platform_low_30m, break_platform_30m
               FROM intraday_stock_minute_state
               WHERE trade_date = $1::date
                 AND stock_id = ANY($2::text[])
               ORDER BY stock_id, minute_ts""",
            td, stock_ids,
        )
        series: dict[str, list[dict]] = {}
        for r in rows:
            sid = r["stock_id"]
            series.setdefault(sid, []).append(dict(r))
        return series

    async def load_index_series(self, trade_date: str) -> list[dict]:
        """加载指数分钟序列。"""
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        rows = await pool.fetch(
            """SELECT minute_ts, index_code, pct_chg
               FROM intraday_index_minute_state
               WHERE trade_date = $1::date
               ORDER BY minute_ts""",
            td,
        )
        return [dict(r) for r in rows]

    async def load_candidates_for_date(self, trade_date: str) -> list[dict]:
        """加载该交易日对应的 D1 候选 (next_trade_date = trade_date)。"""
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        rows = await pool.fetch(
            """SELECT id AS candidate_id, stock_id, stock_name, theme_name,
                      candidate_type, weak_type, candidate_score
               FROM weak_to_strong_candidate_pool
               WHERE next_trade_date = $1::date
                 AND COALESCE(NULLIF(LOWER(pool_entry_type), ''), 'formal') = 'formal'""",
            td,
        )
        return [dict(r) for r in rows]

    # ── 滑动窗口聚合 (禁止未来数据) ──

    @staticmethod
    def sliding_window(series: list[dict], idx: int, n: int) -> list[dict]:
        """取 [idx-n+1, idx] 的历史窗口 (不含 idx 之后)。"""
        start = max(0, idx - n + 1)
        return series[start:idx + 1]

    @staticmethod
    def compute_platform(win: list[dict]) -> tuple[float, float]:
        """计算窗口内最高/最低价。"""
        if not win:
            return 0.0, 0.0
        hi = max(float(r.get("high") or r.get("current") or 0) for r in win)
        lo = min(float(r.get("low") or r.get("current") or 999999) for r in win)
        return hi, lo

    @staticmethod
    def compute_above_vwap_ratio(win: list[dict]) -> float:
        """窗口内 above_vwap 比例。"""
        if not win:
            return 0.0
        above = sum(1 for r in win if r.get("above_vwap"))
        return above / len(win)

    @staticmethod
    def compute_relative_strength(win: list[dict], index_series: list[dict], minute_ts: str) -> float:
        """相对指数强度 (当前分钟)。"""
        stock_pct = float(win[-1].get("pct_chg") or 0) if win else 0
        idx_pct = 0.0
        for ir in index_series:
            if str(ir.get("minute_ts") or "")[:19] == minute_ts[:19]:
                idx_pct = float(ir.get("pct_chg") or 0)
                break
        return round(stock_pct - idx_pct, 4)

    # ── 未来收益计算 ──

    @staticmethod
    def compute_forward_return(series: list[dict], idx: int, n_minutes: int) -> float | None:
        """计算 idx 之后 n 分钟的收益。"""
        future_idx = min(len(series) - 1, idx + n_minutes)
        if future_idx <= idx:
            return None
        current = float(series[idx].get("current") or 0)
        future = float(series[future_idx].get("current") or 0)
        if current <= 0:
            return None
        return round((future - current) / current * 100, 4)

    @staticmethod
    def check_limit_up(series: list[dict], idx: int, window: int = 30) -> bool:
        """检查后续 window 分钟内是否涨停 (pct_chg >= 9.8)。"""
        end = min(len(series), idx + window + 1)
        for i in range(idx + 1, end):
            pct = float(series[i].get("pct_chg") or 0)
            if pct >= 9.8:
                return True
        return False

    @staticmethod
    def check_fell_below_vwap(series: list[dict], idx: int, window: int = 10) -> bool:
        """检查信号后是否快速跌回 VWAP 下方。"""
        end = min(len(series), idx + window + 1)
        for i in range(idx + 1, end):
            if not series[i].get("above_vwap"):
                return True
        return False

    # ── 评分器 (复用 P1-I-4 逻辑，无未来数据) ──

    @staticmethod
    def score_minute(row: dict, win_5: list[dict], rel_strength: float,
                     confirm_level: str, current: float) -> tuple[float, str, dict[str, float]]:
        """逐分钟评分 (复用 P1-I-4 六维)。"""
        breakdown: dict[str, float] = {}

        # 1. above_vwap (0-25)
        above_count = sum(1 for r in win_5 if r.get("above_vwap"))
        above_ratio = above_count / len(win_5) if win_5 else 0
        vwap_score = min(25, above_ratio * 25)
        breakdown["above_vwap"] = round(vwap_score, 1)

        # 2. relative_strength (0-25)
        rel_score = 0.0
        if rel_strength > 1.0:
            rel_score = 25
        elif rel_strength > 0.5:
            rel_score = 20
        elif rel_strength > 0:
            rel_score = 12
        elif rel_strength > -0.5:
            rel_score = 5
        breakdown["rel_strength"] = round(rel_score, 1)

        # 3. platform_break (0-20)
        plat_hi = float(row.get("platform_high_30m") or 0)
        cur = float(row.get("current") or 0)
        break_plat = cur > plat_hi if plat_hi > 0 else False
        plat_score = 20 if break_plat else 0
        breakdown["platform_break"] = round(plat_score, 1)

        # 4. amount_accel (0-15)
        amt_delta = float(row.get("amount_delta") or 0)
        amt_score = 0.0
        amt_accel = False
        if win_5:
            avg_amt = sum(float(r.get("amount_delta") or 0) for r in win_5) / len(win_5)
            if avg_amt > 0 and amt_delta > avg_amt * 1.2:
                amt_accel = True
                amt_score = 15
            elif amt_delta > 0:
                amt_score = 6
        breakdown["amount_accel"] = round(amt_score, 1)

        # 5. support_safety (0-15) — 简化版
        sup_score = 15 if current > 0 else 5
        breakdown["support_safety"] = round(sup_score, 1)

        score = vwap_score + rel_score + plat_score + amt_score + sup_score
        bonus = {"A": 1.1, "B": 1.0, "C": 0.85}.get(confirm_level, 0.85)
        score = min(100, score * bonus)
        breakdown["auction_bonus_factor"] = bonus
        breakdown["total"] = round(score, 1)

        level = "X"
        if score >= 80:
            level = "A"
        elif score >= 65:
            level = "B"
        elif score >= 55:
            level = "C"

        return round(score, 1), level, breakdown

    # ── 主流程 ──

    async def run(self, trade_date: str, limit_stocks: int = 10) -> BacktestResult:
        """逐分钟回放 P1-I-4 评分。"""
        candidates = await self.load_candidates_for_date(trade_date)
        candidate_ids = [str(c.get("stock_id") or "") for c in candidates if c.get("stock_id")]

        # Fallback: 若无 D1 候选，用 strong_watch pool + 有分钟数据的股票
        if not candidate_ids:
            logger.warning("No D1 candidates for %s, falling back to strong_watch with minute data", trade_date)
            pool = await self._get_pool()
            rows = await pool.fetch(
                """SELECT DISTINCT m.stock_id
                   FROM intraday_stock_minute_state m
                   JOIN strong_stock_watch_pool sw
                     ON split_part(sw.stock_id, '.', 1) = split_part(m.stock_id, '.', 1)
                     AND COALESCE(sw.watch_status, '') != 'removed'
                   WHERE m.trade_date = $1::date
                   LIMIT $2""",
                date.fromisoformat(trade_date), limit_stocks,
            )
            candidate_ids = [str(r["stock_id"]) for r in rows]

        if not candidate_ids:
            logger.warning("No stocks with minute data found for %s", trade_date)
            return BacktestResult([], 0, 0)

        candidate_ids = candidate_ids[:limit_stocks]
        series_map = await self.load_minute_series(trade_date, candidate_ids)
        index_series = await self.load_index_series(trade_date)

        # 构建 candidate lookup
        cand_by_sid: dict[str, dict] = {}
        for c in candidates:
            cand_by_sid[str(c.get("stock_id") or "")] = c

        signals: list[BacktestSignal] = []
        total_minutes = 0

        for sid, series in series_map.items():
            if len(series) < 5:
                continue
            cand = cand_by_sid.get(sid, {})
            confirm_level = "B"  # default (no real D2 data in backtest)

            for i in range(len(series)):
                row = series[i]
                total_minutes += 1
                current = float(row.get("current") or 0)
                if current <= 0:
                    continue

                # 重新计算 VWAP (复用单位归一)
                amt_delta = float(row.get("amount_delta") or 0)
                vol_delta = float(row.get("vol_delta") or 0)
                vwap_val, vwap_mode, _, vwap_suspect = calc_vwap(amt_delta, vol_delta, current)
                row["vwap"] = vwap_val
                row["above_vwap"] = current > vwap_val

                # 滑动窗口 (仅用 ≤i 的历史)
                win_5 = self.sliding_window(series, i, 5)
                win_30 = self.sliding_window(series, i, 30)

                rel_str = self.compute_relative_strength(win_5, index_series, str(row.get("minute_ts") or ""))
                plat_hi, plat_lo = self.compute_platform(win_30)
                # 更新 platform (用滑动窗口)
                row["platform_high_30m"] = plat_hi
                row["platform_low_30m"] = plat_lo

                score, level, breakdown = self.score_minute(row, win_5, rel_str, confirm_level, current)

                if level == "X":
                    continue

                # 计算未来收益
                ret_5 = self.compute_forward_return(series, i, 5)
                ret_10 = self.compute_forward_return(series, i, 10)
                ret_30 = self.compute_forward_return(series, i, 30)
                ret_60 = self.compute_forward_return(series, i, 60)

                above_ratio = self.compute_above_vwap_ratio(win_5)

                signals.append(BacktestSignal(
                    minute_ts=str(row.get("minute_ts") or ""),
                    stock_id=sid,
                    stock_name=str(row.get("stock_name") or ""),
                    alert_level=level,
                    intraday_score=score,
                    current=current,
                    vwap=float(row.get("vwap") or 0),
                    above_vwap_ratio=round(above_ratio, 2),
                    relative_strength=round(rel_str, 4),
                    break_platform=float(row.get("platform_high_30m") or 0) > 0 and current > float(row.get("platform_high_30m") or 0),
                    amount_accel=("accel" in str(breakdown.get("amount_accel", ""))),
                    score_breakdown=breakdown,
                    ret_5m=ret_5,
                    ret_10m=ret_10,
                    ret_30m=ret_30,
                    ret_60m=ret_60,
                    hit_limit_up=self.check_limit_up(series, i),
                    fell_below_vwap=self.check_fell_below_vwap(series, i),
                ))

        # 按 level 聚合
        by_level: dict[str, dict] = {}
        for lvl in ("A", "B", "C"):
            lvl_sigs = [s for s in signals if s.alert_level == lvl]
            if not lvl_sigs:
                continue
            by_level[lvl] = {
                "count": len(lvl_sigs),
                "avg_score": round(sum(s.intraday_score for s in lvl_sigs) / len(lvl_sigs), 1),
                "win_rate_5m": round(sum(1 for s in lvl_sigs if s.ret_5m is not None and s.ret_5m > 0) / len(lvl_sigs), 3) if lvl_sigs else 0,
                "avg_ret_5m": round(sum(s.ret_5m for s in lvl_sigs if s.ret_5m is not None) / len(lvl_sigs), 4) if lvl_sigs else 0,
                "avg_ret_30m": round(sum(s.ret_30m for s in lvl_sigs if s.ret_30m is not None) / len(lvl_sigs), 4) if lvl_sigs else 0,
                "hit_limit_up_rate": round(sum(1 for s in lvl_sigs if s.hit_limit_up) / len(lvl_sigs), 3) if lvl_sigs else 0,
                "false_signal_rate": round(sum(1 for s in lvl_sigs if s.fell_below_vwap) / len(lvl_sigs), 3) if lvl_sigs else 0,
            }

        return BacktestResult(
            signals=signals,
            total_minutes=total_minutes,
            stocks_tested=len(series_map),
            by_level=by_level,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
