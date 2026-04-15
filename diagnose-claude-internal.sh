#!/bin/bash
# Claude Code内部环境诊断脚本
# 在Claude Code中运行: 请运行'diagnose-claude-internal.sh'命令

set -euo pipefail

echo "=== Claude Code内部环境诊断 ==="
echo "诊断时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 环境变量检查
echo "1. 环境变量检查:"
echo "----------------------------------------"
echo "AI_THEME_APP_ROOT: ${AI_THEME_APP_ROOT:-未设置}"
echo "PROJECT_ROOT: ${PROJECT_ROOT:-未设置}"
echo "PWD: $PWD"
echo "CWD (process.cwd): $(node -e "console.log(process.cwd())")"
echo ""

# 2. 路径解析测试
echo "2. 路径解析测试:"
echo "----------------------------------------"
TEST_REL_PATH="docs/teams/diagnose-test-$(date +%s).txt"
TEST_ABS_PATH="/Users/admin/desktop/ai_theme_app/docs/teams/diagnose-test-$(date +%s).txt"

echo "测试相对路径: $TEST_REL_PATH"
echo "测试绝对路径: $TEST_ABS_PATH"
echo ""

# 3. 进程信息
echo "3. 进程信息:"
echo "----------------------------------------"
echo "进程ID: $$"
echo "父进程ID: $PPID"
echo "进程树:"
ps -ef | grep -E "($$|$PPID)" | grep -v grep || true
echo ""

# 4. 检查Claude Code配置
echo "4. Claude Code配置检查:"
echo "----------------------------------------"
if [ -f "${HOME}/.claude/settings.fast.json" ]; then
    echo "settings.fast.json存在"
    grep -o '"AI_THEME_APP_ROOT"[^,]*' "${HOME}/.claude/settings.fast.json" || echo "未找到AI_THEME_APP_ROOT配置"
else
    echo "settings.fast.json不存在"
fi
echo ""

# 5. Node.js环境检查
echo "5. Node.js环境检查:"
echo "----------------------------------------"
node -e "
console.log('Node版本:', process.version);
console.log('平台:', process.platform, process.arch);
console.log('NODE_ENV:', process.env.NODE_ENV || '未设置');
console.log('所有环境变量中包含AI_THEME的:');
Object.keys(process.env).filter(k => k.includes('AI_THEME')).forEach(k => console.log('  ', k, '=', process.env[k]));
" 2>/dev/null || echo "Node检查失败"
echo ""

# 6. 文件系统权限检查
echo "6. 文件系统权限检查:"
echo "----------------------------------------"
TARGET_DIR="/Users/admin/desktop/ai_theme_app/docs/teams"
if [ -d "$TARGET_DIR" ]; then
    echo "目标目录存在: $TARGET_DIR"
    echo "权限: $(ls -la "$TARGET_DIR/" | head -3)"

    # 测试写入
    TEST_FILE="$TARGET_DIR/diagnose-write-test-$(date +%s).txt"
    echo "测试写入到: $TEST_FILE"
    echo "诊断测试 $(date)" > "$TEST_FILE"
    if [ $? -eq 0 ]; then
        echo "✓ 写入成功"
        rm "$TEST_FILE"
    else
        echo "✗ 写入失败"
    fi
else
    echo "目标目录不存在: $TARGET_DIR"
fi
echo ""

# 7. 可能的根本原因分析
echo "7. 问题分析:"
echo "----------------------------------------"
echo "如果AI_THEME_APP_ROOT未设置，可能的原因:"
echo "1. ./claude脚本未正确传递环境变量"
echo "2. Bun运行时清除了环境变量"
echo "3. 在多代理/团队场景中环境变量丢失"
echo "4. 异步上下文切换导致环境变量不可用"
echo ""

# 8. 建议的解决方案
echo "8. 解决方案建议:"
echo "----------------------------------------"
echo "1. 强制设置环境变量:"
echo "   export AI_THEME_APP_ROOT=\"/Users/admin/desktop/ai_theme_app\""
echo "   export PROJECT_ROOT=\"\$AI_THEME_APP_ROOT\""
echo ""
echo "2. 修改Claude Code设置文件，添加环境变量:"
echo "   ~/.claude/settings.fast.json 的env部分添加:"
echo "   \"AI_THEME_APP_ROOT\": \"/Users/admin/desktop/ai_theme_app\""
echo ""
echo "3. 检查多代理启动逻辑:"
echo "   确保spawnMultiAgent.ts传递环境变量给子进程"
echo ""
echo "4. 使用绝对路径避免路径解析问题:"
echo "   在文件创建时使用完整绝对路径"
echo ""

echo "=== 诊断完成 ==="
echo ""
echo "后续步骤:"
echo "1. 如果AI_THEME_APP_ROOT未设置，需要修复环境变量传递"
echo "2. 如果路径解析失败，检查cwd.ts和path.ts的修复"
echo "3. 如果只在团队操作中失败，检查多代理环境变量传递"
echo "4. 考虑在settings.fast.json中添加项目根目录配置"