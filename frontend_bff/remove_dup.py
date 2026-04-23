import sys

with open('app.py', 'r') as f:
    lines = f.readlines()

# 找到第一个logger.info的行号
first_logger = -1
for i, line in enumerate(lines):
    if '弱转强日期协议:' in line and first_logger == -1:
        first_logger = i
        break

if first_logger == -1:
    print("未找到logger.info")
    sys.exit(1)

print(f"第一个logger.info在行 {first_logger}")

# 从first_logger+1开始查找重复模式
to_delete = []
i = first_logger + 1
while i < len(lines):
    line = lines[i].strip()
    if line == '# 显式双日期协议：区分候选交易日和确认交易日':
        # 找到重复开始
        start = i
        # 找到下一个logger.info
        for j in range(i, min(i+50, len(lines))):
            to_delete.append(j)
            if '弱转强日期协议:' in lines[j]:
                break
        i = j + 1
    else:
        i += 1

# 删除这些行
for line_num in reversed(sorted(set(to_delete))):
    if line_num < len(lines):
        del lines[line_num]

with open('app.py', 'w') as f:
    f.writelines(lines)

print(f"删除了 {len(set(to_delete))} 行重复代码")
