#!/usr/bin/env python3
"""
最终完整测试 - 修复所有问题
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_complete():
    """完整测试"""
    print("🚀 AI事件抽取 - 最终完整测试")
    print("=" * 60)
    
    # 1. 替换DatabaseManager
    print("1️⃣ 应用DatabaseManager修复...")
    
    # 备份原文件
    import shutil
    if os.path.exists('model_service/database.py'):
        shutil.copy2('model_service/database.py', 'model_service/database_backup.py')
        print("✅ 备份原database.py")
    
    # 应用修复
    shutil.copy2('model_service/database_compatible.py', 'model_service/database.py')
    print("✅ 应用兼容修复版")
    
    # 2. 测试数据库连接
    print("\n2️⃣ 测试数据库连接...")
    
    from model_service.database import DatabaseManager
    
    try:
        # 简单测试连接
        import asyncpg
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        print("✅ 数据库连接成功")
        await conn.close()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return
    
    # 3. 创建测试新闻
    print("\n3️⃣ 创建测试新闻...")
    
    import asyncpg
    from datetime import date
    
    test_news_id = "complete_test_001"
    conn = None
    
    try:
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 清理旧数据
        await conn.execute("""
            DELETE FROM news_event WHERE news_id IN (
                SELECT id FROM news_raw WHERE news_id = $1
            )
        """, test_news_id)
        await conn.execute("DELETE FROM news_raw WHERE news_id = $1", test_news_id)
        
        # 插入测试新闻
        result = await conn.fetchrow("""
            INSERT INTO news_raw 
            (news_id, title, content, source, publish_date, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id
        """,
            test_news_id,
            "完整测试：人工智能重大突破",
            "中国科学家在人工智能领域取得重大突破，实现新的算法创新。",
            "complete_test",
            date(2024, 1, 15)
        )
        
        news_db_id = result['id']
        print(f"✅ 插入测试新闻: ID={news_db_id}")
        
        await conn.close()
        
        # 4. 测试DatabaseManager查找
        print(f"\n4️⃣ 测试DatabaseManager查找...")
        found_id = await DatabaseManager.get_news_raw_id(test_news_id)
        
        if found_id == news_db_id:
            print(f"✅ DatabaseManager查找正确: {found_id}")
        else:
            print(f"❌ DatabaseManager查找错误")
            return
        
        # 5. 测试AI提取器
        print(f"\n5️⃣ 测试AI提取器...")
        
        # 重新导入，确保使用修复后的DatabaseManager
        import importlib
        import model_service.services.ai_extractor
        importlib.reload(model_service.services.ai_extractor)
        
        from model_service.services.ai_extractor import AIExtractor
        
        extractor = AIExtractor()
        
        test_news = [{
            "news_id": test_news_id,
            "title": "完整测试：人工智能重大突破",
            "content": "中国科学家在人工智能领域取得重大突破，实现新的算法创新。",
            "source": "complete_test",
            "publish_date": "2024-01-15"
        }]
        
        print(f"   调用AI提取器...")
        events = await extractor.extract_events_from_news(test_news)
        
        if events:
            event = events[0]
            print(f"✅ AI分析成功!")
            print(f"\n   📊 事件详情:")
            print(f"      类型: {event.event_type}")
            print(f"      影响行业: {event.impact_industries}")
            print(f"      方向: {event.direction}")
            print(f"      置信度: {event.confidence:.2f}")
            print(f"      摘要: {event.summary}")
            
            # 检查impact_industries类型
            print(f"\n   🔍 类型检查:")
            print(f"      impact_industries类型: {type(event.impact_industries)}")
            print(f"      impact_industries值: {event.impact_industries}")
            
            # 6. 保存到数据库
            print(f"\n6️⃣ 保存到数据库...")
            saved_count = await DatabaseManager.save_events(events)
            
            if saved_count > 0:
                print(f"🎉 保存成功! {saved_count} 个事件")
                
                # 7. 验证结果
                await verify_complete_result(news_db_id)
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

async def verify_complete_result(news_id: int):
    """验证完整结果"""
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
        
        # 查看表总数
        total_before = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        
        # 清理测试数据
        print(f"\n🧹 清理测试数据...")
        await conn.execute("DELETE FROM news_event WHERE news_id = $1", news_id)
        await conn.execute("DELETE FROM news_raw WHERE id = $1", news_id)
        
        total_after = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        cleaned = total_before - total_after
        print(f"✅ 清理完成，删除了 {cleaned} 条记录")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")

async def test_original_problem():
    """测试原始问题是否修复"""
    print(f"\n" + "=" * 60)
    print("🎯 测试原始news_id类型问题是否修复")
    print("=" * 60)
    
    # 重启服务以确保使用修复后的代码
    print("🔄 建议重启服务以应用修复...")
    print("   请在另一个终端执行: python start_simple.py")
    
    import time
    print("⏳ 等待5秒...")
    time.sleep(5)
    
    # 测试API
    import aiohttp
    import json
    
    test_data = {
        "news_list": [{
            "news_id": "04702f6ddebf7c76935ddaecb73e3aa4",  # 字符串
            "title": "测试原始问题修复",
            "content": "测试服务是否能正确处理字符串类型的news_id",
            "source": "test",
            "publish_date": "2024-01-15"
        }]
    }
    
    print(f"\n📤 发送API测试请求...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json=test_data,
                timeout=10
            ) as response:
                print(f"📥 响应状态: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ API调用成功:")
                    print(f"   状态: {result.get('status')}")
                    print(f"   消息: {result.get('message')}")
                    
                    print(f"\n⏳ 等待AI处理完成...")
                    time.sleep(5)
                    
                    # 检查数据库
                    await check_original_result()
                    
                else:
                    text = await response.text()
                    print(f"❌ API调用失败: {text[:200]}")
                    
    except Exception as e:
        print(f"❌ 请求异常: {e}")

async def check_original_result():
    """检查原始问题测试结果"""
    print(f"\n🔍 检查数据库...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            "postgresql://postgres:zxbzj~925@localhost/stock_data"
        )
        
        # 查找新闻
        news = await conn.fetchrow("""
            SELECT id, news_id, title FROM news_raw 
            WHERE news_id = '04702f6ddebf7c76935ddaecb73e3aa4'
        """)
        
        if news:
            print(f"✅ 找到新闻: ID={news['id']}")
            
            # 查找相关事件
            events = await conn.fetch("""
                SELECT id, event_type, summary, created_at 
                FROM news_event 
                WHERE news_id = $1
                ORDER BY created_at DESC
                LIMIT 3
            """, news['id'])
            
            if events:
                print(f"✅ 找到 {len(events)} 个事件:")
                for event in events:
                    print(f"   • [{event['event_type']}] {event['summary'][:50]}...")
            else:
                print(f"⚠️  该新闻没有事件记录")
        else:
            print(f"❌ 未找到新闻记录")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")

async def restore_backup():
    """恢复备份"""
    print(f"\n🔄 恢复原database.py...")
    
    try:
        import shutil
        if os.path.exists('model_service/database_backup.py'):
            shutil.copy2('model_service/database_backup.py', 'model_service/database.py')
            print("✅ 恢复原database.py")
        else:
            print("⚠️  没有找到备份文件")
    except Exception as e:
        print(f"❌ 恢复失败: {e}")

if __name__ == "__main__":
    print("开始最终完整测试...\n")
    
    try:
        # 运行完整测试
        asyncio.run(test_complete())
        
        # 测试原始问题
        asyncio.run(test_original_problem())
        
    finally:
        # 恢复备份（可选）
        print(f"\n" + "=" * 60)
        choice = input("是否恢复原database.py？(y/n): ")
        if choice.lower() == 'y':
            asyncio.run(restore_backup())
        
    print("\n" + "=" * 60)
    print("🎯 最终完整测试完成")
    print("=" * 60)
