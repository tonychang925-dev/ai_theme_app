#!/usr/bin/env python3
"""
直接测试完整工作流程
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_complete_workflow():
    """测试完整工作流程"""
    print("🎯 测试完整AI事件抽取工作流程")
    print("=" * 60)
    
    # 先测试数据库连接
    from model_service.database_completely_fixed import DatabaseManagerFixed
    
    print("1️⃣ 测试数据库连接...")
    if not await DatabaseManagerFixed.test_connection():
        print("❌ 数据库连接测试失败，终止测试")
        return
    
    # 初始化数据库
    print("\n2️⃣ 初始化数据库...")
    await DatabaseManagerFixed.initialize_db()
    
    # 插入测试新闻
    print("\n3️⃣ 插入测试新闻...")
    
    import asyncpg
    from datetime import date
    
    conn = None
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 插入测试新闻
        test_news_id = "direct_test_001"
        
        # 先删除可能存在的旧记录
        await conn.execute("DELETE FROM news_raw WHERE news_id = $1", test_news_id)
        
        # 插入新记录
        result = await conn.fetchrow("""
            INSERT INTO news_raw 
            (news_id, title, content, source, publish_date, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id
        """,
            test_news_id,
            "直接测试AI事件抽取",
            "这是一条直接测试AI事件抽取功能的新闻内容，包含人工智能和政策的关鍵詞。",
            "direct_test",
            date(2024, 1, 15)
        )
        
        inserted_id = result['id']
        print(f"✅ 插入测试新闻成功! ID: {inserted_id}")
        
        await conn.close()
        
        # 测试DatabaseManager查找
        print(f"\n4️⃣ 测试DatabaseManager查找...")
        found_id = await DatabaseManagerFixed.get_news_raw_id(test_news_id)
        
        if found_id == inserted_id:
            print(f"✅ DatabaseManager查找正确: {found_id}")
        else:
            print(f"❌ DatabaseManager查找错误: 期望{inserted_id}, 实际{found_id}")
            return
        
        # 测试AI提取器
        print(f"\n5️⃣ 测试AI提取器...")
        
        from model_service.services.ai_extractor import AIExtractor
        from model_service.models.news_event import NewsEvent
        
        extractor = AIExtractor()
        
        # 准备新闻数据
        test_news_data = [{
            "news_id": test_news_id,
            "title": "直接测试AI事件抽取",
            "content": "这是一条直接测试AI事件抽取功能的新闻内容，包含人工智能和政策的关鍵詞。",
            "source": "direct_test",
            "publish_date": "2024-01-15"
        }]
        
        print(f"   调用AI提取器处理新闻...")
        events = await extractor.extract_events_from_news(test_news_data)
        
        if events:
            print(f"✅ AI提取器成功! 提取 {len(events)} 个事件")
            event = events[0]
            
            print(f"\n   📊 提取的事件详情:")
            print(f"      类型: {event.event_type}")
            print(f"      方向: {event.direction}")
            print(f"      置信度: {event.confidence:.2f}")
            print(f"      摘要: {event.summary}")
            print(f"      news_db_id: {event.news_db_id}")
            
            # 测试保存到数据库
            print(f"\n6️⃣ 测试保存到数据库...")
            saved_count = await DatabaseManagerFixed.save_events(events)
            
            if saved_count > 0:
                print(f"✅ 成功保存 {saved_count} 个事件到数据库")
                
                # 验证保存
                await verify_saved_event(inserted_id)
            else:
                print(f"❌ 保存失败")
                
        else:
            print(f"❌ AI提取器没有提取到事件")
            
            # 深入调试
            print(f"\n🔍 深入调试AI提取器...")
            await debug_ai_extractor(extractor, test_news_data[0])
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn and not conn.is_closed():
            await conn.close()

async def debug_ai_extractor(extractor, news_item):
    """调试AI提取器"""
    print("   1. 测试_analyze_single_news方法...")
    
    try:
        event = await extractor._analyze_single_news(news_item)
        if event:
            print(f"      ✅ 方法返回事件: {event.event_type}")
        else:
            print(f"      ❌ 方法返回None")
            
            # 测试各个步骤
            print(f"\n   2. 测试各个步骤...")
            
            # 步骤1: 数据库查找
            from model_service.database_completely_fixed import DatabaseManagerFixed
            news_db_id = await DatabaseManagerFixed.get_news_raw_id(news_item['news_id'])
            print(f"      步骤1-数据库查找: {news_db_id}")
            
            if not news_db_id:
                print(f"      ❗ 数据库查找失败")
                return
            
            # 步骤2: AI分析
            event_data = await extractor._ai_analysis(news_item)
            print(f"      步骤2-AI分析: 成功")
            print(f"          事件类型: {event_data.get('event_type')}")
            print(f"          行业: {event_data.get('industry')}")
            
            # 步骤3: 创建事件
            from model_service.models.news_event import NewsEvent
            try:
                event = NewsEvent.from_ai_response(
                    news_db_id=news_db_id,
                    news_hash_id=news_item['news_id'],
                    ai_data=event_data,
                    raw_news=news_item
                )
                print(f"      步骤3-创建事件: 成功! {event.event_type}")
            except Exception as e:
                print(f"      步骤3-创建事件: 失败! {e}")
                
    except Exception as e:
        print(f"      ❌ 方法执行失败: {e}")

async def verify_saved_event(news_id: int):
    """验证保存的事件"""
    print(f"\n🔍 验证数据库保存...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查找事件
        events = await conn.fetch("""
            SELECT id, event_type, direction, confidence, summary, created_at
            FROM news_event 
            WHERE news_id = $1
            ORDER BY created_at DESC
            LIMIT 3
        """, news_id)
        
        if events:
            print(f"✅ 数据库中找到 {len(events)} 个事件:")
            for event in events:
                print(f"\n   📋 事件:")
                print(f"      ID: {event['id']}")
                print(f"      类型: {event['event_type']}")
                print(f"      方向: {event['direction']}")
                print(f"      置信度: {event['confidence']:.2f}")
                print(f"      摘要: {event['summary']}")
                print(f"      时间: {event['created_at'].strftime('%H:%M:%S')}")
        else:
            print(f"❌ 数据库中未找到事件 (news_id={news_id})")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")

async def cleanup_test_data():
    """清理测试数据"""
    print(f"\n🧹 清理测试数据...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 先删除事件
        await conn.execute("""
            DELETE FROM news_event 
            WHERE news_id IN (
                SELECT id FROM news_raw WHERE news_id = 'direct_test_001'
            )
        """)
        
        # 再删除新闻
        await conn.execute("DELETE FROM news_raw WHERE news_id = 'direct_test_001'")
        
        print(f"✅ 清理完成")
        
        await conn.close()
        
    except Exception as e:
        print(f"⚠️  清理失败: {e}")

if __name__ == "__main__":
    print("开始完整工作流程测试...\n")
    asyncio.run(test_complete_workflow())
    asyncio.run(cleanup_test_data())
    
    print("\n" + "=" * 60)
    print("🎯 完整工作流程测试完成")
    print("=" * 60)
