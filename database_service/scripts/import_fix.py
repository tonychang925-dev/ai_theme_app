
#!/usr/bin/env python3
"""
修复导入问题的脚本
"""
import sys
import os

# 设置路径
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app/database_service')

print("sys.path设置:")
for i, p in enumerate(sys.path[:3]):
    print(f"  {i}: {p}")

# 关键：在导入前确保asyncpg可用
try:
    import asyncpg
    print(f"✅ asyncpg: {asyncpg.__version__}")
except ImportError as e:
    print(f"⚠️  asyncpg不可用: {e}")
    # 创建模拟asyncpg
    import types
    mock_asyncpg = types.ModuleType('asyncpg')
    sys.modules['asyncpg'] = mock_asyncpg
    print("🔄 使用模拟asyncpg")

# 现在导入
try:
    from database_service.managers.postgres_manager import PostgresDatabaseManager
    print("✅ 导入成功!")
    print(f"PostgresDatabaseManager: {PostgresDatabaseManager}")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
