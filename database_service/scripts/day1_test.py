# scripts/test_imports.py
"""
测试导入模块
"""
import sys
import os

print("🔧 测试模块导入")
print("="*60)

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))  # scripts目录
database_dir = os.path.dirname(current_dir)               # database_service目录
project_root = os.path.dirname(database_dir)              # ai_theme_app目录

print(f"📁 当前目录: {current_dir}")
print(f"📁 database_service目录: {database_dir}")
print(f"📁 项目根目录: {project_root}")

# 添加到Python路径
sys.path.insert(0, project_root)  # ai_theme_app
sys.path.insert(0, database_dir)  # database_service

print("\n📋 Python路径:")
for i, path in enumerate(sys.path[:6], 1):
    print(f"{i}. {path}")

# 测试导入
print("\n🧪 测试导入模块...")

try:
    import config
    print("✅ 导入 config 成功")
    print(f"   模块位置: {config.__file__}")
except ImportError as e:
    print(f"❌ 导入 config 失败: {e}")

try:
    import managers.postgres_manager
    print("✅ 导入 postgres_manager 成功")
    print(f"   模块位置: {managers.postgres_manager.__file__}")
except ImportError as e:
    print(f"❌ 导入 postgres_manager 失败: {e}")

try:
    import managers.redis_cached_manager
    print("✅ 导入 redis_cached_manager 成功")
    print(f"   模块位置: {managers.redis_cached_manager.__file__}")
except ImportError as e:
    print(f"❌ 导入 redis_cached_manager 失败: {e}")

try:
    from config import get_config
    print("✅ 从 config 导入 get_config 成功")
except ImportError as e:
    print(f"❌ 导入 get_config 失败: {e}")

print("\n" + "="*60)