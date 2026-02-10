"""
分析导入错误的具体原因
"""
import sys
import os
import traceback

print("🔍 分析导入错误的真正原因...")

# 模拟测试文件的路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

print(f"当前目录: {current_dir}")
print(f"服务目录: {service_dir}")
print(f"项目根目录: {project_root}")

# 设置路径（像测试文件那样）
sys.path.insert(0, project_root)
sys.path.insert(0, service_dir)

print(f"\nPython路径前3项: {sys.path[:3]}")

# 尝试导入 stream_gateway
print("\n尝试导入 stream_gateway...")
try:
    # 清除可能的缓存
    for key in list(sys.modules.keys()):
        if key.startswith('database_service.streams') or 'stream_gateway' in key:
            print(f"  清除缓存: {key}")
            del sys.modules[key]
    
    # 尝试导入
    import importlib
    module = importlib.import_module('database_service.streams.stream_gateway')
    print(f"✅ 成功导入: {module}")
    
    if hasattr(module, 'StreamEnhancedGateway'):
        print(f"✅ 找到 StreamEnhancedGateway 类")
    
except Exception as e:
    print(f"❌ 导入失败: {type(e).__name__}")
    print(f"   错误信息: {e}")
    
    # 详细追踪
    print(f"\n📋 详细追踪:")
    tb_lines = traceback.format_exc().split('\n')
    for line in tb_lines[:20]:  # 显示前20行
        if line.strip():
            print(f"   {line}")
    
    # 检查是否是 typing 问题
    if "Any" in str(e) and "is not defined" in str(e):
        print(f"\n⚠️  检测到 'Any is not defined' 错误")
        print("   可能原因:")
        print("   1. Python 3.13 中 typing 模块的兼容性问题")
        print("   2. 文件中有 from typing import ... 但 Python 环境有问题")
        print("   3. 导入的某个依赖文件有语法错误")
