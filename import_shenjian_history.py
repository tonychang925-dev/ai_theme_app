#!/usr/bin/env python3
"""
导入神剑股份缺失的历史数据到数据库
重点导入3/26-3/31连续涨停数据
"""
import asyncio
import asyncpg
import json
from datetime import date
import sys
import os

async def import_missing_data():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "stock_data_test",
        "user": "postgres",
        "password": "zxbzj~925"
    }

    conn = await asyncpg.connect(**config)

    # 关键日期：需要导入的数据
    critical_dates = [
        date(2026, 3, 26),
        date(2026, 3, 27),
        date(2026, 3, 30),
        date(2026, 3, 31)
    ]

    # 读取JSONL文件数据
    jsonl_path = "/Users/admin/Desktop/ai_theme_app/theme_data_complete/_stock_kline/tushare/daily_bar/002361.SZ.jsonl"

    print(f"读取JSONL文件: {jsonl_path}")
    records = []

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                trade_date_str = data.get('trade_date')
                if not trade_date_str:
                    continue

                # 检查是否在关键日期范围内
                trade_date = date.fromisoformat(trade_date_str)
                if trade_date in critical_dates:
                    records.append((trade_date, data))
            except json.JSONDecodeError:
                print(f"JSON解析错误: {line[:100]}")
                continue

    print(f"找到 {len(records)} 条关键日期记录")

    for trade_date, data in sorted(records, key=lambda x: x[0]):
        print(f"\n处理日期: {trade_date}")
        print(f"  数据: {data}")

        # 检查数据是否已在数据库中
        check_query = """
        SELECT COUNT(*) as count
        FROM subject_stock_daily_snapshot
        WHERE stock_id = $1 AND trade_date = $2
        """
        count = await conn.fetchval(check_query, '002361', trade_date)

        if count > 0:
            print(f"  数据已存在，跳过")
            continue

        # 获取股票名称（从其他日期获取）
        stock_name_query = """
        SELECT stock_name FROM subject_stock_daily_snapshot
        WHERE stock_id = '002361' AND stock_name IS NOT NULL
        LIMIT 1
        """
        stock_name_row = await conn.fetchrow(stock_name_query)
        stock_name = stock_name_row['stock_name'] if stock_name_row else '神剑股份'

        # 获取主题信息（从其他日期获取）
        theme_query = """
        SELECT subject_key FROM subject_stock_daily_snapshot
        WHERE stock_id = '002361' AND subject_key IS NOT NULL
        LIMIT 1
        """
        theme_row = await conn.fetchrow(theme_query)
        subject_key = theme_row['subject_key'] if theme_row else 'unknown_theme'

        # 判断是否为涨停
        pct_chg = float(data.get('pct_chg', 0))
        is_limit_up = pct_chg >= 9.9

        # 判断是否为龙头（需要根据实际情况，这里简化为涨停且涨幅大于9.9%）
        # 真正的龙头判断需要更复杂逻辑
        is_leader = is_limit_up

        # 计算排名顺序（涨停股通常排名靠前）
        rank_order = 1 if is_limit_up else 999

        # 准备插入数据
        insert_query = """
        INSERT INTO subject_stock_daily_snapshot (
            stock_id, stock_name, trade_date, pct_chg, is_leader,
            rank_order, subject_key, open_price, high_price, low_price,
            close_price, volume, amount, limit_up
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        """

        try:
            await conn.execute(
                insert_query,
                '002361',  # stock_id
                stock_name,  # stock_name
                trade_date,  # trade_date
                pct_chg,  # pct_chg
                is_leader,  # is_leader
                rank_order,  # rank_order
                subject_key,  # subject_key
                float(data.get('open_price', 0)),  # open_price
                float(data.get('high_price', 0)),  # high_price
                float(data.get('low_price', 0)),  # low_price
                float(data.get('close_price', 0)),  # close_price
                float(data.get('volume', 0)),  # volume
                float(data.get('amount', 0)),  # amount
                is_limit_up  # limit_up
            )
            print(f"  ✅ 插入成功")
        except Exception as e:
            print(f"  ❌ 插入失败: {e}")

    # 验证导入结果
    print(f"\n验证导入结果:")
    for trade_date in critical_dates:
        verify_query = """
        SELECT trade_date, pct_chg, limit_up, is_leader
        FROM subject_stock_daily_snapshot
        WHERE stock_id = '002361' AND trade_date = $1
        """
        row = await conn.fetchrow(verify_query, trade_date)
        if row:
            pct = float(row['pct_chg'])
            print(f"  {trade_date}: 涨跌幅{pct:.1f}%, 涨停{'✅是' if pct >= 9.9 else '❌否'}, 龙头{'✅是' if row['is_leader'] else '❌否'}")
        else:
            print(f"  {trade_date}: ❌ 数据缺失")

    # 统计连续涨停
    print(f"\n统计连续涨停情况:")
    stats_query = """
    SELECT trade_date, pct_chg
    FROM subject_stock_daily_snapshot
    WHERE stock_id = '002361' AND trade_date >= '2026-03-20' AND trade_date <= '2026-04-10'
    ORDER BY trade_date
    """
    rows = await conn.fetch(stats_query)

    consecutive = 0
    max_consecutive = 0
    for row in rows:
        pct = float(row['pct_chg'])
        date_str = row['trade_date'].strftime("%Y-%m-%d")
        if pct >= 9.9:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
            print(f"  {date_str}: ✅ 涨停 ({pct:.1f}%), 连续{consecutive}天")
        else:
            consecutive = 0
            print(f"  {date_str}: ❌ 未涨停 ({pct:.1f}%)")

    print(f"\n最长连续涨停: {max_consecutive}天")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(import_missing_data())