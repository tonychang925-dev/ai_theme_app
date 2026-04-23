import sys

with open('app.py', 'r') as f:
    lines = f.readlines()

# 找到stage1部分
for i, line in enumerate(lines):
    if 'if run_stage1:' in line:
        stage1_start = i
        # 找到try块开始
        for j in range(i+1, min(i+20, len(lines))):
            if 'try:' in lines[j]:
                try_start = j
                break
        # 在try之前插入next_trade_date计算
        insert_index = try_start
        
        new_lines = [
            '            # 计算候选池的下一交易日\n',
            '            next_trade_date_for_build = confirm_trade_date\n',
            '            if next_trade_date_for_build is None:\n',
            '                next_trade_date_for_build = await _resolve_next_trade_date(candidate_trade_date)\n',
            '\n'
        ]
        
        # 插入新行
        for idx, new_line in enumerate(new_lines):
            lines.insert(insert_index + idx, new_line)
        
        # 更新next_trade_date参数行
        for k in range(insert_index + len(new_lines), min(insert_index + len(new_lines) + 20, len(lines))):
            if 'next_trade_date=confirm_trade_date' in lines[k]:
                lines[k] = lines[k].replace('next_trade_date=confirm_trade_date', 'next_trade_date=next_trade_date_for_build')
                break
        
        print(f"在行 {insert_index} 插入next_trade_date计算")
        break

with open('app.py', 'w') as f:
    f.writelines(lines)
