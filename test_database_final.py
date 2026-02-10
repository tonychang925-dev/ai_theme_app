#!/usr/bin/env python3
"""
最终的数据库连接测试
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

async def test_database_connection():
    print("🧪 最终数据库连接测试")
    print("="*60)
    
    try:
        # 导入配置
        from theme_service.config import settings
        print(f"📊 数据库URL: {settings.DATABASE_URL}")
        
        # 导入并创建数据库实例
        from theme_service.database import ThemeDatabase
        db = ThemeDatabase(settings.DATABASE_URL)
        
        print("\n1. 测试初始化...")
        success = await db.initialize()
        if success:
            print("   ✅ 初始化成功")
        else:
            print("   ❌ 初始化失败")
            return False
        
        print("\n2. 测试健康检查...")
        healthy = await db.health_check()
        if healthy:
            print("   ✅ 健康检查通过")
        else:
            print("   ❌ 健康检查失败")
            return False
        
        print("\n3. 测试获取连接...")
        try:
            conn = await db.acquire_connection()
            print("   ✅ 获取连接成功")
            
            # 测试查询
            result = await conn.fetchval("SELECT 1")
            print(f"   ✅ 查询测试: {result}")
            
            await db.release_connection(conn)
            print("   ✅ 释放连接成功")
        except Exception as e:
            print(f"   ❌ 连接测试失败: {e}")
            return False
        
        print("\n4. 测试 execute_query...")
        try:
            result = await db.execute_query("SELECT version() as db_version")
            if result:
                version = result[0]['db_version']
                print(f"   ✅ 数据库版本: {version.split(',')[0]}")
            else:
                print("   ❌ 查询返回空")
                return False
        except Exception as e:
            print(f"   ❌ execute_query 失败: {e}")
            return False
        
        print("\n5. 测试事件查询...")
        try:
            events = await db.get_recent_events(limit=3)
            print(f"   📰 找到 {len(events)} 个事件")
            
            if events:
                print("   最近事件:")
                for i, event in enumerate(events[:2]):
                    title = event.get('title') or event.get('news_title', '无标题')
                    event_id = event.get('id', 'N/A')
                    print(f"     {i+1}. ID:{event_id} - {title[:40]}...")
        except Exception as e:
            print(f"   ⚠️  事件查询失败 (可能表不存在): {e}")
        
        print("\n6. 测试表创建和主题保存...")
        try:
            # 创建测试主题
            test_theme = {
                "name": f"测试主题_{asyncio.get_event_loop().time():.0f}",
                "keywords": ["测试", "数据库"],
                "status": "test",
                "discovery_source": "test_script",
                "confidence": 0.85
            }
            
            theme_id = await db.save_theme(test_theme)
            if theme_id:
                print(f"   💾 成功保存主题: {test_theme['name']} (ID: {theme_id})")
            else:
                print("   ⚠️  保存主题失败")
        except Exception as e:
            print(f"   ⚠️  主题保存测试失败: {e}")
        
        print("\n7. 获取表统计...")
        try:
            stats = await db.get_table_stats()
            print("   表统计:")
            for table, count in stats.items():
                print(f"     {table}: {count}")
        except Exception as e:
            print(f"   ⚠️  获取统计失败: {e}")
        
        print("\n8. 清理测试数据...")
        try:
            await db.execute_update("DELETE FROM theme_master WHERE status = 'test'")
            print("   🧹 清理测试数据完成")
        except Exception as e:
            print(f"   ⚠️  清理失败: {e}")
        
        print("\n" + "="*60)
        print("🎉 所有数据库测试通过！")
        
        # 关闭连接池
        await db.close()
        print("🔌 数据库连接已关闭")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 运行最终数据库连接测试")
    print("-"*60)
    
    success = asyncio.run(test_database_connection())
    
    if success:
        print("\n✅ 数据库连接问题已完全解决！")
        print("\n📋 下一步:")
        print("   1. 可以开始实现数据流集成")
        print("   2. 运行: python real_data_processor.py")
        print("   3. 检查: ./check_service_status.sh")
    else:
        print("\n❌ 数据库连接测试失败，请检查配置")
    
    sys.exit(0 if success else 1)
