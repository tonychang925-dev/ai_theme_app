"""
v2.7 — Persist existing v2.0/v2.5 JSON results into backtest_* dashboard tables.
"""
from __future__ import annotations

import asyncio, json, os, sys
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")
CONTRACT_DIR = Path(__file__).parent


def _parse_date(v) -> date | None:
    if isinstance(v, date): return v
    if isinstance(v, str):
        try: return date.fromisoformat(v[:10])
        except: pass
    return None


async def persist_run(c, run_id: str, strategy_id: str, name: str, ver: str, m: dict):
    await c.execute_query("""
        INSERT INTO backtest_run (run_id, strategy_id, strategy_name, strategy_version,
            initial_capital, final_equity, total_return, max_drawdown,
            win_rate, profit_factor, trade_count, avg_return_per_trade,
            avg_hold_days, max_single_loss, max_consecutive_losses,
            config_json, skip_stats_json)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb,$17::jsonb)
        ON CONFLICT (strategy_id, strategy_version) DO UPDATE SET
            run_id=EXCLUDED.run_id, total_return=EXCLUDED.total_return,
            max_drawdown=EXCLUDED.max_drawdown, win_rate=EXCLUDED.win_rate,
            profit_factor=EXCLUDED.profit_factor, trade_count=EXCLUDED.trade_count,
            final_equity=EXCLUDED.final_equity
    """, (run_id, strategy_id, name, ver,
          m.get("initial_capital", 1000000),
          m.get("final_equity", 0),
          m.get("total_return", 0),
          m.get("max_drawdown_pct", m.get("max_drawdown", 0)),
          m.get("win_rate", 0),
          m.get("profit_factor"),
          m.get("n_trades", 0),
          m.get("avg_return_per_trade", 0),
          m.get("avg_hold_days", 0),
          m.get("max_single_loss", 0),
          m.get("max_consecutive_losses", 0),
          json.dumps({}),
          json.dumps(m.get("skip_stats", {}))))


async def persist_equity(c, run_id: str, strategy_id: str, curve: list[dict]):
    if not curve: return
    peak = curve[0].get("equity", 1000000) if curve else 1000000
    for pt in curve:
        raw_date = pt.get("date", "")
        if isinstance(raw_date, str):
            raw_date = date.fromisoformat(raw_date[:10])
        eq = float(pt.get("equity", 0))
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0
        await c.execute_query("""
            INSERT INTO backtest_equity_curve (run_id, strategy_id, trade_date,
                cash, position_value, total_equity, cumulative_return, drawdown, active_positions)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (run_id, trade_date) DO NOTHING
        """, (run_id, strategy_id, raw_date,
              pt.get("cash", 0), pt.get("position_value", 0), eq,
              (eq - 1000000) / 1000000, dd, pt.get("active_positions", 0)))


async def persist_monthly(c, run_id: str, strategy_id: str, monthly: dict):
    for month, ret in monthly.items():
        await c.execute_query("""
            INSERT INTO backtest_monthly_return (run_id, strategy_id, month, return_pct)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (run_id, month) DO UPDATE SET return_pct=EXCLUDED.return_pct
        """, (run_id, strategy_id, month, ret))


async def main():
    print("v2.7 — Persisting backtest results...\n")
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ── v2.0 JSON ──
    v20_file = CONTRACT_DIR / "v2_0_backtest_20260519_125607.json"
    if v20_file.exists():
        data = json.loads(v20_file.read_text())
        for ver_name, metrics in data.get("all_results", {}).items():
            if metrics.get("status") != "ok": continue
            # e.g. ver_name = "v2.0_previous_low_only_hold5d"
            run_id = ver_name
            await persist_run(c, run_id, ver_name, ver_name, "v2.0", metrics)
            eq = metrics.get("equity_curve", [])
            if eq:
                await persist_equity(c, run_id, ver_name, eq)
            monthly = metrics.get("monthly_returns", {})
            if monthly:
                await persist_monthly(c, run_id, ver_name, monthly)
            print(f"  ✅ v2.0 {ver_name}: trades={metrics.get('n_trades',0)}, return={metrics.get('total_return',0):.2%}")
    else:
        print("  ⚠ v2.0 JSON not found")

    # ── v2.5 JSON ──
    v25_files = sorted(CONTRACT_DIR.glob("v2_5_dynamic_exit_*.json"), reverse=True)
    if v25_files:
        data = json.loads(v25_files[0].read_text())
        for m in data.get("exit_modes", []):
            mode = m.get("exit_mode", "")
            if not mode: continue
            await persist_run(c, mode, mode, mode, "v2.5", m)
            eq = m.get("equity_curve", [])
            if eq:
                await persist_equity(c, mode, mode, eq)
            monthly = m.get("monthly_returns", {})
            if monthly:
                await persist_monthly(c, mode, mode, monthly)
            print(f"  ✅ v2.5 {mode}: trades={m.get('n_trades',0)}, return={m.get('total_return',0):.2%}")
    else:
        print("  ⚠ v2.5 JSON not found")

    await gw.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
