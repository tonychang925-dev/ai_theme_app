"""
修复多行函数调用
"""
import os

file_path = "database_service/streams/stream_gateway.py"

if not os.path.exists(file_path):
    print(f"❌ 文件不存在: {file_path}")
    exit(1)

print(f"🔧 修复文件: {file_path}")

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 查看第253-256行
print("\n📋 当前第253-256行:")
for i in range(252, min(256, len(lines))):
    print(f"{i+1}: {lines[i].rstrip()}")

# 根据 EventProducer 的签名修复
# EventProducer.publish(event_data, is_major=False)
# 所以我们需要传递 event_with_meta 和 is_major 参数

# 查找 is_major 的值
is_major_value = "False"
for i in range(245, 253):
    if 'is_major=True' in lines[i]:
        is_major_value = "True"
        break

print(f"\n🔍 分析:")
print(f"  is_major 值: {is_major_value}")
print(f"  需要传递的参数: event_with_meta, is_major={is_major_value}")

# 修复第253-256行
if len(lines) > 255:
    # 第253行应该是: message_id = await self.event_producer.publish(event_with_meta, is_major=False)
    lines[252] = f'            message_id = await self.event_producer.publish(event_with_meta, is_major={is_major_value})\n'
    
    # 删除第254-256行（多余的参数行）
    for i in range(253, 256):
        if i < len(lines):
            lines[i] = ''
    
    print("\n✅ 修复后的第253-256行:")
    for i in range(252, min(257, len(lines))):
        if lines[i].strip():  # 只显示非空行
            print(f"{i+1}: {lines[i].rstrip()}")

# 保存修复
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\n✅ 修复完成")

# 验证语法
print("\n🔍 验证语法...")
try:
    with open(file_path, 'r') as f:
        compile(f.read(), file_path, 'exec')
    print("✅ 语法检查通过")
    
    # 测试导入
    print("\n🧪 测试导入...")
    import sys
    import os
    sys.path.insert(0, 'database_service')
    
    try:
        from streams.stream_gateway import StreamEnhancedGateway
        print("✅ 导入成功")
        
        # 创建模拟 EventProducer 测试
        class MockEventProducer:
            async def publish(self, event_data, is_major=False):
                print(f"  MockEventProducer.publish 调用:")
                print(f"    收到 event_data: {type(event_data)}")
                print(f"    收到 is_major: {is_major}")
                return f"mock_event_id_{is_major}"
        
        # 临时替换进行测试
        import importlib
        import streams.stream_gateway as sg_module
        importlib.reload(sg_module)
        
        print("✅ 语法和导入测试通过")
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        
except SyntaxError as e:
    print(f"❌ 语法错误: {e}")
    print(f"   位置: 第{e.lineno}行")
    
    # 显示错误上下文
    if e.lineno:
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        print(f"\n📋 错误上下文:")
        for i in range(start, end):
            prefix = '>>> ' if i == e.lineno - 1 else '    '
            print(f"{prefix}{i+1}: {lines[i].rstrip()}")
