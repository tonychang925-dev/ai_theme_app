#!/usr/bin/env python3
"""
检查数据库中的实际数据
"""
import asyncio
import asyncpg
from datetime import date

async def main():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    print("连接数据库...")
    conn = await asyncpg.connect(**config)

    try:
        # 1. 检查表结构
        print("\n1. 检查subject_stock_daily_snapshot表结构:")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'subject_stock_daily_snapshot'
            ORDER BY ordinal_position
        """)

        for col in columns:
            print(f"   {col['column_name']}: {col['data_type']} ({'nullable' if col['is_nullable'] == 'YES' else 'not null'})")

        # 2. 检查2026-04-10日的数据
        trade_date = date(2026, 4, 10)
        print(f"\n2. 检查{trade_date}的股票数据:")

        rows = await conn.fetch("""
            SELECT *
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
            ORDER BY rank_order
            LIMIT 20
        """, trade_date)

        print(f"   找到{len(rows)}条记录")

        if rows:
            print(f"\n   前{min(len(rows), 10)}条记录:")
            for i, row in enumerate(rows[:10], 1):
                print(f"   {i}. {row.get('stock_id', 'N/A')} - {row.get('stock_name', 'N/A')}")
                print(f"      主题: {row.get('subject_key', 'N/A')}, 排名: {row.get('rank_order', 'N/A')}")
                print(f"      涨跌幅: {row.get('pct_chg', 'N/A')}%, 是否龙头: {row.get('is_leader', 'N/A')}")

        # 3. 检查是否有神剑股份
        print(f"\n3. 检查神剑股份(002361.SZ):")

        shenjian_rows = await conn.fetch("""
            SELECT *
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
            AND stock_id = $2
        """, trade_date, '002361.SZ')

        if shenjian_rows:
            print(f"   ✅ 找到神剑股份数据")
            row = shenjian_rows[0]
            print(f"      股票: {row.get('stock_id')} - {row.get('stock_name')}")
            print(f"      主题: {row.get('subject_key')}")
            print(f"      涨跌幅: {row.get('pct_chg')}%")
            print(f"      排名: {row.get('rank_order')}")
            print(f"      是否龙头: {row.get('is_leader')}")
        else:
            print(f"   ❌ 未找到神剑股份数据")

            # 检查所有股票中有没有神剑股份
            all_stocks = await conn.fetch("""
                SELECT DISTINCT stock_id, stock_name
                FROM subject_stock_daily_snapshot
                WHERE stock_name LIKE '%神剑%' OR stock_id LIKE '%002361%'
                LIMIT 10
            """)

            if all_stocks:
                print(f"   但在其他日期找到相关股票:")
                for stock in all_stocks:
                    print(f"      {stock['stock_id']} - {stock['stock_name']}")

        # 4. 检查theme_master表
        print(f"\n4. 检查theme_master表:")
        try:
            theme_master_rows = await conn.fetch("""
                SELECT id, name, subject_key, heat_score, status
                FROM theme_master
                WHERE status = 'active'
                ORDER BY heat_score DESC
                LIMIT 10
            """)

            if theme_master_rows:
                print(f"   theme_master表中有{len(theme_master_rows)}条活跃主题记录")
                for i, theme in enumerate(theme_master_rows, 1):
                    print(f"   {i}. ID: {theme['id']}, 名称: {theme['name']}, 主题键: {theme['subject_key']}, 热度: {theme['heat_score']}")
            else:
                print(f"   theme_master表为空或无活跃主题")
        except Exception as e:
            print(f"   查询theme_master表失败: {e}")

        # 5. 检查热点主题数据
        print(f"\n5. 检查热点主题:")
        theme_rows = await conn.fetch("""
            SELECT DISTINCT subject_key, COUNT(*) as stock_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1
            GROUP BY subject_key
            ORDER BY stock_count DESC
            LIMIT 10
        """, trade_date)

        for i, theme in enumerate(theme_rows, 1):
            print(f"   {i}. {theme['subject_key']}: {theme['stock_count']}只股票")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(main())