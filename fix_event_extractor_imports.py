#!/usr/bin/env python3
"""
修复event_extractor.py的导入
"""
import os
from pathlib import Path

PROJECT_ROOT = Path.cwd()
extractor_file = PROJECT_ROOT / "model_service" / "services" / "event_extractor.py"

print(f"修复文件: {extractor_file}")

# 备份原文件
import shutil
backup_file = extractor_file.with_suffix('.py.backup_import_fix')
shutil.copy2(extractor_file, backup_file)
print(f"✅ 已备份到: {backup_file}")

# 读取文件
with open(extractor_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复导入语句
# 从: from llm_parser.factory import LLMParserFactory
# 改为: from model_service.llm_parser.factory import LLMParserFactory
fixed_content = content.replace(
    "from llm_parser.factory import LLMParserFactory",
    "from model_service.llm_parser.factory import LLMParserFactory"
).replace(
    "from ..llm_parser.base import LLMParser",
    "from model_service.llm_parser.base import LLMParser"
)

# 写回文件
with open(extractor_file, 'w', encoding='utf-8') as f:
    f.write(fixed_content)

print("✅ 已修复导入语句")

# 验证修复
print("\n🔍 验证修复:")
with open(extractor_file, 'r', encoding='utf-8') as f:
    new_content = f.read()

import_lines = [line for line in new_content.split('\n') if 'import' in line and 'llm_parser' in line]
print("修复后的导入语句:")
for line in import_lines:
    print(f"  {line}")

print("\n🎉 导入修复完成！")
