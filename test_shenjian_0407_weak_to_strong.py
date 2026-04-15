#!/usr/bin/env python3
"""
测试2026-04-07神剑股份弱转强候选
"""
import asyncio
import asyncpg
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService
from real_weak_to_strong_screening_enhanced import RealDatabaseScreener

async def check_shenjian_0407():
    """检查2026-04-07神剑股份数据"""
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

    print(f"测试神剑股份弱转强候选 - {trade_date}")
    print(f"股票: {stock_id}")
    print(f"当日: {trade_date}")
    print(f"前一日: {prev_date}")
    print("=" * 70)

    # 1. 获取神剑股份4/7数据
    query_today = """
    SELECT stock_id, stock_name, trade_date, pct_chg, is_leader, rank_order, subject_key,
           open_price, high_price, low_price, close_price, volume, amount, limit_up
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1 AND trade_date = $2
    LIMIT 1
    """

    row_today = await conn.fetchrow(query_today, stock_id, trade_date)
    row_prev = await conn.fetchrow(query_today, stock_id, prev_date)

    if not row_today:
        print("未找到当日数据")
        await conn.close()
        return

    stock_data = dict(row_today)
    prev_stock_data = dict(row_prev) if row_prev else None

    print(f"当日数据:")
    print(f"  涨跌幅: {stock_data['pct_chg']}%")
    print(f"  是否龙头: {stock_data['is_leader']}")
    print(f"  排名顺序: {stock_data['rank_order']}")
    print(f"  主题key: {stock_data['subject_key']}")

    if prev_stock_data:
        print(f"前一日数据:")
        print(f"  涨跌幅: {prev_stock_data['pct_chg']}%")
        print(f"  是否龙头: {prev_stock_data['is_leader']}")
        print(f"  排名顺序: {prev_stock_data['rank_order']}")

    # 2. 检查当日主题是否为主线
    subject_key = stock_data['subject_key']
    query_mainline = """
    SELECT is_main_theme
    FROM theme_mainline_judgement
    WHERE subject_key = $1 AND trade_date = $2
    LIMIT 1
    """

    mainline_row = await conn.fetchrow(query_mainline, subject_key, trade_date)
    if mainline_row:
        print(f"主题 {subject_key} 在 {trade_date} 是否为主线: {mainline_row['is_main_theme']}")
    else:
        print(f"主题 {subject_key} 在 {trade_date}: 无主线判断")

    # 3. 获取主题信息
    query_theme = """
    SELECT name, code, heat_score, status, description
    FROM theme_master
    WHERE code = $1
    LIMIT 1
    """

    theme_row = await conn.fetchrow(query_theme, subject_key)
    if theme_row:
        theme_name = theme_row['name']
        print(f"主题名称: {theme_name}")
        print(f"主题热度: {theme_row['heat_score']}")
    else:
        theme_name = f"主题_{subject_key}"
        print(f"主题名称: {theme_name} (未找到具体信息)")

    # 4. 检查该主题是否是主线（基于多日判断）
    # 查询过去3天（4/5, 4/6, 4/7）的主线判断
    query_theme_days = """
    WITH theme_days AS (
        SELECT
            subject_key,
            COUNT(*) as total_days,
            SUM(CASE WHEN is_main_theme = TRUE THEN 1 ELSE 0 END) as main_theme_days
        FROM theme_mainline_judgement
        WHERE trade_date >= $1::date - 2 AND trade_date <= $1
        GROUP BY subject_key
    )
    SELECT subject_key, main_theme_days, total_days
    FROM theme_days
    WHERE subject_key = $2
    """

    theme_days_row = await conn.fetchrow(query_theme_days, trade_date, subject_key)
    if theme_days_row:
        print(f"主题 {subject_key} 近3天主线程次数: {theme_days_row['main_theme_days']}/{theme_days_row['total_days']}")
        if theme_days_row['main_theme_days'] >= 2:
            print(f"  ✅ 符合主线主题条件（近3天≥2天为主线）")
        else:
            print(f"  ❌ 不符合主线主题条件")
    else:
        print(f"主题 {subject_key} 近3天无主线判断记录")

    # 5. 如果主题不是主线，检查是否有资金面证据
    is_main_theme = False
    if theme_days_row and theme_days_row['main_theme_days'] >= 2:
        is_main_theme = True
    elif mainline_row and mainline_row['is_main_theme']:
        is_main_theme = True
    else:
        # 检查资金面证据
        print(f"\n检查主题 {subject_key} 的资金面证据...")
        query_capital = """
        SELECT
            COUNT(DISTINCT ss.stock_id) as stock_count,
            SUM(COALESCE(mf.main_net_inflow, 0)) as total_inflow,
            AVG(ss.pct_chg) as avg_pct_chg
        FROM subject_stock_daily_snapshot ss
        LEFT JOIN money_flow_enhanced mf
            ON ss.stock_id = mf.stock_id AND ss.trade_date = mf.trade_date
        WHERE ss.trade_date = $1 AND ss.subject_key = $2
        GROUP BY ss.subject_key
        """

        capital_row = await conn.fetchrow(query_capital, trade_date, subject_key)
        if capital_row:
            stock_count = capital_row['stock_count']
            total_inflow = capital_row['total_inflow']
            avg_pct_chg = capital_row['avg_pct_chg']

            print(f"  主题内股票数量: {stock_count}")
            print(f"  总资金流入: {total_inflow:.0f}")
            print(f"  平均涨跌幅: {avg_pct_chg:.1f}%")

            # 判断资金面是否支持
            if stock_count >= 3 and total_inflow > 0 and avg_pct_chg > 0:
                print(f"  ✅ 有资金面证据支持")
                is_main_theme = True
            else:
                print(f"  ❌ 资金面证据不足")
        else:
            print(f"  无资金面数据")

    print(f"\n最终主线判断: {'✅ 是主线主题' if is_main_theme else '❌ 非主线主题'}")

    if not is_main_theme:
        print(f"  ❌ 主题非主线，不符合弱转强筛选基础条件")
        await conn.close()
        return

    # 6. 分析股票是否为强势股（基于4/7数据）
    print(f"\n分析神剑股份强势股属性（基于4/7数据）...")

    strong_service = StrongStockAnalysisService()
    kline_service = KlineDataService()

    # 4/7股票数据用于PDF分析
    today_stock_data = {
        'stock_id': stock_id,
        'stock_name': stock_data['stock_name'],
        'trade_date': trade_date,
        'open_price': stock_data['open_price'],
        'high_price': stock_data['high_price'],
        'low_price': stock_data['low_price'],
        'close_price': stock_data['close_price'],
        'pre_close': None,
        'pct_chg': stock_data['pct_chg'],
        'change_amount': None,
        'volume': stock_data['volume'],
        'amount': stock_data['amount'],
        'limit_up': stock_data['limit_up'],
        'is_leader': stock_data['is_leader'],
        'rank_order': stock_data['rank_order'],
        'subject_key': stock_data['subject_key']
    }

    # 进行PDF框架强势股分析
    strong_analysis = await strong_service.analyze_stock_by_pdf_framework(
        stock_id,
        trade_date,
        today_stock_data
    )

    print(f"强势股分析结果:")
    print(f"  是否为强势股: {'✅ 是' if strong_analysis['is_strong_stock'] else '❌ 否'}")
    print(f"  总体评分: {strong_analysis['overall_score']}/100")

    # 打印关键维度评分
    for dim_name in ['是否正宗', '是否领涨', '龙头属性']:
        dim_data = strong_analysis['dimensions'].get(dim_name, {})
        print(f"  {dim_name}: {dim_data.get('score', 0)}分")

    # 7. K线缺口支撑分析
    print(f"\nK线缺口支撑分析...")
    gap_analysis = await kline_service.analyze_gap_support(stock_id, trade_date)

    if gap_analysis.get('has_gap'):
        print(f"  发现缺口: {gap_analysis.get('gap_type', '')}, 大小: {gap_analysis.get('gap_size', 0):.2f}%")

    if gap_analysis.get('has_support'):
        print(f"  发现支撑位: {gap_analysis.get('support_type', '')}, 强度: {gap_analysis.get('support_strength', 0):.1f}")

    if gap_analysis.get('technical_signals'):
        for signal in gap_analysis.get('technical_signals', [])[:3]:
            print(f"  技术信号: {signal}")

    # 8. 检查前一日是否弱势（4/6数据）
    prev_day_weak = False
    weak_reasons = []

    if prev_stock_data:
        prev_pct_chg = float(prev_stock_data['pct_chg'])
        if prev_pct_chg < -2.0:
            prev_day_weak = True
            weak_reasons.append(f"大阴线下跌{prev_pct_chg:.2f}%")

    # 9. 判断是否有弱转强潜力（基于4/7数据，需考虑次日可能转强）
    print(f"\n弱转强潜力分析:")
    print(f"  前一日弱势: {prev_day_weak} ({', '.join(weak_reasons) if weak_reasons else '无'})")
    print(f"  当前弱势: {float(stock_data['pct_chg']) < -2.0} ({stock_data['pct_chg']}%)")
    print(f"  支撑位: {gap_analysis.get('has_support', False)}")

    # 计算信号强度和置信度（基于当天数据，预测次日可能转强）
    screener = RealDatabaseScreener()

    # 假设次日可能转强（因为神剑股份4/8确实涨停）
    # 在实际筛选中，我们无法知道次日会涨停，所以这里只是验证
    next_day_pct_chg = 10.03  # 实际4/8的涨幅
    next_day_strong = next_day_pct_chg > 0 and next_day_pct_chg > float(stock_data['pct_chg']) + 3.0

    signal_strength = screener._calculate_weak_to_strong_strength(
        float(stock_data['pct_chg']) if stock_data['pct_chg'] else None,
        next_day_pct_chg,  # 使用实际的次日涨幅
        prev_day_weak,
        next_day_strong,
        gap_analysis,
        strong_analysis['overall_score'],
        None, None  # 无详细K线数据
    )

    confidence = screener._calculate_weak_to_strong_confidence(
        float(stock_data['pct_chg']) if stock_data['pct_chg'] else None,
        next_day_pct_chg,  # 使用实际的次日涨幅
        gap_analysis,
        strong_analysis['overall_score'],
        strong_analysis['is_strong_stock']
    )

    print(f"\n弱转强信号计算结果（基于实际次日涨幅10.03%）:")
    print(f"  信号强度: {signal_strength:.1f}/100")
    print(f"  置信度: {confidence:.1f}%")

    # 判断是否为潜在的弱转强候选
    # 在实际筛选中，我们不知道次日会涨停，所以条件会不同
    # 这里使用实际数据来验证逻辑

    # 实际筛选条件（不知道次日数据）:
    # 1. 主题为主线
    # 2. 股票是强势股
    # 3. 前一日或当日弱势
    # 4. 有支撑位
    # 5. 技术形态显示弱势但到支撑

    is_potential_candidate = (
        is_main_theme and
        strong_analysis['is_strong_stock'] and
        (prev_day_weak or float(stock_data['pct_chg']) < -2.0) and
        gap_analysis.get('has_support', False) and
        gap_analysis.get('is_gap_support', False)
    )

    print(f"\n潜在弱转强候选判断（基于4/7数据）:")
    print(f"  1. 主题为主线: {is_main_theme} {'✅' if is_main_theme else '❌'}")
    print(f"  2. 股票是强势股: {strong_analysis['is_strong_stock']} {'✅' if strong_analysis['is_strong_stock'] else '❌'}")
    print(f"  3. 前一日或当日弱势: {prev_day_weak or float(stock_data['pct_chg']) < -2.0} {'✅' if prev_day_weak or float(stock_data['pct_chg']) < -2.0 else '❌'}")
    print(f"  4. 有支撑位: {gap_analysis.get('has_support', False)} {'✅' if gap_analysis.get('has_support', False) else '❌'}")
    print(f"  5. 是缺口支撑: {gap_analysis.get('is_gap_support', False)} {'✅' if gap_analysis.get('is_gap_support', False) else '❌'}")
    print(f"\n结论: {'✅ 是潜在弱转强候选' if is_potential_candidate else '❌ 非潜在弱转强候选'}")

    await conn.close()
    await strong_service.close()
    await kline_service.close()

    print(f"\n{'='*70}")
    print(f"神剑股份在4/7的实际表现:")
    print(f"  - 4/6: {prev_stock_data['pct_chg'] if prev_stock_data else 'N/A'}%")
    print(f"  - 4/7: {stock_data['pct_chg']}% (下跌)")
    print(f"  - 4/8: 10.03% (涨停)")
    print(f"  - 典型弱转强案例，但需要验证筛选逻辑是否能识别")
    return is_potential_candidate

if __name__ == "__main__":
    result = asyncio.run(check_shenjian_0407())
    print(f"\n测试结果: {'成功识别为潜在候选' if result else '未识别为潜在候选'}")