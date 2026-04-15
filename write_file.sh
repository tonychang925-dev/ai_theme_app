#!/bin/bash
# Write工具的Bash替代方案 - 增强版
# 在Claude Code中调用: 请运行'write_file.sh 文件路径 内容'
# 支持多行内容：正确处理换行符\n

set -euo pipefail

# 项目根目录：优先使用环境变量，否则使用脚本所在目录
if [ -n "${AI_THEME_APP_ROOT:-}" ]; then
    PROJECT_ROOT="$AI_THEME_APP_ROOT"
elif [ -n "${PROJECT_ROOT:-}" ]; then
    PROJECT_ROOT="$PROJECT_ROOT"
else
    # 默认使用脚本所在目录的父目录（ai_theme_app）
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$SCRIPT_DIR"
fi

# 解析参数
if [ $# -lt 2 ]; then
    echo "用法: $0 <文件路径> <内容>"
    echo "示例: $0 'docs/teams/测试.md' '# 测试文件'"
    echo "注意: 内容中的\n会被转换为换行符"
    exit 1
fi

FILE_PATH="$1"
CONTENT="$2"

# 解析路径：如果是相对路径，转换为绝对路径
if [[ "$FILE_PATH" != /* ]]; then
    # 相对路径，基于项目根目录
    FILE_PATH="${PROJECT_ROOT}/${FILE_PATH}"
fi

echo "写入文件: $FILE_PATH"
echo "内容长度: ${#CONTENT} 字符"

# 确保目录存在
DIR_PATH=$(dirname "$FILE_PATH")
mkdir -p "$DIR_PATH"

# 写入文件：使用printf处理换行符
printf "%b" "$CONTENT" > "$FILE_PATH"

# 验证写入
if [ -f "$FILE_PATH" ]; then
    echo "✅ 文件写入成功: $FILE_PATH"
    echo "文件大小: $(wc -c < "$FILE_PATH") 字节"
    echo "行数: $(wc -l < "$FILE_PATH")"
    exit 0
else
    echo "❌ 文件写入失败"
    exit 1
fi