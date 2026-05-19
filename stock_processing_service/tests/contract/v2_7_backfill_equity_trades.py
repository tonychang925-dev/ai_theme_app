"""v2.7 — Backfill equity curves + trades for v2.0 strategies from existing signals.
Read-only: reads w2s_signal_validation_v1_1b + bars, computes equity timeline.
Does NOT regenerate candidates, does NOT modify UseCase.
"""
from __future__ import annotations

import asyncio, json, os, sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")

INITIAL_CAPITAL = 1_000_000.0
POSITION_PCT = 0.10
MAX_BUYS_PER_DAY = 3
MAX_POSITIONS = 10
SLIPPAGE = 0.0010
COMMISSION = 0.0003
STAMP_TAX = 0.0005


@dataclass
class Pos:
    sid: str; name: str; buy_date: date; buy_price: float
    shares: int; cost: float; sell_date: date | None = None
    sell_price: float = 0.0; pnl: float = 0.0; pnl_pct: float = 0.0
    hold_days: int = 0


async def run_one(c, signals: list[dict], bars: dict[date, dict], calendar: list[date],
                   hold_days: int, strategy_id: str):
    """Simplified v2.0 broker — T+1 open buy, hold N, close sell."""
    state_cash = INITIAL_CAPITAL
    positions: list[Pos] = []
    closed: list[Pos] = []
    equity_curve: list[dict] = []
    trades_out: list[dict] = []

    sig_by_date: dict[date, list] = defaultdict(list)
    for s in signals:
        nd = sorted([d for d in calendar if d > s["trade_date"]])
        if nd: sig_by_date[nd[0]].append(s)

    for act_date in sorted(sig_by_date.keys()):
        # Sells
        for pos in list(positions):
            held = len([d for d in calendar if pos.buy_date < d <= act_date])
            if held >= hold_days:
                bar = bars.get(act_date, {}).get(pos.sid)
                if not bar: continue
                sp = float(bar["close_price"])
                gross = pos.shares * sp
                proceeds = gross * (1 - SLIPPAGE - COMMISSION - STAMP_TAX)
                pos.sell_date = act_date; pos.sell_price = sp
                pos.pnl = proceeds - pos.cost
                pos.pnl_pct = pos.pnl / pos.cost if pos.cost > 0 else 0
                pos.hold_days = held
                state_cash += proceeds
                closed.append(pos)
                trades_out.append({
                    "trade_id": f"{strategy_id}_{pos.sid}_{pos.buy_date}",
                    "entry_date": pos.buy_date, "exit_date": act_date,
                    "stock_id": pos.sid, "stock_name": pos.name,
                    "entry_price": pos.buy_price, "exit_price": sp,
                    "shares": pos.shares, "cost": pos.cost, "proceeds": proceeds,
                    "pnl": pos.pnl, "return_pct": pos.pnl_pct,
                    "hold_days": held, "exit_reason": f"hold{hold_days}", "exit_rule": "fixed_hold",
                })
                positions.remove(pos)

        # Buys
        cands = sorted(sig_by_date.get(act_date, []),
                       key=lambda x: -(float(x.get("candidate_score") or 0)))
        buys = 0
        for cand in cands:
            if buys >= MAX_BUYS_PER_DAY: break
            sid = str(cand["stock_id"])
            if any(p.sid == sid for p in positions): continue
            if len(positions) >= MAX_POSITIONS: break
            bar = bars.get(act_date, {}).get(sid)
            if not bar: continue
            op = float(bar["open_price"]); pc = float(bar.get("pre_close") or 0)
            if pc <= 0: continue
            if (op - pc) / pc >= 0.098: continue
            if (op - pc) / pc > 0.07: continue
            pv = state_cash * POSITION_PCT
            if pv < 10000: continue
            bp = op * (1 + SLIPPAGE); sh = int(pv / bp / 100) * 100
            if sh < 100: continue
            cost = sh * bp * (1 + COMMISSION)
            if cost > state_cash * 0.95: continue
            state_cash -= cost
            positions.append(Pos(sid=sid, name=str(cand.get("stock_name","")),
                buy_date=act_date, buy_price=bp, shares=sh, cost=cost))
            buys += 1

        # Daily equity
        pv = sum(p.shares * float(bars.get(act_date,{}).get(p.sid,{}).get("close_price",0)) for p in positions)
        equity = state_cash + pv
        equity_curve.append({
            "date": act_date.isoformat(), "equity": round(equity, 2),
            "cash": round(state_cash, 2), "position_value": round(pv, 2),
            "active_positions": len(positions),
        })

    return equity_curve, trades_out


