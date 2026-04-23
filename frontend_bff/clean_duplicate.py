import sys

with open('app.py', 'r') as f:
    lines = f.readlines()

# 函数开始行
func_start = 589  # 从之前的输出得知

# 标记要删除的行范围
# 第618-658行（0-based索引：617-657）
# 但我们需要动态检测模式

# 方法：找到第一个logger.info之后出现的重复模式
# 我们查找第617行之后的重复日期协议代码

to_delete = set()
in_duplicate = False
duplicate_start = -1

# 第617行是第一个logger.info（索引616）
# 从第618行开始检查（索引617）
for i in range(617, len(lines)):
    line = lines[i]
    if i == 617 and line.strip() == '# 显式双日期协议：区分候选交易日和确认交易日':
        in_duplicate = True
        duplicate_start = i
        to_delete.add(i)
    elif in_duplicate:
        to_delete.add(i)
        # 检查是否到达第二个logger.info
        if 'logger.info(f"弱转强日期协议:' in line:
            in_duplicate = False
            # 继续检查下一段重复
    elif i > 617 and 'run_stage1 = bool(payload.run_stage1)' in line and 'run_stage2 = bool(payload.run_stage2)' in lines[i+1]:
        # 找到重复的run_stage定义
        # 删除这两行及随后的日期协议代码
        for j in range(i, min(i+50, len(lines))):
            to_delete.add(j)
            if 'logger.info(f"弱转强日期协议:' in lines[j]:
                break

# 转换为列表并排序
delete_lines = sorted(to_delete)

# 从后向前删除，避免行号变化
for line_num in reversed(delete_lines):
    if line_num < len(lines):
        del lines[line_num]

# 写入文件
with open('app.py', 'w') as f:
    f.writelines(lines)

print(f"删除了 {len(delete_lines)} 行重复代码")
