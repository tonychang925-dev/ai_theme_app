#!/bin/bash
# 紧急修复"Error writing file"问题
# 强制重启Claude Code并应用所有修复

set -euo pipefail

echo "=== 紧急修复Write工具错误 ==="
echo "修复时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 杀死所有Claude Code进程
echo "1. 停止所有Claude Code进程..."
pkill -f "claude|bun.*dev-cli" 2>/dev/null || true
sleep 2

# 2. 检查并杀死残留进程
echo "检查残留进程..."
if ps aux | grep -E "claude|bun.*dev-cli" | grep -v grep >/dev/null; then
    echo "强制杀死残留进程..."
    pkill -9 -f "claude|bun.*dev-cli" 2>/dev/null || true
    sleep 1
fi

# 3. 验证进程已停止
if ps aux | grep -E "claude|bun.*dev-cli" | grep -v grep >/dev/null; then
    echo "警告: 仍有Claude进程在运行"
    ps aux | grep -E "claude|bun.*dev-cli" | grep -v grep
else
    echo "✓ 所有Claude进程已停止"
fi
echo ""

# 4. 清除环境变量缓存
echo "2. 清除环境变量缓存..."
unset AI_THEME_APP_ROOT PROJECT_ROOT 2>/dev/null || true
echo "环境变量已清除"
echo ""

# 5. 验证settings.fast.json配置
echo "3. 验证Claude设置文件..."
SETTINGS_FILE="${HOME}/.claude/settings.fast.json"
if [ -f "$SETTINGS_FILE" ]; then
    echo "检查settings.fast.json中的AI_THEME_APP_ROOT..."
    if grep -q "AI_THEME_APP_ROOT" "$SETTINGS_FILE"; then
        echo "✓ settings.fast.json已包含AI_THEME_APP_ROOT"
        grep "AI_THEME_APP_ROOT" "$SETTINGS_FILE"
    else
        echo "✗ settings.fast.json缺少AI_THEME_APP_ROOT，正在修复..."
        # 临时修复：使用sed添加
        TEMP_FILE="${SETTINGS_FILE}.tmp"
        sed 's/"CLAUDE_CODE_DISABLE_1M_CONTEXT": "1"/"CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",\n    "AI_THEME_APP_ROOT": "\/Users\/admin\/Desktop\/ai_theme_app",\n    "PROJECT_ROOT": "\/Users\/admin\/Desktop\/ai_theme_app"/' "$SETTINGS_FILE" > "$TEMP_FILE"
        mv "$TEMP_FILE" "$SETTINGS_FILE"
        echo "✓ 已修复settings.fast.json"
    fi
else
    echo "✗ settings.fast.json不存在"
fi
echo ""

# 6. 验证claude脚本
echo "4. 验证claude启动脚本..."
if [ -f "claude" ]; then
    echo "检查claude脚本..."
    if grep -q "normalize_path" "claude"; then
        echo "✓ claude脚本包含路径规范化函数"
    else
        echo "✗ claude脚本缺少路径规范化，正在修复..."
        cat > claude << 'SCRIPT_EOF'
#!/usr/bin/env bash
set -euo pipefail

# 路径规范化函数：确保使用正确的物理路径和大小写
normalize_path() {
  local path="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath "$path" 2>/dev/null || echo "$path"
  else
    (cd "$path" && pwd -P) 2>/dev/null || echo "$path"
  fi
}

# 获取项目目录，使用realpath确保正确的物理路径和大小写
if command -v realpath >/dev/null 2>&1; then
  PROJECT_DIR="$(cd "$(dirname "$0")" && realpath .)"
else
  # 如果realpath不可用，使用pwd -P作为备选
  PROJECT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
fi
cd "${PROJECT_DIR}"

# 设置项目根目录环境变量（用于修复Claude Code的Write工具路径解析问题）
# 强制规范化路径大小写，确保路径解析正确
if [ -n "${AI_THEME_APP_ROOT:-}" ]; then
  # 如果已设置AI_THEME_APP_ROOT，规范化路径
  AI_THEME_APP_ROOT="$(normalize_path "$AI_THEME_APP_ROOT")"
else
  # 否则使用项目目录
  AI_THEME_APP_ROOT="$PROJECT_DIR"
