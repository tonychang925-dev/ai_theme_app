#!/usr/bin/env python3
"""
测试数据库连接
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

async def test_database():
    print("🧪 测试数据库连接")
    print("=" * 50)
    
    try:
        from theme_service.config import settings
        from theme_service.database import ThemeDatabase
        
        print(f"数据库URL: {settings.DATABASE_URL}")
        
        # 创建数据库连接
        db = ThemeDatabase(settings.DATABASE_URL)
        
        print("1. 测试数据库初始化...")
        success = await db.initialize()
        
        if success:
            print("   ✅ 数据库初始化成功")
        else:
            print("   ❌ 数据库初始化失败")
            return False
        
        print("\n2. 测试健康检查...")
        healthy = await db.health_check()
        
        if healthy:
            print("   ✅ 数据库连接正常")
        else:
            print("   ❌ 数据库连接失败")
            return False
        
        print("\n3. 检查 news_event 表...")
        try:
            # 尝试查询事件
            events = await db.get_recent_events(limit=5)
            print(f"   ✅ 找到 {len(events)} 个事件")
            
            if events:
                print("   最近事件示例:")
                for i, event in enumerate(events[:3]):
                    print(f"     {i+1}. ID:{event.get('id')} - {event.get('title', '无标题')[:30]}...")
        except Exception as e:
            print(f"   ⚠️  查询事件失败: {e}")
            print("   可能需要手动创建表或等待 model_service 生成数据")
        
        print("\n4. 检查 theme_master 表...")
        try:
            themes = await db.get_themes_by_status("active", limit=5)
            print(f"   ✅ 找到 {len(themes)} 个主题")
        except Exception as e:
            print(f"   ⚠️  查询主题失败: {e}")
        
        print("\n" + "=" * 50)
        print("🎉 数据库连接测试完成")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("测试 theme_service 数据库连接...")
    print("注意: 需要确保 PostgreSQL 服务正在运行")
    print("-" * 50)
    
    success = asyncio.run(test_database())
    
    if success:
        print("\n✅ 数据库连接正常，可以开始数据流集成")
    else:
        print("\n⚠️  数据库连接有问题，需要先解决")
    
    sys.exit(0 if success else 1)
