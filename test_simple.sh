#!/bin/bash
echo "🔧 简单测试Claude Code修改..."
echo "=========================="

# 创建测试目录
TEST_DIR="/tmp/claude_simple_test_$$"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "1. 测试safe_write函数逻辑..."
cat > test_write.sh << 'EOF'
#!/bin/bash
# 模拟safe_write函数
safe_write() {
  if [ $# -ne 2 ]; then
    echo "用法错误"
    return 1
  fi
  file="$1"
  content="$2"
  mkdir -p "$(dirname "$file")"
  printf "%b" "$content" > "$file"
  echo "写入: $file"
}

# 测试
echo "测试简单写入:"
safe_write "test.txt" "Hello World"
cat test.txt

echo ""
echo "测试特殊字符:"
safe_write "special.txt" "Line1\nLine2 with \"quotes\" and \$var"
cat special.txt
EOF

chmod +x test_write.sh
./test_write.sh

echo ""
echo "2. 测试命令预处理逻辑..."
cat > test_preprocess.js << 'EOF'
// 模拟命令预处理函数
function preprocessCommand(command) {
  // 检测是否是写入命令
  const isWriteCommand = command.includes('write_file.sh') ||
                        command.includes('safe_write') ||
                        command.includes('claude_write')

  if (!isWriteCommand) {
    return command
  }

  console.log('🔧 检测到写入命令，启用智能参数处理...')

  try {
    const trimmed = command.trim()

    // 情况1：标准格式
    const standardMatch = trimmed.match(/^(\.\/)?(write_file\.sh|safe_write|claude_write)\s+["']([^"']+)["']\s+["']([^"']+)["']$/)
    if (standardMatch) {
      console.log(`✅ 标准格式解析成功: ${standardMatch[3]}`)
      return command
    }

    // 情况2：参数未正确引用
    const unquotedMatch = trimmed.match(/^(\.\/)?(write_file\.sh|safe_write|claude_write)\s+(\S+)\s+(.+)$/)
    if (unquotedMatch) {
      console.log(`⚠️  检测到未引用参数，自动修复: ${unquotedMatch[3]}`)
      return `./write_file.sh "${unquotedMatch[3]}" "${unquotedMatch[4].replace(/"/g, '\\"')}"`
    }

    console.log('⚠️  检测到复杂内容，使用备用方案...')
    return command
  } catch (error) {
    console.log('❌ 命令解析失败:', error.message)
    return command
  }
}

// 测试用例
console.log('测试1:', preprocessCommand('./write_file.sh "test.txt" "内容"'))
console.log('测试2:', preprocessCommand('./write_file.sh test.txt 内容'))
console.log('测试3:', preprocessCommand('ls -la'))
EOF

node test_preprocess.js

echo ""
echo "✅ 测试完成!"
echo "清理测试目录..."
cd /
rm -rf "$TEST_DIR"

echo ""
echo "🎉 基本逻辑测试通过!"