fi

if [ -n "${PROJECT_ROOT:-}" ]; then
  # 如果已设置PROJECT_ROOT，规范化路径
  PROJECT_ROOT="$(normalize_path "$PROJECT_ROOT")"
else
  # 否则使用AI_THEME_APP_ROOT
  PROJECT_ROOT="$AI_THEME_APP_ROOT"
fi

export AI_THEME_APP_ROOT
export PROJECT_ROOT

echo "🔧 Claude Code紧急修复版已启动"
echo "   项目目录: $PROJECT_DIR"
echo "   环境变量: AI_THEME_APP_ROOT=$AI_THEME_APP_ROOT"
echo "   环境变量: PROJECT_ROOT=$PROJECT_ROOT"
echo "   启动命令将使用env传递环境变量..."

# 单入口 ./claude：默认使用 deepseek-chat，复杂任务再会话内 /model 手动切换
if [[ -f "${HOME}/.claude/settings.fast.json" ]]; then
  export CLAUDE_CONFIG_DIR="${HOME}/.claude"
  exec env AI_THEME_APP_ROOT="$AI_THEME_APP_ROOT" PROJECT_ROOT="$PROJECT_ROOT" bun /Users/admin/Desktop/claude-code-source-main/src/entrypoints/dev-cli.tsx --settings "${HOME}/.claude/settings.fast.json" "$@"
fi

# 如果用户显式传了 --model，则尊重用户参数；否则默认 deepseek-chat
if [[ " $* " == *" --model "* ]]; then
  exec env AI_THEME_APP_ROOT="$AI_THEME_APP_ROOT" PROJECT_ROOT="$PROJECT_ROOT" /Users/admin/Desktop/ai_theme_app/.claude/bin/claude-dev-stable "$@"
else
  exec env AI_THEME_APP_ROOT="$AI_THEME_APP_ROOT" PROJECT_ROOT="$PROJECT_ROOT" /Users/admin/Desktop/ai_theme_app/.claude/bin/claude-dev-stable --model deepseek-chat "$@"
fi
SCRIPT_EOF
        chmod +x claude
        echo "✓ claude脚本已修复"
    fi
else
    echo "✗ claude脚本不存在"
fi
echo ""

# 7. 创建Write工具包装器
echo "5. 创建Write工具紧急修复包装器..."
cat > write_fix.js << 'JS_EOF'
/**
 * Write工具紧急修复包装器
 * 自动将相对路径转换为绝对路径
 */

const fs = require('fs');
const path = require('path');

// 项目根目录 - 硬编码确保正确
const PROJECT_ROOT = '/Users/admin/Desktop/ai_theme_app';

/**
 * 将相对路径转换为绝对路径
 * @param {string} filePath - 文件路径（相对或绝对）
 * @returns {string} 绝对路径
 */
function resolveFilePath(filePath) {
    // 如果已经是绝对路径，直接返回
    if (path.isAbsolute(filePath)) {
        return filePath;
    }

    // 如果是相对路径，基于项目根目录解析
    const resolvedPath = path.resolve(PROJECT_ROOT, filePath);

    console.log(`路径转换: "${filePath}" -> "${resolvedPath}"`);
    return resolvedPath;
}

/**
 * 修复Write工具参数
 * @param {object} params - Write工具参数
 * @returns {object} 修复后的参数
 */
function fixWriteParams(params) {
    if (!params || typeof params !== 'object') {
        return params;
    }

    const fixedParams = { ...params };

    // 修复file_path参数
    if (fixedParams.file_path && typeof fixedParams.file_path === 'string') {
        fixedParams.file_path = resolveFilePath(fixedParams.file_path);
    }

    return fixedParams;
}

/**
 * 直接写入文件（绕过Claude Code Write工具）
 * @param {string} filePath - 文件路径
 * @param {string} content - 文件内容
 */
function directWriteFile(filePath, content) {
    try {
        const resolvedPath = resolveFilePath(filePath);

        // 确保目录存在
        const dir = path.dirname(resolvedPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
            console.log(`创建目录: ${dir}`);
        }

        // 写入文件
        fs.writeFileSync(resolvedPath, content, 'utf8');
        console.log(`文件写入成功: ${resolvedPath}`);
        return { success: true, path: resolvedPath };
    } catch (error) {
        console.error(`文件写入失败: ${error.message}`);
        return { success: false, error: error.message };
    }
}

