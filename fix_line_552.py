"""
修复第552行的语法错误
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

# 显示第552行及上下文
print("\n📋 错误行上下文:")
for i in range(548, 558):
    if i < len(lines):
        print(f"{i+1:4d}: {lines[i].rstrip()}")

# 修复第552行（实际是索引551）
if len(lines) > 551:
    original_line = lines[551]
    print(f"\n🔍 第552行原内容: {original_line.rstrip()}")
    
    # 修复语法错误：items] 应该是 items
    fixed_line = original_line.replace('items]', 'items')
    
    # 如果是其他括号问题，修复常见的模式
    if fixed_line == original_line:
        # 尝试其他修复
        fixed_line = fixed_line.replace('items, ]', 'items')
        fixed_line = fixed_line.replace('items]', 'items')
        fixed_line = fixed_line.replace('items )', 'items)')
        fixed_line = fixed_line.replace('items ,', 'items,')
    
    print(f"🔧 修复后内容: {fixed_line.rstrip()}")
    
    # 应用修复
    lines[551] = fixed_line
    
    # 保存文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("✅ 已修复第552行")
else:
    print("❌ 文件不足552行")

# 验证修复
print("\n🧪 验证语法...")
try:
    with open(file_path, 'r') as f:
        compile(f.read(), file_path, 'exec')
    print("✅ 语法检查通过")
except SyntaxError as e:
    print(f"❌ 语法错误: {e}")
    print(f"   位置: 第{e.lineno}行, 列{e.offset}")
    
    # 显示错误行
    if e.lineno:
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        print(f"\n📋 错误行上下文:")
        for i in range(start, end):
            prefix = '>>> ' if i == e.lineno - 1 else '    '
            print(f"{prefix}{i+1}: {lines[i].rstrip()}")

print("\n🎉 修复完成！")
