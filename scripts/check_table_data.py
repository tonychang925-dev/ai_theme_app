#!/usr/bin/env python3
"""快速检查数据库表数据"""

import asyncio
import asyncpg
import sys
from datetime import date
from stock_service.config import StockServiceConfig


async def check_table_data():
    config = StockServiceConfig()

    try:
        conn = await asyncpg.connect(
            host=config.postgres_host,
            port=config.postgres_port,
            database=config.postgres_database,
            user=config.postgres_user,
            password=config.postgres_password
        )

        print("📊 数据库表数据检查")
        print("="*60)

        tables = [
            "theme_cycle_judgement",
            "theme_cycle_judgement_v2",
            "theme_cycle_evidence_daily",
            "weak_to_strong_candidate_pool",
            "theme_master",
            "subject_stock_daily_snapshot"
        ]

        for table in tables:
            # 检查表是否存在
            exists_sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = $1
            )
            """
            exists = await conn.fetchval(exists_sql, table)

            if exists:
                # 获取行数
                count_sql = f"SELECT COUNT(*) FROM {table}"
                count = await conn.fetchval(count_sql)

                # 获取最近日期
                date_sql = f"""
                SELECT MAX(trade_date) as latest_date,
                       MIN(trade_date) as earliest_date
                FROM {table}
                WHERE trade_date IS NOT NULL
                """
                try:
                    date_row = await conn.fetchrow(date_sql)
                    latest = date_row["latest_date"] if date_row and date_row["latest_date"] else "N/A"
                    earliest = date_row["earliest_date"] if date_row and date_row["earliest_date"] else "N/A"
                except:
                    latest = "N/A"
                    earliest = "N/A"

                print(f"📋 {table}:")
                print(f"   ✓ 存在")
                print(f"   📈 行数: {count}")
                if latest != "N/A":
                    print(f"   📅 日期范围: {earliest} 到 {latest}")

                # 如果是证据或判定表，显示一些样本
                if table in ["theme_cycle_judgement", "theme_cycle_judgement_v2"] and count > 0:
                    sample_sql = f"""
                    SELECT subject_key, trade_date, is_main_theme, primary_cycle_stage, is_fade
                    FROM {table}
                    ORDER BY trade_date DESC
                    LIMIT 3
                    """
                    try:
                        samples = await conn.fetch(sample_sql)
                        print(f"   🧪 最近样本:")
                        for sample in samples:
                            subject = sample["subject_key"]
                            tdate = sample["trade_date"]
                            is_main = sample.get("is_main_theme", "N/A")
                            stage = sample.get("primary_cycle_stage", "N/A")
                            is_fade = sample.get("is_fade", "N/A")
                            print(f"      • {tdate} {subject}: 主线={is_main}, 阶段={stage}, 退潮={is_fade}")
                    except Exception as e:
                        print(f"   ⚠ 无法获取样本: {e}")

            else:
                print(f"📋 {table}:")
                print(f"   ❌ 不存在")

            print()

        await conn.close()

    except Exception as e:
        print(f"❌ 数据库连接错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_table_data())