#!/bin/bash
# 全面诊断"Error writing file"问题

echo "=== 全面诊断Claude Code写入错误 ==="
echo "诊断时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 系统环境检查
echo "1. 系统环境检查:"
echo "----------------------------------------"
echo "当前用户: $(whoami)"
echo "当前目录: $(pwd)"
echo "物理路径: $(pwd -P)"
echo ""

# 2. 关键环境变量检查
echo "2. 环境变量检查:"
echo "----------------------------------------"
echo "AI_THEME_APP_ROOT: ${AI_THEME_APP_ROOT:-未设置}"
echo "PROJECT_ROOT: ${PROJECT_ROOT:-未设置}"
echo "PWD: $PWD"
echo "HOME: $HOME"
echo "PATH: $PATH"
echo ""

# 3. Claude脚本检查
echo "3. Claude脚本检查:"
echo "----------------------------------------"
CLAUDE_SCRIPT="/Users/admin/Desktop/ai_theme_app/claude"
if [ -f "$CLAUDE_SCRIPT" ]; then
    echo "✓ Claude脚本存在: $CLAUDE_SCRIPT"
    echo "权限: $(ls -la "$CLAUDE_SCRIPT")"
    echo ""
    echo "环境变量设置部分:"
    grep -n -A2 -B2 "AI_THEME_APP_ROOT\|PROJECT_ROOT" "$CLAUDE_SCRIPT"
else
    echo "✗ Claude脚本不存在: $CLAUDE_SCRIPT"
fi
echo ""

# 4. 目录权限检查
echo "4. 目录权限检查:"
echo "----------------------------------------"
TARGET_DIR="/Users/admin/Desktop/ai_theme_app/docs/teams"
if [ -d "$TARGET_DIR" ]; then
    echo "✓ 目标目录存在: $TARGET_DIR"
    echo "权限:"
    ls -la "$TARGET_DIR/" | head -5
    echo ""

    # 测试写入权限
    TEST_FILE="$TARGET_DIR/diagnose-perm-test-$(date +%s).txt"
    echo "测试写入权限: $TEST_FILE"
    echo "权限测试 $(date)" > "$TEST_FILE" 2>&1
    if [ $? -eq 0 ] && [ -f "$TEST_FILE" ]; then
        echo "✓ 直接写入成功"
        rm "$TEST_FILE"
    else
        echo "✗ 直接写入失败"
    fi
else
    echo "✗ 目标目录不存在: $TARGET_DIR"
fi
echo ""

# 5. Claude Code核心文件检查
echo "5. Claude Code核心文件检查:"
echo "----------------------------------------"
PATH_TS="/Users/admin/Desktop/claude-code-source-main/src/utils/path.ts"
if [ -f "$PATH_TS" ]; then
    echo "✓ path.ts存在: $PATH_TS"
    echo "修改时间: $(ls -la "$PATH_TS")"
    echo ""
    echo "关键修改部分 (expandPath函数):"
    grep -n -A5 -B5 "AI_THEME_APP_ROOT" "$PATH_TS" || echo "未找到AI_THEME_APP_ROOT相关代码"
else
    echo "✗ path.ts不存在: $PATH_TS"
fi
echo ""

# 6. tmux团队配置检查
echo "6. tmux团队配置检查:"
echo "----------------------------------------"
TMUX_CONFIG_DIR="/Users/admin/Desktop/ai_theme_app/.tmux-team-config"
if [ -d "$TMUX_CONFIG_DIR" ]; then
    echo "✓ tmux配置目录存在"
    ls -la "$TMUX_CONFIG_DIR/"
else
    echo "✗ tmux配置目录不存在"
fi
echo ""

# 7. 进程检查
echo "7. Claude相关进程检查:"
echo "----------------------------------------"
echo "Claude进程:"
ps aux | grep -E "claude|bun.*dev-cli" | grep -v grep || echo "未找到Claude进程"
echo ""
echo "tmux进程:"
ps aux | grep -E "[t]mux" || echo "未找到tmux进程"
echo ""

# 8. 最近创建的文件检查
echo "8. 最近创建的文件检查:"
echo "----------------------------------------"
echo "最近修改的文件 (docs/teams目录):"
find "/Users/admin/Desktop/ai_theme_app/docs/teams" -name "*.md" -type f -mtime -1 2>/dev/null | head -10 || echo "无最近文件"
echo ""

# 9. 可能的问题分析
echo "9. 可能的问题分析:"
echo "----------------------------------------"

# 检查路径大小写
ACTUAL_PATH=$(cd /Users/admin/Desktop/ai_theme_app && pwd -P)
echo "实际项目路径: $ACTUAL_PATH"
echo "环境变量路径: ${AI_THEME_APP_ROOT:-未设置}"

if [ -n "$AI_THEME_APP_ROOT" ] && [ "$ACTUAL_PATH" != "$AI_THEME_APP_ROOT" ]; then
    echo "⚠ 警告: 实际路径与环境变量路径不匹配"
    echo "  实际: $ACTUAL_PATH"
    echo "  环境: $AI_THEME_APP_ROOT"
fi

# 检查是否在tmux中
if [ -n "$TMUX" ]; then
    echo "⚠ 在tmux会话中，环境变量可能受限"
else
    echo "✓ 不在tmux会话中"
fi

# 检查Claude脚本中的路径
SCRIPT_PATH=$(grep "AI_THEME_APP_ROOT=" "$CLAUDE_SCRIPT" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"' || echo "")
if [ -n "$SCRIPT_PATH" ] && [ "$ACTUAL_PATH" != "$SCRIPT_PATH" ]; then
    echo "⚠ 警告: 脚本路径与实际路径不匹配"
    echo "  脚本: $SCRIPT_PATH"
    echo "  实际: $ACTUAL_PATH"
fi
echo ""

# 10. 诊断建议
echo "10. 诊断建议:"
echo "----------------------------------------"
echo "1. 验证环境变量传递:"
echo "   在Claude Code中运行: '请运行命令: echo \$AI_THEME_APP_ROOT'"
echo ""
echo "2. 测试路径类型:"
echo "   相对路径: '请在 docs/teams/test-rel-\$(date +%s).md 创建文件'"
echo "   绝对路径: '请在 $ACTUAL_PATH/docs/teams/test-abs-\$(date +%s).md 创建文件'"
echo ""
echo "3. 检查Write工具调用:"
echo "   提供完整的错误信息（包括调用堆栈）"
echo ""
echo "4. 可能的解决方案:"
echo "   a. 修改Claude脚本显式传递环境变量"
echo "   b. 清除bun缓存: bun --bun-cache-clear"
echo "   c. 使用包装脚本强制设置环境变量"
echo "   d. 检查Write工具的JSON参数格式"
echo ""
echo "=== 诊断完成 ==="
echo ""
echo "下一步操作建议:"
echo "1. 运行此诊断脚本: bash diagnose-write-error.sh"
echo "2. 根据诊断结果选择对应解决方案"
echo "3. 如果问题持续，提供完整错误信息和诊断结果"