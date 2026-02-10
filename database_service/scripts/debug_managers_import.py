# scripts/debug_managers_import.py
"""
深入诊断 managers 模块导入问题
"""
import sys
import os
import traceback

print("🔍 深入诊断 managers 模块导入问题")
print("="*80)

# 设置路径
base_dir = "/Users/admin/Desktop/ai_theme_app/database_service"
sys.path.insert(0, base_dir)

# 1. 检查 managers 目录结构
print("1. 检查 managers 目录结构:")
managers_dir = os.path.join(base_dir, "managers")
for item in os.listdir(managers_dir):
    if item.endswith('.py'):
        print(f"   📄 {item}")

# 2. 尝试导入 managers 模块
print("\n2. 尝试导入 managers 模块:")
try:
    import managers
    print("   ✅ 导入 managers 模块成功")
    print(f"   模块内容: {dir(managers)}")
except Exception as e:
    print(f"   ❌ 导入 managers 模块失败: {e}")
    traceback.print_exc()

# 3. 尝试直接导入 base_manager
print("\n3. 尝试直接导入 base_manager:")
try:
    # 添加 managers 目录到路径
    if managers_dir not in sys.path:
        sys.path.insert(0, managers_dir)
    
    import base_manager
    print("   ✅ 直接导入 base_manager 成功")
    print(f"   类: {[c for c in dir(base_manager) if 'Manager' in c]}")
except Exception as e:
    print(f"   ❌ 直接导入失败: {e}")
    traceback.print_exc()

# 4. 检查 base_manager.py 的具体导入问题
print("\n4. 检查 base_manager.py 的内部导入:")
base_file = os.path.join(managers_dir, "base_manager.py")
try:
    with open(base_file, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines[:15], 1):
            if 'import' in line:
                print(f"   第{i}行: {line.strip()}")
except Exception as e:
    print(f"   读取失败: {e}")

# 5. 模拟测试代码中的导入
print("\n5. 模拟测试代码中的导入:")
print("   尝试: from managers import PostgresDatabaseManager")
try:
    from managers import PostgresDatabaseManager
    print("   ✅ 成功导入 PostgresDatabaseManager")
except Exception as e:
    print(f"   ❌ 导入失败: {e}")
    traceback.print_exc()

print("\n" + "="*80)