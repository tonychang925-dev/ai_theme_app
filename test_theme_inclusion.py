#!/usr/bin/env python3
"""
测试修改后的主题包含逻辑是否包括神剑股份的主题
"""
import asyncio
import asyncpg
from datetime import date
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from real_weak_to_strong_screening_enhanced import RealDatabaseScreener

async def test():
    """测试主题包含逻辑"""
    print("测试修改后的主题包含逻辑")
    print("=" * 70)

    trade_date = date(2026, 4, 7)
    screener = RealDatabaseScreener()

    try:
        await screener.connect()

        # 测试当前主线主题获取
        print("1. 获取当前主线主题（近3天≥2天为主线）...")
        main_themes = await screener._get_current_main_themes(trade_date)
        print(f"   当前主线主题数量: {len(main_themes)}")
        if "9010317" in main_themes:
            print(f"   ✅ 神剑股份主题9010317在当前主线主题中")
        else:
            print(f"   ❌ 神剑股份主题9010317不在当前主线主题中")

        # 测试潜力主线主题获取
        print("\n2. 获取潜力主线主题（有资金/涨停/龙头）...")
        potential_themes = await screener._get_potential_themes(trade_date)
        print(f"   潜力主线主题数量: {len(potential_themes)}")

        # 检查主题9010317是否在其中
        theme_9010317_included = False
        theme_details = None

        # 查询主题9010317的具体数据
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

        row = await screener.conn.fetchrow(query, trade_date, "9010317")
        if row:
            theme_details = dict(row)
            print(f"   主题9010317数据:")
            print(f"     股票数量: {theme_details['stock_count']}")
            print(f"     总资金流入: {theme_details['total_inflow']:.0f}")
            print(f"     平均涨跌幅: {theme_details['avg_pct_chg']:.1f}%")
            print(f"     涨停股票数: {theme_details['limit_up_count']}")
            print(f"     龙头股票数: {theme_details['leader_count']}")

            # 检查是否符合潜力主题条件
            conditions = []
            if theme_details['stock_count'] >= 10:
                conditions.append(f"股票数量≥10 ({theme_details['stock_count']})")
            if theme_details['total_inflow'] > 0:
                conditions.append(f"资金流入>0 ({theme_details['total_inflow']:.0f})")
            else:
                conditions.append(f"资金流入≤0")
            if theme_details['limit_up_count'] > 0:
                conditions.append(f"有涨停股 ({theme_details['limit_up_count']})")
            if theme_details['leader_count'] > 0:
                conditions.append(f"有龙头股 ({theme_details['leader_count']})")
            if theme_details['avg_pct_chg'] > 0:
                conditions.append(f"平均涨幅>0 ({theme_details['avg_pct_chg']:.1f}%)")

            print(f"     潜力主题条件: {', '.join(conditions)}")

            # 检查是否在潜力主题列表中
            if "9010317" in potential_themes:
                print(f"   ✅ 神剑股份主题9010317在潜力主线主题中")
                theme_9010317_included = True
            else:
                print(f"   ❌ 神剑股份主题9010317不在潜力主线主题中")
        else:
            print(f"   ❌ 未找到主题9010317的数据")

        # 测试完整的主题获取方法
        print("\n3. 测试完整的主题获取方法...")
        all_themes = await screener.get_main_theme_subject_keys(trade_date)
        print(f"   总候选主题数量: {len(all_themes)}")
        if "9010317" in all_themes:
            print(f"   ✅ 神剑股份主题9010317在总候选主题中")
        else:
            print(f"   ❌ 神剑股份主题9010317不在总候选主题中")

        # 显示所有候选主题（最多20个）
        print(f"\n   候选主题列表（最多20个）:")
        for i, theme in enumerate(all_themes[:20]):
            print(f"     {i+1}. {theme}")

        print("\n" + "=" * 70)
        print("测试完成")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await screener.disconnect()

if __name__ == "__main__":
    asyncio.run(test())