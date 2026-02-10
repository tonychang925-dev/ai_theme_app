"""
直接修复 publish_event 方法
"""
import os

file_path = "database_service/streams/stream_gateway.py"

if not os.path.exists(file_path):
    print(f"❌ 文件不存在: {file_path}")
    exit(1)

print(f"🔧 直接修复: {file_path}")

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 查找 publish_event 方法
in_publish_event = False
publish_event_start = -1

for i, line in enumerate(lines):
    if 'async def publish_event' in line:
        in_publish_event = True
        publish_event_start = i
        print(f"📌 找到 publish_event 方法在第 {i+1} 行")
    
    if in_publish_event and 'def ' in line and i > publish_event_start and 'async def publish_event' not in line:
        in_publish_event = False
    
    if in_publish_event and 'await self.event_producer.publish(' in line:
        print(f"📌 找到 EventProducer.publish 调用在第 {i+1} 行")
        print(f"   原行: {line.rstrip()}")
        
        # 根据 EventProducer 的实际签名修复
        # EventProducer.publish(event_data, is_major=False)
        # 我们需要传递 event_with_meta 和 is_major
        
        # 查找 is_major 参数值
        is_major_value = "False"
        for j in range(max(0, i-10), i):
            if 'is_major=' in lines[j]:
                if 'is_major=True' in lines[j]:
                    is_major_value = "True"
                break
        
        # 修复调用
        # 移除 stream_key 参数，添加 is_major 参数
        if 'stream_key=' in line:
            # 提取 event_data 参数
            import re
            match = re.search(r'await self\.event_producer\.publish\(([^,]+)', line)
            if match:
                event_data_param = match.group(1).strip()
                new_line = f'            message_id = await self.event_producer.publish({event_data_param}, is_major={is_major_value})\n'
                lines[i] = new_line
                print(f"   新行: {new_line.rstrip()}")
        else:
            # 确保有 is_major 参数
            if 'is_major=' not in line:
                new_line = line.rstrip()
                if new_line.endswith(')'):
                    new_line = new_line[:-1] + f', is_major={is_major_value})'
                else:
                    new_line = new_line + f', is_major={is_major_value}'
                new_line = new_line + '\n'
                lines[i] = new_line
                print(f"   添加 is_major 参数: {new_line.rstrip()}")

# 保存修复
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("\n✅ 修复完成")

# 快速测试
print("\n🧪 快速测试...")
test_code = '''
import sys
import os
sys.path.insert(0, 'database_service')

try:
    # 创建模拟的 EventProducer 测试
    class MockEventProducer:
        async def publish(self, event_data, is_major=False):
            print(f"MockEventProducer.publish called with:")
            print(f"  event_data keys: {list(event_data.keys())}")
            print(f"  is_major: {is_major}")
            return f"mock_event_id_{is_major}"
    
    # 临时替换
    import streams.stream_gateway as sg
    original_event_producer = None
    
    # 测试调用
    import asyncio
    async def test():
        # 创建实例但不实际调用
        print("测试准备完成 - 需要实际运行完整测试验证")
    
    asyncio.run(test())
    
    print("✅ 测试准备完成")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
'''

with open('quick_test.py', 'w') as f:
    f.write(test_code)

import subprocess
result = subprocess.run(['python', 'quick_test.py'], capture_output=True, text=True)
print(result.stdout)
