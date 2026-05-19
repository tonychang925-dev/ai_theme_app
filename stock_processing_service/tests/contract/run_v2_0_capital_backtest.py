"""
v2.0 capital backtest MVP — Daily-bar level, no intraday/auction execution.
================================================================================
Input:  w2s_signal_validation_v1_1b (verified signals from v1.1b/v1.1c)
Output: v2_0_backtest_report_*.json (isolated)

Rules:
  - Buy: T+1 open price (next trading day after signal)
  - Sell: hold 3 or 5 trading days, sell at close
  - Position: 10% per stock, max 3 buys/day, max 10 concurrent
  - Skip: limit-up open, no bar, already holding, cash < min
  - Costs: slippage 0.1% buy+sell, commission 0.03%, stamp tax 0.05%

Versions:
  - v2.0_all_signals
  - v2.0_previous_low_only
  - v2.0_previous_low_support80

Usage: python stock_processing_service/tests/contract/run_v2_0_capital_backtest.py
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

# ── Configuration ──
INITIAL_CAPITAL = 1_000_000.0
POSITION_PCT = 0.10
MAX_BUYS_PER_DAY = 3
MAX_POSITIONS = 10
SLIPPAGE = 0.0010
COMMISSION = 0.0003
STAMP_TAX = 0.0005

# ── Types ──

@dataclass
class Position:
    stock_id: str
    stock_name: str
    buy_date: date
    buy_price: float
    shares: int
    cost: float
    sell_date: date | None = None
    sell_price: float = 0.0
    sell_proceeds: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    skip_reason: str = ""


@dataclass
class BrokerState:
    cash: float = INITIAL_CAPITAL
    positions: list[Position] = field(default_factory=list)
    closed_positions: list[Position] = field(default_factory=list)
    daily_equity: list[dict] = field(default_factory=list)
    skip_stats: dict[str, int] = field(default_factory=lambda: defaultdict(int))


async def load_data(c):
    """Load signals, bars, and trading calendar."""
    # ── Signals from v1.1b validation ──
    signals = await c.execute_query("""
        SELECT v.trade_date, v.stock_id, v.stock_name,
               v.next_1d_return, v.next_3d_return, v.next_5d_return,
               v.is_win_3d, v.is_win_5d, v.loss_over_5pct,
               c.support_type, c.support_strength, c.pool_entry_type,
               c.candidate_score, c.weak_type, c.rule_version
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

    # ── Bars ──
    dates = sorted({s["trade_date"] for s in signals})
    min_d, max_d = dates[0], dates[-1]

    bar_rows = await c.execute_query(
        """SELECT trade_date, stock_id, open_price, high_price, low_price,
                  close_price, pre_close, pct_chg, volume, amount
           FROM stock_daily_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           AND source_name LIKE 'tushare%'
           ORDER BY trade_date, stock_id""",
        (min_d - timedelta(days=1), max_d + timedelta(days=20)),
    )
    bars: dict[date, dict[str, dict]] = {}
    for r in bar_rows:
        td = r["trade_date"]
        bars.setdefault(td, {})[str(r["stock_id"])] = r

    # ── Trading calendar ──
    cal_rows = await c.execute_query(
        "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
        (min_d - timedelta(days=1), max_d + timedelta(days=20)),
    )
    calendar = [r["trade_date"] for r in cal_rows]

    return signals, bars, calendar, dates


def filter_signals(signals: list[dict], version: str) -> list[dict]:
    """Filter signals by backtest version."""
    out = []
    for s in signals:
        st = s.get("support_type", "")
        ss = s.get("support_strength", 0)
        if version == "v2.0_all_signals":
            out.append(s)
        elif version == "v2.0_previous_low_only":
            if st == "previous_low":
                out.append(s)
        elif version == "v2.0_previous_low_support80":
            if st == "previous_low" and ss >= 80:
                out.append(s)
    return out


