#!/usr/bin/env python3
"""
最终修复测试
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_final_fix():
    """测试最终修复"""
    print("🚀 AI事件抽取 - 最终修复测试")
    print("=" * 60)
    
    # 使用最终修复版
    from model_service.database_final_fix import DatabaseManagerFinal
    
    print("1️⃣ 检查数据库结构...")
    await DatabaseManagerFinal.initialize_db()
    
    print("\n2️⃣ 测试数据保存...")
    await DatabaseManagerFinal.test_save_simple()
    
    print("\n3️⃣ 完整流程测试...")
    
    # 插入测试新闻
    import asyncpg
    from datetime import date
    
    test_news_id = "final_fix_test_001"
    conn = None
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 清理旧数据
        await conn.execute("DELETE FROM news_raw WHERE news_id = $1", test_news_id)
        
        # 插入测试新闻
        result = await conn.fetchrow("""
            INSERT INTO news_raw 
            (news_id, title, content, source, publish_date, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id
        """,
            test_news_id,
            "最终修复测试：AI政策利好",
            "国家发布新的人工智能支持政策，投入千亿资金发展AI产业。",
            "final_test",
            date(2024, 1, 15)
        )
        
        news_db_id = result['id']
        print(f"✅ 插入测试新闻: ID={news_db_id}")
        
        await conn.close()
        
        # 使用AI提取器
        print("\n4️⃣ 使用AI提取器分析...")
        
        from model_service.services.ai_extractor import AIExtractor
        from model_service.models.news_event import NewsEvent
        
        extractor = AIExtractor()
        
        test_news = [{
            "news_id": test_news_id,
            "title": "最终修复测试：AI政策利好",
            "content": "国家发布新的人工智能支持政策，投入千亿资金发展AI产业。",
            "source": "final_test",
            "publish_date": "2024-01-15"
        }]
        
        events = await extractor.extract_events_from_news(test_news)
        
        if events:
            event = events[0]
            print(f"✅ AI分析成功!")
            print(f"   事件类型: {event.event_type}")
            print(f"   影响行业: {event.impact_industries}")
            print(f"   方向: {event.direction}")
            print(f"   摘要: {event.summary}")
            
            # 检查impact_industries类型
            print(f"\n🔍 检查impact_industries类型:")
            print(f"   类型: {type(event.impact_industries)}")
            print(f"   值: {event.impact_industries}")
            
            # 保存到数据库
            print(f"\n5️⃣ 保存到数据库...")
            saved_count = await DatabaseManagerFinal.save_events(events)
            
            if saved_count > 0:
                print(f"🎉 保存成功! {saved_count} 个事件")
                
                # 验证
                await verify_final_result(news_db_id)
            else:
                print(f"❌ 保存失败")
                
        else:
            print(f"❌ AI分析失败")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn and not conn.is_closed():
            await conn.close()

async def verify_final_result(news_id: int):
    """验证最终结果"""
    print(f"\n🔍 验证数据库结果...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查找事件
        events = await conn.fetch("""
            SELECT id, event_type, impact_industries, direction, confidence, summary, created_at
            FROM news_event 
            WHERE news_id = $1
            ORDER BY created_at DESC
        """, news_id)
        
        if events:
            print(f"✅ 找到 {len(events)} 个事件:")
            
            for event in events:
                print(f"\n   📋 事件详情:")
                print(f"      ID: {event['id']}")
                print(f"      类型: {event['event_type']}")
                print(f"      影响行业: {event['impact_industries']}")
                print(f"      方向: {event['direction']}")
                print(f"      置信度: {event['confidence']:.2f}")
                print(f"      摘要: {event['summary']}")
                
                # 特别检查impact_industries
                industries = event['impact_industries']
                print(f"      impact_industries类型: {type(industries)}")
                print(f"      impact_industries值: {industries}")
        
        # 查看表总数
        total = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        print(f"\n📈 news_event表总数: {total}")
        
        # 清理
        print(f"\n🧹 清理测试数据...")
        await conn.execute("DELETE FROM news_event WHERE news_id = $1", news_id)
        await conn.execute("DELETE FROM news_raw WHERE id = $1", news_id)
        print(f"✅ 清理完成")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")

async def check_current_database_manager():
    """检查当前的DatabaseManager"""
    print(f"\n🔧 检查当前DatabaseManager实现...")
    
    try:
        # 读取当前文件
        with open('model_service/database.py', 'r') as f:
            content = f.read()
            
        # 检查关键部分
        if 'json.dumps' in content and 'impact_industries' in content:
            print("⚠️  当前DatabaseManager可能使用json.dumps处理impact_industries")
            
            # 查看相关代码
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'json.dumps' in line and 'impact_industries' in line:
                    print(f"   第{i+1}行: {line.strip()}")
                    # 显示上下文
                    for j in range(max(0, i-2), min(len(lines), i+3)):
                        print(f"   {j+1:4}: {lines[j]}")
        
        # 检查NewsEvent模型的to_db_dict方法
        with open('model_service/models/news_event.py', 'r') as f:
            news_event_content = f.read()
            
        if 'to_db_dict' in news_event_content:
            print(f"\n🔍 检查NewsEvent.to_db_dict方法...")
            # 找到to_db_dict方法
            lines = news_event_content.split('\n')
            in_method = False
            for i, line in enumerate(lines):
                if 'def to_db_dict' in line:
                    in_method = True
                    print(f"   找到to_db_dict方法:")
                if in_method:
                    if line.strip() and not line.startswith(' ' * 8):
                        if i > 0 and 'def to_db_dict' not in lines[i-1]:
                            in_method = False
                    else:
                        print(f"   {line.rstrip()}")
                        
    except Exception as e:
        print(f"❌ 检查失败: {e}")

if __name__ == "__main__":
    print("开始最终修复测试...\n")
    
    # 先检查当前状态
    asyncio.run(check_current_database_manager())
    
    # 运行测试
    asyncio.run(test_final_fix())
    
    print("\n" + "=" * 60)
    print("🎯 最终修复测试完成")
    print("=" * 60)
