#!/usr/bin/env python3
"""
快速验证event_extractor.py修改
"""
import sys
import re
from pathlib import Path

# 直接使用当前目录
current_dir = Path.cwd()
sys.path.insert(0, str(current_dir))

print("🔍 验证 event_extractor.py 修改")
print("="*60)

# 读取文件
extractor_file = current_dir / "model_service" / "service" / "event_extractor.py"
with open(extractor_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 关键检查点
checks = [
    ("有original_data字段", "'original_data'" in content),
    ("保存完整content", "content': content" in content),
    ("有data_integrity字段", "'data_integrity'" in content),
    ("有ai_response字段", "'ai_response'" in content),
    ("有event_result变量", "event_result = {" in content),
    ("有enhancement_ratio", "enhancement_ratio" in content),
]

print("✅ 修改检查:")
all_passed = True
for check_name, passed in checks:
    status = "✅" if passed else "❌"
    print(f"  {status} {check_name}")
    if not passed:
        all_passed = False

# 检查返回语句结构
print(f"\n🔍 返回语句结构:")
import ast
try:
    tree = ast.parse(content)
    
    # 查找extract_event方法
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'extract_event':
            # 找到返回语句
            for item in ast.walk(node):
                if isinstance(item, ast.Return):
                    # 获取返回语句的代码
                    start_line = item.lineno - 1
                    lines = content.split('\n')
                    
                    # 显示返回语句附近
                    start = max(0, start_line - 3)
                    end = min(len(lines), start_line + 10)
                    
                    print("返回语句上下文:")
                    for i in range(start, end):
                        prefix = ">>>" if i == start_line else "   "
                        print(f"{prefix} {i+1:3d}: {lines[i]}")
                    break
            break
            
    print("✅ 语法解析成功")
except Exception as e:
    print(f"❌ 语法解析失败: {e}")
    all_passed = False

print("\n" + "="*60)
if all_passed:
    print("🎉 event_extractor.py 修改验证通过！")
    print("可以开始修改 deepseek_parser.py")
    sys.exit(0)
else:
    print("⚠️  event_extractor.py 需要进一步修改")
    sys.exit(1)
