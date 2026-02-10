#!/usr/bin/env python3
"""
测试真实AI分析
"""
import asyncio
import aiohttp
import json

async def test_real_ai():
    """测试真实AI分析能力"""
    print("🧠 测试真实AI事件分析")
    print("=" * 60)
    
    # 使用真实的新闻数据
    test_news = [
        {
            "news_id": "test_ai_news_001",
            "title": "国家发改委发布人工智能产业支持政策，明确千亿资金扶持计划",
            "content": "国家发展和改革委员会今日发布《人工智能产业发展三年行动计划》，计划在未来三年投入超过1000亿元资金支持AI芯片、算法框架、应用场景等关键领域的发展。政策明确了对人工智能企业的税收优惠、研发补贴和人才引进支持措施。",
            "source": "gov_policy",
            "publish_date": "2024-01-15"
        },
        {
            "news_id": "test_ai_news_002", 
            "title": "宁德时代发布2023年财报：净利润同比增长45%，动力电池出货量全球第一",
            "content": "宁德时代发布2023年度财务报告，公司实现营业收入3285亿元，同比增长42%；净利润412亿元，同比增长45%。动力电池出货量达到289GWh，连续七年位居全球第一。公司宣布将加大固态电池研发投入。",
            "source": "company_report",
            "publish_date": "2024-01-15"
        },
        {
            "news_id": "test_ai_news_003",
            "title": "微软与OpenAI宣布深化战略合作，将投资100亿美元开发下一代AI系统",
            "content": "微软和OpenAI宣布达成新的战略合作协议，微软将追加投资100亿美元用于开发下一代人工智能系统。双方将在AI芯片、云基础设施、企业应用等多个领域展开深度合作，共同推动AGI技术发展。",
            "source": "tech_news", 
            "publish_date": "2024-01-15"
        }
    ]
    
    print(f"📰 测试新闻:")
    for i, news in enumerate(test_news):
        print(f"  {i+1}. {news['title'][:50]}...")
    
    print(f"\n🚀 发送AI分析请求...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": test_news},
                timeout=15
            ) as response:
                print(f"📥 响应状态: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ API响应:")
                    print(f"  状态: {result.get('status')}")
                    print(f"  消息: {result.get('message')}")
                    
                    print(f"\n⏳ 等待AI分析完成...")
                    await asyncio.sleep(5)
                    
                    # 检查数据库结果
                    await check_ai_results()
                    
                else:
                    text = await response.text()
                    print(f"❌ API失败: {text[:200]}")
                    
    except Exception as e:
        print(f"❌ 请求异常: {e}")

async def check_ai_results():
    """检查AI分析结果"""
    print("\n🔍 检查AI分析结果...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查看最新事件（按时间倒序）
        events = await conn.fetch("""
            SELECT id, news_id, event_type, impact_industries, direction, 
                   confidence, summary, created_at 
            FROM news_event 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        if events:
            print(f"📊 最新 {len(events)} 个事件:")
            for event in events:
                industries = event['impact_industries'] or []
                industry_str = industries[0] if industries else "通用"
                
                print(f"\n   [{event['event_type']}] {industry_str}行业")
                print(f"   方向: {event['direction']}, 置信度: {event['confidence']:.2f}")
                print(f"   摘要: {event['summary'][:60]}...")
                print(f"   时间: {event['created_at'].strftime('%H:%M:%S')}")
        else:
            print("⚠️  没有找到事件记录")
        
        # 事件类型分布
        print(f"\n📈 事件类型分布:")
        type_stats = await conn.fetch("""
            SELECT event_type, COUNT(*) as count 
            FROM news_event 
            GROUP BY event_type 
            ORDER BY count DESC
        """)
        
        for stat in type_stats:
            print(f"   {stat['event_type']}: {stat['count']} 个")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")

async def cleanup_test_data():
    """清理测试数据"""
    print("\n🧹 清理测试数据...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        deleted = await conn.fetchval("""
            DELETE FROM news_event 
            WHERE summary LIKE '%测试%' 
            OR summary LIKE '%test_ai_news%'
            RETURNING COUNT(*)
        """)
        
        if deleted:
            print(f"✅ 清理了 {deleted} 条测试记录")
        else:
            print("✅ 无需清理")
        
        await conn.close()
        
    except Exception as e:
        print(f"⚠️ 清理失败: {e}")

if __name__ == "__main__":
    print("开始真实AI分析测试...\n")
    asyncio.run(test_real_ai())
    asyncio.run(cleanup_test_data())
    
    print("\n" + "=" * 60)
    print("🎯 测试完成！请查看上面的AI分析结果")
    print("=" * 60)
