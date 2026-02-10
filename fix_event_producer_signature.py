"""
修复 EventProducer.publish() 调用签名
"""
import os
import re

file_path = "database_service/streams/stream_gateway.py"

if not os.path.exists(file_path):
    print(f"❌ 文件不存在: {file_path}")
    exit(1)

print(f"🔧 修复文件: {file_path}")

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 查找 EventProducer.publish 调用
print("\n📋 查找 EventProducer.publish 调用...")
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'self.event_producer.publish' in line:
        print(f"第 {i+1} 行: {line.strip()}")

# 修复调用 - 原来的代码可能是：
# await self.event_producer.publish(event_with_meta, stream_key=stream_key)
# 应该改为：
# await self.event_producer.publish(event_with_meta, is_major=is_major)

# 使用正则表达式修复
print("\n🔄 修复调用签名...")

# 修复 publish_event 方法中的调用
# 查找 publish_event 方法
publish_event_start = -1
for i, line in enumerate(lines):
    if 'async def publish_event' in line:
        publish_event_start = i
        break

if publish_event_start != -1:
    print(f"找到 publish_event 方法在第 {publish_event_start+1} 行")
    
    # 查找方法内的调用
    for i in range(publish_event_start, min(publish_event_start + 50, len(lines))):
        if 'await self.event_producer.publish(' in lines[i]:
            print(f"找到调用在第 {i+1} 行: {lines[i].strip()}")
            
            # 提取 is_major 参数
            is_major_value = "True" if "is_major=True" in lines[i-5:i+5] else "False"
            
            # 修复调用
            old_line = lines[i]
            # 移除 stream_key 参数，添加 is_major 参数
            if 'stream_key=' in old_line:
                # 提取 event_data 参数
                match = re.search(r'await self\.event_producer\.publish\(([^,]+)', old_line)
                if match:
                    event_data_param = match.group(1)
                    new_line = f'            message_id = await self.event_producer.publish({event_data_param}, is_major={is_major_value})'
                    lines[i] = new_line
                    print(f"修复后: {new_line}")
            else:
                # 如果已经有 is_major 参数，确保正确
                if 'is_major=' not in old_line:
                    # 在参数末尾添加 is_major
                    new_line = old_line.replace(')', f', is_major={is_major_value})')
                    lines[i] = new_line
                    print(f"添加 is_major 参数: {new_line}")

# 重新构建内容
content = '\n'.join(lines)

# 保存修复
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ 修复完成")

# 验证语法
print("\n🔍 验证语法...")
try:
    compile(content, file_path, 'exec')
    print("✅ 语法检查通过")
except SyntaxError as e:
    print(f"❌ 语法错误: {e}")
    print(f"   位置: 第{e.lineno}行")
    if e.lineno:
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        for i in range(start, end):
            prefix = '>>> ' if i == e.lineno - 1 else '    '
            print(f"{prefix}{i+1}: {lines[i].rstrip()}")
