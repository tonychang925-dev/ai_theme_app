#!/usr/bin/env python3
"""
详细分析神剑股份 (002361) 在4月7日和4月3日的条件
"""
import asyncio
import sys
import os
from datetime import date, timedelta
import asyncpg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from stock_service.services.kline_data_service import KlineDataService

async def analyze_stock(stock_id: str, analysis_date: date):
    print(f"\n{'='*80}")
    print(f"详细分析 {stock_id} 在 {analysis_date}")
    print(f"{'='*80}")

    # 连接数据库
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }
    conn = await asyncpg.connect(**config)

    try:
        # 获取当日数据
        query = """
        SELECT stock_id, stock_name, pct_chg, open_price, high_price, low_price, close_price,
               volume, amount, limit_up, subject_key
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        ORDER BY rank_order ASC
        LIMIT 1
        """
        row = await conn.fetchrow(query, stock_id, analysis_date)
        if not row:
            print(f"未找到 {stock_id} 在 {analysis_date} 的数据")
            return

        stock_data = dict(row)
        stock_data['trade_date'] = analysis_date

        # 条件1: 当日弱势下跌 (<-2.0%)
        pct_chg = float(stock_data['pct_chg'])
        print(f"1. 当日弱势下跌: {pct_chg:.1f}% {'✅' if pct_chg < -2.0 else '❌'} (<-2.0%)")

        # 条件2: 前一天也弱势下跌 (<-1.5%)
        prev_date = analysis_date - timedelta(days=1)
        prev_query = """
        SELECT pct_chg FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        ORDER BY rank_order ASC
        LIMIT 1
        """
        prev_row = await conn.fetchrow(prev_query, stock_id, prev_date)
        prev_weak = False
        if prev_row and prev_row['pct_chg'] is not None:
            prev_pct_chg = float(prev_row['pct_chg'])
            prev_weak = prev_pct_chg < -1.5
            print(f"2. 前一天弱势下跌: {prev_pct_chg:.1f}% {'✅' if prev_weak else '❌'} (<-1.5%)")
        else:
            print(f"2. 前一天数据缺失: ❌")

        # 条件3: 真正强势股 (使用涨停模式分析)
        strong_analysis_service = StrongStockAnalysisService()
        limit_up_pattern = await strong_analysis_service._analyze_limit_up_pattern(
            stock_id, analysis_date, trading_days=7
        )
        has_limit_up = limit_up_pattern['has_limit_up_pattern']
        limit_up_count = limit_up_pattern['limit_up_count']
        max_consecutive = limit_up_pattern['max_consecutive_days']
        pattern_type = limit_up_pattern['pattern_type']

        is_real_strong = (max_consecutive >= 2) or (limit_up_count >= 2)
        print(f"3. 真正强势股分析:")
        print(f"   涨停模式: {pattern_type}")
        print(f"   涨停次数: {limit_up_count}, 最大连续: {max_consecutive}")
        print(f"   是否真正强势 (连续>=2或次数>=2): {'✅' if is_real_strong else '❌'}")

        # 判断是否需要缺口支撑
        def requires_gap_support(limit_up_pattern):
            max_consecutive = limit_up_pattern.get('max_consecutive_days', 0)
            limit_up_count = limit_up_pattern.get('limit_up_count', 0)
            if max_consecutive >= 3:
                return True
            if limit_up_count >= 4:
                return True
            return False

        requires_gap = requires_gap_support(limit_up_pattern)
        print(f"   是否需要缺口支撑 (连续>=3或次数>=4): {'✅' if requires_gap else '❌'}")

        # 条件4: 严格支撑位
        kline_service = KlineDataService()
        gap_analysis = await kline_service.analyze_gap_support(stock_id, analysis_date)

        has_gap_support = gap_analysis.get('is_gap_support', False)
        has_support = gap_analysis.get('has_support', False)
        support_strength = gap_analysis.get('support_strength', 0.0)
        support_level = gap_analysis.get('support_level', 0.0)
        gap_support_level = gap_analysis.get('gap_support_level', 0.0)
        support_type = gap_analysis.get('support_type', '')

        print(f"4. 支撑位分析:")
        print(f"   有支撑: {has_support}, 类型: {support_type}")
        print(f"   支撑强度: {support_strength:.1f} (需要>=0.6)")
        print(f"   缺口支撑: {has_gap_support}, 缺口支撑位: {gap_support_level:.2f}")

        # 检查支撑有效性
        has_valid_support = False
        if has_gap_support:
            if support_strength >= 0.6:
                has_valid_support = True
                print(f"   ✅ 严格缺口支撑有效")
            else:
                print(f"   ❌ 缺口支撑强度不足")
        elif has_support:
            if support_strength >= 0.6:
                if requires_gap:
                    print(f"   ❌ 需要缺口支撑但未检测到")
                else:
                    has_valid_support = True
                    print(f"   ✅ 严格{support_type}支撑有效")
            else:
                print(f"   ❌ 支撑强度不足")
        else:
            print(f"   ❌ 无有效支撑位")

        # 弱转强条件综合
        is_weak_to_strong = (pct_chg < -2.0 and prev_weak and is_real_strong and has_valid_support)
        print(f"\n综合弱转强条件:")
        print(f"  当日弱势下跌: {'✅' if pct_chg < -2.0 else '❌'}")
        print(f"  前一天弱势下跌: {'✅' if prev_weak else '❌'}")
        print(f"  真正强势股: {'✅' if is_real_strong else '❌'}")
        print(f"  有效支撑位: {'✅' if has_valid_support else '❌'}")
        print(f"  {'✅ 符合弱转强条件' if is_weak_to_strong else '❌ 不符合弱转强条件'}")

        # 显示技术信号
        tech_signals = gap_analysis.get('technical_signals', [])
        if tech_signals:
            print(f"\n技术信号:")
            for signal in tech_signals[:3]:  # 最多显示3个
                print(f"   • {signal}")

    finally:
        await conn.close()
        print(f"\n数据库连接已关闭")

async def main():
    stock_id = "002361"
    dates = [date(2026, 4, 7), date(2026, 4, 3)]

    for d in dates:
        await analyze_stock(stock_id, d)

if __name__ == "__main__":
    asyncio.run(main())