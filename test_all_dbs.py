#!/usr/bin/env python3
"""
测试所有数据库
"""
import asyncio
import asyncpg
import os

async def test_all_dbs():
    # 尝试常见的数据库名
    db_names = ["postgres", "ai_theme", "ai_theme_app", "theme_app", "stock", "stock_service"]
    
    for db_name in db_names:
        print(f"\n尝试数据库: {db_name}")
        try:
            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                database=db_name,
                user="admin",
                password="",
                timeout=5
            )
            
            # 检查表
            tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            print(f"  表数量: {len(tables)}")
            
            # 检查是否有弱转强相关表
            w2s_tables = [t for t in tables if 'weak_to_strong' in t['table_name'].lower()]
            if w2s_tables:
                print(f"  弱转强相关表: {[t['table_name'] for t in w2s_tables]}")
                
                # 查询weak_to_strong_candidate_pool
                if any('candidate_pool' in t['table_name'].lower() for t in w2s_tables):
                    count = await conn.fetchval("SELECT COUNT(*) FROM weak_to_strong_candidate_pool")
                    print(f"  candidate_pool记录数: {count}")
            
            await conn.close()
            
        except Exception as e:
            print(f"  连接失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_dbs())
