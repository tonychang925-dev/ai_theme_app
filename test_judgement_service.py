#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.theme_cycle_judgement_service import ThemeCycleJudgementService

async def main():
    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)

    service = ThemeCycleJudgementService()
    try:
        print(f"开始执行 {test_date} 的主题周期判决...")
        judgements = await service.judge_all_themes_for_date(test_date)
        print(f"完成 {len(judgements)} 个主题的判决")

        # 打印前几个结果
        for i, judgement in enumerate(judgements[:10], 1):
            subject_key = judgement.get('subject_key', 'unknown')
            final_state = judgement.get('final_cycle_state', 'unknown')
            mainline_alive = judgement.get('final_mainline_alive', False)
            fade_watch = judgement.get('fade_watch', False)
            fade_confirmed = judgement.get('fade_confirmed', False)
            print(f"{i}. 主题 {subject_key}: {final_state} (主线存活: {mainline_alive}, 退潮观察: {fade_watch}, 退潮确认: {fade_confirmed})")
    finally:
        await service.close()

if __name__ == "__main__":
    asyncio.run(main())