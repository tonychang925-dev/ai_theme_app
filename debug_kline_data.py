#!/usr/bin/env python3
"""
调试K线数据获取问题
"""
import asyncio
from datetime import date, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.kline_data_service import KlineDataService

async def debug_kline_data():
    stock_ids = ["002335", "301236", "000034"]
    test_date = date(2026, 4, 7)

    service = KlineDataService()

    for stock_id in stock_ids:
        print(f"\n调试股票 {stock_id} - {test_date}")
        print("-" * 60)

        # 测试不同天数的数据获取
        for days in [5, 10, 20, 60]:
            try:
                kline_data = await service.get_kline_data(stock_id, test_date, days_before=days, days_after=0)
                print(f"  获取前{days:2d}天数据: {len(kline_data):3d}条")

                if len(kline_data) > 0:
                    # 显示最早和最晚的日期
                    dates = [d['trade_date'] for d in kline_data]
                    dates.sort()
                    print(f"    日期范围: {dates[0]} 到 {dates[-1]}")

                    # 检查是否有连续数据
                    expected_count = min(days, len(kline_data))
                    if len(kline_data) < days:
                        print(f"    ⚠️  数据不足: 期望{days}天，实际{len(kline_data)}天")

            except Exception as e:
                print(f"  获取前{days}天数据时出错: {e}")

        # 检查数据库中的总数据量
        try:
            conn = await service.get_connection()
            count_query = """
            SELECT COUNT(*) as total_count
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1
            """
            total_count = await conn.fetchval(count_query, stock_id)

            # 检查在测试日期之前的数据量
            before_query = """
            SELECT COUNT(*) as before_count
            FROM subject_stock_daily_snapshot
            WHERE stock_id = $1 AND trade_date <= $2
            """
            before_count = await conn.fetchval(before_query, stock_id, test_date)

            print(f"\n  数据库统计:")
            print(f"    总数据量: {total_count}条")
            print(f"    在{test_date}之前的数据: {before_count}条")

            # 检查数据表结构
            table_query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'subject_stock_daily_snapshot'
            ORDER BY ordinal_position
            """
            columns = await conn.fetch(table_query)
            print(f"    数据表列数: {len(columns)}")

            await service.release_connection(conn)

        except Exception as e:
            print(f"  数据库查询出错: {e}")

    await service.close()

async def main():
    print("调试K线数据获取问题")
    print("=" * 80)

    await debug_kline_data()

    print("\n" + "=" * 80)
    print("调试完成")

if __name__ == "__main__":
    asyncio.run(main())