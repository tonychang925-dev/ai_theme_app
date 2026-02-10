#!/usr/bin/env python3
"""
不自动清理的测试 - 让AI服务有时间处理
"""
import asyncio
import aiohttp
import json
import asyncpg
from datetime import date

async def insert_and_test():
    """插入测试新闻并等待AI处理"""
    print("🎯 测试AI服务（不自动清理）")
    print("=" * 60)
    
    conn = None
    try:
        # 1. 连接数据库
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 2. 插入测试新闻
        test_news_data = [
            {
                "news_id": "no_cleanup_test_001",
                "title": "国家发布人工智能产业支持政策",
                "content": "国家发布人工智能产业支持政策，投入千亿资金",
                "source": "test",
                "publish_date": date(2024, 1, 15)
            }
        ]
        
        print("📝 插入测试新闻...")
        result = await conn.fetchrow("""
            INSERT INTO news_raw 
            (news_id, title, content, source, publish_date, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id
        """,
            test_news_data[0]["news_id"],
            test_news_data[0]["title"],
            test_news_data[0]["content"],
            test_news_data[0]["source"],
            test_news_data[0]["publish_date"]
        )
        
        news_id = result['id']
        print(f"✅ 插入成功! ID: {news_id}")
        
        await conn.close()
        
        # 3. 调用AI服务
        print(f"\n🚀 调用AI服务...")
        
        # 准备API调用数据
        api_news = [{
            "news_id": "no_cleanup_test_001",
            "title": "国家发布人工智能产业支持政策",
            "content": "国家发布人工智能产业支持政策，投入千亿资金",
            "source": "test",
            "publish_date": "2024-01-15"
        }]
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": api_news},
                timeout=15
            ) as response:
                print(f"📥 AI服务响应: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 服务接受请求: {result.get('message')}")
                    
                    # 4. 等待足够长时间
                    print(f"\n⏳ 等待AI处理完成...")
                    for i in range(1, 11):
                        await asyncio.sleep(1)
                        print(f"   等待 {i} 秒...")
                    
                    # 5. 检查结果
                    await check_results()
                    
                else:
                    text = await response.text()
                    print(f"❌ 服务调用失败: {text[:200]}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn and not conn.is_closed():
            await conn.close()

async def check_results():
    """检查结果"""
    print(f"\n🔍 检查AI处理结果...")
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查找我们的测试新闻
        news = await conn.fetchrow("""
            SELECT id, news_id, title FROM news_raw 
            WHERE news_id = 'no_cleanup_test_001'
        """)
        
        if not news:
            print("❌ 测试新闻不存在（可能被清理了）")
            return
        
        print(f"✅ 测试新闻存在: ID={news['id']}")
        
        # 查找相关事件
        events = await conn.fetch("""
            SELECT id, event_type, direction, confidence, summary, created_at
            FROM news_event 
            WHERE news_id = $1
            ORDER BY created_at DESC
        """, news['id'])
        
        if events:
            print(f"🎯 找到 {len(events)} 个事件:")
            for event in events:
                print(f"\n   📊 事件详情:")
                print(f"     事件ID: {event['id']}")
                print(f"     类型: {event['event_type']}")
                print(f"     方向: {event['direction']}")
                print(f"     置信度: {event['confidence']:.2f}")
                print(f"     摘要: {event['summary']}")
                print(f"     时间: {event['created_at'].strftime('%H:%M:%S')}")
        else:
            print("⚠️  没有找到事件（AI处理可能失败）")
            
            # 检查服务日志
            print(f"\n🔍 可能的原因:")
            print(f"   1. AI服务没有正确处理请求")
            print(f"   2. 数据库连接问题")
            print(f"   3. AI提取器内部错误")
            
            # 查看news_event表总数
            total = await conn.fetchval("SELECT COUNT(*) FROM news_event")
            print(f"\n   📈 news_event表总数: {total}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")

async def manual_cleanup():
    """手动清理"""
    print(f"\n🧹 手动清理测试数据...")
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 先删事件
        deleted_events = await conn.execute("""
            DELETE FROM news_event 
            WHERE news_id IN (
                SELECT id FROM news_raw WHERE news_id = 'no_cleanup_test_001'
            )
        """)
        
        # 再删新闻
        deleted_news = await conn.execute("""
            DELETE FROM news_raw WHERE news_id = 'no_cleanup_test_001'
        """)
        
        print(f"✅ 清理完成")
        
        await conn.close()
        
    except Exception as e:
        print(f"⚠️  清理失败: {e}")

if __name__ == "__main__":
    print("开始测试（不自动清理）...\n")
    asyncio.run(insert_and_test())
    
    # 询问是否清理
    print("\n" + "=" * 60)
    choice = input("是否清理测试数据？(y/n): ")
    if choice.lower() == 'y':
        asyncio.run(manual_cleanup())
    
    print("=" * 60)
    print("🎯 测试完成")
    print("=" * 60)
