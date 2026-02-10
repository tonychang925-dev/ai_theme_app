#!/usr/bin/env python3
"""
诊断问题：为什么PureDataFetcher调用失败
"""
import os
import sys
import asyncio

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

async def diagnose():
    print("🔍 诊断PureDataFetcher问题...")
    
    try:
        # 1. 导入组件
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.client import DatabaseClient
        from database_service.pure_data_fetcher import PureDataFetcher
        
        # 2. 初始化数据库
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 3. 添加测试数据
        await db_manager.create_theme(
            name="人工智能芯片",
            keywords=["AI", "芯片"],
            description="测试主题"
        )
        
        # 4. 测试不同的配置
        
        print("\n🔧 测试1: 直接使用DatabaseManager创建PureDataFetcher")
        try:
            fetcher1 = PureDataFetcher(db_manager)
            themes1 = await fetcher1.get_all_active_themes(limit=5)
            print(f"   ✅ 成功！获取到 {len(themes1)} 个主题")
        except Exception as e:
            print(f"   ❌ 失败: {e}")
        
        print("\n🔧 测试2: 使用DatabaseClient创建PureDataFetcher")
        db_client = DatabaseClient(db_manager)
        try:
            fetcher2 = PureDataFetcher(db_client)
            themes2 = await fetcher2.get_all_active_themes(limit=5)
            print(f"   ✅ 成功！获取到 {len(themes2)} 个主题")
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            print(f"   DatabaseClient类型: {type(db_client)}")
            print(f"   DatabaseClient方法: {[m for m in dir(db_client) if not m.startswith('_')][:10]}")
        
        print("\n🔧 测试3: 检查DatabaseClient是否有db_manager属性")
        if hasattr(db_client, 'db_manager'):
            print(f"   ✅ db_manager属性存在: {type(db_client.db_manager)}")
            db_manager_methods = [m for m in dir(db_client.db_manager) if 'theme' in m.lower() and not m.startswith('_')]
            print(f"   db_manager的主题相关方法: {db_manager_methods}")
        else:
            print("   ❌ db_manager属性不存在")
        
        # 清理
        await db_manager.disconnect()
        
    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(diagnose())
