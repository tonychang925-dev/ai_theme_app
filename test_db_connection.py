#!/usr/bin/env python3
"""
测试数据库连接
"""
import asyncio
import asyncpg
import os
from datetime import date

async def test_db():
    print("测试数据库连接...")

    # 尝试从环境变量获取连接信息
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")
    db_user = os.getenv("DB_USER", "admin")
    db_password = os.getenv("DB_PASSWORD", "")

    print(f"连接参数: host={db_host}, port={db_port}, db={db_name}, user={db_user}")

    try:
        conn = await asyncpg.connect(
            host=db_host,
            port=int(db_port),
            database=db_name,
            user=db_user,
            password=db_password,
            timeout=10
        )
        print("✅ 数据库连接成功")

        # 测试查询
        print("\n测试weak_to_strong_candidate_pool表...")
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM weak_to_strong_candidate_pool")
            print(f"总记录数: {count}")

            # 查询2026-04-07的数据
            rows = await conn.fetch("""
                SELECT trade_date, next_trade_date, stock_id, candidate_score
                FROM weak_to_strong_candidate_pool
                WHERE trade_date = $1 OR next_trade_date = $1
                LIMIT 5
            """, date(2026, 4, 7))

            print(f"2026-04-07相关记录数: {len(rows)}")
            for row in rows:
                print(f"  stock_id={row['stock_id']}, trade_date={row['trade_date']}, next_trade_date={row['next_trade_date']}, score={row['candidate_score']}")

        except Exception as e:
            print(f"查询表失败: {e}")
            # 检查表是否存在
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            print(f"可用表: {[t['table_name'] for t in tables[:10]]}")

        await conn.close()
        print("\n✅ 数据库测试完成")

    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_db())
