#!/usr/bin/env python3
"""
验证model_service修复
"""
import asyncio
import aiohttp
import json

async def verify_model_service():
    print("🔧 验证model_service修复")
    print("=" * 60)
    
    # 使用我们刚测试成功的news_id
    test_news = [{
        "news_id": "04702f6ddebf7c76935ddaecb73e3aa4",  # 已确认存在的
        "title": "国家发布人工智能发展规划，千亿资金支持AI产业",
        "content": "国务院近日印发《新一代人工智能发展规划》，明确未来五年将投入超过1000亿元资金，重点支持AI核心算法、芯片等关键技术研发...",
        "source": "akshare_cls",
        "publish_date": "2024-01-05"
    }]
    
    print(f"📤 发送测试新闻:")
    print(f"   news_id: {test_news[0]['news_id'][:10]}...")
    print(f"   标题: {test_news[0]['title']}")
    
    try:
        async with aiohttp.ClientSession() as session:
            print(f"\n🌐 调用model_service API...")
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": test_news},
                timeout=15
            ) as response:
                print(f"📥 收到响应: HTTP {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ API成功:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    # 检查数据库
                    await check_database()
                else:
                    print(f"❌ API失败: {response.status}")
                    text = await response.text()
                    print(f"   响应内容: {text[:200]}")
                    
    except Exception as e:
        print(f"❌ 请求失败: {e}")

async def check_database():
    """检查数据库结果"""
    print(f"\n🔍 检查数据库...")
    
    import asyncpg
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查看最新事件
        events = await conn.fetch("""
            SELECT 
                ne.id as event_id,
                ne.news_id as news_raw_id,
                nr.news_id as hash_id,
                ne.event_type,
                ne.impact_industries,
                ne.direction,
                ne.confidence,
                ne.summary,
                ne.created_at,
                nr.title as news_title
            FROM news_event ne
            JOIN news_raw nr ON ne.news_id = nr.id
            WHERE nr.news_id = '04702f6ddebf7c76935ddaecb73e3aa4'
            ORDER BY ne.created_at DESC
            LIMIT 3
        """)
        
        if events:
            print(f"📊 找到 {len(events)} 条相关事件:")
            for event in events:
                print(f"\n  事件ID: {event['event_id']}")
                print(f"  新闻ID: {event['news_raw_id']} (哈希: {event['hash_id'][:10]}...)")
                print(f"  事件类型: {event['event_type']}")
                print(f"  方向: {event['direction']}")
                print(f"  置信度: {event['confidence']}")
                print(f"  摘要: {event['summary'][:50]}...")
                print(f"  创建时间: {event['created_at']}")
        else:
            print("⚠️  未找到相关事件记录")
            print("  可能原因:")
            print("  1. model_service尚未处理完成")
            print("  2. AI分析未返回有效事件")
            print("  3. 事件保存失败")
        
        # 查看model_service的日志输出
        print(f"\n📋 请查看model_service控制台输出:")
        print("  应该看到: '找到news_raw.id: 801 for hash: 04702f6dde...'")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")

if __name__ == "__main__":
    asyncio.run(verify_model_service())
