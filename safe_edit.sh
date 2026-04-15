#!/bin/bash
# 安全编辑脚本 - 彻底解决Edit工具参数传递问题

# 安全编辑函数
safe_edit() {
  if [ $# -lt 3 ]; then
    echo "用法: safe_edit \"<文件路径>\" \"<旧字符串>\" \"<新字符串>\" [replace_all]"
    echo "示例: safe_edit \"test.txt\" \"旧内容\" \"新内容\""
    echo "注意: 所有参数必须用双引号包裹"
    return 1
  fi

  local file_path="$1"
  local old_string="$2"
  local new_string="$3"
  local replace_all="${4:-false}"

  # 使用项目根目录
  local project_root="${AI_THEME_APP_ROOT:-$(pwd)}"

  # 如果是相对路径，转换为绝对路径
  if [[ "$file_path" != /* ]]; then
    file_path="${project_root}/${file_path}"
  fi

  # 检查文件是否存在
  if [ ! -f "$file_path" ]; then
    echo "❌ 文件不存在: $file_path"
    return 1
  fi

  # 读取文件内容
  local file_content
  file_content=$(cat "$file_path")

  # 检查旧字符串是否存在
  if [[ "$file_content" != *"$old_string"* ]]; then
    echo "❌ 在文件中未找到旧字符串"
    return 1
  fi

  # 执行替换
  if [ "$replace_all" = "true" ]; then
    # 替换所有出现
    local new_content="${file_content//$old_string/$new_string}"
  else
    # 只替换第一次出现
    local new_content="${file_content/$old_string/$new_string}"
  fi

  # 写入文件
  printf "%b" "$new_content" > "$file_path"

  if [ $? -eq 0 ]; then
    echo "✅ 文件编辑成功: $file_path"
    return 0
  else
    echo "❌ 文件编辑失败: $file_path"
    return 1
  fi
}

# 如果直接调用脚本
if [ "${1:-}" = "edit" ]; then
  if [ $# -lt 4 ]; then
    echo "用法: $0 edit \"<文件路径>\" \"<旧字符串>\" \"<新字符串>\" [replace_all]"
    exit 1
  fi
  FILE_PATH="$2"
  OLD_STRING="$3"
  NEW_STRING="$4"
  REPLACE_ALL="${5:-false}"

  safe_edit "$FILE_PATH" "$OLD_STRING" "$NEW_STRING" "$REPLACE_ALL"
  exit $?
fi

# 导出函数
export -f safe_edit

echo "🔧 安全编辑函数已加载"
echo "使用方法: safe_edit \"文件路径\" \"旧字符串\" \"新字符串\" [replace_all]"