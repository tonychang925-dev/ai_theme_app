#!/bin/bash
# 诊断"Error writing file"问题

echo "=== 诊断Claude Code写入错误 ==="
echo "诊断时间: $(date)"
echo ""

# 1. 检查当前目录和环境变量
echo "1. 当前工作目录:"
pwd
echo ""
echo "环境变量:"
echo "AI_THEME_APP_ROOT: $AI_THEME_APP_ROOT"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "PWD: $PWD"
echo ""

# 2. 检查Claude脚本
echo "2. Claude脚本内容 (环境变量设置部分):"
grep -n "AI_THEME_APP_ROOT\|PROJECT_ROOT" /Users/admin/desktop/ai_theme_app/claude
echo ""

# 3. 检查docs/teams目录权限
echo "3. 目标目录权限检查:"
ls -la /Users/admin/desktop/ai_theme_app/docs/teams/
echo ""
echo "当前用户: $(whoami)"
echo ""

# 4. 直接测试文件创建
echo "4. 直接文件创建测试:"
TEST_FILE="/Users/admin/desktop/ai_theme_app/docs/teams/debug-test-$(date +%s).txt"
echo "测试文件: $TEST_FILE"
echo "测试内容" > "$TEST_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✓ 直接创建成功"
    rm "$TEST_FILE"
else
    echo "✗ 直接创建失败"
fi
echo ""

# 5. 检查tmux模式配置
echo "5. tmux团队配置检查:"
if [ -d "/Users/admin/desktop/ai_theme_app/.tmux-team-config" ]; then
    echo "配置目录存在"
    ls -la "/Users/admin/desktop/ai_theme_app/.tmux-team-config/"
else
    echo "配置目录不存在"
fi
echo ""

# 6. 检查Claude Code进程环境
echo "6. Claude Code进程检查:"
ps aux | grep -E "claude|bun.*dev-cli" | grep -v grep
echo ""

# 7. 建议的测试步骤
echo "=== 建议测试步骤 ==="
echo "1. 在Claude Code中运行:"
echo "   '请运行命令: echo \$AI_THEME_APP_ROOT'"
echo ""
echo "2. 在Claude Code中测试相对路径:"
echo "   '请在 docs/teams/test-rel-path.md 创建文件'"
echo ""
echo "3. 在Claude Code中测试绝对路径:"
echo "   '请在 /Users/admin/desktop/ai_theme_app/docs/teams/test-abs-path.md 创建文件'"
echo ""
echo "4. 检查错误详细信息:"
echo "   记录完整的错误消息，包括行号和上下文"
echo ""
echo "=== 诊断完成 ==="