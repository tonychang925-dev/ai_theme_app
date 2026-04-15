#!/usr/bin/env python3
"""
清理神剑股份的重复数据
"""
import asyncio
import asyncpg
from datetime import date

async def clean_duplicates():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    stock_id = "002361"

    # 找出有重复记录的日期
    duplicate_query = """
    SELECT trade_date, COUNT(*) as record_count
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1
    GROUP BY trade_date
    HAVING COUNT(*) > 1
    ORDER BY trade_date
    """

    duplicate_rows = await conn.fetch(duplicate_query, stock_id)

    print(f"找到 {len(duplicate_rows)} 个有重复记录的日期")

    cleaned_count = 0
    for row in duplicate_rows:
        trade_date = row['trade_date']
        record_count = row['record_count']

        print(f"\n处理 {trade_date}: {record_count} 条记录")

        # 查看所有记录
        detail_query = """
        SELECT id, rank_order, pct_chg, open_price, high_price, low_price, close_price, is_leader, limit_up
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        ORDER BY rank_order ASC, pct_chg DESC
        """

        detail_rows = await conn.fetch(detail_query, stock_id, trade_date)

        # 显示详情
        for i, detail in enumerate(detail_rows):
            print(f"  记录{i+1}: rank_order={detail['rank_order']}, pct_chg={detail['pct_chg']:.1f}%, "
                  f"O{detail['open_price']:.2f} H{detail['high_price']:.2f} L{detail['low_price']:.2f} C{detail['close_price']:.2f}")

        # 策略：保留rank_order最小且为正值的记录，如果没有则保留pct_chg最大的
        # 先尝试找rank_order最小的正记录
        valid_records = [r for r in detail_rows if r['rank_order'] > 0]

        if valid_records:
            # 取rank_order最小的
            valid_records.sort(key=lambda x: x['rank_order'])
            record_to_keep = valid_records[0]
        else:
            # 如果没有正rank_order，取pct_chg最大的
            detail_rows.sort(key=lambda x: x['pct_chg'], reverse=True)
            record_to_keep = detail_rows[0]

        print(f"  保留记录: id={record_to_keep['id']}, rank_order={record_to_keep['rank_order']}")

        # 删除其他记录
        delete_query = """
        DELETE FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2 AND id != $3
        """

        deleted_count = await conn.execute(delete_query, stock_id, trade_date, record_to_keep['id'])
        cleaned_count += (record_count - 1)
        print(f"  删除 {record_count - 1} 条重复记录")

    # 修正4/7日数据（根据JSONL文件）
    print(f"\n修正4/7日数据...")
    correct_date = date(2026, 4, 7)

    # JSONL中的数据：开盘15.85, 最高16.47, 最低14.80, 收盘15.25
    update_query = """
    UPDATE subject_stock_daily_snapshot
    SET open_price = 15.85, high_price = 16.47, low_price = 14.80, close_price = 15.25
    WHERE stock_id = $1 AND trade_date = $2
    """

    updated = await conn.execute(update_query, stock_id, correct_date)
    print(f"  更新4/7日价格数据")

    # 验证清理结果
    print(f"\n验证清理结果:")
    verify_query = """
    SELECT trade_date, COUNT(*) as count
    FROM subject_stock_daily_snapshot
    WHERE stock_id = $1
    GROUP BY trade_date
    HAVING COUNT(*) > 1
    ORDER BY trade_date
    """

    remaining_duplicates = await conn.fetch(verify_query, stock_id)

    if remaining_duplicates:
        print(f"  仍有 {len(remaining_duplicates)} 个日期有重复记录")
        for row in remaining_duplicates:
            print(f"    {row['trade_date']}: {row['count']}条记录")
    else:
        print(f"  ✅ 所有重复记录已清理")

    print(f"\n总计: 清理了 {cleaned_count} 条重复记录")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(clean_duplicates())