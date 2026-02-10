#!/usr/bin/env python3
"""
验证导入问题
"""
import sys
import os

print("="*60)
print("🔍 验证导入路径")
print("="*60)

# 1. 获取路径
current_file = os.path.abspath(__file__)
print(f"当前文件: {current_file}")

scripts_dir = os.path.dirname(current_file)
print(f"scripts目录: {scripts_dir}")

database_dir = os.path.dirname(scripts_dir)
print(f"database_service目录: {database_dir}")

managers_dir = os.path.join(database_dir, "managers")
print(f"managers目录: {managers_dir}")

# 2. 检查目录是否存在
print("\n📁 目录检查:")
print(f"  scripts目录存在: {os.path.exists(scripts_dir)}")
print(f"  database_service目录存在: {os.path.exists(database_dir)}")
print(f"  managers目录存在: {os.path.exists(managers_dir)}")

if os.path.exists(managers_dir):
    print(f"  managers目录内容:")
    for item in os.listdir(managers_dir):
        if item.endswith('.py'):
            print(f"    - {item}")

# 3. 设置路径
print("\n📊 Python路径设置:")
sys.path.insert(0, database_dir)
print(f"  已添加 database_service 到 Python 路径")

sys.path.insert(0, managers_dir)
print(f"  已添加 managers 目录到 Python 路径")

print("\n📋 当前 sys.path 前5个:")
for i, path in enumerate(sys.path[:5]):
    print(f"  [{i}] {path}")

# 4. 测试导入
print("\n🚀 测试导入:")
try:
    import managers
    print("✅ 导入 managers 模块成功")
    
    # 检查模块内容
    print("📦 managers 模块内容:")
    for attr in dir(managers):
        if not attr.startswith('_'):
            print(f"    - {attr}: {getattr(managers, attr)}")
except ImportError as e:
    print(f"❌ 导入 managers 失败: {e}")

# 5. 测试直接导入
print("\n🔧 测试直接导入 postgres_manager:")
try:
    from managers.postgres_manager import PostgresDatabaseManager
    print("🎉 成功导入 PostgresDatabaseManager!")
    print(f"   类: {PostgresDatabaseManager}")
except ImportError as e:
    print(f"❌ 导入 PostgresDatabaseManager 失败: {e}")
    
    # 尝试直接导入
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "postgres_manager", 
            os.path.join(managers_dir, "postgres_manager.py")
        )
        postgres_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(postgres_module)
        PostgresDatabaseManager = postgres_module.PostgresDatabaseManager
        print("✅ 通过直接文件导入成功")
        print(f"   类: {PostgresDatabaseManager}")
    except Exception as e2:
        print(f"💥 直接导入也失败: {e2}")

print("\n" + "="*60)
