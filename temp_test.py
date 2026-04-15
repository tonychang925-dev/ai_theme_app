import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test():
    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)
    try:
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f'总记录数: {len(rows)}')
        found = False
        for row in rows:
            if '002361' in str(row.get('stock_id', '')) or '002361' in str(row.get('stock_code', '')):
                found = True
                print('找到神剑股份:')
                print(f'  stock_id: {row.get("stock_id")}')
                print(f'  stock_code: {row.get("stock_code")}')
                print(f'  stock_name: {row.get("stock_name")}')
                print(f'  is_main_theme: {row.get("is_main_theme")}')
                print(f'  is_fade: {row.get("is_fade")}')
                break
        if not found:
            print('未找到神剑股份')
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())