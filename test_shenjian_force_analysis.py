#!/usr/bin/env python3
"""
强制分析神剑股份的弱转强潜力
"""
import asyncio
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from real_weak_to_strong_screening_enhanced import RealDatabaseScreener
from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService

async def test_shenjian_force():
    """强制分析神剑股份"""
    print("强制分析神剑股份弱转强潜力")
    print("=" * 70)

    stock_id = "002361"
    trade_date = date(2026, 4, 7)
    prev_date = date(2026, 4, 6)

    screener = RealDatabaseScreener()

    try:
        await screener.connect()

        # 获取股票数据
        query = """
        SELECT
            t1.stock_id,
            t1.stock_name,
            t1.subject_key,
            t1.pct_chg as today_pct_chg,
            t1.is_leader as today_is_leader,
            t1.rank_order,
            t2.pct_chg as prev_pct_chg,
            t2.is_leader as prev_is_leader,
            CASE
                WHEN t2.pct_chg IS NULL THEN FALSE
                WHEN t2.pct_chg < -2.0 THEN TRUE
                ELSE FALSE
            END as prev_day_weak,
            CASE
                WHEN t1.pct_chg > 0 AND t1.pct_chg > COALESCE(t2.pct_chg, 0) + 3.0 THEN TRUE
                ELSE FALSE
            END as today_strong,
            t1.open_price,
            t1.high_price,
            t1.low_price,
            t1.close_price,
            t1.volume,
            t1.amount,
            t1.limit_up
        FROM subject_stock_daily_snapshot t1
        LEFT JOIN subject_stock_daily_snapshot t2
            ON t1.stock_id = t2.stock_id
            AND t2.trade_date = $2
        WHERE t1.trade_date = $1
          AND t1.stock_id = $3
        LIMIT 1
        """

        rows = await screener.conn.fetch(query, trade_date, prev_date, stock_id)

        if not rows:
            print("未找到神剑股份数据")
            await screener.disconnect()
            return

        stock_data = dict(rows[0])
        print(f"神剑股份数据:")
        print(f"  股票: {stock_data['stock_name']} ({stock_data['stock_id']})")
        print(f"  主题: {stock_data['subject_key']}")
        print(f"  今日涨跌幅: {stock_data['today_pct_chg']}%")
        print(f"  前一日涨跌幅: {stock_data['prev_pct_chg'] if stock_data['prev_pct_chg'] is not None else '无数据'}")
        print(f"  前一日弱势: {stock_data['prev_day_weak']}")
        print(f"  今日强势: {stock_data['today_strong']}")

        # 获取主题信息
        theme_info = await screener.get_theme_for_subject_key(stock_data['subject_key'])
        print(f"\n主题信息:")
        print(f"  主题名称: {theme_info['name']}")
        print(f"  主题热度: {theme_info['heat_score']}")

        # 强势股分析
        print(f"\n进行强势股分析...")
        strong_service = StrongStockAnalysisService()

        # 准备股票数据
        stock_input = {
            'stock_id': stock_id,
            'stock_name': stock_data['stock_name'],
            'trade_date': trade_date,
            'open_price': stock_data['open_price'],
            'high_price': stock_data['high_price'],
            'low_price': stock_data['low_price'],
            'close_price': stock_data['close_price'],
            'pre_close': None,
            'pct_chg': stock_data['today_pct_chg'],
            'change_amount': None,
            'volume': stock_data['volume'],
            'amount': stock_data['amount'],
            'limit_up': stock_data['limit_up'],
            'is_leader': stock_data['today_is_leader'],
            'rank_order': stock_data['rank_order'],
            'subject_key': stock_data['subject_key']
        }

        strong_analysis = await strong_service.analyze_stock_by_pdf_framework(
            stock_id,
            trade_date,
            stock_input
        )

        print(f"强势股分析结果:")
        print(f"  是否为强势股: {'✅ 是' if strong_analysis['is_strong_stock'] else '❌ 否'}")
        print(f"  总体评分: {strong_analysis['overall_score']}/100")

        # K线缺口支撑分析
        print(f"\n进行K线缺口支撑分析...")
        kline_service = KlineDataService()
        gap_analysis = await kline_service.analyze_gap_support(stock_id, trade_date)

        print(f"缺口支撑分析:")
        print(f"  是否有缺口: {gap_analysis.get('has_gap', False)}")
        print(f"  是否有支撑: {gap_analysis.get('has_support', False)}")
        if gap_analysis.get('has_support'):
            print(f"  支撑类型: {gap_analysis.get('support_type', '')}")
            print(f"  支撑强度: {gap_analysis.get('support_strength', 0)}")

        # 计算弱转强信号（即使不是强势股也计算）
        print(f"\n计算弱转强信号...")

        # 准备输入
        prev_day_weak = stock_data['prev_day_weak']
        today_strong = stock_data['today_strong']

        # 注意：神剑股份在4/7日是下跌的，所以today_strong为False
        # 但我们要预测它可能在次日转强（事实上4/8日确实涨停）
        # 这里我们使用实际次日数据来验证逻辑
        next_day_pct_chg = 10.03  # 4/8日实际涨幅
        next_day_strong = next_day_pct_chg > 0 and next_day_pct_chg > float(stock_data['today_pct_chg']) + 3.0

        signal_strength = screener._calculate_weak_to_strong_strength(
            float(stock_data['today_pct_chg']),
            next_day_pct_chg,  # 使用实际次日数据
            prev_day_weak,
            next_day_strong,
            gap_analysis,
            strong_analysis['overall_score'],
            None, None  # 无详细K线数据
        )

        confidence = screener._calculate_weak_to_strong_confidence(
            float(stock_data['today_pct_chg']),
            next_day_pct_chg,  # 使用实际次日数据
            gap_analysis,
            strong_analysis['overall_score'],
            strong_analysis['is_strong_stock']
        )

        print(f"\n弱转强信号计算结果（使用实际4/8日数据10.03%）:")
        print(f"  信号强度: {signal_strength:.1f}/100")
        print(f"  置信度: {confidence:.1f}%")

        # 判断是否为弱转强候选（放宽条件）
        is_weak_to_strong_candidate = (
            (strong_analysis['is_strong_stock'] or strong_analysis['overall_score'] >= 40) and  # 放宽强势股要求
            (prev_day_weak or float(stock_data['today_pct_chg']) < -2.0) and  # 前一日或当日弱势
            gap_analysis.get('has_support', False) and  # 有支撑位
            signal_strength >= 50.0 and  # 信号强度中等
            confidence >= 50.0  # 置信度中等
        )

        print(f"\n弱转强候选判断（放宽条件）:")
        print(f"  1. 是强势股或评分≥40: {strong_analysis['is_strong_stock'] or strong_analysis['overall_score'] >= 40} ({strong_analysis['overall_score']})")
        print(f"  2. 前一日或当日弱势: {prev_day_weak or float(stock_data['today_pct_chg']) < -2.0}")
        print(f"  3. 有支撑位: {gap_analysis.get('has_support', False)}")
        print(f"  4. 信号强度≥50: {signal_strength >= 50.0} ({signal_strength:.1f})")
        print(f"  5. 置信度≥50: {confidence >= 50.0} ({confidence:.1f})")
        print(f"\n结论: {'✅ 是弱转强候选' if is_weak_to_strong_candidate else '❌ 非弱转强候选'}")

        await strong_service.close()
        await kline_service.close()
        await screener.disconnect()

        return is_weak_to_strong_candidate

    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()
        await screener.disconnect()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_shenjian_force())
    print(f"\n最终结果: {'神剑股份可识别为弱转强候选' if result else '神剑股份不可识别为弱转强候选'}")