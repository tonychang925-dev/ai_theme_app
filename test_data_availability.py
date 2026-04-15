#!/usr/bin/env python3
"""测试数据可用性检查脚本"""

import asyncio
import sys
from datetime import date
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.check_data_availability import DataAvailabilityChecker

async def main():
    test_date = date(2026, 4, 7)
    print(f"测试数据可用性检查，日期: {test_date}")

    checker = DataAvailabilityChecker()
    try:
        results = await checker.check_all_tables(test_date)

        # 打印关键信息
        print("\n=== 关键检查结果 ===")

        # 表状态
        print("\n1. 表状态:")
        table_status = results.get("table_status", {})
        for table, info in table_status.items():
            print(f"  {table}: {'✅存在' if info.get('exists') else '❌缺失'} ({info.get('status')})")

        # 总体状态
        overall = results.get("overall_status", {})
        print(f"\n2. 总体状态: {overall.get('status', 'unknown')}")

        if overall.get('critical_tables_missing'):
            print(f"   关键表缺失: {overall['critical_tables_missing']}")

        # 建议
        recommendations = overall.get('recommendations', [])
        if recommendations:
            print(f"\n3. 建议:")
            for rec in recommendations:
                print(f"   {rec}")

    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await checker.close()

if __name__ == "__main__":
    asyncio.run(main())