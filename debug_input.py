import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test():
    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)
    try:
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f'总记录数: {len(rows)}')

        # 打印所有股票，查找神剑股份
        for i, row in enumerate(rows):
            stock_id = str(row.get('stock_id', ''))
            stock_code = str(row.get('stock_code', ''))
            stock_name = str(row.get('stock_name', ''))

            if '002361' in stock_id or '002361' in stock_code or '神剑' in stock_name:
                print(f'\n找到神剑股份 (索引 {i}):')
                print(f'  stock_id: {stock_id}')
                print(f'  stock_code: {stock_code}')
                print(f'  stock_name: {stock_name}')
                print(f'  subject_key: {row.get("subject_key")}')
                print(f'  theme_name: {row.get("theme_name")}')
                print(f'  is_main_theme: {row.get("is_main_theme")}')
                print(f'  is_fade: {row.get("is_fade")}')
                print(f'  is_leader: {row.get("is_leader")}')
                print(f'  limit_up: {row.get("limit_up")}')
                print(f'  pct_chg: {row.get("pct_chg")}')
                print(f'  recent_limit_up_count: {row.get("recent_limit_up_count")}')

                # 尝试构建候选
                candidate = await builder._async_to_candidate(row, test_date, test_date)
                if candidate:
                    print(f'  ✅ 构建候选成功! 分数: {candidate.get("candidate_score")}')
                else:
                    print(f'  ❌ 构建候选失败')

        # 如果没有找到，打印前20条记录
        print('\n如果没有找到，前20条记录:')
        for i, row in enumerate(rows[:20]):
            print(f'{i+1}. {row.get("stock_id")} {row.get("stock_name")} - '
                  f'主题: {row.get("subject_key")}, '
                  f'is_main_theme: {row.get("is_main_theme")}, '
                  f'is_fade: {row.get("is_fade")}')

    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())