#!/usr/bin/env python3
"""
端到端测试：插入测试新闻 + AI分析
"""
import asyncio
import aiohttp
import json
import asyncpg
from datetime import datetime

async def insert_test_news():
    """插入测试新闻到news_raw表"""
    print("📝 插入测试新闻到数据库...")
    
    test_news_data = [
        {
            "news_id": "test_ai_policy_001",
            "title": "国家发改委发布人工智能产业支持政策，明确千亿资金扶持计划",
            "content": "国家发展和改革委员会今日发布《人工智能产业发展三年行动计划》，计划在未来三年投入超过1000亿元资金支持AI芯片、算法框架、应用场景等关键领域的发展。政策明确了对人工智能企业的税收优惠、研发补贴和人才引进支持措施。",
            "source": "gov_policy",
            "publish_date": "2024-01-15"
        },
        {
            "news_id": "test_financial_report_002", 
            "title": "宁德时代发布2023年财报：净利润同比增长45%，动力电池出货量全球第一",
            "content": "宁德时代发布2023年度财务报告，公司实现营业收入3285亿元，同比增长42%；净利润412亿元，同比增长45%。动力电池出货量达到289GWh，连续七年位居全球第一。公司宣布将加大固态电池研发投入。",
            "source": "company_report",
            "publish_date": "2024-01-15"
        },
        {
            "news_id": "test_tech_cooperation_003",
            "title": "微软与OpenAI宣布深化战略合作，将投资100亿美元开发下一代AI系统",
            "content": "微软和OpenAI宣布达成新的战略合作协议，微软将追加投资100亿美元用于开发下一代人工智能系统。双方将在AI芯片、云基础设施、企业应用等多个领域展开深度合作，共同推动AGI技术发展。",
            "source": "tech_news", 
            "publish_date": "2024-01-15"
        }
    ]
    
    conn = None
    inserted_ids = []
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        for news in test_news_data:
            # 检查是否已存在
            existing = await conn.fetchrow(
                "SELECT id FROM news_raw WHERE news_id = $1",
                news["news_id"]
            )
            
            if existing:
                print(f"   ⚠️  新闻已存在: {news['news_id']} (ID: {existing['id']})")
                inserted_ids.append(existing['id'])
            else:
                # 插入新记录
                result = await conn.fetchrow("""
                    INSERT INTO news_raw 
                    (news_id, title, content, source, publish_date, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    RETURNING id
                """,
                    news["news_id"],
                    news["title"],
                    news["content"],
                    news["source"],
                    news["publish_date"]
                )
                
                inserted_id = result['id']
                inserted_ids.append(inserted_id)
                print(f"   ✅ 插入成功: {news['title'][:40]}... (ID: {inserted_id})")
        
        return inserted_ids
        
    except Exception as e:
        print(f"❌ 插入新闻失败: {e}")
        return []
    finally:
        if conn:
            await conn.close()

async def call_ai_service(test_news):
    """调用AI服务"""
    print(f"\n🚀 调用AI事件抽取服务...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": test_news},
                timeout=15
            ) as response:
                print(f"📥 服务响应: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 服务接受请求:")
                    print(f"   状态: {result.get('status')}")
                    print(f"   消息: {result.get('message')}")
                    return True
                else:
                    text = await response.text()
                    print(f"❌ 服务调用失败: {text[:200]}")
                    return False
                    
    except Exception as e:
        print(f"❌ 服务调用异常: {e}")
        return False

async def check_results():
    """检查分析结果"""
    print(f"\n🔍 检查AI分析结果...")
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查找测试新闻的事件
        events = await conn.fetch("""
            SELECT ne.id, ne.news_id, ne.event_type, ne.impact_industries, 
                   ne.direction, ne.confidence, ne.summary, ne.created_at,
                   nr.news_id as raw_news_id, nr.title
            FROM news_event ne
            JOIN news_raw nr ON ne.news_id = nr.id
            WHERE nr.news_id LIKE 'test_%'
            ORDER BY ne.created_at DESC
        """)
        
        if events:
            print(f"🎯 找到 {len(events)} 个测试事件:")
            for event in events:
                title_preview = event['title'][:40] + '...' if len(event['title']) > 40 else event['title']
                
                print(f"\n   📰 新闻: {title_preview}")
                print(f"   🏷️  事件类型: {event['event_type']}")
                print(f"   📊 方向: {event['direction']}, 置信度: {event['confidence']:.2f}")
                print(f"   📝 摘要: {event['summary'][:60]}...")
                print(f"   ⏰ 时间: {event['created_at'].strftime('%H:%M:%S')}")
        else:
            print("⚠️  没有找到测试事件")
            
            # 查看news_raw表中的测试新闻
            test_news = await conn.fetch("""
                SELECT id, news_id, title FROM news_raw 
                WHERE news_id LIKE 'test_%'
            """)
            
            if test_news:
                print(f"\n📋 测试新闻在news_raw表中:")
                for news in test_news:
                    print(f"   ID: {news['id']}, News ID: {news['news_id'][:20]}...")
            else:
                print("❌ news_raw表中也没有测试新闻")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 检查结果失败: {e}")

