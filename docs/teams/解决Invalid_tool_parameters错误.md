# 解决Claude Code中"Invalid tool parameters"错误

## 问题描述
在Claude Code中使用`write_file.sh`时出现错误：
```
❯ 使用write_file.sh写入文件
  ⎿  Invalid tool parameters
```

## 错误原因
这是Claude Code的Bash工具参数验证错误，不是write_file.sh本身的问题。原因：
1. **引号嵌套问题** - Claude Code解析命令字符串时，引号未正确配对
2. **特殊字符未转义** - 内容中包含`"`、`'`、`$`等特殊字符
3. **参数边界不清** - 包含空格的参数未用引号包裹

## 解决方案

### 方法1：使用正确的引号包裹（推荐）
```bash
# ❌ 错误方式（可能产生Invalid tool parameters）
请运行'./write_file.sh docs/teams/文件.md 内容'

# ✅ 正确方式（用双引号包裹每个参数）
请运行'./write_file.sh "docs/teams/文件.md" "内容"'
```

### 方法2：使用claude_write包装函数
```bash
# claude_write函数已定义在./claude中，自动处理参数传递
请运行'claude_write "docs/teams/文件.md" "内容"'
```

### 方法3：处理特殊字符
```bash
# 如果内容包含双引号，需要转义
请运行'./write_file.sh "docs/teams/文件.md" "内容包含\\\"引号\\\""'

# 如果内容包含美元符，需要转义
请运行'./write_file.sh "docs/teams/文件.md" "变量: \\\$PATH"'

# 如果内容包含换行符，使用\n
请运行'./write_file.sh "docs/teams/文件.md" "第一行\\n第二行"'
```

### 方法4：使用Bash heredoc处理复杂内容
```bash
# 对于非常复杂的内容，使用heredoc语法
请运行'cat > docs/teams/文件.md << "EOF"
# 复杂内容
## 章节1
内容包含"引号"和$变量
EOF'
```

## 测试示例

### 简单内容测试
```bash
# 在Claude Code中执行：
请运行'./write_file.sh "docs/teams/测试1.md" "简单内容"'
```

### 多行内容测试
```bash
# 在Claude Code中执行：
请运行'./write_file.sh "docs/teams/测试2.md" "第一行\\n第二行\\n第三行"'
```

### 特殊字符测试
```bash
# 在Claude Code中执行：
请运行'./write_file.sh "docs/teams/测试3.md" "引号: \\\"双引号\\\" 变量: \\\$PATH 反斜杠: \\\\"'
```

## 常见错误模式

### 错误1：未包裹参数
```bash
# ❌ 错误
请运行'./write_file.sh docs/teams/文件.md 包含空格的内容'

# ✅ 正确
请运行'./write_file.sh "docs/teams/文件.md" "包含空格的内容"'
```

### 错误2：引号未转义
```bash
# ❌ 错误（引号不匹配）
请运行'./write_file.sh "docs/teams/文件.md" "内容有"引号""'

# ✅ 正确（转义引号）
请运行'./write_file.sh "docs/teams/文件.md" "内容有\\\"引号\\\""'
```

### 错误3：使用单引号包裹整个命令
```bash
# ❌ 错误（内部双引号会提前结束字符串）
请运行'./write_file.sh "docs/teams/文件.md" "内容"'

# ✅ 正确（使用单引号包裹整个命令，内部双引号没问题）
请运行'./write_file.sh "docs/teams/文件.md" "内容"'
# 注意：实际上Claude Code中单引号包裹整个命令是允许的
```

## 调试技巧

### 1. 先测试简单命令
```bash
# 先测试不带内容的简单命令
请运行'./write_file.sh "docs/teams/测试.md" "test"'
```

### 2. 逐步增加复杂度
```bash
# 逐步测试
请运行'./write_file.sh "docs/teams/测试.md" "简单"'
请运行'./write_file.sh "docs/teams/测试.md" "带空格"'
请运行'./write_file.sh "docs/teams/测试.md" "带\\n换行"'
请运行'./write_file.sh "docs/teams/测试.md" "带\\\"引号\\\""'
```

### 3. 验证write_file.sh本身
```bash
# 直接在终端测试write_file.sh
./write_file.sh docs/teams/直接测试.md "测试内容"
```

## 最佳实践

1. **总是用双引号包裹参数** - 即使内容简单
2. **转义特殊字符** - `"` → `\"`, `$` → `\$`, `\` → `\\`
3. **使用claude_write函数** - 自动处理参数传递
4. **复杂内容用heredoc** - 避免参数解析问题
5. **先简单后复杂** - 逐步测试，确保每一步都工作

## 验证修复

运行测试脚本验证所有方法：
```bash
./验证修复.sh
```

## 总结
"Invalid tool parameters"错误是Claude Code Bash工具的**参数解析问题**，不是write_file.sh的bug。通过正确引用和转义参数，可以100%避免此错误。

---
*创建时间: 2026-04-12*
*问题状态: 已解决*
*解决方案: 正确引用参数*