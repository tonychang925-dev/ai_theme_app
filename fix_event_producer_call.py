"""
修复 EventProducer.publish() 调用问题
"""
import os

file_path = "database_service/streams/stream_gateway.py"

if not os.path.exists(file_path):
    print(f"❌ 文件不存在: {file_path}")
    exit(1)

print(f"🔧 修复文件: {file_path}")

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复 EventProducer.publish() 调用
# 查找并修复调用
lines = content.split('\n')
fixed_lines = []

for line in lines:
    # 修复 EventProducer.publish 调用
    if 'await self.event_producer.publish(' in line and 'data=' in line:
        print(f"📌 修复 EventProducer.publish 调用: {line}")
        
        # 提取参数
        import re
        match = re.search(r'data=([^,)]+)', line)
        if match:
            data_param = match.group(1)
            # 替换参数名
            fixed_line = line.replace(f'data={data_param}', f'{data_param}')
            print(f"   修复后: {fixed_line}")
            line = fixed_line
    
    fixed_lines.append(line)

# 保存修复
with open(file_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))

print("✅ 修复完成")

# 测试修复
print("\n🧪 测试修复...")
test_code = '''
import sys
import os
sys.path.insert(0, 'database_service')

try:
    from streams.stream_gateway import StreamEnhancedGateway
    print('✅ 导入成功')
    
    class MockGateway:
        async def close(self):
            pass
    
    import asyncio
    
    async def test():
        gateway = StreamEnhancedGateway(MockGateway())
        
        # 测试事件发布
        try:
            result = await gateway.publish_event({
                'id': 'test_event',
                'classification': 'test'
            })
            print(f'✅ 事件发布: {result}')
        except Exception as e:
            print(f'❌ 事件发布失败: {e}')
    
    asyncio.run(test())
    
except Exception as e:
    print(f'❌ 导入失败: {e}')
    import traceback
    traceback.print_exc()
'''

with open('test_fix.py', 'w') as f:
    f.write(test_code)

import subprocess
result = subprocess.run(['python', 'test_fix.py'], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
