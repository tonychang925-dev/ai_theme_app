#!/usr/bin/env python3
"""
检查测试环境状态
"""
import sys
import os
import asyncio
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
service_dir = current_dir
sys.path.insert(0, service_dir)

from config import DatabaseConfig, RedisConfig, DatabaseType
from managers.postgres_manager import PostgresDatabaseManager


async def check_database_status():
    """检查数据库状态"""
    databases = [
        ("stock_data", "生产数据库"),
        ("stock_data_test", "测试数据库")
    ]
    
    print("🔍 检查数据库环境状态")
    print("=" * 60)
    
    for db_name, description in databases:
        print(f"\n📊 检查 {description} ({db_name})...")
        
        try:
            config = DatabaseConfig(
                db_type=DatabaseType.POSTGRESQL,
                postgres_host="localhost",
                postgres_port=5432,
                postgres_database=db_name,
                postgres_username="postgres",
                postgres_password="",
                table_names_config={
                    "theme_master": "theme_master",
                    "news_raw": "news_raw",
                    "news_event": "news_event"
                },
                redis=RedisConfig(enabled=False)
            )
            
            manager = PostgresDatabaseManager(config)
            await manager.connect()
            
            try:
                # 检查连接
                healthy = await manager.health_check()
                if healthy:
                    print(f"  ✅ 连接状态: 健康")
                else:
                    print(f"  ⚠️  连接状态: 异常")
                
                # 检查表和数据
                async with manager.pool.acquire() as conn:
                    # 检查表
                    tables = await conn.fetch("""
                        SELECT table_name, COUNT(*) as row_count
                        FROM information_schema.tables 
                        WHERE table_schema = 'public'
                        AND table_name IN ('theme_master', 'news_raw', 'news_event', 'financial_categories')
                        GROUP BY table_name
                        ORDER BY table_name
                    """)
                    
                    if tables:
                        print(f"  📋 找到 {len(tables)} 个相关表:")
                        for table in tables:
                            print(f"    - {table['table_name']}: {table['row_count']:,} 行")
                    else:
                        print(f"  ⚠️  未找到相关表")
                    
                    # 检查测试数据
                    test_data = await conn.fetchval("""
                        SELECT COUNT(*) FROM (
                            SELECT 1 FROM theme_master WHERE source_system LIKE '%test%'
                            UNION ALL
                            SELECT 1 FROM news_raw WHERE source LIKE '%test%'
                        ) t
                    """)
                    
                    if test_data > 0:
                        print(f"  ⚠️  发现 {test_data} 条测试数据")
                    else:
                        print(f"  ✅ 无测试数据污染")
                
            finally:
                await manager.disconnect()
                
        except Exception as e:
            print(f"  ❌ 连接失败: {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    print("✅ 环境检查完成")


async def clean_test_database():
    """清理测试数据库"""
    print("\n🧹 清理测试数据库...")
    
    try:
        config = DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host="localhost",
            postgres_port=5432,
            postgres_database="stock_data_test",
            postgres_username="postgres",
            postgres_password="",
            table_names_config={
                "theme_master": "theme_master",
                "news_raw": "news_raw",
                "news_event": "news_event",
                "event_theme_map": "event_theme_map",
                "financial_categories": "financial_categories"
            },
            redis=RedisConfig(enabled=False)
        )
        
        manager = PostgresDatabaseManager(config)
        await manager.connect()
        
        try:
            async with manager.pool.acquire() as conn:
                # 清理所有测试数据
                deleted_counts = await conn.fetch("""
                    SELECT 
                        (SELECT COUNT(*) FROM theme_master WHERE source_system LIKE '%test%') as test_themes,
                        (SELECT COUNT(*) FROM news_raw WHERE source LIKE '%test%') as test_news,
                        (SELECT COUNT(*) FROM news_event WHERE event_type LIKE '%test%') as test_events,
                        (SELECT COUNT(*) FROM financial_categories WHERE category_code LIKE '%TEST%') as test_categories
                """)
                
                counts = deleted_counts[0]
                total_test = sum(counts.values())
                
                if total_test > 0:
                    print(f"  发现 {total_test} 条测试数据:")
                    if counts['test_themes'] > 0:
                        print(f"    - 主题: {counts['test_themes']} 条")
                    if counts['test_news'] > 0:
                        print(f"    - 新闻: {counts['test_news']} 条")
                    if counts['test_events'] > 0:
                        print(f"    - 事件: {counts['test_events']} 条")
                    if counts['test_categories'] > 0:
                        print(f"    - 分类: {counts['test_categories']} 条")
                    
                    # 执行清理
                    print("  开始清理...")
                    async with conn.transaction():
                        await conn.execute("DELETE FROM event_theme_map WHERE theme_id IN (SELECT id FROM theme_master WHERE source_system LIKE '%test%')")
                        await conn.execute("DELETE FROM news_event WHERE event_type LIKE '%test%'")
                        await conn.execute("DELETE FROM news_raw WHERE source LIKE '%test%'")
                        await conn.execute("DELETE FROM theme_master WHERE source_system LIKE '%test%'")
                        await conn.execute("DELETE FROM financial_categories WHERE category_code LIKE '%TEST%'")
                    
                    print("  ✅ 清理完成")
                else:
                    print("  ✅ 无测试数据需要清理")
                
        finally:
            await manager.disconnect()
            
    except Exception as e:
        print(f"  ❌ 清理失败: {e}")


async def main():
    """主函数"""
    print("🛠️  PostgreSQL测试环境检查工具")
    print("=" * 60)
    
    await check_database_status()
    await clean_test_database()
    
    print("\n🎉 所有检查完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
