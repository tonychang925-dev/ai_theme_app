#!/usr/bin/env python3
import asyncio
import sys
import os
from datetime import date

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from stock_service.services.weak_to_strong_auction_service import WeakToStrongAuctionService

async def main():
    trade_date = date(2026, 4, 8)
    print(f"测试弱转强竞价确认，交易日: {trade_date}")
    service = WeakToStrongAuctionService()
    try:
        # 设置超时
        result = await asyncio.wait_for(
            service.confirm(trade_date),
            timeout=30.0
        )
        print(f"确认成功: total_candidates={result.total_candidates}, persisted_count={result.persisted_count}")
        print(f"信号级别统计: {result.level_count}")
    except asyncio.TimeoutError:
        print("确认超时（30秒）")
    except Exception as e:
        print(f"确认失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await service.close()

if __name__ == "__main__":
    asyncio.run(main())
