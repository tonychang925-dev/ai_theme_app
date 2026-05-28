"""v2.8a — Parameterized Capital Backtest Runner.

Pure-engine: reads validated signals, applies trading-layer parameter filters,
runs capital backtest, writes to isolated backtest_* tables.

Does NOT:
  - Regenerate A/B/C/D candidates
  - Call StrongStockTrackingService or BuildWeakToStrongCandidateUseCase
  - Modify UseCase thresholds
  - Write to production tables
"""

from __future__ import annotations

import json, uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


@dataclass
class TradeRecord:
    trade_id: str; stock_id: str; stock_name: str
    entry_date: date; entry_price: float
    exit_date: date; exit_price: float
    shares: int; cost: float; proceeds: float
    pnl: float; return_pct: float; hold_days: int
    exit_reason: str; exit_rule: str
    support_type: str = ""; support_strength: float = 0
    weak_type: str = ""; candidate_score: float = 0
    candidate_type: str = ""; pool_entry_type: str = ""


@dataclass
class Position:
    sid: str; name: str; buy_date: date; buy_price: float
    shares: int; cost: float


class ParameterizedBacktestRunner:
    """Run a capital backtest from signal data + parameter set."""

    def __init__(self, gateway_client):
        self._c = gateway_client

    async def run(self, params: dict[str, Any], param_set_id: str | None = None) -> str:
        """Execute a backtest. Returns run_id. Writes to backtest_* tables."""
        run_id = f"lab_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # ── Extract params ──
        hold_days = int(params.get("hold_days", 5))
        position_pct = float(params.get("position_pct", 0.10))
        max_daily_buys = int(params.get("max_daily_buys", 3))
        max_positions = int(params.get("max_positions", 10))
        support_types: list[str] = params.get("support_types", [])
        if isinstance(support_types, str):
            import json as _json; support_types = _json.loads(support_types) if support_types else []
        min_support_strength = float(params.get("min_support_strength", 0))
        min_candidate_score = float(params.get("min_candidate_score", 0))
        min_watch_score = float(params.get("min_watch_score", 0))
        exit_rule = str(params.get("exit_rule", "fixed_hold"))
        slippage = float(params.get("slippage", 0.001))
        commission = float(params.get("commission", 0.0003))
        stamp_tax = float(params.get("stamp_tax", 0.0005))
        initial_capital = float(params.get("initial_capital", 1_000_000))
        signal_source = str(params.get("signal_source", "w2s_signal_validation_v1_1b"))
        source_chain = str(params.get("source_chain", "backtest_replay"))

        # ── Load signals (READ ONLY — no candidate regeneration) ──
        signals = await self._c.execute_query("""
            SELECT v.trade_date, v.stock_id, v.stock_name,
                   v.next_3d_return, v.next_5d_return, v.is_win_3d, v.is_win_5d,
                   c.support_type, c.support_strength, c.candidate_score,
                   c.weak_type, c.pool_entry_type, c.candidate_type,
                   c.rule_version
            FROM w2s_signal_validation_v1_1b v
            JOIN w2s_candidate_rebuild c ON v.trade_date=c.trade_date AND v.stock_id=c.stock_id
            WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
            ORDER BY v.trade_date
        """)
        for s in signals:
            if isinstance(s["trade_date"], str):
                s["trade_date"] = date.fromisoformat(s["trade_date"])
            s["support_strength"] = float(s.get("support_strength") or 0)
            s["candidate_score"] = float(s.get("candidate_score") or 0)
            s["watch_score"] = float(s.get("watch_score") or 0)

        # ── Apply parameter filters ──
        filtered = []
        for s in signals:
            st = s.get("support_type", "")
            ss = s["support_strength"]
            cs = s["candidate_score"]
            ws = s["watch_score"]

            if support_types and st not in support_types:
                continue
            if min_support_strength > 0 and ss < min_support_strength:
                continue
            if min_candidate_score > 0 and cs < min_candidate_score:
                continue
            if min_watch_score > 0 and ws < min_watch_score:
                continue
            filtered.append(s)

        if not filtered:
            return run_id  # empty result

        # ── Load bars ──
        all_dates = sorted({s["trade_date"] for s in filtered})
        min_d, max_d = all_dates[0], all_dates[-1]

        bar_rows = await self._c.execute_query(
            """SELECT trade_date, stock_id, open_price, high_price, low_price,
                      close_price, pre_close, pct_chg, volume
               FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2
               AND source_name LIKE 'tushare%' ORDER BY trade_date, stock_id""",
            (min_d - timedelta(days=5), max_d + timedelta(days=20)))
        bars: dict[date, dict] = defaultdict(dict)
        for r in bar_rows:
            td = r["trade_date"]; bars[td][str(r["stock_id"])] = r

        cal_rows = await self._c.execute_query(
            "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date>=$1 AND trade_date<=$2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
            (min_d - timedelta(days=5), max_d + timedelta(days=20)))
        calendar = [r["trade_date"] for r in cal_rows]

        # ── Run backtest ──
        sig_by_date: dict[date, list] = defaultdict(list)
        for s in filtered:
            nd = sorted([d for d in calendar if d > s["trade_date"]])
            if nd: sig_by_date[nd[0]].append(s)

        cash = initial_capital
        positions: list[Position] = []
        closed: list[TradeRecord] = []
        equity_curve: list[dict] = []

        for act_date in sorted(sig_by_date.keys()):
            # ── Sells ──
            for pos in list(positions):
                held = len([d for d in calendar if pos.buy_date < d <= act_date])
                should_sell = held >= hold_days  # fixed_hold for now; exit_rule variants in v2.8b
                if should_sell:
                    bar = bars.get(act_date, {}).get(pos.sid)
                    if not bar: continue
                    sp = float(bar["close_price"])
                    gross = pos.shares * sp
                    proceeds = gross * (1 - slippage - commission - stamp_tax)
                    pnl = proceeds - pos.cost
                    pnl_pct = pnl / pos.cost if pos.cost > 0 else 0

                    closed.append(TradeRecord(
                        trade_id=f"{run_id}_{pos.sid}_{pos.buy_date}",
                        stock_id=pos.sid, stock_name=pos.name,
                        entry_date=pos.buy_date, entry_price=pos.buy_price,
                        exit_date=act_date, exit_price=sp,
                        shares=pos.shares, cost=pos.cost, proceeds=proceeds,
                        pnl=pnl, return_pct=pnl_pct, hold_days=held,
                        exit_reason=f"hold{hold_days}", exit_rule=exit_rule if exit_rule == "fixed_hold" else exit_rule,
                    ))
                    cash += proceeds
                    positions.remove(pos)

            # ── Buys ──
            cands = sorted(sig_by_date.get(act_date, []),
                           key=lambda x: -(float(x.get("candidate_score") or 0)))
            buys = 0
            for cand in cands:
                if buys >= max_daily_buys: break
                sid = str(cand["stock_id"])
                if any(p.sid == sid for p in positions): continue
                if len(positions) >= max_positions: break
                bar = bars.get(act_date, {}).get(sid)
                if not bar: continue
                op = float(bar["open_price"])
                pc = float(bar.get("pre_close") or 0)
                if pc <= 0:
                    continue
                open_pct = (op - pc) / pc
                if open_pct >= 0.098:
                    continue
                if open_pct > 0.07:
                    continue
                pv = cash * position_pct
                if pv < 10000: continue
                bp = op * (1 + slippage); sh = int(pv / bp / 100) * 100
                if sh < 100: continue
                cost = sh * bp * (1 + commission)
                if cost > cash * 0.95: continue
                cash -= cost
                positions.append(Position(sid=sid, name=str(cand.get("stock_name","")),
                    buy_date=act_date, buy_price=bp, shares=sh, cost=cost))
                buys += 1

            # ── Record equity ──
            pv = sum(p.shares * float(bars.get(act_date,{}).get(p.sid,{}).get("close_price",0)) for p in positions)
            equity_curve.append({
                "date": act_date, "cash": round(cash, 2), "position_value": round(pv, 2),
                "equity": round(cash + pv, 2), "active_positions": len(positions),
            })

        # ── Compute metrics ──
        n = len(closed)
        if n == 0: return run_id

        wins = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]
        wr = len(wins) / n
        total_pnl = sum(t.pnl for t in closed)
        avg_ret = sum(t.return_pct for t in closed) / n
        pf = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else 999
        final_eq = equity_curve[-1]["equity"] if equity_curve else initial_capital
        total_return = (final_eq - initial_capital) / initial_capital
        max_single_loss = min(t.pnl for t in closed)
        avg_hold = sum(t.hold_days for t in closed) / n

        # Drawdown
        peak = initial_capital
        max_dd = 0.0
        for pt in equity_curve:
            peak = max(peak, pt["equity"])
            dd = (peak - pt["equity"]) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        name = params.get("name", f"lab_{run_id[:12]}")

        # ── Write: backtest_run ──
        await self._c.execute_query("""
            INSERT INTO backtest_run (run_id, strategy_id, strategy_name, strategy_version,
                initial_capital, final_equity, total_return, max_drawdown,
                win_rate, profit_factor, trade_count, avg_return_per_trade,
                avg_hold_days, max_single_loss, config_json,
                param_set_id, signal_source, source_chain)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,$16,$17,$18)
            ON CONFLICT (strategy_id, strategy_version) DO UPDATE SET
                run_id=EXCLUDED.run_id, total_return=EXCLUDED.total_return,
                max_drawdown=EXCLUDED.max_drawdown, win_rate=EXCLUDED.win_rate,
                profit_factor=EXCLUDED.profit_factor, trade_count=EXCLUDED.trade_count,
                config_json=EXCLUDED.config_json,
                param_set_id=EXCLUDED.param_set_id,
                signal_source=EXCLUDED.signal_source,
                source_chain=EXCLUDED.source_chain
        """, (run_id, run_id, name, "v2.8a", initial_capital, final_eq, total_return,
              max_dd, wr, pf, n, avg_ret, avg_hold, max_single_loss,
              json.dumps(params, ensure_ascii=False, default=str),
              param_set_id, signal_source, source_chain))

        # ── Write: equity curve ──
        peak2 = initial_capital
        for pt in equity_curve:
            eq = pt["equity"]; peak2 = max(peak2, eq)
            dd = (peak2 - eq) / peak2 if peak2 > 0 else 0
            await self._c.execute_query("""
                INSERT INTO backtest_equity_curve (run_id, strategy_id, trade_date,
                    cash, position_value, total_equity, cumulative_return, drawdown, active_positions)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (run_id, trade_date) DO UPDATE SET
                    total_equity=EXCLUDED.total_equity, drawdown=EXCLUDED.drawdown
            """, (run_id, run_id, pt["date"], pt["cash"], pt["position_value"], eq,
                  (eq - initial_capital) / initial_capital, dd, pt["active_positions"]))

        # ── Write: trades ──
        for t in closed:
            sig = next((s for s in signals if s["trade_date"] and s["stock_id"] == t.stock_id), {})
            await self._c.execute_query("""
                INSERT INTO backtest_trade (trade_id, run_id, strategy_id, stock_id, stock_name,
                    entry_date, entry_price, exit_date, exit_price, shares, cost, proceeds,
                    pnl, return_pct, hold_days, exit_reason, exit_rule,
                    support_type, support_strength, weak_type, candidate_score, candidate_type, pool_entry_type)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
                ON CONFLICT (run_id, entry_date, stock_id) DO UPDATE SET
                    pnl=EXCLUDED.pnl, return_pct=EXCLUDED.return_pct
            """, (t.trade_id, run_id, run_id, t.stock_id, t.stock_name,
                  t.entry_date, t.entry_price, t.exit_date, t.exit_price,
                  t.shares, t.cost, t.proceeds, t.pnl, t.return_pct, t.hold_days,
                  t.exit_reason, t.exit_rule,
                  sig.get("support_type",""), sig.get("support_strength"),
                  sig.get("weak_type"), sig.get("candidate_score"),
                  sig.get("candidate_type"), sig.get("pool_entry_type")))

        # ── Write: monthly returns ──
        monthly: dict[str, list] = defaultdict(list)
        for pt in equity_curve:
            month = str(pt["date"])[:7]
            monthly[month].append(pt["equity"])
        for month, vals in monthly.items():
            ret = (vals[-1] - initial_capital) / initial_capital
            await self._c.execute_query("""
                INSERT INTO backtest_monthly_return (run_id, strategy_id, month, return_pct)
                VALUES ($1,$2,$3,$4) ON CONFLICT (run_id, month) DO UPDATE SET return_pct=EXCLUDED.return_pct
            """, (run_id, run_id, month, ret))

        return run_id
