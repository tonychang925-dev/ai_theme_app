#!/usr/bin/env python3
"""
详细调试AI提取器
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def debug_extractor_complete():
    """完整调试AI提取器"""
    print("🔧 详细调试AI事件提取器")
    print("=" * 60)
    
    try:
        from model_service.services.ai_extractor import AIExtractor
        from model_service.database import DatabaseManager
        
        print("✅ 导入成功")
        
        # 初始化数据库
        await DatabaseManager.initialize_db()
        print("✅ 数据库初始化成功")
        
        # 创建提取器实例
        extractor = AIExtractor()
        
        # 测试新闻数据 - 注意：使用已经插入的新闻ID
        test_news_list = [
            {
                "news_id": "test_ai_policy_001",  # 这个应该在数据库中，ID=806
                "title": "国家发改委发布人工智能产业支持政策，明确千亿资金扶持计划",
                "content": "国家发展和改革委员会今日发布《人工智能产业发展三年行动计划》，计划在未来三年投入超过1000亿元资金支持AI芯片、算法框架、应用场景等关键领域的发展。政策明确了对人工智能企业的税收优惠、研发补贴和人才引进支持措施。",
                "source": "gov_policy",
                "publish_date": "2024-01-15"
            }
        ]
        
        print(f"\n🎯 测试单条新闻处理:")
        print(f"   新闻ID: {test_news_list[0]['news_id']}")
        print(f"   标题: {test_news_list[0]['title']}")
        
        # 1. 先检查数据库查找
        print(f"\n1️⃣ 检查数据库查找...")
        news_hash_id = test_news_list[0]['news_id']
        news_db_id = await DatabaseManager.get_news_raw_id(news_hash_id)
        
        if news_db_id:
            print(f"   ✅ 找到news_raw记录: ID = {news_db_id}")
        else:
            print(f"   ❌ 未找到news_raw记录: {news_hash_id}")
            # 检查数据库中实际有什么
            await check_database_content()
            return
        
        # 2. 测试AI分析
        print(f"\n2️⃣ 测试AI分析逻辑...")
        event_data = await extractor._ai_analysis(test_news_list[0])
        
        print(f"   ✅ AI分析结果:")
        print(f"     事件类型: {event_data.get('event_type')}")
        print(f"     行业: {event_data.get('industry')}")
        print(f"     情感: {event_data.get('sentiment'):.2f}")
        print(f"     置信度: {event_data.get('confidence'):.2f}")
        print(f"     摘要: {event_data.get('summary')}")
        
        # 3. 测试完整的事件提取
        print(f"\n3️⃣ 测试完整事件提取...")
        events = await extractor.extract_events_from_news(test_news_list)
        
        if events:
            print(f"   ✅ 成功提取 {len(events)} 个事件")
            for event in events:
                print(f"\n   📊 事件详情:")
                print(f"     类型: {event.event_type}")
                print(f"     方向: {event.direction}")
                print(f"     置信度: {event.confidence:.2f}")
                print(f"     摘要: {event.summary}")
                print(f"     news_id: {event.news_id}")
                print(f"     news_db_id: {event.news_db_id}")
                print(f"     news_hash_id: {event.news_hash_id}")
                
                # 测试to_db_dict
                db_dict = event.to_db_dict()
                print(f"     数据库格式news_id: {db_dict.get('news_id')}")
        else:
            print("   ❌ 没有提取到事件")
            
            # 深入调试
            print(f"\n🔍 深入调试问题...")
            await debug_extractor_internals(extractor, test_news_list[0])
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

async def debug_extractor_internals(extractor, news_item):
    """深入调试提取器内部逻辑"""
    print("   1. 测试_process_single_news_simple方法...")
    
    # 检查提取器是否有这个方法
    if hasattr(extractor, '_process_single_news_simple'):
        try:
            event = await extractor._process_single_news_simple(news_item)
            if event:
                print(f"      ✅ 方法返回事件: {event.event_type}")
            else:
                print(f"      ❌ 方法返回None")
        except Exception as e:
            print(f"      ❌ 方法执行失败: {e}")
    else:
        print(f"      ⚠️  提取器没有_process_single_news_simple方法")
    
    print(f"\n   2. 检查AI提取器类的方法...")
    methods = [m for m in dir(extractor) if not m.startswith('_')]
    print(f"     公开方法: {', '.join(methods)}")

async def check_database_content():
    """检查数据库内容"""
    print(f"\n📋 检查数据库内容...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查看所有以test_开头的新闻
        test_news = await conn.fetch("""
            SELECT id, news_id, title 
            FROM news_raw 
            WHERE news_id LIKE 'test_%' 
            OR news_id LIKE 'test%'
            ORDER BY id DESC
            LIMIT 10
        """)
        
        if test_news:
            print(f"   找到 {len(test_news)} 条测试新闻:")
            for news in test_news:
                print(f"     ID: {news['id']}, News ID: {news['news_id']}")
        else:
            print("   ⚠️  没有测试新闻")
        
        # 查看news_event表
        events_count = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        print(f"\n   news_event表总数: {events_count}")
        
        # 查看最新事件
        recent_events = await conn.fetch("""
            SELECT ne.id, ne.news_id, ne.event_type, ne.summary, ne.created_at
            FROM news_event ne
            ORDER BY ne.created_at DESC
            LIMIT 3
        """)
        
        if recent_events:
            print(f"   最新 {len(recent_events)} 个事件:")
            for event in recent_events:
                print(f"     ID: {event['id']}, 新闻ID: {event['news_id']}, 类型: {event['event_type']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"   ❌ 数据库检查失败: {e}")

async def test_database_manager():
    """测试DatabaseManager"""
    print(f"\n🔧 测试DatabaseManager...")
    
    try:
        from model_service.database import DatabaseManager
        
        # 测试get_news_raw_id
        test_ids = [
            "test_ai_policy_001",  # 应该存在
            "non_existent_id",     # 应该不存在
            "04702f6ddebf7c76935ddaecb73e3aa4"  # 应该存在
        ]
        
        for test_id in test_ids:
            result = await DatabaseManager.get_news_raw_id(test_id)
            if result:
                print(f"   ✅ {test_id[:20]}... -> ID: {result}")
            else:
                print(f"   ❌ {test_id[:20]}... -> 未找到")
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")

if __name__ == "__main__":
    print("开始详细调试AI提取器...\n")
    asyncio.run(debug_extractor_complete())
    asyncio.run(test_database_manager())
    
    print("\n" + "=" * 60)
    print("🎯 详细调试完成")
    print("=" * 60)