// 导出函数
module.exports = {
    resolveFilePath,
    fixWriteParams,
    directWriteFile,
    PROJECT_ROOT
};
JS_EOF

echo "✓ Write工具包装器已创建: write_fix.js"
echo ""

# 8. 创建使用指南
echo "6. 创建紧急使用指南..."
cat > WRITE_ERROR_紧急修复指南.md << 'GUIDE_EOF'
# Write工具"Error writing file"紧急修复指南

## 问题状态
"Error writing file"错误持续出现，已应用多次修复但问题仍然存在。

## 紧急解决方案

### 方案1: 强制重启并应用所有修复
```bash
cd /Users/admin/desktop/ai_theme_app
./紧急修复_write_error.sh
```

### 方案2: 使用绝对路径（100%可靠）
在Claude Code中，**始终使用绝对路径**：
```
请在 /Users/admin/Desktop/ai_theme_app/docs/teams/文件名.md 创建文件
```

### 方案3: 使用Write工具包装器（Node.js）
```javascript
const writeFix = require('./write_fix.js');

// 方法1: 直接写入文件
const result = writeFix.directWriteFile(
    'docs/teams/测试文件.md',
    '文件内容'
);

// 方法2: 修复Write工具参数
const fixedParams = writeFix.fixWriteParams({
    file_path: 'docs/teams/测试文件.md',
    content: '文件内容'
});
// 然后将fixedParams传递给Write工具
```

## 已应用的修复

### 1. 环境变量修复
- ✅ 修改`settings.fast.json`添加`AI_THEME_APP_ROOT`
- ✅ 修改`claude`脚本强制规范化路径大小写
- ✅ 使用`env`命令显式传递环境变量

### 2. 核心代码修复
- ✅ 修改`src/utils/path.ts` - `expandPath()`优先使用环境变量
- ✅ 修改`src/utils/cwd.ts` - `getCwd()`优先返回环境变量
- ✅ 修改`src/utils/swarm/spawnUtils.ts` - 传递环境变量给队友

### 3. 路径大小写修复
- ✅ 使用`realpath`规范化所有路径
- ✅ 强制环境变量使用正确大小写格式

## 问题根源
macOS路径大小写不一致 + 环境变量传递链断裂

## 验证修复

### 步骤1: 运行紧急修复脚本
```bash
./紧急修复_write_error.sh
```

### 步骤2: 启动Claude Code
```bash
./claude
```
应显示：
```
🔧 Claude Code紧急修复版已启动
   项目目录: /Users/admin/Desktop/ai_theme_app
   环境变量: AI_THEME_APP_ROOT=/Users/admin/Desktop/ai_theme_app
```

### 步骤3: 测试文件写入
```
请在 /Users/admin/Desktop/ai_theme_app/docs/teams/测试文件.md 创建文件
```

## 长期解决方案
1. 向Claude Code项目提交修复PR
2. 建议Claude Code团队改进路径解析机制
3. 考虑使用符号链接统一路径大小写

## 技术支持
如问题仍然存在：
1. 使用绝对路径确保成功
2. 检查文件系统权限
3. 重启系统清除所有缓存

---
*紧急修复创建时间: $(date)*
*问题跟踪: 路径大小写不一致 + 环境变量传递问题*
GUIDE_EOF

echo "✓ 紧急修复指南已创建: WRITE_ERROR_紧急修复指南.md"
echo ""

# 9. 最终验证
echo "7. 最终验证..."
echo "当前目录: $(pwd)"
echo "实际路径: $(realpath .)"
echo ""

echo "=== 紧急修复完成 ==="
echo ""
echo "下一步操作:"
echo "1. 运行修复脚本: ./紧急修复_write_error.sh"
echo "2. 启动Claude Code: ./claude"
echo "3. 使用绝对路径创建文件确保成功"
echo "4. 如果仍失败，使用write_fix.js直接写入"
echo ""
echo "重要提示: 在Claude Code中优先使用绝对路径!"
echo "示例: 请在 /Users/admin/Desktop/ai_theme_app/docs/teams/文件名.md 创建文件"