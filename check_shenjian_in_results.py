#!/usr/bin/env python3
"""
检查神剑股份是否在查询结果中
"""
import asyncio
import asyncpg
from datetime import date

async def check():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    stock_id = "002361"
    trade_date = date(2026, 4, 7)
    prev_date = date(2026, 4, 6)

    # 首先获取主题列表
    query_themes = """
    SELECT subject_key
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1 AND stock_id = $2
    LIMIT 1
    """

    theme_row = await conn.fetchrow(query_themes, trade_date, stock_id)
    if not theme_row:
        print("未找到神剑股份的主题")
        await conn.close()
        return

    subject_key = theme_row['subject_key']
    print(f"神剑股份主题: {subject_key}")

    # 现在测试实际的查询
    query = """
    SELECT
        t1.stock_id,
        t1.stock_name,
        t1.subject_key,
        t1.pct_chg as today_pct_chg,
        t1.is_leader as today_is_leader,
        t1.rank_order,
        t2.pct_chg as prev_pct_chg,
        t2.is_leader as prev_is_leader
    FROM subject_stock_daily_snapshot t1
    LEFT JOIN subject_stock_daily_snapshot t2
        ON t1.stock_id = t2.stock_id
        AND t2.trade_date = $2
    WHERE t1.trade_date = $1
      AND t1.subject_key = ANY($3)
    ORDER BY t1.rank_order ASC
    LIMIT 500
    """

    rows = await conn.fetch(query, trade_date, prev_date, [subject_key])

    print(f"主题 {subject_key} 下的股票数量: {len(rows)}")

    # 检查神剑股份是否在其中
    shenjian_found = False
    for i, row in enumerate(rows):
        if row['stock_id'] == stock_id:
            shenjian_found = True
            print(f"\n✅ 找到神剑股份在位置 {i+1}:")
            print(f"   排名: {row['rank_order']}")
            print(f"   涨跌幅: {row['today_pct_chg']}%")
            print(f"   是否龙头: {row['today_is_leader']}")
            break

    if not shenjian_found:
        print(f"\n❌ 神剑股份不在前 {len(rows)} 条记录中")

        # 检查神剑股份的排名
        query_rank = """
        SELECT rank_order
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1 AND stock_id = $2
        LIMIT 1
        """

        rank_row = await conn.fetchrow(query_rank, trade_date, stock_id)
        if rank_row:
            print(f"   神剑股份排名: {rank_row['rank_order']}")

            # 检查主题下有多少股票
            query_count = """
            SELECT COUNT(*) as total_count, MIN(rank_order) as min_rank, MAX(rank_order) as max_rank
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1 AND subject_key = $2
            """

            count_row = await conn.fetchrow(query_count, trade_date, subject_key)
            if count_row:
                print(f"   主题 {subject_key} 下股票总数: {count_row['total_count']}")
                print(f"   最低排名: {count_row['min_rank']}, 最高排名: {count_row['max_rank']}")

    # 检查前10只股票
    print(f"\n主题 {subject_key} 下前10只股票:")
    for i, row in enumerate(rows[:10]):
        print(f"  {i+1}. {row['stock_name']} ({row['stock_id']}): 排名 {row['rank_order']}, 涨跌幅 {row['today_pct_chg']}%")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())