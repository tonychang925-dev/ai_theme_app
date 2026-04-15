#!/usr/bin/env python3
"""
调试潜力主题筛选逻辑
"""
import asyncio
import asyncpg
from datetime import date

async def debug_potential_themes():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)
    trade_date = date(2026, 4, 7)

    # 查询主题9010317的完整数据
    query = """
    SELECT
        ss.subject_key,
        COUNT(DISTINCT ss.stock_id) as stock_count,
        SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
        AVG(ss.pct_chg) as avg_pct_chg,
        SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
        SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) as leader_count
    FROM subject_stock_daily_snapshot ss
    LEFT JOIN money_flow_enhanced mf
        ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
    WHERE ss.trade_date = $1 AND ss.subject_key = $2
    GROUP BY ss.subject_key
    """

    row = await conn.fetchrow(query, trade_date, "9010317")
    if row:
        print(f"主题9010317完整数据:")
        print(f"  股票数量: {row['stock_count']}")
        print(f"  总资金流入: {row['total_inflow']}")
        print(f"  平均涨跌幅: {row['avg_pct_chg']}")
        print(f"  涨停股票数: {row['limit_up_count']}")
        print(f"  龙头股票数: {row['leader_count']}")

        # 检查是否符合潜力主题条件
        has_enough_stocks = row['stock_count'] >= 3
        has_big_inflow = row['total_inflow'] > 100000000  # 1亿以上
        has_limit_up_and_positive = row['limit_up_count'] >= 1 and row['avg_pct_chg'] > 0
        has_leader_and_positive = row['leader_count'] >= 1 and row['avg_pct_chg'] > 0

        print(f"\n条件检查:")
        print(f"  股票数量≥3: {has_enough_stocks}")
        print(f"  资金流入>1亿: {has_big_inflow} ({row['total_inflow']})")
        print(f"  有涨停股且平均涨幅>0: {has_limit_up_and_positive}")
        print(f"  有龙头股且平均涨幅>0: {has_leader_and_positive}")

        # 检查是否满足任意条件
        condition_met = has_big_inflow or has_limit_up_and_positive or has_leader_and_positive
        print(f"\n  满足任意条件: {condition_met}")

        if not condition_met:
            print(f"  ❌ 不满足任何条件")
        else:
            print(f"  ✅ 至少满足一个条件")

    # 现在查询实际返回的主题列表
    query_all = """
    SELECT
        ss.subject_key,
        COUNT(DISTINCT ss.stock_id) as stock_count,
        SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
        AVG(ss.pct_chg) as avg_pct_chg,
        SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
        SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) as leader_count
    FROM subject_stock_daily_snapshot ss
    LEFT JOIN money_flow_enhanced mf
        ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
    WHERE ss.trade_date = $1
    GROUP BY ss.subject_key
    HAVING
        COUNT(DISTINCT ss.stock_id) >= 3
        AND (
            SUM(COALESCE(mf.main_net_inflow, 0)) > 100000000
            OR
            (SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) >= 1 AND AVG(ss.pct_chg) > 0)
            OR
            (SUM(CASE WHEN ss.is_leader = TRUE THEN 1 ELSE 0 END) >= 1 AND AVG(ss.pct_chg) > 0)
        )
    ORDER BY
        total_inflow DESC,
        limit_up_count DESC,
        avg_pct_chg DESC
    """

    rows = await conn.fetch(query_all, trade_date)

    print(f"\n{'='*70}")
    print(f"所有符合条件的主题 (共{len(rows)}个):")

    # 检查9010317是否在结果中
    theme_9010317_index = -1
    for i, row in enumerate(rows):
        if row['subject_key'] == '9010317':
            theme_9010317_index = i
            print(f"\n  ⭐ 找到9010317在位置 {i+1}:")
            print(f"     股票数量: {row['stock_count']}")
            print(f"     资金流入: {row['total_inflow']}")
            print(f"     平均涨幅: {row['avg_pct_chg']:.1f}%")
            print(f"     涨停股数: {row['limit_up_count']}")
            print(f"     龙头股数: {row['leader_count']}")

    if theme_9010317_index == -1:
        print(f"\n  ❌ 9010317不在查询结果中")

        # 检查排序问题：列出前20个主题看看
        print(f"\n  前20个主题:")
        for i, row in enumerate(rows[:20]):
            print(f"    {i+1}. {row['subject_key']}: 资金流入{row['total_inflow']:.0f}, {row['limit_up_count']}涨停, 均涨{row['avg_pct_chg']:.1f}%")

        # 检查9010317是否因为排序太低而没被LIMIT 15截断
        if len(rows) > 15:
            print(f"\n  ⚠️  查询返回{len(rows)}个主题，但原方法只取前15个")
            print(f"     第15个主题: {rows[14]['subject_key']}: 资金流入{rows[14]['total_inflow']:.0f}, {rows[14]['limit_up_count']}涨停")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(debug_potential_themes())