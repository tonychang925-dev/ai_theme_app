"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.6 — Pattern/Volume Enhanced Backtest                                  ║
║  Date: 2026-05-19                                                          ║
║  Purpose: Compare v2.0 baseline vs pattern-enhanced filters               ║
║  Does NOT modify frozen v2.0 ReadPorts.                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

Versions:
  v2.0_prev_low_hold5          — Baseline (unchanged)
  v2.6_high_vol_unbroken       — Only candidates with 高量不破
  v2.6_good_bad_limit_up       — Only bad_limit_up with quality=good
  v2.6_shrink_pullback         — Only 缩量回踩 candidates
  v2.6_enhanced_combo          — 高量不破 + 缩量回踩 + good_烂板

Usage: python stock_processing_service/tests/contract/run_v2_6_pattern_enhanced_backtest.py
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

# Reuse v2.0 broker config
INITIAL_CAPITAL = 1_000_000.0
POSITION_PCT = 0.10
MAX_BUYS_PER_DAY = 3
MAX_POSITIONS = 10
SLIPPAGE = 0.0010
COMMISSION = 0.0003
STAMP_TAX = 0.0005
HOLD_DAYS = 5


@dataclass
class Pos:
    sid: str; name: str; buy_date: date; buy_price: float
    shares: int; cost: float; sell_date: date | None = None
    sell_price: float = 0.0; pnl: float = 0.0; pnl_pct: float = 0.0
    hold_days: int = 0


@dataclass
class State:
    cash: float = INITIAL_CAPITAL
    positions: list[Pos] = field(default_factory=list)
    closed: list[Pos] = field(default_factory=list)
    equity: list[dict] = field(default_factory=list)
    skips: dict[str, int] = field(default_factory=lambda: defaultdict(int))


