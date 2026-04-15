#!/usr/bin/env python3
"""
深入分析神剑股份案例，找出筛选逻辑的不足
"""
import asyncio
import asyncpg
from datetime import date

async def analyze():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    stock_id = "002361"
    print(f"深入分析神剑股份案例")
    print(f"股票ID: {stock_id}")
    print("=" * 70)

    # 1. 获取4/5-4/10全部数据
    dates = [date(2026, 4, 5), date(2026, 4, 6), date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 10)]

    print(f"神剑股份每日数据:")
    for d in dates:
        query = """
        SELECT stock_id, stock_name, trade_date, pct_chg, is_leader, rank_order, subject_key
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        LIMIT 1
        """
        row = await conn.fetchrow(query, stock_id, d)
        if row:
            print(f"  {d}: 涨跌幅 {row['pct_chg']}%, 是否龙头 {row['is_leader']}, 排名 {row['rank_order']}, 主题 {row['subject_key']}")
        else:
            print(f"  {d}: 无数据")

    # 2. 检查主题9010317在4/7-4/8的主线状态
    subject_key = "9010317"
    print(f"\n主题 {subject_key} 的主线状态:")
    for d in [date(2026, 4, 7), date(2026, 4, 8)]:
        query = """
        SELECT is_main_theme
        FROM theme_mainline_judgement
        WHERE subject_key = $1 AND trade_date = $2
        LIMIT 1
        """
        row = await conn.fetchrow(query, subject_key, d)
        if row:
            print(f"  {d}: 是否为主线 {row['is_main_theme']}")
        else:
            print(f"  {d}: 无主线判断")

    # 3. 检查主题9010317的详细信息
    print(f"\n主题 {subject_key} 的详细信息:")
    query = """
    SELECT name, code, heat_score, status, description
    FROM theme_master
    WHERE code = $1
    LIMIT 1
    """
    row = await conn.fetchrow(query, subject_key)
    if row:
        print(f"  主题名称: {row['name']}")
        print(f"  主题热度: {row['heat_score']}")
        print(f"  主题状态: {row['status']}")
        print(f"  描述: {row['description'][:100]}..." if row['description'] else "  描述: 无")
    else:
        print(f"  未找到主题详细信息")

    # 4. 检查主题9010317在4/7-4/8的资金面证据
    print(f"\n主题 {subject_key} 的资金面证据:")
    for d in [date(2026, 4, 7), date(2026, 4, 8)]:
        query = """
        SELECT
            COUNT(DISTINCT ss.stock_id) as stock_count,
            SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
            AVG(ss.pct_chg) as avg_pct_chg,
            SUM(CASE WHEN ss.pct_chg >= 9.9 THEN 1 ELSE 0 END) as limit_up_count
        FROM subject_stock_daily_snapshot ss
        LEFT JOIN money_flow_enhanced mf
            ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
        WHERE ss.trade_date = $1 AND ss.subject_key = $2
        GROUP BY ss.subject_key
        """
        row = await conn.fetchrow(query, d, subject_key)
        if row:
            print(f"  {d}:")
            print(f"    股票数量: {row['stock_count']}")
            print(f"    总资金流入: {row['total_inflow']:.0f}")
            print(f"    平均涨跌幅: {row['avg_pct_chg']:.1f}%")
            print(f"    涨停股票数: {row['limit_up_count']}")
        else:
            print(f"  {d}: 无资金面数据")

    # 5. 检查神剑股份在4/8是否是主题9010317中唯一的涨停股
    print(f"\n神剑股份在4/8日的主题内地位:")
    query = """
    SELECT
        COUNT(*) as total_stocks_in_theme,
        SUM(CASE WHEN pct_chg >= 9.9 THEN 1 ELSE 0 END) as limit_up_count,
        SUM(CASE WHEN is_leader = TRUE THEN 1 ELSE 0 END) as leader_count,
        MIN(rank_order) as top_rank
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1 AND subject_key = $2
    """
    row = await conn.fetchrow(query, date(2026, 4, 8), subject_key)
    if row:
        print(f"  主题内股票总数: {row['total_stocks_in_theme']}")
        print(f"  涨停股票数: {row['limit_up_count']}")
        print(f"  龙头股票数: {row['leader_count']}")
        print(f"  最高排名: {row['top_rank']}")

        # 检查神剑股份是否是唯一的龙头
        query2 = """
        SELECT stock_id, stock_name, pct_chg, is_leader, rank_order
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1 AND subject_key = $2 AND is_leader = TRUE
        ORDER BY rank_order
        """
        rows = await conn.fetch(query2, date(2026, 4, 8), subject_key)
        if rows:
            print(f"  龙头股票列表:")
            for r in rows:
                print(f"    {r['stock_name']} ({r['stock_id']}): 涨跌幅 {r['pct_chg']}%, 排名 {r['rank_order']}")

    # 6. 检查神剑股份前几天的表现（是否有强势股历史）
    print(f"\n神剑股份历史表现分析:")
    query = """
    SELECT trade_date, pct_chg, is_leader, rank_order
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date >= $2::date - 10 AND trade_date < $2
    ORDER BY trade_date DESC
    """
    rows = await conn.fetch(query, stock_id, date(2026, 4, 7))
    if rows:
        print(f"  前10天表现:")
        for r in rows:
            print(f"    {r['trade_date']}: 涨跌幅 {r['pct_chg']}%, 是否龙头 {r['is_leader']}, 排名 {r['rank_order']}")
    else:
        print(f"  无历史数据")

    # 7. 检查4/7有哪些主线主题
    print(f"\n2026-04-07的主线主题:")
    query = """
    SELECT subject_key, is_main_theme
    FROM theme_mainline_judgement
    WHERE trade_date = $1 AND is_main_theme = TRUE
    ORDER BY subject_key
    LIMIT 10
    """
    rows = await conn.fetch(query, date(2026, 4, 7))
    if rows:
        print(f"  找到 {len(rows)} 个主线主题:")
        for r in rows:
            # 获取主题名称
            query_name = """
            SELECT name FROM theme_master WHERE code = $1 LIMIT 1
            """
            name_row = await conn.fetchrow(query_name, r['subject_key'])
            theme_name = name_row['name'] if name_row else f"主题_{r['subject_key']}"
            print(f"    {r['subject_key']}: {theme_name}")
    else:
        print(f"  无主线主题")

    # 8. 建议改进点
    print(f"\n{'='*70}")
    print(f"神剑股份案例分析总结:")
    print(f"1. 神剑股份在4/7属于主题9010317，但该主题不是主线")
    print(f"2. 神剑股份在4/8涨停，成为主题9010317的龙头")
    print(f"3. 弱转强筛选逻辑要求'先有主线存在，才能有弱转强的基础'")
    print(f"4. 但神剑股份案例表明：强势股可以在非主线主题中启动，并可能带动主题成为主线")
    print(f"\n建议改进筛选逻辑:")
    print(f"1. 考虑'潜在主线'：有资金流入、有涨停股、热度上升的主题")
    print(f"2. 考虑'前强势股'：历史上有强势表现，当前调整到支撑位的股票")
    print(f"3. 考虑'龙头种子'：可能成为新龙头，带动主题成为主线的股票")
    print(f"4. 弱化'必须从主线中选股'的限制，但保持'必须从有潜力的主题中选股'")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze())