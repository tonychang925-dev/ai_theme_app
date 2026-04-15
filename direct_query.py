#!/usr/bin/env python3
"""
直接查询数据库，检查神剑股份数据
"""
import asyncio
from datetime import date
import asyncpg
from stock_service.config import StockServiceConfig

async def main():
    print("📊 直接查询神剑股份数据库记录")
    print("=" * 60)

    config = StockServiceConfig()
    test_date = date(2026, 4, 7)

    conn = None
    try:
        # 连接数据库
        conn = await asyncpg.connect(
            host=config.postgres_host,
            port=config.postgres_port,
            database=config.postgres_database,
            user=config.postgres_user,
            password=config.postgres_password
        )

        # 1. 检查神剑股份在 subject_stock_daily_snapshot 中
        print("1️⃣ 检查 subject_stock_daily_snapshot 表...")
        sql1 = """
        SELECT stock_id, stock_name, subject_key, pct_chg, limit_up, is_leader, rank_order
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND (stock_id LIKE '%002361%' OR stock_name LIKE '%神剑%')
        """
        rows1 = await conn.fetch(sql1, test_date)

        if rows1:
            print(f"✅ 找到 {len(rows1)} 条记录:")
            for row in rows1:
                print(f"  stock_id: {row['stock_id']}")
                print(f"  stock_name: {row['stock_name']}")
                print(f"  subject_key: {row['subject_key']}")
                print(f"  pct_chg: {row['pct_chg']}")
                print(f"  limit_up: {row['limit_up']}")
                print(f"  is_leader: {row['is_leader']}")
                print(f"  rank_order: {row['rank_order']}")
        else:
            print("❌ 在 subject_stock_daily_snapshot 中未找到神剑股份")

        # 2. 检查主题判断表
        print("\n2️⃣ 检查 theme_mainline_judgement 表...")
        if rows1:
            subject_key = rows1[0]['subject_key'] if rows1 else ''
            sql2 = """
            SELECT subject_key, is_main_theme
            FROM theme_mainline_judgement
            WHERE trade_date = $1::date AND subject_key = $2
            """
            rows2 = await conn.fetch(sql2, test_date, subject_key)

            if rows2:
                print(f"✅ 找到主题判断记录:")
                for row in rows2:
                    print(f"  subject_key: {row['subject_key']}")
                    print(f"  is_main_theme: {row['is_main_theme']}")
            else:
                print(f"❌ 主题 '{subject_key}' 在 theme_mainline_judgement 中无记录")

        # 3. 检查主题周期判断表
        print("\n3️⃣ 检查 theme_cycle_judgement 表...")
        if rows1:
            sql3 = """
            SELECT subject_key, primary_cycle_stage, action_bias, is_divergence,
                   is_rebound, is_fermentation, is_fade
            FROM theme_cycle_judgement
            WHERE trade_date = $1::date AND subject_key = $2
            """
            rows3 = await conn.fetch(sql3, test_date, subject_key)

            if rows3:
                print(f"✅ 找到主题周期判断记录:")
                for row in rows3:
                    print(f"  subject_key: {row['subject_key']}")
                    print(f"  primary_cycle_stage: {row['primary_cycle_stage']}")
                    print(f"  action_bias: {row['action_bias']}")
                    print(f"  is_divergence: {row['is_divergence']}")
                    print(f"  is_rebound: {row['is_rebound']}")
                    print(f"  is_fermentation: {row['is_fermentation']}")
                    print(f"  is_fade: {row['is_fade']}")
            else:
                print(f"❌ 主题 '{subject_key}' 在 theme_cycle_judgement 中无记录")

        # 4. 检查涨停记录
        print("\n4️⃣ 检查近期涨停记录...")
        sql4 = """
        SELECT COUNT(*) as count
        FROM subject_stock_daily_snapshot
        WHERE split_part(stock_id, '.', 1) = '002361'
          AND trade_date <= $1::date
          AND trade_date > $1::date - INTERVAL '30 days'
          AND COALESCE(limit_up, FALSE) = TRUE
        """
        count = await conn.fetchval(sql4, test_date)
        print(f"  30天内涨停次数: {count}")

        # 5. 检查前一日数据
        print("\n5️⃣ 检查前一日数据...")
        sql5 = """
        SELECT pct_chg, limit_up
        FROM subject_stock_daily_snapshot
        WHERE split_part(stock_id, '.', 1) = '002361'
          AND trade_date < $1::date
        ORDER BY trade_date DESC
        LIMIT 1
        """
        prev_row = await conn.fetchrow(sql5, test_date)
        if prev_row:
            print(f"  前一日涨跌幅: {prev_row['pct_chg']}")
            print(f"  前一日是否涨停: {prev_row['limit_up']}")
        else:
            print("  未找到前一日数据")

    except Exception as e:
        print(f"❌ 数据库查询错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()

    print("\n" + "=" * 60)
    print("查询完成")

if __name__ == "__main__":
    asyncio.run(main())