#!/usr/bin/env python3
"""PR4.2.34d — Batch collect Tushare moneyflow for direction universe stocks."""
import asyncio, asyncpg, json, os, sys, time
from datetime import date
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))

import tushare as ts
from stock_processing_service.application.services.capital_evidence.tushare_moneyflow import TushareMoneyflowNormalizer

def to_ts_code(stock_id):
    if '.' in stock_id: return stock_id
    if stock_id.startswith(('0','3')): return f"{stock_id}.SZ"
    if stock_id.startswith(('6','9')): return f"{stock_id}.SH"
    return f"{stock_id}.SZ"

async def persist_row(conn, row):
    td = row.get("trade_date")
    if hasattr(td, "isoformat"): td = td.isoformat()
    await conn.execute("""
        INSERT INTO stock_fund_flow_daily (
            trade_date, ts_code,
            buy_elg_amount_yuan, sell_elg_amount_yuan,
            buy_lg_amount_yuan, sell_lg_amount_yuan,
            buy_md_amount_yuan, sell_md_amount_yuan,
            buy_sm_amount_yuan, sell_sm_amount_yuan,
            order_size_flow_amount_yuan,
            available_at, source_name, source_endpoint, source_version,
            collected_at, semantic_type, not_owner_identity,
            quality, diagnostics, raw_json
        ) VALUES ($1::date,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20::jsonb,$21::jsonb)
        ON CONFLICT (trade_date, ts_code, source_name, source_endpoint, source_version)
        DO UPDATE SET order_size_flow_amount_yuan=EXCLUDED.order_size_flow_amount_yuan, collected_at=EXCLUDED.collected_at
    """, td, row["ts_code"],
        row.get("buy_elg_amount_yuan"), row.get("sell_elg_amount_yuan"),
        row.get("buy_lg_amount_yuan"), row.get("sell_lg_amount_yuan"),
        row.get("buy_md_amount_yuan"), row.get("sell_md_amount_yuan"),
        row.get("buy_sm_amount_yuan"), row.get("sell_sm_amount_yuan"),
        row.get("order_size_flow_amount_yuan"),
        row.get("available_at"), row["source_name"], row["source_endpoint"],
        row["source_version"], row["collected_at"],
        row["semantic_type"], row["not_owner_identity"],
        row["quality"], json.dumps(row["diagnostics"], ensure_ascii=False),
        json.dumps(row["raw_json"], ensure_ascii=False))

async def main():
    token = os.environ.get('TUSHARE_TOKEN', '')
    ts.set_token(token)
    pro = ts.pro_api(timeout=30)

    # Get stock universe
    conn = await asyncpg.connect('postgresql://localhost:5432/stock_data_test', user='postgres', password='')
    try:
        core_keys = ['9015778','9014001','9018144','9014636','9019807','9066740','9013416',
                     '半导体设备','光刻胶','生成式物理AI']
        all_stocks = set()
        for sk in core_keys:
            rows = await conn.fetch(
                "SELECT DISTINCT stock_id FROM subject_stock_daily_snapshot "
                "WHERE subject_key = $1 AND trade_date = '2026-07-09'::date", sk)
            for r in rows: all_stocks.add(r['stock_id'])
    finally:
        await conn.close()

    stocks = sorted(all_stocks)
    print(f"Universe: {len(stocks)} stocks, collecting...")

    # Connect for writes
    db_conn = await asyncpg.connect('postgresql://localhost:5432/stock_data_test', user='postgres', password='')
    normalizer = TushareMoneyflowNormalizer()
    collected = 0; errors = 0; empty = 0

    try:
        for i, stock_id in enumerate(stocks):
            ts_code = to_ts_code(stock_id)
            try:
                df = pro.moneyflow(ts_code=ts_code, trade_date='20260709')
                if len(df) > 0:
                    row = df.iloc[0].to_dict()
                    evidence = normalizer.normalize_row(row)
                    await persist_row(db_conn, evidence.to_row())
                    collected += 1
                else:
                    empty += 1
            except Exception as e:
                if errors < 3:
                    print(f"  ERR {stock_id}→{ts_code}: {type(e).__name__}: {str(e)[:100]}")
                errors += 1
            time.sleep(0.15)

            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(stocks)}] collected={collected} errors={errors} empty={empty}")
    finally:
        await db_conn.close()

    print(f"\nDone: {collected} collected, {errors} errors, {empty} empty (no data)")

asyncio.run(main())