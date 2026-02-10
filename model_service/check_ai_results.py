#!/usr/bin/env python3
"""
查看AI处理结果
"""
import asyncpg
import asyncio
from datetime import datetime, timedelta

DB_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"

async def check_results():
    """检查结果"""
    print("🔍 AI处理结果检查")
    print("=" * 70)
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # 1. 总体统计
        print("\n📊 1. 总体统计:")
        
        total_events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        total_news = await conn.fetchval("SELECT COUNT(*) FROM news_raw")
        processed_news = await conn.fetchval("SELECT COUNT(*) FROM news_raw WHERE is_processed = TRUE")
        
        print(f"   事件总数: {total_events}")
        print(f"   新闻总数: {total_news}")
        print(f"   已处理新闻: {processed_news} ({processed_news/total_news*100:.1f}% 如果total_news>0 else 0%)")
        
        # 2. 今日AI处理结果
        print("\n🤖 2. 今日AI处理结果:")
        
        today_events = await conn.fetch("""
            SELECT 
                ne.id,
                ne.event_type,
                ne.direction,
                ne.confidence,
                LEFT(ne.summary, 60) as summary_short,
                array_to_string(ne.impact_industries, ', ') as industries,
                nr.title,
                TO_CHAR(ne.created_at, 'HH24:MI:SS') as time
            FROM news_event ne
            JOIN news_raw nr ON ne.news_id = nr.id
            WHERE DATE(ne.created_at) = CURRENT_DATE
            ORDER BY ne.created_at DESC
            LIMIT 10
        """)
        
        if today_events:
            print(f"   今日处理事件数: {len(today_events)}")
            for i, event in enumerate(today_events, 1):
                print(f"\n   [{i}] {event['time']} - {event['event_type']}")
                print(f"      标题: {event['title'][:50]}...")
                print(f"      方向: {event['direction']} ({event['confidence']}%置信度)")
                print(f"      影响行业: {event['industries'] or '无'}")
                print(f"      摘要: {event['summary_short']}...")
        else:
            print("   今日尚无AI处理事件")
        
        # 3. 事件类型分布
        print("\n📈 3. 事件类型分布:")
        
        event_stats = await conn.fetch("""
            SELECT 
                event_type,
                COUNT(*) as count,
                ROUND(AVG(confidence), 1) as avg_confidence,
                STRING_AGG(DISTINCT direction, ', ') as directions
            FROM news_event
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 8
        """)
        
        for stat in event_stats:
            print(f"   {stat['event_type']}: {stat['count']} 次")
            print(f"      平均置信度: {stat['avg_confidence']}%")
            print(f"      方向分布: {stat['directions']}")
        
        # 4. 待处理新闻
        print("\n⏳ 4. 待处理新闻:")
        
        pending_news = await conn.fetch("""
            SELECT 
                id,
                title,
                source,
                TO_CHAR(publish_time, 'YYYY-MM-DD HH24:MI') as time
            FROM news_raw
            WHERE is_processed = FALSE
            ORDER BY publish_time ASC
            LIMIT 5
        """)
        
        if pending_news:
            print(f"   待处理新闻数: {len(pending_news)} (只显示前5条)")
            for i, news in enumerate(pending_news, 1):
                print(f"   [{i}] {news['time']} - {news['source']}")
                print(f"      标题: {news['title'][:60]}...")
        else:
            print("   暂无待处理新闻")
        
        # 5. 建议
        print("\n💡 5. 建议:")
        
        if total_events == 0:
            print("   ⚠️  尚无事件数据，请运行事件提取器")
        elif pending_news:
            print(f"   ✅ 有{pending_news}条待处理新闻，可继续处理")
        else:
            print("   ✅ 所有新闻已处理完毕")
        
        if total_events > 0:
            # 计算平均置信度
            avg_confidence = await conn.fetchval("SELECT ROUND(AVG(confidence), 1) FROM news_event")
            print(f"   📊 平均置信度: {avg_confidence}%")
            
            if avg_confidence < 70:
                print("   ⚠️  平均置信度较低，考虑优化提示词")
    
    finally:
        await conn.close()
    
    print("\n" + "=" * 70)
    print("检查完成！")

if __name__ == "__main__":
    asyncio.run(check_results())
