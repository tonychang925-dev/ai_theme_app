#!/usr/bin/env python3
import asyncio
import asyncpg
from datetime import date

async def main():
    test_date = date(2026, 4, 7)
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='postgres',
        password='postgres', database='stock_data_test'
    )

    # 检查theme_cycle_judgement表的新增字段
    print(f"检查theme_cycle_judgement表的新增字段 (日期: {test_date})")

    # 获取表结构
    sql = """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'theme_cycle_judgement'
      AND column_name IN (
          'leader_stock_id', 'leader_stock_name', 'board_stock_count',
          'limit_down_count', 'red_ratio', 'big_drop_ratio',
          'front_row_strength_score', 'relay_strength_score', 'front_row_survival_ratio'
      )
    ORDER BY column_name
    """
    rows = await conn.fetch(sql)
    print(f"找到 {len(rows)} 个新增字段:")
    for row in rows:
        print(f"  {row['column_name']}: {row['data_type']} ({'可为空' if row['is_nullable'] == 'YES' else '非空'})")

    # 检查是否有数据
    sql = """
    SELECT
        COUNT(*) as total_rows,
        COUNT(leader_stock_id) as leader_stock_id_count,
        COUNT(leader_stock_name) as leader_stock_name_count,
        COUNT(board_stock_count) as board_stock_count_count
    FROM theme_cycle_judgement
    WHERE trade_date = $1
    """
    row = await conn.fetchrow(sql, test_date)
    print(f"\n数据统计 (日期: {test_date}):")
    print(f"  总行数: {row['total_rows']}")
    print(f"  leader_stock_id有值: {row['leader_stock_id_count']}")
    print(f"  leader_stock_name有值: {row['leader_stock_name_count']}")
    print(f"  board_stock_count有值: {row['board_stock_count_count']}")

    # 检查theme_mainline_judgement的新增字段
    print(f"\n检查theme_mainline_judgement表的新增字段")
    sql = """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'theme_mainline_judgement'
      AND column_name IN (
          'event_count_3d', 'event_count_7d',
          'strong_event_count_7d', 'event_recency_days'
      )
    ORDER BY column_name
    """
    rows = await conn.fetch(sql)
    print(f"找到 {len(rows)} 个新增字段:")
    for row in rows:
        print(f"  {row['column_name']}: {row['data_type']} ({'可为空' if row['is_nullable'] == 'YES' else '非空'})")

    # 检查是否有数据
    sql = """
    SELECT
        COUNT(*) as total_rows,
        COUNT(event_count_3d) as event_count_3d_count,
        COUNT(event_recency_days) as event_recency_days_count
    FROM theme_mainline_judgement
    WHERE trade_date = $1
    """
    row = await conn.fetchrow(sql, test_date)
    print(f"\n数据统计 (日期: {test_date}):")
    print(f"  总行数: {row['total_rows']}")
    print(f"  event_count_3d有值: {row['event_count_3d_count']}")
    print(f"  event_recency_days有值: {row['event_recency_days_count']}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())