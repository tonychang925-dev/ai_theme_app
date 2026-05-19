"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.5 — Dynamic Exit Rules Backtest                                       ║
║  Date: 2026-05-19                                                          ║
║  Purpose: Compare dynamic exit variants vs v2.0 hold5 baseline            ║
╚══════════════════════════════════════════════════════════════════════════════╝

Exit variants:
  v2.0_prev_low_hold5             — Baseline: fixed hold 5 days
  v2.5a_support_stop              — Sell if close < support_level or close < MA10
  v2.5b_failed_repair_exit        — Sell if no yang recovery within 2 days post-buy
  v2.5c_limitup_weakopen_exit     — Sell if limit up then next day weak open < -2%
  v2.5_combo                      — All rules combined

All variants use previous_low signals only (strongest per v2.0).
Buy rules: identical to v2.0 (T+1 open, same position sizing, same filters).
Only exit rules differ.

Usage: python stock_processing_service/tests/contract/run_v2_5_dynamic_exit_backtest.py
"""

from __future__ import annotations

import asyncio, json, os, sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")

# ── Config ──
INITIAL_CAPITAL = 1_000_000.0
POSITION_PCT = 0.10
MAX_BUYS_PER_DAY = 3
MAX_POSITIONS = 10
SLIPPAGE = 0.0010
COMMISSION = 0.0003
STAMP_TAX = 0.0005

# Dynamic exit thresholds
SUPPORT_BREAK_PCT = 0.03       # close below support_level * (1 - 3%)
FAILED_REPAIR_DAYS = 2         # no yang recovery within N days
FAILED_REPAIR_RECOVERY_PCT = 0.015  # need > 1.5% up day for recovery
LIMITUP_THRESHOLD = 0.095      # >= 9.5% = limit up
WEAK_OPEN_THRESHOLD = -0.02    # next day open < -2%


# ── Types ──

@dataclass
class Position:
    stock_id: str
    stock_name: str
    buy_date: date
    buy_price: float
    shares: int
    cost: float
    support_level: float = 0.0
    support_type: str = ""
    exit_rule: str = ""
    exit_reason: str = ""
    sell_date: date | None = None
    sell_price: float = 0.0
    sell_proceeds: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    hit_limit_up: bool = False
    highest_close_pct: float = 0.0  # best return from buy_price


@dataclass
class BrokerState:
    cash: float = INITIAL_CAPITAL
    positions: list[Position] = field(default_factory=list)
    closed_positions: list[Position] = field(default_factory=list)
    daily_equity: list[dict] = field(default_factory=list)
    skip_stats: dict[str, int] = field(default_factory=lambda: defaultdict(int))


# ── Data Loading ──

async def load_data(c) -> tuple[list[dict], dict, list[date], list[date]]:
    """Load signals + bars + calendar (identical to v2.0)."""
    signals = await c.execute_query("""
        SELECT v.trade_date, v.stock_id, v.stock_name,
               v.next_3d_return, v.next_5d_return,
               v.is_win_3d, v.is_win_5d, v.loss_over_5pct,
               c.support_type, c.support_strength, c.pool_entry_type,
               c.candidate_score, c.weak_type, c.support_level
        FROM w2s_signal_validation_v1_1b v
        JOIN w2s_candidate_rebuild c ON v.trade_date=c.trade_date AND v.stock_id=c.stock_id
        WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
        ORDER BY v.trade_date, c.candidate_score DESC NULLS LAST
    """)
    for s in signals:
        td = s["trade_date"]
        if isinstance(td, str):
            s["trade_date"] = date.fromisoformat(td)
        s["support_strength"] = float(s.get("support_strength") or 0)
        s["support_level"] = float(s.get("support_level") or 0)

    dates = sorted({s["trade_date"] for s in signals})
    min_d, max_d = dates[0], dates[-1]

    bar_rows = await c.execute_query(
        """SELECT trade_date, stock_id, open_price, high_price, low_price,
                  close_price, pre_close, pct_chg, volume, amount
           FROM stock_daily_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           AND source_name LIKE 'tushare%'
           ORDER BY trade_date, stock_id""",
        (min_d - timedelta(days=30), max_d + timedelta(days=20)),
    )
    bars: dict[date, dict[str, dict]] = {}
    for r in bar_rows:
        td = r["trade_date"]
        bars.setdefault(td, {})[str(r["stock_id"])] = r

    cal_rows = await c.execute_query(
        "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
        (min_d - timedelta(days=30), max_d + timedelta(days=20)),
    )
    calendar = [r["trade_date"] for r in cal_rows]
    return signals, bars, calendar, dates


# ── Dynamic Exit Checks ──

def compute_ma10(sid: str, target_date: date, bars: dict, calendar: list[date]) -> float:
    """Compute simple MA10 close for a stock on a given date."""
    past_dates = [d for d in calendar if d <= target_date]
    if len(past_dates) < 10:
        return 0.0
    closes = []
    for d in past_dates[-10:]:
        bar = bars.get(d, {}).get(sid)
        if bar:
            closes.append(float(bar["close_price"]))
    return sum(closes) / len(closes) if len(closes) >= 8 else 0.0


def _bar_for(sid: str, dt: date, bars: dict) -> dict | None:
    return bars.get(dt, {}).get(sid)


def check_support_break(pos: Position, act_date: date, bars: dict, calendar: list[date]) -> tuple[bool, str]:
    """Check if close breached support_level or MA10."""
    bar = _bar_for(pos.stock_id, act_date, bars)
    if not bar:
        return False, ""

    close = float(bar["close_price"])

    # Rule 1: close below support_level with margin
    if pos.support_level > 0:
        if close < pos.support_level * (1 - SUPPORT_BREAK_PCT):
            return True, f"support_break:close={close:.2f}<support={pos.support_level:.2f}"

    # Rule 2: close significantly below MA10 (3% margin to avoid marginal breaks)
    ma10 = compute_ma10(pos.stock_id, act_date, bars, calendar)
    if ma10 > 0 and close < ma10 * 0.97:
        return True, f"ma10_break:close={close:.2f}<ma10={ma10:.2f}"

    return False, ""


def check_failed_repair(pos: Position, act_date: date, buy_date: date, bars: dict, calendar: list[date]) -> tuple[bool, str]:
    """Check if no yang recovery within FAILED_REPAIR_DAYS."""
    days_since_buy = len([d for d in calendar if buy_date < d <= act_date])
    if days_since_buy < FAILED_REPAIR_DAYS:
        return False, ""

    # Check if any day since buy had recovery
    holding_dates = [d for d in calendar if buy_date < d <= act_date]
    buy_bar = _bar_for(pos.stock_id, buy_date, bars)
    buy_open = float(buy_bar["open_price"]) if buy_bar else pos.buy_price
    buy_close = float(buy_bar["close_price"]) if buy_bar else pos.buy_price

    has_recovery = False
    best_pct = 0.0
    for d in holding_dates:
        bar = _bar_for(pos.stock_id, d, bars)
        if not bar:
            continue
        close = float(bar["close_price"])
        pct_from_buy_open = (close - buy_open) / buy_open
        best_pct = max(best_pct, pct_from_buy_open)
        # Recovery: close above buy day open AND positive pct_chg
        if pct_from_buy_open > 0.005 and float(bar.get("pct_chg") or 0) > FAILED_REPAIR_RECOVERY_PCT:
            has_recovery = True
            break

    # No recovery and price still below buy point
    current_bar = _bar_for(pos.stock_id, act_date, bars)
    if not current_bar:
        return False, ""

    current_close = float(current_bar["close_price"])
    still_below = current_close < buy_open * 1.005

    if not has_recovery and still_below and days_since_buy >= FAILED_REPAIR_DAYS:
        return True, f"failed_repair:{days_since_buy}d_no_yang_recovery,close={current_close:.2f}"

    return False, ""


def check_limitup_weakopen(pos: Position, act_date: date, bars: dict, calendar: list[date]) -> tuple[bool, str]:
    """If hit limit up on any prior day, check if today opens weak."""
    if not pos.hit_limit_up:
        return False, ""

    bar = _bar_for(pos.stock_id, act_date, bars)
    if not bar:
        return False, ""

    open_price = float(bar["open_price"])
    pre_close = float(bar.get("pre_close") or 0)
    if pre_close <= 0:
        return False, ""

    open_pct = (open_price - pre_close) / pre_close
    if open_pct < WEAK_OPEN_THRESHOLD:
        return True, f"limitup_weakopen:prev_day_limitup,open_pct={open_pct:.2%}"

    return False, ""


# ── Backtest Runner ──

def run_backtest(
    signals: list[dict],
    bars: dict[date, dict[str, dict]],
    calendar: list[date],
    exit_mode: str,
) -> BrokerState:
    """Run backtest with specified exit mode."""
    state = BrokerState()

    # Group signals by T+1 act_date
    signals_by_act_date: dict[date, list[dict]] = defaultdict(list)
    for s in signals:
        td = s["trade_date"]
        next_dates = sorted([d for d in calendar if d > td])
        if not next_dates:
            state.skip_stats["no_next_trading_day"] += 1
            continue
        signals_by_act_date[next_dates[0]].append(s)

    eligible_dates = sorted(signals_by_act_date.keys())

    for act_date in eligible_dates:
        # ── Process sells ──
        for pos in list(state.positions):
            if pos.sell_date is not None:
                continue

            should_sell = False
            exit_reason = ""
            exit_rule = ""

            # Determine sell based on exit_mode
            if exit_mode in ("v2.5a_support_stop", "v2.5_combo"):
                sell, reason = check_support_break(pos, act_date, bars, calendar)
                if sell:
                    should_sell = True
                    exit_reason = reason
                    exit_rule = "support_stop"

            if exit_mode in ("v2.5b_failed_repair_exit", "v2.5_combo") and not should_sell:
                sell, reason = check_failed_repair(pos, act_date, pos.buy_date, bars, calendar)
                if sell:
                    should_sell = True
                    exit_reason = reason
                    exit_rule = "failed_repair"

            if exit_mode in ("v2.5c_limitup_weakopen_exit", "v2.5_combo") and not should_sell:
                sell, reason = check_limitup_weakopen(pos, act_date, bars, calendar)
                if sell:
                    should_sell = True
                    exit_reason = reason
                    exit_rule = "limitup_weakopen"

            # Fixed hold fallback or max hold
            max_hold = 10  # max 10 days for any mode
            held_days = len([d for d in calendar if pos.buy_date < d <= act_date])

            if not should_sell:
                if exit_mode == "v2.0_prev_low_hold5" and held_days >= 5:
                    should_sell = True
                    exit_reason = "hold5_expired"
                    exit_rule = "fixed_hold5"
                elif exit_mode != "v2.0_prev_low_hold5" and held_days >= max_hold:
                    should_sell = True
                    exit_reason = f"max_hold{max_hold}_expired"
                    exit_rule = "max_hold"

            if should_sell:
                bar = _bar_for(pos.stock_id, act_date, bars)
                if not bar:
                    continue

                sell_price = float(bar["close_price"])
                gross = pos.shares * sell_price
                slip = gross * SLIPPAGE
                comm = gross * COMMISSION
                stamp = gross * STAMP_TAX
                proceeds = gross - slip - comm - stamp

                pos.sell_date = act_date
                pos.sell_price = sell_price
                pos.sell_proceeds = proceeds
                pos.pnl = proceeds - pos.cost
                pos.pnl_pct = pos.pnl / pos.cost if pos.cost > 0 else 0
                pos.hold_days = len([d for d in calendar if pos.buy_date < d <= act_date])
                pos.exit_rule = exit_rule
                pos.exit_reason = exit_reason

                state.cash += proceeds
                state.closed_positions.append(pos)
                state.positions.remove(pos)

            # Track hit_limit_up and highest_close_pct for active positions
            else:
                bar = _bar_for(pos.stock_id, act_date, bars)
                if bar:
                    close = float(bar["close_price"])
                    pct_chg = float(bar.get("pct_chg") or 0)
                    if pct_chg >= LIMITUP_THRESHOLD:
                        pos.hit_limit_up = True
                    pct_from_buy = (close - pos.buy_price) / pos.buy_price
                    pos.highest_close_pct = max(pos.highest_close_pct, pct_from_buy)

        # ── Process buys ──
        candidates = signals_by_act_date.get(act_date, [])
        candidates.sort(key=lambda x: (
            0 if x.get("support_type") == "previous_low" else 1,
            -(float(x.get("support_strength") or 0)),
            -(float(x.get("candidate_score") or 0)),
        ))

        buys_today = 0
        for cand in candidates:
            if buys_today >= MAX_BUYS_PER_DAY:
                state.skip_stats["max_daily_positions_skip"] += 1
                continue

            sid = str(cand["stock_id"])
            if any(p.stock_id == sid and p.sell_date is None for p in state.positions):
                state.skip_stats["already_holding_skip"] += 1
                continue

            active = [p for p in state.positions if p.sell_date is None]
            if len(active) >= MAX_POSITIONS:
                state.skip_stats["max_positions_skip"] += 1
                break

            bar = _bar_for(sid, act_date, bars)
            if not bar:
                state.skip_stats["no_bar_skip"] += 1
                continue

            open_price = float(bar["open_price"])
            pre_close = float(bar.get("pre_close") or 0)
            if pre_close <= 0:
                state.skip_stats["no_pre_close_skip"] += 1
                continue

            open_pct = (open_price - pre_close) / pre_close
            if open_pct >= 0.098:
                state.skip_stats["limit_up_open_skip"] += 1
                continue
            if open_pct > 0.07:
                state.skip_stats["open_pct_too_high_skip"] += 1
                continue

            position_value = state.cash * POSITION_PCT
            if position_value < 10000:
                state.skip_stats["cash_not_enough_skip"] += 1
                continue

            buy_price = open_price * (1 + SLIPPAGE)
            shares = int(position_value / buy_price / 100) * 100
            if shares < 100:
                state.skip_stats["shares_too_few_skip"] += 1
                continue

            cost = shares * buy_price
            comm = cost * COMMISSION
            total_cost = cost + comm
            if total_cost > state.cash * 0.95:
                state.skip_stats["cash_not_enough_skip"] += 1
                continue

            state.cash -= total_cost
            pos = Position(
                stock_id=sid,
                stock_name=str(cand.get("stock_name", "")),
                buy_date=act_date,
                buy_price=buy_price,
                shares=shares,
                cost=total_cost,
                support_level=float(cand.get("support_level") or 0),
                support_type=str(cand.get("support_type") or ""),
            )
            state.positions.append(pos)
            buys_today += 1

        # ── Record daily equity ──
        active = [p for p in state.positions if p.sell_date is None]
        position_value = 0.0
        for p in active:
            bar = _bar_for(p.stock_id, act_date, bars)
            if bar:
                position_value += p.shares * float(bar["close_price"])
        total_equity = state.cash + position_value

        state.daily_equity.append({
            "date": act_date.isoformat(),
            "cash": round(state.cash, 2),
            "position_value": round(position_value, 2),
            "equity": round(total_equity, 2),
            "active_positions": len(active),
            "pnl_from_start": round(total_equity - INITIAL_CAPITAL, 2),
        })

    return state


# ── Metrics ──

def compute_metrics(state: BrokerState, exit_mode: str, hold_days: int = 5) -> dict:
    closed = state.closed_positions
    if not closed:
        return {"status": "no_trades", "exit_mode": exit_mode, "n_trades": 0}

    n = len(closed)
    wins = [p for p in closed if p.pnl > 0]
    losses = [p for p in closed if p.pnl <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n if n else 0

    total_pnl = sum(p.pnl for p in closed)
    avg_return = sum(p.pnl_pct for p in closed) / n if n else 0
    avg_win = sum(p.pnl for p in wins) / n_wins if n_wins else 0
    avg_loss = sum(p.pnl for p in losses) / n_losses if n_losses else 0
    pf = abs(sum(p.pnl for p in wins) / sum(p.pnl for p in losses)) if n_losses and sum(p.pnl for p in losses) != 0 else float("inf")

    max_loss = min(p.pnl for p in closed)
    avg_hold = sum(p.hold_days for p in closed) / n if n else 0

    # Exit reason distribution
    exit_reasons: dict[str, int] = defaultdict(int)
    for p in closed:
        reason = p.exit_reason or "unknown"
        exit_reasons[reason] += 1

    # Consecutive losses
    max_cl = 0
    cur = 0
    for p in sorted(closed, key=lambda x: x.buy_date):
        cur = cur + 1 if p.pnl <= 0 else 0
        max_cl = max(max_cl, cur)

    # Drawdown
    equity_curve = [e["equity"] for e in state.daily_equity]
    peak = equity_curve[0] if equity_curve else INITIAL_CAPITAL
    max_dd_amt = 0.0
    max_dd_pct = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = peak - eq
        dd_pct = dd / peak if peak > 0 else 0
        max_dd_amt = max(max_dd_amt, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)

    final_equity = equity_curve[-1] if equity_curve else INITIAL_CAPITAL
    total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL

    if state.daily_equity:
        first_date = date.fromisoformat(state.daily_equity[0]["date"])
        last_date = date.fromisoformat(state.daily_equity[-1]["date"])
        years = max(0.01, (last_date - first_date).days / 365.25)
        annual_return = ((1 + total_return) ** (1 / years) - 1) if years > 0 else total_return
    else:
        years = 0
        annual_return = 0

    monthly_returns = defaultdict(float)
    for e in state.daily_equity:
        month = e["date"][:7]
        monthly_returns[month] = (e["equity"] - INITIAL_CAPITAL) / INITIAL_CAPITAL

    return {
        "status": "ok",
        "exit_mode": exit_mode,
        "hold_days": hold_days,
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "max_drawdown_amount": round(max_dd_amt, 2),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "avg_return_per_trade": round(avg_return, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_single_loss": round(max_loss, 2),
        "max_consecutive_losses": max_cl,
        "avg_hold_days": round(avg_hold, 1),
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "monthly_returns": dict(monthly_returns),
        "skip_stats": dict(state.skip_stats),
        "exit_reason_distribution": dict(exit_reasons),
        "equity_curve": state.daily_equity[:10],
    }


# ── Main ──

async def main():
    print(f"\n{'='*80}")
    print(f"  v2.5 DYNAMIC EXIT RULES BACKTEST")
    print(f"  Baseline: v2.0_prev_low_hold5  |  Signal: previous_low only")
    print(f"{'='*80}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # Load data
    signals, bars, calendar, dates = await load_data(c)

    # Filter to previous_low only (strongest subset per v2.0)
    prev_low_signals = [s for s in signals if s.get("support_type") == "previous_low"]
    print(f"  All signals: {len(signals)}")
    print(f"  previous_low signals: {len(prev_low_signals)}")
    print(f"  Bar dates: {len(bars)}  |  Calendar: {len(calendar)} days\n")

    exit_modes = [
        "v2.0_prev_low_hold5",
        "v2.5a_support_stop",
        "v2.5b_failed_repair_exit",
        "v2.5c_limitup_weakopen_exit",
        "v2.5_combo",
    ]

    results: list[dict] = []

    for mode in exit_modes:
        print(f"  Running {mode}...")
        state = run_backtest(prev_low_signals, bars, calendar, exit_mode=mode)
        metrics = compute_metrics(state, exit_mode=mode, hold_days=5 if mode == "v2.0_prev_low_hold5" else 0)
        results.append(metrics)

        n = metrics.get("n_trades", 0)
        wr = metrics.get("win_rate", 0)
        tr = metrics.get("total_return", 0)
        mdd = metrics.get("max_drawdown_pct", 0)
        pf = metrics.get("profit_factor", 0)
        avg_hold = metrics.get("avg_hold_days", 0)
        print(f"    trades={n}  WR={wr:.1%}  return={tr:+.2%}  MaxDD={mdd:.1%}  PF={pf}  avg_hold={avg_hold}d")

    # ── Print comparison table ──
    print(f"\n{'─'*80}")
    print(f"  COMPARISON TABLE")
    print(f"{'─'*80}")
    header = f"  {'Exit Mode':<35} {'Trades':>6} {'WR':>7} {'Return':>9} {'MaxDD':>7} {'PF':>7} {'AvgHold':>8} {'MaxLoss':>10}"
    print(header)
    print(f"  {'─'*80}")

    baseline = results[0] if results else {}
    for m in results:
        mode = m["exit_mode"]
        n = m.get("n_trades", 0)
        wr = m.get("win_rate", 0)
        tr = m.get("total_return", 0)
        mdd = m.get("max_drawdown_pct", 0)
        pf = m.get("profit_factor", "∞")
        ah = m.get("avg_hold_days", 0)
        ml = m.get("max_single_loss", 0)

        # Delta markers vs baseline
        wr_delta = ""
        tr_delta = ""
        mdd_delta = ""
        if mode != "v2.0_prev_low_hold5" and baseline.get("n_trades", 0) > 0:
            wr_delta = f" {'↑' if wr > baseline['win_rate'] else '↓'}{abs(wr - baseline['win_rate']):.1%}"
            tr_delta = f" {'↑' if tr > baseline['total_return'] else '↓'}{abs(tr - baseline['total_return']):.2%}"
            mdd_delta = f" {'↓' if mdd < baseline['max_drawdown_pct'] else '↑'}{abs(mdd - baseline['max_drawdown_pct']):.1%}"

        pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else str(pf)
        print(f"  {mode:<35} {n:>6} {wr:>6.1%}{wr_delta:<8} {tr:>8.2%}{tr_delta:<10} {mdd:>6.1%}{mdd_delta:<8} {pf_str:>7} {ah:>7.1f}d {ml:>9.0f}")

    # ── Print exit reason distribution for combo ──
    for m in results:
        if m["exit_mode"] == "v2.5_combo":
            exit_dist = m.get("exit_reason_distribution", {})
            if exit_dist:
                print(f"\n  v2.5_combo exit reason distribution:")
                for reason, cnt in sorted(exit_dist.items(), key=lambda x: -x[1]):
                    print(f"    {reason}: {cnt}")

    # ── Save report ──
    report = {
        "phase": "v2.5_dynamic_exit_backtest",
        "timestamp": datetime.now().isoformat(),
        "signal_set": "previous_low_only",
        "signal_count": len(prev_low_signals),
        "exit_modes": results,
        "comparison_note": "All buy rules identical to v2.0. Only exit rules differ.",
    }

    out_path = Path(__file__).parent / f"v2_5_dynamic_exit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")

    await gw.close()
    return report


if __name__ == "__main__":
    asyncio.run(main())
