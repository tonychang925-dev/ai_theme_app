#!/usr/bin/env python3
"""
检查数据库中K线数据
"""
import asyncio
import asyncpg
from datetime import date, timedelta
import sys

async def main():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    print("检查数据库中的K线数据...")
    conn = await asyncpg.connect(**config)

    try:
        # 1. 检查表结构
        print("\n1. subject_stock_daily_snapshot表字段:")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'subject_stock_daily_snapshot'
            ORDER BY ordinal_position
        """)

        for col in columns:
            print(f"   {col['column_name']}: {col['data_type']} ({'可为空' if col['is_nullable'] == 'YES' else '非空'})")

        # 2. 检查日期范围
        print("\n2. 检查日期范围:")
        date_range = await conn.fetch("""
            SELECT
                MIN(trade_date) as min_date,
                MAX(trade_date) as max_date,
                COUNT(DISTINCT trade_date) as date_count
            FROM subject_stock_daily_snapshot
        """)

        if date_range:
            row = date_range[0]
            print(f"   日期范围: {row['min_date']} 到 {row['max_date']}")
            print(f"   交易天数: {row['date_count']}")

        # 3. 检查股票数量
        print("\n3. 检查股票数量:")
        stock_stats = await conn.fetch("""
            SELECT
                COUNT(DISTINCT stock_id) as unique_stocks,
                COUNT(*) as total_records
            FROM subject_stock_daily_snapshot
        """)

        if stock_stats:
            row = stock_stats[0]
            print(f"   唯一股票数: {row['unique_stocks']}")
            print(f"   总记录数: {row['total_records']}")
            if row['unique_stocks'] > 0:
                avg_records = row['total_records'] / row['unique_stocks']
                print(f"   平均每只股票记录: {avg_records:.1f}")

        # 4. 检查特定股票的K线数据
        print("\n4. 检查神剑股份(002361.SZ)的K线数据:")
        shenjian_data = await conn.fetch("""
            SELECT
                trade_date,
                open_price,
                high_price,
                low_price,
                close_price,
                pct_chg,
                volume,
                amount,
                rank_order,
                is_leader
            FROM subject_stock_daily_snapshot
            WHERE stock_id = '002361.SZ'
            ORDER BY trade_date DESC
            LIMIT 10
        """)

        if shenjian_data:
            print(f"   找到{len(shenjian_data)}条神剑股份记录:")
            for i, row in enumerate(shenjian_data, 1):
                print(f"   {i}. {row['trade_date']}:")
                print(f"      开盘: {row['open_price']}, 最高: {row['high_price']}, 最低: {row['low_price']}, 收盘: {row['close_price']}")
                print(f"      涨跌幅: {row['pct_chg']}%, 成交量: {row['volume']}")
        else:
            print("   ❌ 未找到神剑股份数据")

            # 检查是否有类似的股票代码
            similar_stocks = await conn.fetch("""
                SELECT DISTINCT stock_id, stock_name
                FROM subject_stock_daily_snapshot
                WHERE stock_id LIKE '%002361%' OR stock_name LIKE '%神剑%'
                LIMIT 5
            """)

            if similar_stocks:
                print("   类似的股票:")
                for stock in similar_stocks:
                    print(f"     {stock['stock_id']} - {stock['stock_name']}")

        # 5. 检查K线数据完整性（关键字段是否有数据）
        print("\n5. 检查K线数据完整性:")
        completeness = await conn.fetch("""
            SELECT
                COUNT(*) as total,
                COUNT(open_price) as has_open,
                COUNT(high_price) as has_high,
                COUNT(low_price) as has_low,
                COUNT(close_price) as has_close,
                COUNT(pct_chg) as has_pct_chg,
                COUNT(volume) as has_volume
            FROM subject_stock_daily_snapshot
        """)

        if completeness:
            row = completeness[0]
            total = row['total']
            print(f"   总记录数: {total}")
            print(f"   开盘价完整性: {row['has_open']}/{total} ({row['has_open']/total*100:.1f}%)")
            print(f"   最高价完整性: {row['has_high']}/{total} ({row['has_high']/total*100:.1f}%)")
            print(f"   最低价完整性: {row['has_low']}/{total} ({row['has_low']/total*100:.1f}%)")
            print(f"   收盘价完整性: {row['has_close']}/{total} ({row['has_close']/total*100:.1f}%)")
            print(f"   涨跌幅完整性: {row['has_pct_chg']}/{total} ({row['has_pct_chg']/total*100:.1f}%)")
            print(f"   成交量完整性: {row['has_volume']}/{total} ({row['has_volume']/total*100:.1f}%)")

        # 6. 检查是否可以用于弱转强分析
        print("\n6. 弱转强分析可行性评估:")
        # 需要至少2天数据才能分析
        multi_day_stocks = await conn.fetch("""
            SELECT
                stock_id,
                COUNT(DISTINCT trade_date) as date_count
            FROM subject_stock_daily_snapshot
            GROUP BY stock_id
            HAVING COUNT(DISTINCT trade_date) >= 2
            ORDER BY date_count DESC
            LIMIT 10
        """)

        if multi_day_stocks:
            print(f"   有2天以上数据的股票: {len(multi_day_stocks)}只")
            print(f"   示例股票数据完整性:")
            for stock in multi_day_stocks[:5]:
                stock_id = stock['stock_id']
                stock_data = await conn.fetch("""
                    SELECT trade_date, pct_chg
                    FROM subject_stock_daily_snapshot
                    WHERE stock_id = $1
                    ORDER BY trade_date DESC
                    LIMIT 3
                """, stock_id)

                dates = [str(d['trade_date']) for d in stock_data]
                pct_chgs = [float(d['pct_chg']) if d['pct_chg'] else 0 for d in stock_data]
                print(f"     {stock_id}: {stock['date_count']}天, 最近3天涨跌幅: {pct_chgs}")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(main())