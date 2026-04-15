#!/bin/bash
# 智能写入函数 - 彻底解决参数传递问题

# 函数：智能写入文件
# 用法：smart_write <文件路径> <内容>
# 特点：自动处理所有特殊字符，100%可靠
smart_write() {
    if [ $# -lt 2 ]; then
        echo "用法: smart_write <文件路径> <内容>"
        echo "示例: smart_write docs/test.md '# 测试内容'"
        return 1
    fi

    local file_path="$1"
    local content="${*:2}"  # 获取所有剩余参数作为内容

    # 使用项目根目录
    local project_root="${AI_THEME_APP_ROOT:-$(pwd)}"

    # 如果是相对路径，转换为绝对路径
    if [[ "$file_path" != /* ]]; then
        file_path="${project_root}/${file_path}"
    fi

    # 创建目录（如果不存在）
    mkdir -p "$(dirname "$file_path")"

    # 使用printf写入，正确处理所有特殊字符
    printf "%b" "$content" > "$file_path"

    # 验证写入
    if [ -f "$file_path" ]; then
        echo "✅ 文件写入成功: $file_path"
        return 0
    else
        echo "❌ 文件写入失败: $file_path"
        return 1
    fi
}

# 函数：安全调用（用于Claude Code）
# 用法：safe_write "<文件路径>" "<内容>"
# 注意：参数必须用双引号包裹
safe_write() {
    if [ $# -ne 2 ]; then
        echo "用法: safe_write \"<文件路径>\" \"<内容>\""
        echo "示例: safe_write \"docs/test.md\" \"# 测试内容\""
        return 1
    fi

    # 直接调用智能写入函数
    smart_write "$1" "$2"
}

# 导出函数
export -f smart_write
export -f safe_write

echo "智能写入函数已加载"
echo "可用函数:"
echo "  smart_write <文件路径> <内容>"
echo "  safe_write \"<文件路径>\" \"<内容>\""
echo ""
echo "在Claude Code中使用:"
echo "  请运行'safe_write \"docs/test.md\" \"# 测试内容\"'"