import asyncpg
import asyncio
import os

DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data_test"

async def apply_migration(sql_file):
    """应用SQL迁移文件"""
    try:
        with open(sql_file, 'r') as f:
            sql_content = f.read()

        conn = await asyncpg.connect(DATABASE_URL)
        print(f"应用迁移: {sql_file}")

        # 执行SQL
        await conn.execute(sql_content)

        print(f"✅ 完成: {sql_file}")
        await conn.close()

    except Exception as e:
        print(f"❌ 错误: {e}")

async def check_tables():
    """检查表是否存在"""
    conn = await asyncpg.connect(DATABASE_URL)

    tables = [
        'weak_to_strong_candidate_pool',
        'weak_to_strong_auction_signal',
        'stock_screening_strategy',
        'stock_screening_execution',
        'stock_screening_result',
        'subject_stock_daily_snapshot'
    ]

    for table in tables:
        exists = await conn.fetchval(
            'SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)',
            table
        )
        print(f"{table}: {'✅ 存在' if exists else '❌ 不存在'}")

    await conn.close()

async def main():
    print("=== 检查当前表状态 ===")
    await check_tables()

    print("\n=== 应用迁移 ===")

    # 应用弱转强表迁移
    w2s_file = "/Users/admin/Desktop/ai_theme_app/stock_service/database/migrations/add_weak_to_strong_tables.sql"
    if os.path.exists(w2s_file):
        await apply_migration(w2s_file)
    else:
        print(f"❌ 文件不存在: {w2s_file}")

    # 应用选股器表迁移
    screener_file = "/Users/admin/Desktop/ai_theme_app/stock_service/database/migrations/add_stock_screener_tables.sql"
    if os.path.exists(screener_file):
        await apply_migration(screener_file)
    else:
        print(f"❌ 文件不存在: {screener_file}")

    print("\n=== 迁移后表状态 ===")
    await check_tables()

if __name__ == '__main__':
    asyncio.run(main())