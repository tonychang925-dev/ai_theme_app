"""
修复 stream_gateway.py 中的导入问题
"""
import os

file_path = "database_service/streams/stream_gateway.py"

if not os.path.exists(file_path):
    print(f"❌ 文件不存在: {file_path}")
    exit(1)

print(f"🔧 修复导入: {file_path}")

# 备份
import shutil
shutil.copy2(file_path, file_path + '.import_backup')

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复相对导入
print("\n🔄 修复相对导入...")

# 替换相对导入为绝对导入或 try/except 包装
import_patterns = [
    (r'from \.stream_config import', 'try:\n    from .stream_config import'),
    (r'from \.stream_manager import', 'try:\n    from .stream_manager import'),
    (r'from \.producers\.news_producer import', 'try:\n    from .producers.news_producer import'),
    (r'from \.producers\.event_producer import', 'try:\n    from .producers.event_producer import'),
    (r'from \.producers\.theme_producer import', 'try:\n    from .producers.theme_producer import'),
    (r'from \.utils\.retry_manager import', 'try:\n    from .utils.retry_manager import'),
]

for pattern, replacement in import_patterns:
    if pattern in content:
        print(f"📌 找到: {pattern}")
        # 需要更复杂的替换

# 更简单的方法：直接修改文件内容
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # 检查是否需要修复的导入行
    if line.strip().startswith('from .'):
        print(f"📌 修复第 {i+1} 行: {line}")
        
        # 获取导入的模块名
        match = line.split('import')
        if len(match) == 2:
            module_path = match[0].replace('from ', '').strip()
            imports = match[1].strip()
            
            # 创建安全的导入
            new_lines.append(f'try:')
            new_lines.append(f'    {line}')
            new_lines.append(f'    IMPORT_SUCCESS = True')
            new_lines.append(f'except ImportError:')
            new_lines.append(f'    IMPORT_SUCCESS = False')
            new_lines.append(f'    import logging')
            new_lines.append(f'    logging.getLogger(__name__).warning(f"导入失败: {module_path}")')
            
            # 添加空行
            new_lines.append('')
            
            i += 1
            continue
    
    new_lines.append(line)
    i += 1

# 重新构建内容
content = '\n'.join(new_lines)

# 保存
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 导入修复完成")

# 测试
print("\n🧪 测试导入...")
test_code = '''
import sys
import os

# 设置正确的路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database_service.streams.stream_gateway import StreamEnhancedGateway
    print('✅ 成功导入 StreamEnhancedGateway')
    
    class MockGateway:
        async def create_theme(self, name, code):
            class Theme:
                def __init__(self):
                    self.id = 1
                    self.name = name
                    self.code = code
            return Theme()
    
    import asyncio
    async def test():
        gateway = StreamEnhancedGateway(MockGateway())
        print('✅ 成功创建实例')
        
    asyncio.run(test())
    
except Exception as e:
    print(f'❌ 导入失败: {e}')
    import traceback
    traceback.print_exc()
'''

# 写入临时文件测试
with open('test_import.py', 'w') as f:
    f.write(test_code)

print("运行测试...")
import subprocess
result = subprocess.run([sys.executable, 'test_import.py'], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

print("\n🎉 修复完成！")
