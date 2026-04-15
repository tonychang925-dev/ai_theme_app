#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.theme_cycle_evidence_builder import ThemeCycleEvidenceBuilder

async def main():
    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)

    builder = ThemeCycleEvidenceBuilder()
    try:
        print(f"开始构建 {test_date} 的周期证据...")
        evidence_list = await builder.build_evidence_for_date(test_date)
        print(f"完成构建 {len(evidence_list)} 个证据")

        # 打印前几个证据
        for i, evidence in enumerate(evidence_list[:5], 1):
            print(f"{i}. 主题 {evidence.subject_key} ({evidence.theme_name})")
            print(f"   事件强度: {evidence.event_strength_score}, 事件连续性: {evidence.event_continuity_score}")
            print(f"   龙头存活: {evidence.leader_alive_score}, 接力强度: {evidence.relay_strength_score}")
            print(f"   涨停数: {evidence.limit_up_count}, 跌停数: {evidence.limit_down_count}")
            print(f"   前一日状态: {evidence.previous_cycle_state}")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())