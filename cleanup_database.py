# ai_theme_app/cleanup_database.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.database import DatabaseManager, init_database

async def cleanup():
    await init_database()
    
    async with (await DatabaseManager.get_pool()).acquire() as conn:
        # 删除source为NULL的记录
        deleted = await conn.execute("DELETE FROM news_raw WHERE source IS NULL")
        print(f"清理了 {deleted.split()[-1]} 条source为NULL的记录")
        
        # 重新统计
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT source) as source_count,
                COUNT(DISTINCT news_id) as unique_news
            FROM news_raw
        """)
        
        print(f"\n📊 清理后数据库状态:")
        print(f"   总记录数: {stats['total']}")
        print(f"   数据源数量: {stats['source_count']}")
        print(f"   唯一新闻数: {stats['unique_news']}")
        
        # 各源统计
        dist = await conn.fetch("""
            SELECT source, COUNT(*) as count 
            FROM news_raw 
            GROUP BY source 
            ORDER BY count DESC
        """)
        
        print(f"\n📈 数据源分布:")
        for row in dist:
            print(f"   {row['source']}: {row['count']} 条")

if __name__ == "__main__":
    asyncio.run(cleanup())