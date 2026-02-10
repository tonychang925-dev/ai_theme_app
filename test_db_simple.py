#!/usr/bin/env python3
"""
简单数据库测试 - 避免复杂依赖
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

async def simple_db_test():
    print("🧪 简单数据库测试")
    print("=" * 50)
    
    try:
        # 1. 导入配置
        from theme_service.config import settings
        print(f"数据库URL: {settings.DATABASE_URL[:50]}...")
        
        # 2. 创建数据库实例
        from theme_service.database import ThemeDatabase
        db = ThemeDatabase(settings.DATABASE_URL)
        
        print("1. 测试数据库初始化...")
        try:
            success = await db.initialize()
            if success:
                print("   ✅ 数据库初始化成功")
            else:
                print("   ❌ 数据库初始化失败")
                return False
        except Exception as e:
            print(f"   ❌ 初始化异常: {e}")
            return False
        
        print("\n2. 测试简单查询...")
        try:
            # 使用简单连接方式测试
            conn = await db.acquire_connection()
            try:
                # 测试查询
                result = await conn.fetchval("SELECT 1")
                if result == 1:
                    print("   ✅ 简单查询成功")
                else:
                    print(f"   ❌ 查询返回异常值: {result}")
                    return False
                
                # 检查表是否存在
                tables = ["news_raw", "news_event", "theme_master"]
                for table in tables:
                    exists = await conn.fetchval(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                        table
                    )
                    status = "✅ 存在" if exists else "⚠️  不存在"
                    print(f"   表 {table}: {status}")
                
            finally:
                await db.release_connection(conn)
                
        except Exception as e:
            print(f"   ❌ 查询测试失败: {e}")
            return False
        
        print("\n3. 测试事件查询...")
        try:
            events = await db.get_recent_events(limit=3)
            print(f"   找到 {len(events)} 个事件")
            
            if events:
                print("   最近事件:")
                for i, event in enumerate(events[:2]):
                    title = event.get('title') or event.get('news_title', '无标题')
                    print(f"     {i+1}. ID:{event.get('id')} - {title[:40]}...")
            else:
                print("   ⚠️  没有找到事件，可能是表为空或需要 model_service 先运行")
                
        except Exception as e:
            print(f"   ⚠️  事件查询失败: {e}")
            print("   可能需要先创建表或运行 model_service")
        
        print("\n" + "=" * 50)
        print("✅ 数据库基本功能测试通过")
        print("\n📋 数据库状态:")
        print(f"   连接: 正常")
        print(f"   查询: 正常")
        print(f"   事件表: {'有数据' if events else '无数据/不存在'}")
        
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
    print("简单数据库连接测试")
    print("测试 theme_service 数据库基本功能")
    print("-" * 50)
    
    success = asyncio.run(simple_db_test())
    
    if success:
        print("\n🎉 数据库连接正常，可以开始数据流集成")
    else:
        print("\n⚠️  数据库连接测试失败")
    
    sys.exit(0 if success else 1)