def run_backtest(signals: list[dict], bars: dict[date, dict[str, dict]],
                 calendar: list[date], hold_days: int) -> BrokerState:
    """Execute daily-bar capital backtest with T+1 open buy, hold N days sell at close."""
    state = BrokerState()
    calendar_set = set(calendar)

    # Group signals by T-day (the date when we act)
    signals_by_act_date: dict[date, list[dict]] = defaultdict(list)
    for s in signals:
        td = s["trade_date"]
        # Find next trading day for T+1 buy
        next_dates = sorted([d for d in calendar if d > td])
        if not next_dates:
            state.skip_stats["no_next_trading_day"] += 1
            continue
        act_date = next_dates[0]  # T+1
        signals_by_act_date[act_date].append(s)

    # Sort eligible action dates
    eligible_dates = sorted(signals_by_act_date.keys())

    for act_date in eligible_dates:
        # ── Process sells (positions reaching hold_days today) ──
        for pos in list(state.positions):
            if pos.sell_date is not None:
                continue
            held_days = len([d for d in calendar if pos.buy_date < d <= act_date])
            if held_days >= hold_days:
                # Sell at close today
                bar = bars.get(act_date, {}).get(pos.stock_id)
                if not bar:
                    # Can't sell — hold until we can
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
                pos.hold_days = held_days

                state.cash += proceeds
                state.closed_positions.append(pos)
                state.positions.remove(pos)

        # ── Process buys ──
        candidates = signals_by_act_date.get(act_date, [])
        # Sort by priority: previous_low first, then support_strength desc, then candidate_score desc
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

            # Already holding check
            if any(p.stock_id == sid and p.sell_date is None for p in state.positions):
                state.skip_stats["already_holding_skip"] += 1
                continue

            # Max positions check
            active_positions = [p for p in state.positions if p.sell_date is None]
            if len(active_positions) >= MAX_POSITIONS:
                state.skip_stats["max_positions_skip"] += 1
                break

            # Get T+1 bar
            bar = bars.get(act_date, {}).get(sid)
            if not bar:
                state.skip_stats["no_bar_skip"] += 1
                continue

            open_price = float(bar["open_price"])
            pre_close = float(bar.get("pre_close") or 0)
            if pre_close <= 0:
                state.skip_stats["no_pre_close_skip"] += 1
                continue

            open_pct = (open_price - pre_close) / pre_close

            # Limit-up open skip
            if open_pct >= 0.098:
                state.skip_stats["limit_up_open_skip"] += 1
                continue

            # Open too high skip (track separately)
            if open_pct > 0.07:
                state.skip_stats["open_pct_too_high_skip"] += 1
                # v2.0 MVP: skip these, can be a separate group later
                continue

            # Calculate position size
            position_value = state.cash * POSITION_PCT
            if position_value < 10000:
                state.skip_stats["cash_not_enough_skip"] += 1
                continue

            # Buy price with slippage
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

            # Execute buy
            state.cash -= total_cost

            pos = Position(
                stock_id=sid,
                stock_name=str(cand.get("stock_name", "")),
                buy_date=act_date,
                buy_price=buy_price,
                shares=shares,
                cost=total_cost,
            )
            state.positions.append(pos)
            buys_today += 1

        # ── Record daily equity ──
        active_positions = [p for p in state.positions if p.sell_date is None]
        position_value = 0.0
        for p in active_positions:
            bar = bars.get(act_date, {}).get(p.stock_id)
            if bar:
                position_value += p.shares * float(bar["close_price"])
        total_equity = state.cash + position_value

        state.daily_equity.append({
            "date": act_date.isoformat(),
            "cash": round(state.cash, 2),
            "position_value": round(position_value, 2),
            "equity": round(total_equity, 2),
            "active_positions": len(active_positions),
            "pnl_from_start": round(total_equity - INITIAL_CAPITAL, 2),
        })

    return state


def compute_metrics(state: BrokerState, hold_days: int) -> dict:
    """Compute all required backtest metrics."""
    closed = state.closed_positions

    if not closed:
        return {"status": "no_trades", "n_trades": 0}

    n = len(closed)
    wins = [p for p in closed if p.pnl > 0]
    losses = [p for p in closed if p.pnl <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n if n else 0

    total_pnl = sum(p.pnl for p in closed)
    avg_return_pct = sum(p.pnl_pct for p in closed) / n if n else 0
    avg_win = sum(p.pnl for p in wins) / n_wins if n_wins else 0
    avg_loss = sum(p.pnl for p in losses) / n_losses if n_losses else 0
    profit_factor = abs(sum(p.pnl for p in wins) / sum(p.pnl for p in losses)) if n_losses and sum(p.pnl for p in losses) != 0 else float("inf")

    max_loss = min(p.pnl for p in closed)
    avg_hold = sum(p.hold_days for p in closed) / n if n else 0

    # Consecutive losses
    max_consec_losses = 0
    cur_consec = 0
    for p in sorted(closed, key=lambda x: x.buy_date):
        if p.pnl <= 0:
            cur_consec += 1
        else:
            cur_consec = 0
        max_consec_losses = max(max_consec_losses, cur_consec)

    # Drawdown
    equity_curve = [e["equity"] for e in state.daily_equity]
    peak = equity_curve[0] if equity_curve else INITIAL_CAPITAL
    max_dd = 0.0
    max_dd_pct = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = dd / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)

    # Final metrics
    final_equity = equity_curve[-1] if equity_curve else INITIAL_CAPITAL
    total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL

    # Annualized (approximate)
    if state.daily_equity:
        first_date = date.fromisoformat(state.daily_equity[0]["date"])
        last_date = date.fromisoformat(state.daily_equity[-1]["date"])
        years = (last_date - first_date).days / 365.25
        annual_return = ((1 + total_return) ** (1 / years) - 1) if years > 0 else total_return
    else:
        years = 0
        annual_return = 0

    # Monthly returns
    monthly_returns = defaultdict(float)
    for e in state.daily_equity:
        month = e["date"][:7]
        monthly_returns[month] = (e["equity"] - INITIAL_CAPITAL) / INITIAL_CAPITAL

    # Skip summary
    skip_total = sum(state.skip_stats.values())

    return {
        "status": "ok",
        "hold_days": hold_days,
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown_amount": round(max_dd, 2),
        "max_drawdown_pct": max_dd_pct,
        "avg_return_per_trade": avg_return_pct,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_single_loss": round(max_loss, 2),
        "max_consecutive_losses": max_consec_losses,
        "avg_hold_days": round(avg_hold, 1),
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "monthly_returns": dict(monthly_returns),
        "skip_stats": dict(state.skip_stats),
        "skip_total": skip_total,
        "equity_curve": state.daily_equity,
    }


