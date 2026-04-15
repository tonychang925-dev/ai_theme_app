#!/bin/bash
# 模拟Claude Code解析用户输入的命令

echo "=== 模拟Claude Code参数解析 ==="
echo ""

# 模拟用户输入：请运行'./write_file.sh "test.md" "内容"'
USER_INPUT='./write_file.sh "test.md" "内容"'
echo "用户输入: $USER_INPUT"

# Claude Code会解析这个字符串，提取命令和参数
# 问题可能出现在这里：Claude Code如何解析引号？

echo ""
echo "=== 测试不同解析方式 ==="

# 方式1：直接eval（可能有问题）
echo "方式1: 直接eval"
CMD='./write_file.sh "test_eval1.md" "简单内容"'
echo "命令: $CMD"
eval $CMD
echo "状态: $?"

# 方式2：使用数组（更安全）
echo ""
echo "方式2: 使用数组"
CMD_ARRAY=("./write_file.sh" "test_array.md" "简单内容")
echo "命令: ${CMD_ARRAY[@]}"
"${CMD_ARRAY[@]}"
echo "状态: $?"

# 方式3：包含特殊字符
echo ""
echo "方式3: 包含特殊字符"
SPECIAL_CMD='./write_file.sh "test_special.md" "内容有\"引号\""'
echo "命令: $SPECIAL_CMD"
eval $SPECIAL_CMD
echo "状态: $?"

echo ""
echo "=== 分析问题 ==="
echo "Claude Code可能使用类似方式1的解析，这会导致："
echo "1. 引号嵌套问题"
echo "2. 特殊字符转义问题"
echo "3. 参数边界问题"