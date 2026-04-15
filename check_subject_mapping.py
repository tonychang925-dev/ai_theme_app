#!/usr/bin/env python3
"""
检查主题映射表
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
        # 1. 检查subject_key_map表
        print("\n1. 检查subject_key_map表:")
        try:
            map_rows = await conn.fetch("""
                SELECT subject_key, subject_name
                FROM subject_key_map
                LIMIT 20
            """)

            if map_rows:
                print(f"   找到{len(map_rows)}条映射记录:")
                for i, row in enumerate(map_rows, 1):
                    print(f"   {i}. 键: {row['subject_key']} -> 名称: {row['subject_name']}")
            else:
                print(f"   subject_key_map表为空")

                # 检查表是否存在
                table_check = await conn.fetch("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'subject_key_map'
                    )
                """)
                print(f"   subject_key_map表存在: {table_check[0]['exists']}")
        except Exception as e:
            print(f"   查询subject_key_map表失败: {e}")

        # 2. 检查theme_master表结构
        print(f"\n2. 检查theme_master表结构:")
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'theme_master'
            ORDER BY ordinal_position
        """)

        if columns:
            print(f"   theme_master表有{len(columns)}列:")
            for col in columns[:15]:  # 只显示前15列
                print(f"     {col['column_name']}: {col['data_type']}")
        else:
            print(f"   theme_master表不存在或无列")

        # 3. 检查theme_master表中的实际数据
        print(f"\n3. 检查theme_master表中的实际数据:")
        try:
            theme_rows = await conn.fetch("""
                SELECT *
                FROM theme_master
                WHERE status = 'active'
                ORDER BY heat_score DESC
                LIMIT 5
            """)

            if theme_rows:
                print(f"   找到{len(theme_rows)}条活跃主题记录")
                for i, row in enumerate(theme_rows, 1):
                    print(f"   {i}. ID: {row.get('id', 'N/A')}")
                    print(f"      名称: {row.get('name', 'N/A')}")
                    print(f"      热度: {row.get('heat_score', 'N/A')}")
                    print(f"      状态: {row.get('status', 'N/A')}")

                    # 尝试查找任何可能包含subject_key的字段
                    for key in ['subject_key', 'subject_id', 'key', 'code']:
                        if key in row:
                            print(f"      {key}: {row[key]}")
            else:
                print(f"   theme_master表中无活跃主题")
        except Exception as e:
            print(f"   查询theme_master表数据失败: {e}")

        # 4. 检查subject_detail表
        print(f"\n4. 检查subject_detail表:")
        try:
            detail_rows = await conn.fetch("""
                SELECT subject_key, subject_name, subject_type
                FROM subject_detail
                LIMIT 10
            """)

            if detail_rows:
                print(f"   找到{len(detail_rows)}条主题详情记录:")
                for i, row in enumerate(detail_rows, 1):
                    print(f"   {i}. 键: {row['subject_key']} -> 名称: {row['subject_name']} ({row.get('subject_type', 'N/A')})")
            else:
                print(f"   subject_detail表为空")
        except Exception as e:
            print(f"   查询subject_detail表失败: {e}")

    finally:
        await conn.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    asyncio.run(main())