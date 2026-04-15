#!/usr/bin/env python3
"""
分析神剑股份所属主题的历史持续性
"""
import asyncio
import asyncpg
from datetime import date, timedelta
import sys

async def analyze_theme_persistence():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    stock_id = "002361"
    analysis_date = date(2026, 4, 8)

    print(f"分析神剑股份主题持续性 - {analysis_date}")
    print("=" * 70)

    # 1. 获取神剑股份所属主题
    theme_query = """
    SELECT DISTINCT tsm.subject_key, tsm.theme_id, tsm.theme_name, tsm.confidence
    FROM theme_stock_map tsm
    WHERE tsm.stock_id = $1
    ORDER BY tsm.confidence DESC
    """
    theme_rows = await conn.fetch(theme_query, stock_id)

    if not theme_rows:
        print("未找到主题映射")
        await conn.close()
        return

    print(f"神剑股份所属主题:")
    for row in theme_rows:
        print(f"  主题ID: {row['theme_id']}, 主题名称: {row['theme_name']}, 置信度: {row['confidence']}")

    # 2. 分析每个主题的历史事件持续性
    history_days = 30  # 分析30天内的历史事件

    for row in theme_rows:
        theme_id = row['theme_id']
        theme_name = row['theme_name']

        print(f"\n分析主题: {theme_name} (ID: {theme_id})")
        print("-" * 50)

        # 查询历史事件
        history_query = """
        SELECT rank_date, heat, heat_name, pct_chg, driver_summary
        FROM theme_history_event
        WHERE theme_id = $1 AND rank_date <= $2 AND rank_date >= $3
        ORDER BY rank_date DESC
        """
        start_date = analysis_date - timedelta(days=history_days)

        history_rows = await conn.fetch(history_query, theme_id, analysis_date, start_date)

        if not history_rows:
            print("  无历史事件记录")
            continue

        # 统计事件
        total_events = len(history_rows)
        hot_events = sum(1 for r in history_rows if r['heat_name'] == '热')
        avg_pct_chg = sum(float(r['pct_chg']) for r in history_rows if r['pct_chg'] is not None) / total_events

        print(f"  最近{history_days}天事件数: {total_events}")
        print(f"  热点事件数: {hot_events}")
        print(f"  平均涨跌幅: {avg_pct_chg:.2f}%")

        # 检查近期是否有驱动事件
        recent_days = 7
        recent_start = analysis_date - timedelta(days=recent_days)
        recent_events = [r for r in history_rows if r['rank_date'] >= recent_start]

        if recent_events:
            print(f"  最近{recent_days}天事件:")
            for event in recent_events[:3]:  # 显示最近3个事件
                print(f"    {event['rank_date']}: {event['driver_summary'][:100]}...")

        # 3. 分析主题资金流入（通过主题下股票的资金流入汇总）
        capital_query = """
        SELECT
            ss.trade_date,
            SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
            COUNT(DISTINCT ss.stock_id) as stock_count,
            AVG(ss.pct_chg) as avg_pct_chg
        FROM subject_stock_daily_snapshot ss
        LEFT JOIN money_flow_enhanced mf
            ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
        WHERE ss.subject_key = $1 AND ss.trade_date <= $2 AND ss.trade_date >= $3
        GROUP BY ss.trade_date
        ORDER BY ss.trade_date DESC
        LIMIT 10
        """

        capital_rows = await conn.fetch(capital_query, row['subject_key'], analysis_date, start_date)

        if capital_rows:
            total_capital = sum(r['total_inflow'] for r in capital_rows if r['total_inflow'] is not None)
            positive_days = sum(1 for r in capital_rows if r['total_inflow'] and r['total_inflow'] > 0)

            print(f"  资金流入分析:")
            print(f"    累计资金流入: {total_capital:,.0f}")
            print(f"    资金流入为正的天数: {positive_days}/{len(capital_rows)}")

            # 最近3天资金流入
            recent_capital = capital_rows[:3]
            if recent_capital:
                print(f"    最近{len(recent_capital)}天资金流入:")
                for cap in recent_capital:
                    inflow_text = f"{cap['total_inflow']/100000000:.2f}亿" if cap['total_inflow'] and cap['total_inflow'] > 100000000 else f"{cap['total_inflow']:,.0f}"
                    print(f"      {cap['trade_date']}: {inflow_text}, {cap['stock_count']}只股票, 均涨{cap['avg_pct_chg']:.1f}%")

        # 4. 评估主线潜力
        print(f"  主线潜力评估:")

        # 条件1: 近期有热点事件
        has_recent_hot_events = any(r['heat_name'] == '热' for r in recent_events)
        if has_recent_hot_events:
            print(f"    ✅ 近期有热点事件刺激")
        else:
            print(f"    ⚠️  近期无热点事件")

        # 条件2: 持续资金流入
        has_sustained_capital = positive_days >= 3  # 至少3天资金流入为正
        if has_sustained_capital:
            print(f"    ✅ 有持续资金流入 ({positive_days}天)")
        else:
            print(f"    ⚠️  资金流入持续性不足")

        # 条件3: 事件频率
        event_frequency = total_events / history_days  # 每天事件数
        if event_frequency >= 0.2:  # 平均每5天至少一个事件
            print(f"    ✅ 事件频率较高 ({event_frequency:.2f}/天)")
        else:
            print(f"    ⚠️  事件频率较低")

        # 综合判断
        if has_recent_hot_events and has_sustained_capital and event_frequency >= 0.1:
            print(f"    🎯 该主题具有主线潜力！")
        elif has_recent_hot_events and (has_sustained_capital or event_frequency >= 0.2):
            print(f"    📈 该主题有一定主线潜力")
        else:
            print(f"    ⚠️  该主题主线潜力不足")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze_theme_persistence())