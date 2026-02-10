"""
直接导入验证脚本
"""
import sys
import os
import traceback

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
service_dir = os.path.dirname(current_dir)
sys.path.insert(0, service_dir)

print(f"Python 版本: {sys.version}")
print(f"工作目录: {os.getcwd()}")
print(f"Python 路径: {sys.path}")

# 尝试直接导入原始文件
print("\n=== 尝试导入原始 stream_gateway.py ===")
try:
    # 直接读取文件检查语法
    file_path = os.path.join(service_dir, "streams", "stream_gateway.py")
    print(f"文件路径: {file_path}")
    
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否有 typing 导入
        if 'from typing import' in content:
            print("✅ 文件中包含 'from typing import'")
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'typing' in line:
                    print(f"   第 {i+1} 行: {line}")
        
        # 检查是否有 Any 类型
        if ': Any' in content or '-> Any' in content:
            print("⚠️  文件中使用了 'Any' 类型注解")
        
        # 尝试编译检查语法
        print("\n=== 尝试编译检查 ===")
        try:
            compile(content, file_path, 'exec')
            print("✅ 文件语法检查通过")
        except SyntaxError as e:
            print(f"❌ 文件语法错误: {e}")
            print(f"   错误位置: 第{e.lineno}行, 列{e.offset}")
        
        # 尝试导入模块
        print("\n=== 尝试导入模块 ===")
        try:
            sys.path.insert(0, os.path.join(service_dir, "streams"))
            import stream_gateway
            print("✅ 成功导入 stream_gateway 模块")
            print(f"模块位置: {stream_gateway.__file__}")
            
            # 检查 StreamEnhancedGateway 类
            if hasattr(stream_gateway, 'StreamEnhancedGateway'):
                print("✅ 找到 StreamEnhancedGateway 类")
                # 尝试创建实例
                class MockGateway:
                    async def create_theme(self, name, code):
                        return type('Theme', (), {'id': 1, 'name': name, 'code': code})()
                
                gateway = stream_gateway.StreamEnhancedGateway(base_gateway=MockGateway())
                print("✅ 成功创建 StreamEnhancedGateway 实例")
            else:
                print("❌ 未找到 StreamEnhancedGateway 类")
                
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            traceback.print_exc()
        
    else:
        print(f"❌ 文件不存在: {file_path}")
        
except Exception as e:
    print(f"❌ 检查过程中出错: {e}")
    traceback.print_exc()

# 检查当前目录结构
print("\n=== 目录结构 ===")
for root, dirs, files in os.walk(service_dir, topdown=True):
    level = root.replace(service_dir, '').count(os.sep)
    indent = ' ' * 2 * level
    print(f'{indent}{os.path.basename(root)}/')
    subindent = ' ' * 2 * (level + 1)
    for file in files:
        if file.endswith('.py'):
            print(f'{subindent}{file}')
