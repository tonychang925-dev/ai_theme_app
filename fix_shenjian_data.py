#!/usr/bin/env python3
"""
修正神剑股份错误的价格数据
根据JSONL文件修正数据库
"""
import asyncio
import asyncpg
import json
from datetime import date

async def fix_data():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    # 从JSONL读取正确数据
    jsonl_path = "/Users/admin/Desktop/ai_theme_app/theme_data_complete/_stock_kline/tushare/daily_bar/002361.SZ.jsonl"

    correct_data = {}

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                trade_date_str = data.get('trade_date')
                if not trade_date_str:
                    continue

                trade_date = date.fromisoformat(trade_date_str)

                # 只关注关键日期
                if trade_date >= date(2026, 3, 26) and trade_date <= date(2026, 4, 10):
                    correct_data[trade_date] = {
                        'open_price': float(data.get('open_price', 0)),
                        'high_price': float(data.get('high_price', 0)),
                        'low_price': float(data.get('low_price', 0)),
                        'close_price': float(data.get('close_price', 0)),
                        'pct_chg': float(data.get('pct_chg', 0))
                    }
            except json.JSONDecodeError:
                continue

    print(f"从JSONL读取到 {len(correct_data)} 条正确数据")

    # 修正数据库
    for trade_date, correct_values in sorted(correct_data.items()):
        # 检查数据库中是否有该日期的数据
        check_query = """
        SELECT open_price, high_price, low_price, close_price, pct_chg
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        """

        row = await conn.fetchrow(check_query, '002361', trade_date)

        if not row:
            print(f"  {trade_date}: ❌ 数据库中无数据")
            continue

        db_open = float(row['open_price']) if row['open_price'] else 0
        db_high = float(row['high_price']) if row['high_price'] else 0
        db_low = float(row['low_price']) if row['low_price'] else 0
        db_close = float(row['close_price']) if row['close_price'] else 0
        db_pct = float(row['pct_chg']) if row['pct_chg'] else 0

        # 检查是否需要更新
        needs_update = (
            abs(db_open - correct_values['open_price']) > 0.01 or
            abs(db_high - correct_values['high_price']) > 0.01 or
            abs(db_low - correct_values['low_price']) > 0.01 or
            abs(db_close - correct_values['close_price']) > 0.01 or
            abs(db_pct - correct_values['pct_chg']) > 0.01
        )

        if needs_update:
            print(f"  {trade_date}: ⚠️  数据不匹配，需要更新")
            print(f"    数据库: O{db_open:.2f} H{db_high:.2f} L{db_low:.2f} C{db_close:.2f} ({db_pct:.1f}%)")
            print(f"    JSONL: O{correct_values['open_price']:.2f} H{correct_values['high_price']:.2f} "
                  f"L{correct_values['low_price']:.2f} C{correct_values['close_price']:.2f} ({correct_values['pct_chg']:.1f}%)")

            update_query = """
            UPDATE subject_stock_daily_snapshot
            SET open_price = $3, high_price = $4, low_price = $5, close_price = $6, pct_chg = $7
            WHERE stock_id = $1 AND trade_date = $2
            """

            await conn.execute(
                update_query,
                '002361',
                trade_date,
                correct_values['open_price'],
                correct_values['high_price'],
                correct_values['low_price'],
                correct_values['close_price'],
                correct_values['pct_chg']
            )

            print(f"    ✅ 已更新")
        else:
            print(f"  {trade_date}: ✅ 数据正确")

    # 验证关键缺口
    print(f"\n验证关键缺口（3/31 → 4/1）:")
    query_0331 = """
    SELECT close_price FROM subject_stock_daily_snapshot
    WHERE stock_id = '002361' AND trade_date = '2026-03-31'
    """
    query_0401 = """
    SELECT open_price FROM subject_stock_daily_snapshot
    WHERE stock_id = '002361' AND trade_date = '2026-04-01'
    """

    row_0331 = await conn.fetchrow(query_0331)
    row_0401 = await conn.fetchrow(query_0401)

    if row_0331 and row_0401:
        close_0331 = float(row_0331['close_price'])
        open_0401 = float(row_0401['open_price'])

        print(f"  3/31收盘价: {close_0331:.2f}")
        print(f"  4/1开盘价: {open_0401:.2f}")

        if open_0401 > close_0331:
            gap = open_0401 - close_0331
            gap_pct = gap / close_0331 * 100
            print(f"  ✅ 向上跳空缺口: +{gap:.2f} ({gap_pct:.2f}%)")
            print(f"  缺口区间: [{close_0331:.2f}, {open_0401:.2f}]")
        elif open_0401 < close_0331:
            gap = close_0331 - open_0401
            gap_pct = gap / close_0331 * 100
            print(f"  ⚠️  向下跳空缺口: -{gap:.2f} ({gap_pct:.2f}%)")
        else:
            print(f"  ⚠️  无缺口")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_data())