async def cleanup():
    """清理测试数据"""
    print(f"\n🧹 清理测试数据...")
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 先删除news_event中的测试记录
        deleted_events = await conn.fetchval("""
            DELETE FROM news_event 
            WHERE news_id IN (
                SELECT id FROM news_raw WHERE news_id LIKE 'test_%'
            )
            RETURNING COUNT(*)
        """)
        
        if deleted_events:
            print(f"   ✅ 删除了 {deleted_events} 条事件记录")
        
        # 再删除news_raw中的测试记录
        deleted_news = await conn.fetchval("""
            DELETE FROM news_raw 
            WHERE news_id LIKE 'test_%'
            RETURNING COUNT(*)
        """)
        
        if deleted_news:
            print(f"   ✅ 删除了 {deleted_news} 条新闻记录")
        
        if not deleted_events and not deleted_news:
            print("   ✅ 无需清理，没有测试数据")
        
        await conn.close()
        
    except Exception as e:
        print(f"⚠️  清理失败: {e}")

async def main():
    """主测试流程"""
    print("🎯 AI事件抽取服务 - 端到端测试")
    print("=" * 60)
    
    # 测试新闻数据
    test_news = [
        {
            "news_id": "test_ai_policy_001",
            "title": "国家发改委发布人工智能产业支持政策，明确千亿资金扶持计划",
            "content": "国家发展和改革委员会今日发布《人工智能产业发展三年行动计划》，计划在未来三年投入超过1000亿元资金支持AI芯片、算法框架、应用场景等关键领域的发展。政策明确了对人工智能企业的税收优惠、研发补贴和人才引进支持措施。",
            "source": "gov_policy",
            "publish_date": "2024-01-15"
        },
        {
            "news_id": "test_financial_report_002", 
            "title": "宁德时代发布2023年财报：净利润同比增长45%，动力电池出货量全球第一",
            "content": "宁德时代发布2023年度财务报告，公司实现营业收入3285亿元，同比增长42%；净利润412亿元，同比增长45%。动力电池出货量达到289GWh，连续七年位居全球第一。公司宣布将加大固态电池研发投入。",
            "source": "company_report",
            "publish_date": "2024-01-15"
        },
        {
            "news_id": "test_tech_cooperation_003",
            "title": "微软与OpenAI宣布深化战略合作，将投资100亿美元开发下一代AI系统",
            "content": "微软和OpenAI宣布达成新的战略合作协议，微软将追加投资100亿美元用于开发下一代人工智能系统。双方将在AI芯片、云基础设施、企业应用等多个领域展开深度合作，共同推动AGI技术发展。",
            "source": "tech_news", 
            "publish_date": "2024-01-15"
        }
    ]
    
    # 1. 插入测试数据
    inserted_ids = await insert_test_news()
    
    if not inserted_ids:
        print("❌ 测试新闻插入失败，终止测试")
        return
    
    # 等待一下
    await asyncio.sleep(1)
    
    # 2. 调用AI服务
    print(f"\n📤 发送 {len(test_news)} 条新闻给AI分析...")
    for news in test_news:
        print(f"   📰 {news['title'][:50]}...")
    
    success = await call_ai_service(test_news)
    
    if not success:
        print("❌ AI服务调用失败")
        return
    
    # 3. 等待AI处理完成
    print(f"\n⏳ 等待AI分析处理...")
    await asyncio.sleep(8)  # 给足够的时间处理
    
    # 4. 检查结果
    await check_results()
    
    # 5. 清理
    await cleanup()
    
    print("\n" + "=" * 60)
    print("🎯 端到端测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
