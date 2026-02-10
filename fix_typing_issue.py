"""
直接修复 typing 导入问题
"""
import os
import re

# 目标文件
file_path = "database_service/streams/stream_gateway.py"

if not os.path.exists(file_path):
    print(f"❌ 文件不存在: {file_path}")
    exit(1)

print(f"🔧 修复文件: {file_path}")

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 创建备份
backup_path = file_path + '.backup'
with open(backup_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ 已创建备份: {backup_path}")

# 方案1: 尝试简单修复 - 确保 typing 导入正确
lines = content.split('\n')
fixed_lines = []

for i, line in enumerate(lines):
    # 修复 typing 导入
    if 'from typing import Dict, List, Any, Optional, Callable, Union' in line:
        print(f"📌 找到 typing 导入在第 {i+1} 行")
        print(f"   原行: {line}")
        
        # 方案A: 保留但确保正确
        fixed_line = line
        # 方案B: 移除 typing 导入，稍后内联注释
        # fixed_line = "# " + line + "  # 已注释掉，避免 Python 3.13 导入问题"
        
        print(f"   新行: {fixed_line}")
        fixed_lines.append(fixed_line)
    else:
        fixed_lines.append(line)

# 保存方案1
output_path1 = file_path + '.fixed1.py'
with open(output_path1, 'w', encoding='utf-8') as f:
    f.write('\n'.join(fixed_lines))
print(f"✅ 方案1保存到: {output_path1}")

# 方案2: 完全移除类型注解
print("\n🔄 尝试方案2: 完全移除类型注解...")
content_no_types = content

# 移除 typing 导入
content_no_types = re.sub(r'^from typing import .*$', '', content_no_types, flags=re.MULTILINE)

# 移除函数参数的类型注解
content_no_types = re.sub(r'def \w+\([^)]*\) -> [^:]*:', lambda m: m.group().split('->')[0] + ':', content_no_types)
content_no_types = re.sub(r':\s*Dict\[[^\]]*\]', '', content_no_types)
content_no_types = re.sub(r':\s*List\[[^\]]*\]', '', content_no_types)
content_no_types = re.sub(r':\s*Optional\[[^\]]*\]', '', content_no_types)
content_no_types = re.sub(r':\s*Callable\[[^\]]*\]', '', content_no_types)
content_no_types = re.sub(r':\s*Union\[[^\]]*\]', '', content_no_types)
content_no_types = re.sub(r':\s*Any\b', '', content_no_types)
content_no_types = re.sub(r'->\s*Any\b', '', content_no_types)
content_no_types = re.sub(r'->\s*Optional\[[^\]]*\]', '', content_no_types)
content_no_types = re.sub(r'->\s*Dict\[[^\]]*\]', '', content_no_types)

# 移除重复的空行
content_no_types = re.sub(r'\n\s*\n\s*\n', '\n\n', content_no_types)

output_path2 = file_path + '.fixed2.py'
with open(output_path2, 'w', encoding='utf-8') as f:
    f.write(content_no_types)
print(f"✅ 方案2保存到: {output_path2}")

# 方案3: 直接替换原文件（推荐）
print("\n🚀 应用方案3: 直接修复原文件...")

# 重新读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    original_lines = f.readlines()

# 直接编辑原文件
with open(file_path, 'w', encoding='utf-8') as f:
    for line in original_lines:
        # 替换 typing 导入
        if 'from typing import' in line:
            # 修改为更简单的导入
            f.write('# from typing import Dict, List, Any, Optional, Callable, Union  # 已注释，避免 Python 3.13 问题\n')
            print(f"📝 注释掉 typing 导入: {line.strip()}")
        else:
            # 移除所有类型注解
            cleaned_line = line
            
            # 移除参数类型注解
            cleaned_line = re.sub(r':\s*Dict\[[^\]]*\]', '', cleaned_line)
            cleaned_line = re.sub(r':\s*List\[[^\]]*\]', '', cleaned_line)
            cleaned_line = re.sub(r':\s*Optional\[[^\]]*\]', '', cleaned_line)
            cleaned_line = re.sub(r':\s*Callable\[[^\]]*\]', '', cleaned_line)
            cleaned_line = re.sub(r':\s*Union\[[^\]]*\]', '', cleaned_line)
            cleaned_line = re.sub(r':\s*Any\b', '', cleaned_line)
            cleaned_line = re.sub(r'->\s*Any\b', '', cleaned_line)
            
            f.write(cleaned_line)

print("✅ 原文件已修复")

# 验证修复
print("\n🔍 验证修复结果...")
with open(file_path, 'r', encoding='utf-8') as f:
    fixed_content = f.read()

# 检查
if 'from typing import' in fixed_content:
    print("⚠️  警告: 仍然存在 typing 导入")
else:
    print("✅ 已移除 typing 导入")

if ': Any' in fixed_content or '-> Any' in fixed_content:
    print("⚠️  警告: 仍然存在 Any 类型")
else:
    print("✅ 已移除 Any 类型")

print("\n🎉 修复完成！")
print("📋 可以运行测试验证修复效果:")
print(f"   python database_service/tests/streams/test_stream_enhanced_gateway_unit.py")
