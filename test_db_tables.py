import asyncpg
import asyncio

async def test_db():
    try:
        conn = await asyncpg.connect('postgresql://postgres:zxbzj~925@localhost/stock_data_test')

        # 检查表
        tables = ['weak_to_strong_candidate_pool', 'weak_to_strong_auction_signal', 'subject_stock_daily_snapshot']
        for table in tables:
            exists = await conn.fetchval('SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)', table)
            print(f'{table} 表存在: {exists}')

            if exists:
                count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
                print(f'  {table} 记录数: {count}')

                # 如果是weak_to_strong_candidate_pool，检查神剑股份
                if table == 'weak_to_strong_candidate_pool':
                    rows = await conn.fetch("SELECT * FROM weak_to_strong_candidate_pool WHERE stock_id LIKE '%002361%'")
                    print(f'  神剑股份记录数: {len(rows)}')
                    for row in rows[:3]:
                        print(f'    trade_date: {row["trade_date"]}, next_trade_date: {row["next_trade_date"]}, candidate_score: {row["candidate_score"]}')

        # 检查subject_stock_daily_snapshot在2026-04-07的数据
        count = await conn.fetchval("SELECT COUNT(*) FROM subject_stock_daily_snapshot WHERE trade_date='2026-04-07'::date")
        print(f'subject_stock_daily_snapshot 在2026-04-07的记录数: {count}')

        await conn.close()
    except Exception as e:
        print(f'错误: {e}')

if __name__ == '__main__':
    asyncio.run(test_db())