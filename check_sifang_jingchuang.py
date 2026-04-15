#!/usr/bin/env python3
"""
检查四方精创是否是龙头股/强势股
"""
import asyncio
import asyncpg
from datetime import date

async def check_sifang_jingchuang():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    print("检查四方精创 (300468) 是否是龙头股/强势股")
    print("=" * 70)

    conn = await asyncpg.connect(**config)

    try:
        stock_id = "300468"
        analysis_date = date(2026, 4, 10)

        # 检查4/10日数据
        query = """
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
        LIMIT 5
        """

        rows = await conn.fetch(query, stock_id, analysis_date)

        if rows:
            for row in rows:
                print(f"股票ID: {row['stock_id']}")
                print(f"股票名称: {row['stock_name']}")
                print(f"交易日期: {row['trade_date']}")
                print(f"涨跌幅: {row['pct_chg']}%")
                print(f"是否龙头: {row['is_leader']}")
                print(f"排名顺序: {row['rank_order']}")
                print()
        else:
            print(f"未找到{stock_id}在{analysis_date}的数据")

        # 检查近期是否有龙头标记
        print(f"\n检查{stock_id}近期龙头标记:")
        query_leader_history = """
        SELECT
            trade_date,
            pct_chg,
            is_leader,
            rank_order
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date >= ($2::date - 7)
        ORDER BY trade_date DESC
        LIMIT 7
        """

        rows_history = await conn.fetch(query_leader_history, stock_id, analysis_date)

        if rows_history:
            print(f"  近期7天数据:")
            for row in rows_history:
                leader_status = "✅ 龙头" if row['is_leader'] else "  "
                print(f"    {row['trade_date']}: {row['pct_chg']}% {leader_status} (排名:{row['rank_order']})")
        else:
            print("  无近期数据")

        # 检查该股票在热点主题中的表现 (暂时注释，因为theme_name列可能不存在)
        print(f"\n检查股票在热点主题中的表现: 暂不检查")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(check_sifang_jingchuang())