#!/usr/bin/env python3
"""
测试适配后的集成
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_adapted():
    print("🧪 测试适配后的集成")
    print("=" * 60)
    
    # 测试数据 - 使用已存在的news_id
    test_news = [
        {
            "news_id": "test_001",  # 这个应该在news_raw表中存在
            "title": "测试适配架构 - AI政策利好",
            "content": "测试内容：国家发布AI支持政策...",
            "source": "test",
            "publish_date": "2024-01-05"
        }
    ]
    
    # 先检查news_raw表
    try:
        import asyncpg
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查找一条存在的news记录
        existing = await conn.fetchrow(
            "SELECT news_id, id FROM news_raw LIMIT 1"
        )
        
        if existing:
            test_news[0]["news_id"] = existing['news_id']
            print(f"✅ 使用存在的news_id: {existing['news_id']} (id: {existing['id']})")
        else:
            print("⚠️  news_raw表为空，无法测试关联")
            return
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")
        return
    
    # 调用model_service
    try:
        import aiohttp
        
        print("\n📤 调用model_service...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": test_news},
                timeout=15
            ) as response:
                result = await response.json()
                print(f"✅ API调用成功: {result}")
                
                # 等待处理
                print("⏳ 等待5秒...")
                await asyncio.sleep(5)
                
                # 检查结果
                await check_results()
                
    except Exception as e:
        print(f"❌ 测试失败: {e}")

async def check_results():
    """检查处理结果"""
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查看最新事件
        events = await conn.fetch("""
            SELECT ne.*, nr.title as news_title
            FROM news_event ne
            JOIN news_raw nr ON ne.news_id = nr.id
            ORDER BY ne.created_at DESC
            LIMIT 3
        """)
        
        if events:
            print(f"\n📊 最新 {len(events)} 条事件:")
            for i, event in enumerate(events, 1):
                print(f"  {i}. 新闻: {event['news_title'][:50]}...")
                print(f"     事件类型: {event['event_type']}")
                print(f"     影响行业: {event['impact_industries']}")
                print(f"     方向: {event['direction']}")
                print(f"     置信度: {event['confidence']}")
                print(f"     摘要: {event['summary'][:50]}...")
        else:
            print("\n⚠️  没有找到事件记录")
        
        # 统计
        total = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        print(f"\n📈 news_event表总计: {total} 条记录")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 检查结果失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_adapted())
