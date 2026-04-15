#!/usr/bin/env python3
"""
测试四方精创是否符合强势股条件
"""
import asyncio
import asyncpg
from datetime import date

async def test_sifang_condition():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    stock_id = "300468"
    analysis_date = date(2026, 4, 10)
    prev_date = analysis_date - date.resolution  # 前一日

    conn = await asyncpg.connect(**config)

    try:
        # 检查今日数据
        query_today = """
        SELECT
            stock_id,
            stock_name,
            trade_date,
            pct_chg,
            is_leader,
            rank_order
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        ORDER BY rank_order ASC
        LIMIT 1
        """

        today_row = await conn.fetchrow(query_today, stock_id, analysis_date)

        # 检查前一日数据
        query_prev = """
        SELECT
            stock_id,
            stock_name,
            trade_date,
            pct_chg,
            is_leader,
            rank_order
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        ORDER BY rank_order ASC
        LIMIT 1
        """

        prev_row = await conn.fetchrow(query_prev, stock_id, prev_date)

        print("四方精创强势股条件测试")
        print("=" * 60)

        if today_row:
            print(f"今日数据 (4/10):")
            print(f"  股票ID: {today_row['stock_id']}")
            print(f"  股票名称: {today_row['stock_name']}")
            print(f"  涨跌幅: {today_row['pct_chg']}%")
            print(f"  是否龙头: {today_row['is_leader']}")
            print(f"  排名顺序: {today_row['rank_order']}")

            today_is_strong = today_row['is_leader'] or today_row['rank_order'] <= 5
            print(f"  今日是否符合强势股条件 (is_leader=True或rank_order<=5): {today_is_strong}")
        else:
            print("未找到今日数据")

        if prev_row:
            print(f"\n前一日数据 (4/9):")
            print(f"  股票ID: {prev_row['stock_id']}")
            print(f"  股票名称: {prev_row['stock_name']}")
            print(f"  涨跌幅: {prev_row['pct_chg']}%")
            print(f"  是否龙头: {prev_row['is_leader']}")
            print(f"  排名顺序: {prev_row['rank_order']}")

            prev_is_strong = prev_row['is_leader'] or prev_row['rank_order'] <= 10
            print(f"  前一日是否符合强势股条件 (is_leader=True或rank_order<=10): {prev_is_strong}")

            # 检查前一日是否弱势
            prev_is_weak = prev_row['pct_chg'] < -2.0
            print(f"  前一日是否弱势 (pct_chg < -2.0%): {prev_is_weak}")
        else:
            print("\n未找到前一日数据")

        # 综合判断
        if today_row and prev_row:
            is_strong_stock = today_is_strong and prev_is_strong
            print(f"\n综合判断:")
            print(f"  是否强势股 (今日强势且前一日强势): {is_strong_stock}")
            print(f"  是否符合弱转强条件 (前一日弱势且今日转强): {prev_is_weak and today_row['pct_chg'] > 0}")

            # 新筛选逻辑条件
            new_filter_condition = (
                today_is_strong and
                prev_is_strong and
                prev_is_weak and
                today_row['pct_chg'] > 0
            )
            print(f"  是否通过新筛选逻辑 (今日强势+前一日强势+前一日弱势+今日上涨): {new_filter_condition}")

            if not prev_is_strong:
                print(f"  ❌ 前一日不是强势股 (rank_order={prev_row['rank_order']}, is_leader={prev_row['is_leader']})")
            if not prev_is_weak:
                print(f"  ⚠️  前一日不是弱势 (跌幅不够)")
            if not today_is_strong:
                print(f"  ❌ 今日不是强势股")

        else:
            print("\n数据不全，无法综合判断")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(test_sifang_condition())