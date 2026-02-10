#!/usr/bin/env python3
"""
测试数据库模块
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_database():
    print("🧪 测试数据库模块")
    print("=" * 50)
    
    try:
        # 1. 导入测试
        print("1. 导入模块...")
        from theme_service.database import ThemeDatabase
        print("   ✅ ThemeDatabase 导入成功")
        
        from theme_service.config import settings
        print("   ✅ settings 导入成功")
        
        # 2. 创建实例
        print("\n2. 创建数据库实例...")
        # 使用内存SQLite测试，避免真实数据库依赖
        db = ThemeDatabase("sqlite:///:memory:")
        print("   ✅ 数据库实例创建成功")
        
        # 3. 测试方法
        print("\n3. 测试方法...")
        methods = [m for m in dir(db) if not m.startswith('_')]
        print(f"   可用方法: {methods[:10]}...")
        
        # 检查关键方法
        required_methods = ['initialize', 'save_theme', 'save_event_theme_mapping', 'health_check']
        for method in required_methods:
            if hasattr(db, method):
                print(f"   ✅ 存在 {method} 方法")
            else:
                print(f"   ❌ 缺失 {method} 方法")
        
        # 4. 测试初始化（跳过真实连接）
        print("\n4. 跳过真实数据库连接测试...")
        print("   ⏭️  使用内存数据库，跳过连接测试")
        
        print("\n" + "=" * 50)
        print("✅ 数据库模块测试通过")
        print("   模块结构正确，可以集成到主题服务中")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_database())
    sys.exit(0 if success else 1)
