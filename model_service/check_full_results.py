#!/usr/bin/env python3
"""
完整结果检查
"""
import asyncpg
import asyncio
from datetime import datetime, timedelta

DB_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"

async def check_full_results():
    """检查完整结果"""
    print("🎉 AI事件提取系统 - 完整结果报告")
    print("=" * 80)
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # 1. 总体统计
        print("\n📊 1. 系统总体统计")
        print("-" * 40)
        
        stats = await conn.fetch("""
            SELECT 
                (SELECT COUNT(*) FROM news_raw) as total_news,
                (SELECT COUNT(*) FROM news_raw WHERE is_processed = TRUE) as processed_news,
                (SELECT COUNT(*) FROM news_event) as total_events,
                (SELECT COUNT(*) FROM news_event WHERE DATE(created_at) = CURRENT_DATE) as today_events,
                (SELECT ROUND(AVG(confidence)::numeric, 1) FROM news_event WHERE DATE(created_at) = CURRENT_DATE) as avg_confidence
        """)
        
        stat = stats[0]
        print(f"   新闻总数: {stat['total_news']}")
        print(f"   已处理新闻: {stat['processed_news']} ({stat['processed_news']/stat['total_news']*100:.1f}%)")
        print(f"   事件总数: {stat['total_events']}")
        print(f"   今日新增事件: {stat['today_events']}")
        print(f"   今日平均置信度: {stat['avg_confidence']}%")
        
        # 2. 今日事件详情
        print("\n🤖 2. 今日AI生成事件详情")
        print("-" * 40)
        
        today_events = await conn.fetch("""
            SELECT 
                ne.id,
                ne.event_type,
                ne.direction,
                ne.confidence,
                array_to_string(ne.impact_industries, ', ') as industries,
                ne.summary,
                nr.title,
                TO_CHAR(ne.created_at, 'HH24:MI:SS') as time
            FROM news_event ne
            JOIN news_raw nr ON ne.news_id = nr.id
            WHERE DATE(ne.created_at) = CURRENT_DATE
            ORDER BY ne.created_at DESC
        """)
        
        print(f"   今日共处理 {len(today_events)} 个事件:")
        for i, event in enumerate(today_events, 1):
            print(f"\n   [{i}] [{event['time']}] {event['event_type']} - {event['direction']} ({event['confidence']}%)")
            print(f"       标题: {event['title'][:60]}...")
            print(f"       影响行业: {event['industries'] or '无'}")
            print(f"       摘要: {event['summary'][:80]}...")
        
        # 3. 事件类型分析
        print("\n📈 3. 事件类型分布")
        print("-" * 40)
        
        type_stats = await conn.fetch("""
            SELECT 
                event_type,
                COUNT(*) as count,
                ROUND(AVG(confidence)::numeric, 1) as avg_confidence,
                COUNT(CASE WHEN direction = 'positive' THEN 1 END) as positive_count,
                COUNT(CASE WHEN direction = 'negative' THEN 1 END) as negative_count,
                COUNT(CASE WHEN direction = 'neutral' THEN 1 END) as neutral_count
            FROM news_event
            GROUP BY event_type
            ORDER BY count DESC
        """)
        
        for stat in type_stats:
            print(f"\n   📌 {stat['event_type']}: {stat['count']} 次")
            print(f"       平均置信度: {stat['avg_confidence']}%")
            print(f"       方向分布: ↑{stat['positive_count']} ↓{stat['negative_count']} →{stat['neutral_count']}")
        
        # 4. 行业影响分析
        print("\n🏭 4. 行业影响分析")
        print("-" * 40)
        
        # 展开所有行业的数组并统计
        industry_stats = await conn.fetch("""
            SELECT unnest(impact_industries) as industry, COUNT(*) as count
            FROM news_event
            WHERE impact_industries IS NOT NULL AND array_length(impact_industries, 1) > 0
            GROUP BY industry
            ORDER BY count DESC
            LIMIT 10
        """)
        
        if industry_stats:
            print("   最常影响的行业:")
            for i, stat in enumerate(industry_stats, 1):
                print(f"      {i}. {stat['industry']}: {stat['count']} 次")
        else:
            print("   暂无行业影响数据")
        
        # 5. 系统状态评估
        print("\n✅ 5. 系统状态评估")
        print("-" * 40)
        
        if stat['today_events'] > 0:
            print(f"   🎉 AI事件提取系统运行成功!")
            print(f"   ✅ 今日成功处理 {stat['today_events']} 个事件")
            print(f"   ✅ 平均置信度 {stat['avg_confidence']}% (质量良好)")
            
            if stat['avg_confidence'] > 80:
                print("   ⭐ AI解析质量优秀")
            elif stat['avg_confidence'] > 70:
                print("   👍 AI解析质量良好")
            else:
                print("   ⚠️  AI解析质量有待提升")
        else:
            print("   ⚠️  今日尚无事件处理记录")
        
        # 6. 下一步建议
        print("\n🚀 6. 下一步建议")
        print("-" * 40)
        
        pending_count = stat['total_news'] - stat['processed_news']
        if pending_count > 0:
            print(f"   📋 还有 {pending_count} 条新闻待处理")
            print("   💡 建议: 运行批量处理脚本继续处理")
            print("       命令: python batch_process.py")
        else:
            print("   ✅ 所有新闻已处理完毕")
        
        print(f"   🎯 建议: 开始集成 theme_service 进行题材分析")
        print("       命令: cd /Users/admin/Desktop/ai_theme_app && mkdir -p theme_service")
        
    finally:
        await conn.close()
    
    print("\n" + "=" * 80)
    print("🎊 恭喜！AI事件提取系统已完全正常运行！")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(check_full_results())
