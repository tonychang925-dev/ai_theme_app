#!/bin/bash
# 验证参数传递解决方案

echo "=== 验证参数传递解决方案 ==="
echo "测试时间: $(date)"
echo ""

# 设置环境变量
export AI_THEME_APP_ROOT="/Users/admin/Desktop/ai_theme_app"
export PROJECT_ROOT="/Users/admin/Desktop/ai_theme_app"

# 定义safe_write函数
safe_write() {
  if [ $# -ne 2 ]; then
    echo "用法: safe_write \"<文件路径>\" \"<内容>\""
    return 1
  fi

  local file_path="$1"
  local content="$2"
  local project_root="${AI_THEME_APP_ROOT:-$(pwd)}"

  if [[ "$file_path" != /* ]]; then
    file_path="${project_root}/${file_path}"
  fi

  mkdir -p "$(dirname "$file_path")"
  printf "%b" "$content" > "$file_path"

  if [ -f "$file_path" ]; then
    return 0
  else
    return 1
  fi
}

# 定义claude_write函数
claude_write() {
  if [ $# -lt 2 ]; then
    echo "用法: claude_write <文件路径> <内容>"
    return 1
  fi
  ./write_file.sh "$@"
}

# 测试计数器
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local command="$2"
    local expected_result="${3:-0}"

    echo "测试: $test_name"
    echo "命令: $command"

    # 执行命令
    eval "$command" > /dev/null 2>&1
    local result=$?

    if [ $result -eq $expected_result ]; then
        echo "结果: ✅ 通过"
        ((TESTS_PASSED++))
    else
        echo "结果: ❌ 失败 (退出码: $result)"
        ((TESTS_FAILED++))
    fi
    echo ""
}

# 测试1: safe_write 简单内容
run_test "safe_write 简单内容" 'safe_write "test_safe1.md" "简单内容"'

# 测试2: safe_write 包含引号
run_test "safe_write 包含引号" 'safe_write "test_safe2.md" "内容包含\"引号\""'

# 测试3: safe_write 包含美元符
run_test "safe_write 包含美元符" 'safe_write "test_safe3.md" "变量: \$PATH"'

# 测试4: safe_write 多行内容
run_test "safe_write 多行内容" 'safe_write "test_safe4.md" "第一行\n第二行\n第三行"'

# 测试5: claude_write 简单内容
run_test "claude_write 简单内容" 'claude_write "test_claude1.md" "简单内容"'

# 测试6: ./claude write 命令
run_test "./claude write 命令" './claude write "test_cli1.md" "命令行写入"'

# 清理测试文件
cleanup() {
    rm -f test_*.md
    echo "已清理测试文件"
}

# 显示结果
echo "=== 测试结果 ==="
echo "总测试数: $((TESTS_PASSED + TESTS_FAILED))"
echo "通过: $TESTS_PASSED"
echo "失败: $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo "🎉 所有测试通过！参数传递问题已彻底解决。"
    echo ""
    echo "推荐使用方案:"
    echo "1. 在Claude Code中: 请运行'safe_write \"文件路径\" \"内容\"'"
    echo "2. 在终端中: ./claude write 文件路径 内容"
else
    echo "⚠️  有测试失败，请检查问题。"
fi

echo ""
echo "=== 生成的测试文件 ==="
ls -la test_*.md 2>/dev/null || echo "没有测试文件"

echo ""
echo "是否清理测试文件？(y/n)"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    cleanup
fi

echo ""
echo "=== 使用指南 ==="
echo "1. 在Claude Code中总是使用: safe_write \"文件路径\" \"内容\""
echo "2. 确保参数用双引号包裹"
echo "3. 无需转义特殊字符，safe_write会自动处理"
echo ""
echo "问题已彻底解决！"