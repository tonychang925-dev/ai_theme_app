#!/usr/bin/env python3
"""
修复路径计算问题
"""
import sys
import os

print("="*60)
print("🔧 修复路径计算")
print("="*60)

# 正确计算路径
current_file = os.path.abspath(__file__)
print(f"当前文件: {current_file}")

# 当前文件在 database_service 目录下
current_dir = os.path.dirname(current_file)
print(f"当前目录 (database_service): {current_dir}")

# managers 目录应该在 database_service 下面
managers_dir = os.path.join(current_dir, "managers")
print(f"正确的managers目录: {managers_dir}")
print(f"managers目录存在: {os.path.exists(managers_dir)}")

# 列出 managers 目录内容
if os.path.exists(managers_dir):
    print("📁 managers目录内容:")
    for item in os.listdir(managers_dir):
        if item.endswith('.py'):
            print(f"  - {item}")

# 正确的路径设置
print("\n📊 正确的Python路径设置:")
# 添加 database_service 目录
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
    print(f"✅ 添加 database_service 目录到 Python 路径")

# 验证导入
print("\n🚀 验证导入:")
try:
    # 现在应该可以正常导入
    from managers.postgres_manager import PostgresDatabaseManager
    print("🎉 成功导入 PostgresDatabaseManager!")
    print(f"  类: {PostgresDatabaseManager}")
    
    # 也可以这样导入
    from managers import PostgresDatabaseManager as PDM2
    print("✅ 也可以这样导入: from managers import PostgresDatabaseManager")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    
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
    except Exception as e2:
        print(f"💥 直接导入失败: {e2}")

print("\n" + "="*60)
