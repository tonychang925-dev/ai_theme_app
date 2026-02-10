#!/usr/bin/env python3
"""
终极测试 - 全面测试服务
"""
import asyncio
import aiohttp
import json
import sys

async def test_service():
    """测试服务"""
    print("🎯 AI事件抽取服务 - 终极测试")
    print("=" * 60)
    
    # 等待服务启动
    await asyncio.sleep(2)
    
    # 1. 测试健康检查
    print("1️⃣ 测试健康检查...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8001/health",
                timeout=5
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"   ✅ 健康检查通过: {result.get('status')}")
                else:
                    print(f"   ❌ 健康检查失败: {response.status}")
                    return False
    except Exception as e:
        print(f"   ❌ 健康检查异常: {e}")
        return False
    
    # 2. 测试事件处理
    print("\n2️⃣ 测试事件处理API...")
    
    test_news = [{
        "news_id": "04702f6ddebf7c76935ddaecb73e3aa4",
        "title": "国家发布人工智能发展规划，千亿资金支持AI产业",
        "content": "国务院近日印发《新一代人工智能发展规划》，明确未来五年将投入超过1000亿元资金支持人工智能产业发展...",
        "source": "akshare_cls", 
        "publish_date": "2024-01-05"
    }]
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": test_news},
                timeout=10
            ) as response:
                print(f"   📥 响应状态: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"   ✅ API调用成功:")
                    print(f"     状态: {result.get('status')}")
                    print(f"     消息: {result.get('message')}")
                    
                    # 等待处理完成
                    print(f"\n   ⏳ 等待处理完成...")
                    await asyncio.sleep(3)
                    
                    # 检查数据库
                    await check_database()
                    return True
                    
                else:
                    text = await response.text()
                    print(f"   ❌ API调用失败: {text[:200]}")
                    return False
                    
    except Exception as e:
        print(f"   ❌ API调用异常: {e}")
        return False

async def check_database():
    """检查数据库"""
    print("\n3️⃣ 检查数据库结果...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 检查news_raw
        news_raw = await conn.fetchrow(
            "SELECT id, news_id FROM news_raw WHERE news_id = $1",
            "04702f6ddebf7c76935ddaecb73e3aa4"
        )
        
        if not news_raw:
            print("   ⚠️ 未找到news_raw记录，可能需要先运行新闻收集器")
            await conn.close()
            return
        
        print(f"   📊 找到news_raw记录:")
        print(f"     ID: {news_raw['id']}")
        
        # 检查news_event
        events = await conn.fetch("""
            SELECT id, event_type, direction, confidence, summary, created_at 
            FROM news_event 
            WHERE news_id = $1
            ORDER BY created_at DESC
            LIMIT 3
        """, news_raw['id'])
        
        if events:
            print(f"   ✅ 成功创建事件 ({len(events)} 个):")
            for event in events:
                print(f"     • [{event['event_type']}] {event['direction']} ({event['confidence']:.2f})")
                print(f"       {event['summary'][:60]}...")
        else:
            print("   ⚠️ 该新闻还没有事件记录")
        
        # 查看总数
        total = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        print(f"   📈 当前news_event表总数: {total}")
        
        await conn.close()
        
    except Exception as e:
        print(f"   ❌ 数据库检查失败: {e}")

async def cleanup():
    """清理测试数据"""
    print("\n4️⃣ 清理测试数据...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 删除测试事件
        deleted = await conn.fetchval("""
            DELETE FROM news_event 
            WHERE summary LIKE '%测试%' 
            OR summary LIKE '%AI政策%'
            RETURNING COUNT(*)
        """)
        
        if deleted:
            print(f"   🧹 清理了 {deleted} 条测试记录")
        else:
            print("   ✅ 无需清理")
        
        await conn.close()
        
    except Exception as e:
        print(f"   ⚠️ 清理失败: {e}")

if __name__ == "__main__":
    print("开始测试...")
    success = asyncio.run(test_service())
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 测试成功！服务运行正常")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ 测试失败！请检查服务")
        print("=" * 60)
        sys.exit(1)
