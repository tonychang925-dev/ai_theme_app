#!/bin/bash
# 测试Claude Code参数传递问题

echo "=== 测试Claude Code参数传递 ==="
echo "测试时间: $(date)"
echo ""

# 测试1：简单参数
echo "测试1: 简单参数"
echo "命令: ./write_file.sh \"test_simple.md\" \"简单内容\""
./write_file.sh "test_simple.md" "简单内容"
echo "状态: $?"
echo ""

# 测试2：包含空格的参数
echo "测试2: 包含空格的参数"
echo "命令: ./write_file.sh \"test_space.md\" \"内容 包含 空格\""
./write_file.sh "test_space.md" "内容 包含 空格"
echo "状态: $?"
echo ""

# 测试3：包含双引号的参数
echo "测试3: 包含双引号的参数"
echo "命令: ./write_file.sh \"test_quote.md\" \"内容包含\\\"引号\\\"\""
./write_file.sh "test_quote.md" "内容包含\"引号\""
echo "状态: $?"
echo ""

# 测试4：包含换行符的参数
echo "测试4: 包含换行符的参数"
echo "命令: ./write_file.sh \"test_newline.md\" \"第一行\\n第二行\""
./write_file.sh "test_newline.md" "第一行
第二行"
echo "状态: $?"
echo ""

# 测试5：复杂参数
echo "测试5: 复杂参数"
CONTENT='# 标题
## 子标题
内容包含"引号"和$变量
还有反斜杠\\'
echo "命令: ./write_file.sh \"test_complex.md\" \"$CONTENT\""
./write_file.sh "test_complex.md" "$CONTENT"
echo "状态: $?"
echo ""

echo "=== 测试完成 ==="
echo "检查生成的文件:"
ls -la test_*.md 2>/dev/null || echo "没有生成测试文件"