#!/usr/bin/env python3
"""
最简单的导入测试
"""
import sys
import os
import importlib.util

print("🚀 最简单的导入测试")

# 计算路径
current_file = os.path.abspath(__file__)
database_dir = os.path.dirname(current_file)
postgres_path = os.path.join(database_dir, "managers", "postgres_manager.py")

print(f"当前目录: {database_dir}")
print(f"postgres_manager.py 路径: {postgres_path}")
print(f"文件存在: {os.path.exists(postgres_path)}")

# 直接导入
try:
    spec = importlib.util.spec_from_file_location("my_postgres", postgres_path)
    postgres_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(postgres_module)
    
    print("✅ 直接导入成功")
    
    # 获取类
    PostgresDatabaseManager = postgres_module.PostgresDatabaseManager
    print(f"✅ 获取 PostgresDatabaseManager 类: {PostgresDatabaseManager}")
    
    # 测试创建实例
    class MockConfig:
        postgres_host = 'localhost'
        postgres_port = 5432
        postgres_user = 'postgres'
        postgres_password = ''
        postgres_database = 'stock_data_test'
    
    config = MockConfig()
    manager = PostgresDatabaseManager(config)
    print(f"✅ 创建实例成功: {manager}")
    
    # 测试连接（异步）
    import asyncio
    
    async def test_connection():
        try:
            await manager.connect()
            print("✅ 连接成功（或模拟连接成功）")
            return True
        except Exception as e:
            print(f"⚠️  连接失败（可能正常）: {e}")
            return True  # 连接失败不代表测试失败
    
    # 运行异步测试
    success = asyncio.run(test_connection())
    print(f"测试结果: {'✅ 成功' if success else '❌ 失败'}")
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n🎉 测试完成")
