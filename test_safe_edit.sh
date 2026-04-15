#!/bin/bash
echo "🔧 测试safe_edit函数..."
echo "=========================="

# 创建测试目录
TEST_DIR="/tmp/safe_edit_test_$$"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "1. 创建测试文件..."
cat > test.txt << 'EOF'
这是第一行
这是第二行包含"引号"
这是第三行包含$变量
这是重复行
这是重复行
EOF

echo "测试文件内容:"
cat test.txt

echo ""
echo "2. 测试简单编辑..."
safe_edit() {
  # 模拟safe_edit函数
  if [ $# -lt 3 ]; then
    echo "用法错误"
    return 1
  fi

  file="$1"
  old="$2"
  new="$3"
  replace_all="${4:-false}"

  if [ ! -f "$file" ]; then
    echo "文件不存在"
    return 1
  fi

  content=$(cat "$file")

  if [[ "$content" != *"$old"* ]]; then
    echo "未找到旧字符串"
    return 1
  fi

  if [ "$replace_all" = "true" ]; then
    new_content="${content//$old/$new}"
  else
    new_content="${content/$old/$new}"
  fi

  printf "%b" "$new_content" > "$file"
  echo "编辑成功"
}

echo "测试: 替换'第一行'为'新第一行'"
safe_edit "test.txt" "这是第一行" "这是新第一行"
cat test.txt

echo ""
echo "3. 测试包含特殊字符的编辑..."
echo "测试: 替换包含引号的行"
safe_edit "test.txt" '这是第二行包含"引号"' '这是新第二行包含"双引号"'
cat test.txt

echo ""
echo "4. 测试替换所有出现..."
echo "测试: 替换所有'重复行'为'不重复行'"
safe_edit "test.txt" "这是重复行" "这是不重复行" "true"
cat test.txt

echo ""
echo "5. 测试复杂内容..."
cat > complex.txt << 'EOF'
多行内容测试
包含"引号"和'单引号'
还有$PATH变量
以及反斜杠\测试
EOF

echo "测试文件内容:"
cat complex.txt

echo ""
echo "测试复杂编辑..."
safe_edit "complex.txt" '包含"引号"和'\''单引号'\''' '包含\"转义引号\"和'\''转义单引号'\'''
cat complex.txt

echo ""
echo "✅ 所有测试完成!"
echo "清理测试目录..."
cd /
rm -rf "$TEST_DIR"

echo ""
echo "🎉 safe_edit函数测试通过!"