async def main():
    print(f"\n{'='*70}")
    print(f"  v2.0 CAPITAL BACKTEST MVP")
    print(f"  Mode: DAILY BAR — T+1 OPEN BUY, HOLD N DAYS")
    print(f"  Capital: {INITIAL_CAPITAL:,.0f}  |  Position: {POSITION_PCT:.0%}")
    print(f"  Max buys/day: {MAX_BUYS_PER_DAY}  |  Max positions: {MAX_POSITIONS}")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    signals, bars, calendar, dates = await load_data(c)
    print(f"Signals loaded: {len(signals)}")
    print(f"Bars loaded: {sum(len(v) for v in bars.values())} rows, {len(bars)} dates")
    print(f"Calendar dates: {len(calendar)}")
    print(f"Signal date range: {dates[0]} → {dates[-1]}")

    results = {}

    for version in ["v2.0_all_signals", "v2.0_previous_low_only", "v2.0_previous_low_support80"]:
        filtered = filter_signals(signals, version)
        print(f"\n{'─'*70}")
        print(f"  {version}: {len(filtered)} signals")

        ver_results = {}
        for hold_days in [3, 5]:
            state = run_backtest(filtered, bars, calendar, hold_days)
            metrics = compute_metrics(state, hold_days)
            ver_results[f"hold_{hold_days}d"] = metrics

            print(f"  hold_{hold_days}d:  trades={metrics.get('n_trades',0):>4}  "
                  f"return={metrics.get('total_return',0):>+.2%}  "
                  f"WR={metrics.get('win_rate',0):>.1%}  "
                  f"maxDD={metrics.get('max_drawdown_pct',0):>.1%}  "
                  f"PF={metrics.get('profit_factor',float('inf')):.2f}  "
                  f"skips={metrics.get('skip_total',0)}")

        results[version] = ver_results

    # ═══ Summary table ═══
    print(f"\n{'='*70}")
    print(f"  V2.0 BACKTEST SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Version':<32} {'Hold':>5} {'N':>4} {'Return':>8} {'Annual':>8} {'WR':>6} {'MaxDD':>6} {'PF':>6}")
    print(f"  {'─'*32} {'─'*5} {'─'*4} {'─'*8} {'─'*8} {'─'*6} {'─'*6} {'─'*6}")

    for ver in ["v2.0_all_signals", "v2.0_previous_low_only", "v2.0_previous_low_support80"]:
        for hd in [3, 5]:
            m = results[ver][f"hold_{hd}d"]
            print(f"  {ver:<32} {hd:>4}d {m.get('n_trades',0):>4} "
                  f"{m.get('total_return',0):>7.2%} {m.get('annual_return',0):>7.2%} "
                  f"{m.get('win_rate',0):>5.1%} {m.get('max_drawdown_pct',0):>5.1%} "
                  f"{m.get('profit_factor',float('inf')):>5.2f}")

    # ═══ Best version details ═══
    best = results["v2.0_previous_low_support80"]["hold_5d"]
    print(f"\n{'─'*70}")
    print(f"  BEST: v2.0_previous_low_support80 hold_5d")
    print(f"{'─'*70}")
    print(f"  Trades: {best['n_trades']}  |  Win rate: {best['win_rate']:.1%}")
    print(f"  Total return: {best['total_return']:+.2%}  |  Annual: {best['annual_return']:+.2%}")
    print(f"  Max DD: {best['max_drawdown_pct']:.1%}  |  Profit factor: {best['profit_factor']:.2f}")
    print(f"  Avg trade: {best['avg_return_per_trade']:+.2%}  |  Avg hold: {best['avg_hold_days']}d")
    print(f"  Max single loss: {best['max_single_loss']:,.0f}  |  Max consec losses: {best['max_consecutive_losses']}")
    print(f"  Skip reasons: {best['skip_stats']}")

    # ═══ Monthly returns ═══
    print(f"\n  Monthly returns:")
    for mth in sorted(best.get("monthly_returns", {}).keys()):
        print(f"    {mth}: {best['monthly_returns'][mth]:+.2%}")

    # ═══ Write to isolated table ═══
    await c.execute_query("""
        CREATE TABLE IF NOT EXISTS v2_0_backtest_results (
            run_id TEXT PRIMARY KEY,
            version TEXT, hold_days INTEGER,
            n_trades INTEGER, n_wins INTEGER, n_losses INTEGER,
            total_return DOUBLE PRECISION, annual_return DOUBLE PRECISION,
            max_drawdown_pct DOUBLE PRECISION, win_rate DOUBLE PRECISION,
            profit_factor DOUBLE PRECISION,
            avg_return_per_trade DOUBLE PRECISION,
            total_pnl DOUBLE PRECISION,
            avg_hold_days DOUBLE PRECISION,
            max_single_loss DOUBLE PRECISION,
            max_consecutive_losses INTEGER,
            initial_capital DOUBLE PRECISION,
            final_equity DOUBLE PRECISION,
            skip_stats JSONB,
            equity_curve JSONB,
            monthly_returns JSONB,
            executed_at TIMESTAMP DEFAULT now()
        )
    """)

    for ver in ["v2.0_all_signals", "v2.0_previous_low_only", "v2.0_previous_low_support80"]:
        for hd in [3, 5]:
            m = results[ver][f"hold_{hd}d"]
            run_id = f"{ver}_hold{hd}d"
            try:
                await c.execute_query("""
                    INSERT INTO v2_0_backtest_results (
                        run_id, version, hold_days,
                        n_trades, n_wins, n_losses,
                        total_return, annual_return, max_drawdown_pct,
                        win_rate, profit_factor, avg_return_per_trade,
                        total_pnl, avg_hold_days, max_single_loss,
                        max_consecutive_losses,
                        initial_capital, final_equity,
                        skip_stats, equity_curve, monthly_returns
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
                    ON CONFLICT (run_id) DO UPDATE SET
                        total_return=EXCLUDED.total_return,
                        annual_return=EXCLUDED.annual_return,
                        max_drawdown_pct=EXCLUDED.max_drawdown_pct,
                        win_rate=EXCLUDED.win_rate,
                        profit_factor=EXCLUDED.profit_factor
                """, (
                    run_id, ver, hd,
                    m.get("n_trades", 0), m.get("n_wins", 0), m.get("n_losses", 0),
                    m.get("total_return", 0), m.get("annual_return", 0), m.get("max_drawdown_pct", 0),
                    m.get("win_rate", 0), m.get("profit_factor", 0), m.get("avg_return_per_trade", 0),
                    m.get("total_pnl", 0), m.get("avg_hold_days", 0), m.get("max_single_loss", 0),
                    m.get("max_consecutive_losses", 0),
                    INITIAL_CAPITAL, m.get("final_equity", 0),
                    json.dumps(m.get("skip_stats", {})),
                    json.dumps(m.get("equity_curve", []), default=str),
                    json.dumps(m.get("monthly_returns", {}))
                ))
            except Exception as e:
                print(f"  Write error for {run_id}: {e}")

    # ═══ Full report ═══
    report = {
        "phase": "v2.0_capital_backtest_mvp",
        "executed_at": datetime.now().isoformat(),
        "config": {
            "initial_capital": INITIAL_CAPITAL,
            "position_pct": POSITION_PCT,
            "max_buys_per_day": MAX_BUYS_PER_DAY,
            "max_positions": MAX_POSITIONS,
            "slippage": SLIPPAGE,
            "commission": COMMISSION,
            "stamp_tax": STAMP_TAX,
            "signal_source": "w2s_signal_validation_v1_1b",
        },
        "all_results": {},
    }
    for ver in ["v2.0_all_signals", "v2.0_previous_low_only", "v2.0_previous_low_support80"]:
        for hd in [3, 5]:
            m = results[ver][f"hold_{hd}d"]
            report["all_results"][f"{ver}_hold{hd}d"] = {
                k: v for k, v in m.items() if k != "equity_curve"
            }

    out_path = Path(__file__).parent / f"v2_0_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")

    await gw.close()
    return report


if __name__ == "__main__":
    asyncio.run(main())
