#!/usr/bin/env python3
import re

def extract_codes_from_md(file_path, table_start_marker=None):
    """从Markdown表格中提取股票代码"""
    codes = []
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_table = False
    for line in lines:
        line = line.strip()

        # 如果指定了表格开始标记
        if table_start_marker and table_start_marker in line:
            in_table = True
            continue

        # 检测表格行（包含|字符且不是表头分隔线）
        if '|' in line and line.startswith('|') and '---' not in line:
            # 提取所有单元格
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 3:
                # 尝试提取股票代码（可能被`包围）
                code_cell = parts[1] if '代码' in parts[0] else parts[2] if len(parts) > 2 else parts[1]
                # 清理代码
                code = code_cell.strip().strip('`')
                if code.isdigit() and (len(code) == 6 or len(code) == 6):
                    codes.append(code)

    return codes

# 提取技术形态筛选报告中的股票
tech_file = 'flag_technical_patterns_report_20260409_094041.md'
tech_codes = extract_codes_from_md(tech_file)
print(f"技术形态筛选报告股票 ({len(tech_codes)} 只):")
for code in tech_codes:
    print(f"  {code}")

# 提取综合报告中的重点关注股票
comp_file = 'daily_comprehensive_report_2026_04_08_20260409_094021.md'
comp_codes = extract_codes_from_md(comp_file)
print(f"\n综合报告重点关注股票 ({len(comp_codes)} 只):")
for code in comp_codes[:30]:  # 只显示前30只
    print(f"  {code}")

# 找出重叠股票
overlap = set(tech_codes) & set(comp_codes)
print(f"\n重叠股票 (同时出现在两个报告中) ({len(overlap)} 只):")
for code in sorted(overlap):
    print(f"  {code}")

# 输出详细重叠信息
print("\n=== 重叠股票详细分析 ===")
# 读取两个文件内容获取详细信息
def load_stock_info(file_path):
    """加载股票详细信息"""
    stocks = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 使用正则提取表格行
    lines = content.split('\n')
    for line in lines:
        if '|' in line and line.startswith('|') and '---' not in line and '代码' not in line:
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 4:
                code = parts[1].strip().strip('`')
                if code.isdigit() and len(code) == 6:
                    stocks[code] = {
                        'name': parts[2] if len(parts) > 2 else '',
                        '涨幅': parts[3] if len(parts) > 3 else '',
                        '技术形态': parts[9] if len(parts) > 9 else '' if file_path == tech_file else parts[8] if len(parts) > 8 else ''
                    }
    return stocks

tech_stocks = load_stock_info(tech_file)
comp_stocks = load_stock_info(comp_file)

print("代码\t名称\t涨幅(技术)\t涨幅(综合)\t技术形态")
for code in sorted(overlap):
    tech = tech_stocks.get(code, {})
    comp = comp_stocks.get(code, {})
    print(f"{code}\t{tech.get('name', '')}\t{tech.get('涨幅', '')}\t{comp.get('涨幅', '')}\t{tech.get('技术形态', '')}")