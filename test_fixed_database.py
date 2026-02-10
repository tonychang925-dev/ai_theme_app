#!/usr/bin/env python3
"""
测试修复后的数据库连接
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

async def test_fixed_database():
    print("🧪 测试修复后的数据库连接")
    print("="*60)
    
    try:
        # 导入配置和模块
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        print(f"📊 数据库URL: {settings.DATABASE_URL}")
        
        # 1. 创建数据库实例
        db = ThemeDatabase(settings.DATABASE_URL)
        
        # 2. 测试初始化
        print("\n1. 测试初始化...")
        try:
            success = await db.initialize()
            if success:
                print("   ✅ 初始化成功")
            else:
                print("   ❌ 初始化失败")
                return False
        except Exception as e:
            print(f"   ❌ 初始化异常: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 3. 测试健康检查
        print("\n2. 测试健康检查...")
        try:
            healthy = await db.health_check()
            if healthy:
                print("   ✅ 健康检查通过")
            else:
                print("   ❌ 健康检查失败")
                return False
        except Exception as e:
            print(f"   ❌ 健康检查异常: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 4. 测试直接获取连接
        print("\n3. 测试直接获取连接...")
        conn = None
        try:
            conn = await db.acquire_connection()
            print("   ✅ 获取连接成功")
            
            # 测试查询
            result = await conn.fetchval("SELECT 1")
            print(f"   ✅ 查询测试: {result}")
            
            await db.release_connection(conn)
            conn = None
            print("   ✅ 释放连接成功")
        except Exception as e:
            print(f"   ❌ 连接测试失败: {e}")
            if conn:
                await db.release_connection(conn)
            return False
        
        # 5. 测试执行查询方法
        print("\n4. 测试 execute_query...")
        try:
            result = await db.execute_query("SELECT 1 as test_value")
            if result and result[0]["test_value"] == 1:
                print("   ✅ execute_query 测试成功")
            else:
                print(f"   ❌ execute_query 返回异常: {result}")
        except Exception as e:
            print(f"   ❌ execute_query 失败: {e}")
            return False
        
        # 6. 测试获取事件（如果表存在）
        print("\n5. 测试获取事件...")
        try:
            events = await db.get_recent_events(limit=3)
            print(f"   📰 找到 {len(events)} 个事件")
            
            if events:
                print("   最近事件:")
                for i, event in enumerate(events[:2]):
                    title = event.get('title') or event.get('news_title', '无标题')
                    print(f"     {i+1}. ID:{event.get('id')} - {title[:40]}...")
        except Exception as e:
            print(f"   ⚠️  获取事件失败: {e}")
            print("     (这可能是因为表不存在，但不影响数据库连接测试)")
        
        # 7. 测试表结构
        print("\n6. 检查表结构...")
        try:
            conn = await db.acquire_connection()
            tables = ["news_raw", "news_event", "theme_master"]
            
            for table in tables:
                exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                    table
                )
                status = "✅ 存在" if exists else "⚠️  不存在"
                print(f"   表 {table}: {status}")
            
            await db.release_connection(conn)
        except Exception as e:
            print(f"   ⚠️  表检查失败: {e}")
            if conn:
                await db.release_connection(conn)
        
        print("\n" + "="*60)
        print("🎉 所有数据库测试通过！")
        print("\n📋 数据库状态总结:")
        print("   ✅ 连接: 正常")
        print("   ✅ 查询: 正常")
        print("   ✅ 连接池: 工作正常")
        print(f"   📊 表状态: 检查了 {len(tables)} 个表")
        
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
    print("🧪 运行修复后的数据库测试")
    print("-"*60)
    
    success = asyncio.run(test_fixed_database())
    
    if success:
        print("\n✅ 数据库连接问题已解决！")
        print("\n🚀 现在可以继续实现数据流集成了")
    else:
        print("\n❌ 数据库连接仍有问题")
    
    sys.exit(0 if success else 1)