async def main():
    print("v2.7 — Backfilling equity curves + trades for v2.0 strategies...\n")
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # Load signals
    sig_rows = await c.execute_query("""
        SELECT v.trade_date, v.stock_id, v.stock_name,
               c.support_type, c.support_strength, c.candidate_score,
               c.weak_type, c.candidate_type, c.pool_entry_type
        FROM w2s_signal_validation_v1_1b v
        JOIN w2s_candidate_rebuild c ON v.trade_date=c.trade_date AND v.stock_id=c.stock_id
        WHERE c.rule_version='w2s_v1.0_usecase_replay' ORDER BY v.trade_date
    """)
    for s in sig_rows:
        if isinstance(s["trade_date"], str): s["trade_date"] = date.fromisoformat(s["trade_date"])
        s["support_strength"] = float(s.get("support_strength") or 0)
        s["candidate_score"] = float(s.get("candidate_score") or 0)

    all_dates = sorted({s["trade_date"] for s in sig_rows})
    min_d, max_d = all_dates[0], all_dates[-1]

    # Load bars
    bar_rows = await c.execute_query(
        """SELECT trade_date, stock_id, open_price, high_price, low_price,
                  close_price, pre_close, pct_chg, volume
           FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2
           AND source_name LIKE 'tushare%' ORDER BY trade_date, stock_id""",
        (min_d - timedelta(days=30), max_d + timedelta(days=20)))
    bars: dict[date, dict] = defaultdict(dict)
    for r in bar_rows:
        td = r["trade_date"]; bars[td][str(r["stock_id"])] = r

    cal_rows = await c.execute_query(
        "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
        (min_d - timedelta(days=30), max_d + timedelta(days=20)))
    calendar = [r["trade_date"] for r in cal_rows]

    # Run for each v2.0 strategy variant
    versions = [
        ("v2.0_all_signals_hold3d", lambda s: True, 3),
        ("v2.0_all_signals_hold5d", lambda s: True, 5),
        ("v2.0_previous_low_only_hold3d", lambda s: s.get("support_type") == "previous_low", 3),
        ("v2.0_previous_low_only_hold5d", lambda s: s.get("support_type") == "previous_low", 5),
        ("v2.0_previous_low_support80_hold3d", lambda s: s.get("support_type") == "previous_low" and s.get("support_strength", 0) >= 80, 3),
        ("v2.0_previous_low_support80_hold5d", lambda s: s.get("support_type") == "previous_low" and s.get("support_strength", 0) >= 80, 5),
    ]

    for sid, filt, hd in versions:
        filtered = [s for s in sig_rows if filt(s)]
        eq, trades = await run_one(c, filtered, bars, calendar, hd, sid)

        # Write equity
        peak = INITIAL_CAPITAL
        for pt in eq:
            eq_val = pt["equity"]
            peak = max(peak, eq_val)
            dd = (peak - eq_val) / peak if peak > 0 else 0
            raw_d = date.fromisoformat(pt["date"][:10])
            await c.execute_query("""
                INSERT INTO backtest_equity_curve (run_id, strategy_id, trade_date,
                    cash, position_value, total_equity, cumulative_return, drawdown, active_positions)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (run_id, trade_date) DO UPDATE SET
                    total_equity=EXCLUDED.total_equity, drawdown=EXCLUDED.drawdown
            """, (sid, sid, raw_d, pt["cash"], pt["position_value"], eq_val,
                  (eq_val - INITIAL_CAPITAL) / INITIAL_CAPITAL, dd, pt["active_positions"]))

        # Write trades
        for t in trades:
            td_key = (t["entry_date"], t["stock_id"])
            sig = next((s for s in sig_rows if s["trade_date"] and s["stock_id"] == t["stock_id"]), {})
            await c.execute_query("""
                INSERT INTO backtest_trade (trade_id, run_id, strategy_id, stock_id, stock_name,
                    entry_date, entry_price, exit_date, exit_price, shares, cost, proceeds,
                    pnl, return_pct, hold_days, exit_reason, exit_rule,
                    support_type, support_strength, weak_type, candidate_score, candidate_type, pool_entry_type)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
                ON CONFLICT (run_id, entry_date, stock_id) DO UPDATE SET
                    pnl=EXCLUDED.pnl, return_pct=EXCLUDED.return_pct, exit_date=EXCLUDED.exit_date
            """, (t["trade_id"], sid, sid, t["stock_id"], t["stock_name"],
                  t["entry_date"], t["entry_price"], t["exit_date"], t["exit_price"],
                  t["shares"], t["cost"], t["proceeds"],
                  t["pnl"], t["return_pct"], t["hold_days"],
                  t["exit_reason"], t["exit_rule"],
                  sig.get("support_type",""), sig.get("support_strength"),
                  sig.get("weak_type"), sig.get("candidate_score"),
                  sig.get("candidate_type"), sig.get("pool_entry_type")))

        print(f"  ✅ {sid}: equity={len(eq)}pts  trades={len(trades)}")

    # Also recompute monthly returns
    for sid, _, _ in versions:
        eq_pts = await c.execute_query(
            "SELECT trade_date, total_equity FROM backtest_equity_curve WHERE strategy_id=$1 ORDER BY trade_date", [sid])
        monthly: dict[str, list] = defaultdict(list)
        for pt in eq_pts:
            month = str(pt["trade_date"])[:7]
            monthly[month].append(float(pt["total_equity"]))
        for month, vals in monthly.items():
            ret = (vals[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL
            await c.execute_query("""
                INSERT INTO backtest_monthly_return (run_id, strategy_id, month, return_pct)
                VALUES ($1,$2,$3,$4) ON CONFLICT (run_id, month) DO UPDATE SET return_pct=EXCLUDED.return_pct
            """, (sid, sid, month, ret))

    await gw.close()
    print("\nDone — equity curves + trades backfilled for all v2.0 strategies.")


if __name__ == "__main__":
    asyncio.run(main())