async def main():
    print(f"\n{'='*80}")
    print(f"  v2.6 — PATTERN ENHANCED BACKTEST")
    print(f"  Approach: Compute enhanced patterns → filter signals → backtest")
    print(f"{'='*80}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ── Import detector ──
    from stock_processing_service.domain.services.enhanced_pattern_detector import (
        EnhancedPatternDetector, VolumeBar,
    )
    detector = EnhancedPatternDetector()

    # ── Load v2.0 signals ──
    signals = await c.execute_query("""
        SELECT v.trade_date, v.stock_id, v.stock_name,
               v.next_3d_return, v.next_5d_return, v.is_win_3d, v.is_win_5d,
               c.support_type, c.support_strength, c.candidate_score,
               c.weak_type, c.pool_entry_type, c.support_level
        FROM w2s_signal_validation_v1_1b v
        JOIN w2s_candidate_rebuild c ON v.trade_date=c.trade_date AND v.stock_id=c.stock_id
        WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
        ORDER BY v.trade_date, c.candidate_score DESC
    """)
    for s in signals:
        if isinstance(s["trade_date"], str):
            s["trade_date"] = date.fromisoformat(s["trade_date"])
        s["support_strength"] = float(s.get("support_strength") or 0)
        s["support_level"] = float(s.get("support_level") or 0)

    dates = sorted({s["trade_date"] for s in signals})
    min_d, max_d = dates[0], dates[-1]

    # ── Load bars ──
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
        if isinstance(td, str): td = date.fromisoformat(td)
        bars.setdefault(td, {})[str(r["stock_id"])] = r

    cal_rows = await c.execute_query(
        """SELECT DISTINCT trade_date FROM stock_daily_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           AND source_name LIKE 'tushare%' ORDER BY trade_date""",
        (min_d - timedelta(days=30), max_d + timedelta(days=20)),
    )
    calendar = [r["trade_date"] if isinstance(r["trade_date"], date) else date.fromisoformat(str(r["trade_date"]))
                for r in cal_rows]
    bar_dates = sorted(bars.keys())

    print(f"  Signals: {len(signals)}  |  Bar dates: {len(bar_dates)}  |  Calendar: {len(calendar)}")

    # ── Compute enhanced patterns for each signal ──
    pattern_cache: dict[tuple[date, str], dict] = {}

    for s in signals:
        td = s["trade_date"]
        sid = str(s["stock_id"])
        bar = bars.get(td, {}).get(sid)
        if not bar:
            continue

        # Build history (up to 30 days before trade_date)
        hist = []
        for d in sorted(bar_dates):
            if d >= td: break
            b = bars.get(d, {}).get(sid)
            if b:
                hist.append(VolumeBar(
                    trade_date=d,
                    volume=float(b.get("volume") or 0),
                    high=float(b.get("high_price") or 0),
                    low=float(b.get("low_price") or 0),
                    close=float(b.get("close_price") or 0),
                    open=float(b.get("open_price") or 0),
                    pre_close=float(b.get("pre_close") or 0),
                    pct_chg=float(b.get("pct_chg") or 0),
                ))
        hist = hist[-30:]

        cur = VolumeBar(
            trade_date=td,
            volume=float(bar.get("volume") or 0),
            high=float(bar.get("high_price") or 0),
            low=float(bar.get("low_price") or 0),
            close=float(bar.get("close_price") or 0),
            open=float(bar.get("open_price") or 0),
            pre_close=float(bar.get("pre_close") or 0),
            pct_chg=float(bar.get("pct_chg") or 0),
        )

        result = detector.detect(
            sid, cur, hist,
            support_level=s["support_level"],
            support_type=str(s.get("support_type") or ""),
            is_bad_limit_up=(s.get("weak_type") == "bad_limit_up"),
            prev_day_limit_up=bool(float(bar.get("pct_chg") or 0) >= 9.5),
        )
        pattern_cache[(td, sid)] = {
            "high_volume_unbroken": result.high_volume_unbroken,
            "double_volume_not_pierced": result.double_volume_not_pierced,
            "pullback_status": result.pullback_status,
            "volume_pattern_status": result.volume_pattern_status,
            "breakout_status": result.breakout_status,
            "bad_limit_up_quality": result.bad_limit_up_quality,
            "pattern_labels": result.pattern_labels,
            "prior_swing_high": result.prior_swing_high,
        }

    # ── Print pattern coverage ──
    total = len(pattern_cache)
    hv_unbroken = sum(1 for v in pattern_cache.values() if v["high_volume_unbroken"])
    dv_not_pierced = sum(1 for v in pattern_cache.values() if v["double_volume_not_pierced"])
    shrink_pb = sum(1 for v in pattern_cache.values() if v["pullback_status"] == "缩量回踩")
    good_blu = sum(1 for v in pattern_cache.values() if v["bad_limit_up_quality"] == "good")
    ok_blu = sum(1 for v in pattern_cache.values() if v["bad_limit_up_quality"] in ("good", "ok"))

    print(f"\n  Pattern coverage on {total} candidate-date pairs:")
    print(f"    高量不破:        {hv_unbroken} ({hv_unbroken/total*100:.1f}%)")
    print(f"    倍量不穿:        {dv_not_pierced} ({dv_not_pierced/total*100:.1f}%)")
    print(f"    缩量回踩:        {shrink_pb} ({shrink_pb/total*100:.1f}%)")
    print(f"    烂而不弱(good):  {good_blu} ({good_blu/total*100:.1f}%)")
    print(f"    烂板ok+:         {ok_blu} ({ok_blu/total*100:.1f}%)")

    # ── Define signal filters ──
    def filter_signals(base_signals, version):
        out = []
        for s in base_signals:
            st = s.get("support_type", "")
            ss = s.get("support_strength", 0)
            td = s["trade_date"]
            sid = str(s["stock_id"])
            pat = pattern_cache.get((td, sid), {})

            # Always require previous_low (strongest per v2.0)
            if st != "previous_low":
                continue

            if version == "v2.0_prev_low_hold5":
                out.append(s)
            elif version == "v2.6_high_vol_unbroken":
                if pat.get("high_volume_unbroken"): out.append(s)
            elif version == "v2.6_shrink_pullback":
                if pat.get("pullback_status") == "缩量回踩": out.append(s)
            elif version == "v2.6_good_bad_limit_up":
                if pat.get("bad_limit_up_quality") == "good": out.append(s)
            elif version == "v2.6_hvu_prev_low_s80":
                if pat.get("high_volume_unbroken") and st == "previous_low" and ss >= 80:
                    out.append(s)
            elif version == "v2.6_hvu_support80":
                if pat.get("high_volume_unbroken") and ss >= 80:
                    out.append(s)
        return out

    # ── Run backtests ──
    versions = [
        "v2.0_prev_low_hold5",
        "v2.6_high_vol_unbroken",
        "v2.6_hvu_prev_low_s80",     # 高量不破 + previous_low + support_strength >= 80
        "v2.6_hvu_support80",        # 高量不破 + support_strength >= 80 (any support_type)
    ]

    results = []

    for ver in versions:
        filtered = filter_signals(signals, ver)
        if not filtered:
            results.append({"version": ver, "n_signals": 0, "n_trades": 0, "status": "empty"})
            continue

        # Run backtest (simplified v2.0 broker)
        state = State()
        sig_by_date: dict[date, list] = defaultdict(list)
        for s in filtered:
            next_dates = sorted([d for d in calendar if d > s["trade_date"]])
            if next_dates:
                sig_by_date[next_dates[0]].append(s)

        for act_date in sorted(sig_by_date.keys()):
            # Sells
            for pos in list(state.positions):
                if pos.sell_date: continue
                held = len([d for d in calendar if pos.buy_date < d <= act_date])
                if held >= HOLD_DAYS:
                    bar = bars.get(act_date, {}).get(pos.sid)
                    if not bar: continue
                    sell_p = float(bar["close_price"])
                    gross = pos.shares * sell_p
                    proceeds = gross * (1 - SLIPPAGE - COMMISSION - STAMP_TAX)
                    pos.sell_date = act_date; pos.sell_price = sell_p
                    pos.pnl = proceeds - pos.cost
                    pos.pnl_pct = pos.pnl / pos.cost if pos.cost > 0 else 0
                    pos.hold_days = held
                    state.cash += proceeds
                    state.closed.append(pos)
                    state.positions.remove(pos)

            # Buys
            cands = sorted(sig_by_date.get(act_date, []),
                           key=lambda x: -(float(x.get("candidate_score") or 0)))
            buys = 0
            for cand in cands:
                if buys >= MAX_BUYS_PER_DAY: break
                sid = str(cand["stock_id"])
                if any(p.sid == sid and not p.sell_date for p in state.positions): continue
                if len([p for p in state.positions if not p.sell_date]) >= MAX_POSITIONS: break

                bar = bars.get(act_date, {}).get(sid)
                if not bar: continue
                op = float(bar["open_price"])
                pc = float(bar.get("pre_close") or 0)
                if pc <= 0: continue
                if (op - pc) / pc >= 0.098: continue
                if (op - pc) / pc > 0.07: continue

                pos_val = state.cash * POSITION_PCT
                if pos_val < 10000: continue
                bp = op * (1 + SLIPPAGE)
                sh = int(pos_val / bp / 100) * 100
                if sh < 100: continue
                cost = sh * bp * (1 + COMMISSION)
                if cost > state.cash * 0.95: continue
                state.cash -= cost
                state.positions.append(Pos(sid=sid, name=str(cand.get("stock_name","")),
                    buy_date=act_date, buy_price=bp, shares=sh, cost=cost))
                buys += 1

            # Record equity
            active = [p for p in state.positions if not p.sell_date]
            pv = sum(p.shares * float(bars.get(act_date,{}).get(p.sid,{}).get("close_price",0))
                     for p in active)
            state.equity.append({"date": act_date.isoformat(), "equity": round(state.cash + pv, 2)})

        # Metrics
        closed = state.closed
        if not closed:
            results.append({"version": ver, "n_signals": len(filtered), "n_trades": 0, "status": "no_trades"})
            continue

        n = len(closed)
        wins = [p for p in closed if p.pnl > 0]
        losses = [p for p in closed if p.pnl <= 0]
        wr = len(wins) / n
        total_pnl = sum(p.pnl for p in closed)
        avg_ret = sum(p.pnl_pct for p in closed) / n if n else 0
        pf = abs(sum(p.pnl for p in wins) / sum(p.pnl for p in losses)) if losses and sum(p.pnl for p in losses) != 0 else float("inf")
        final_eq = state.equity[-1]["equity"] if state.equity else INITIAL_CAPITAL
        total_return = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL

        peak = state.equity[0]["equity"] if state.equity else INITIAL_CAPITAL
        max_dd = 0.0
        for e in state.equity:
            peak = max(peak, e["equity"])
            dd = (peak - e["equity"]) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        results.append({
            "version": ver,
            "n_signals": len(filtered),
            "n_trades": n,
            "win_rate": round(wr, 4),
            "profit_factor": round(pf, 2) if pf != float("inf") else None,
            "total_return": round(total_return, 4),
            "max_drawdown": round(max_dd, 4),
            "avg_return": round(avg_ret, 4),
            "total_pnl": round(total_pnl, 2),
            "final_equity": round(final_eq, 2),
        })

    # ── Comparison table ──
    print(f"\n{'─'*80}")
    print(f"  COMPARISON: v2.0 baseline vs v2.6 pattern-enhanced")
    print(f"{'─'*80}")
    print(f"  {'Version':<30} {'Signals':>7} {'Trades':>6} {'WR':>7} {'Return':>9} {'MaxDD':>7} {'PF':>7}")
    print(f"  {'─'*80}")

    baseline = results[0] if results else {}
    for m in results:
        ver = m["version"]
        ns = m.get("n_signals", 0)
        nt = m.get("n_trades", 0)
        wr = m.get("win_rate", 0)
        tr = m.get("total_return", 0)
        dd = m.get("max_drawdown", 0)
        pf = m.get("profit_factor", "—")
        pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else str(pf)

        # Deltas
        wr_d = ""; tr_d = ""; dd_d = ""
        if ver != "v2.0_prev_low_hold5" and baseline.get("n_trades", 0) > 0:
            wr_d = f" {'↑' if wr > baseline['win_rate'] else '↓'}{abs(wr - baseline['win_rate']):.1%}"
            tr_d = f" {'↑' if tr > baseline['total_return'] else '↓'}{abs(tr - baseline['total_return']):.2%}"
            dd_d = f" {'↓' if dd < baseline['max_drawdown'] else '↑'}{abs(dd - baseline['max_drawdown']):.1%}"

        print(f"  {ver:<30} {ns:>7} {nt:>6} {wr:>6.1%}{wr_d:<10} {tr:>8.2%}{tr_d:<12} {dd:>6.1%}{dd_d:<10} {pf_str:>7}")

    # Save
    report = {
        "phase": "v2.6_pattern_enhanced_backtest",
        "timestamp": datetime.now().isoformat(),
        "pattern_coverage": {
            "total": total, "high_vol_unbroken": hv_unbroken,
            "double_vol_not_pierced": dv_not_pierced,
            "shrink_pullback": shrink_pb, "good_bad_limit_up": good_blu,
        },
        "results": results,
    }
    out_path = Path(__file__).parent / f"v2_6_pattern_enhanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")
    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
