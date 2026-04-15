#!/usr/bin/env python3
"""
测试数据加载
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"

def test_load_stock():
    """测试加载风华高科数据"""
    stock_code = "000636"

    # 查找所有文件
    all_files = list(STOCK_DAILY_DIR.glob("*_stocks.jsonl"))
    print(f"找到 {len(all_files)} 个数据文件")

    # 测试读取一个文件
    test_file = all_files[0]
    print(f"\n测试文件: {test_file.name}")

    # 解析文件名获取日期
    parts = test_file.name.split('_')
    print(f"文件名分割: {parts}")

    if len(parts) >= 2:
        date_str = parts[1]
        print(f"解析日期: {date_str}")

    # 读取文件内容
    count = 0
    with open(test_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"行 {line_num} JSON解析错误: {e}")
                continue

            # 检查是否是列表且包含股票代码
            if isinstance(data, list) and len(data) > 2:
                code = data[2]
                if code == stock_code:
                    print(f"\n✅ 找到股票 {stock_code} 在第 {line_num} 行")
                    print(f"数据长度: {len(data)}")
                    print(f"日期: {data[0]}")
                    print(f"名称: {data[3]}")
                    print(f"收盘价: {data[7]}")
                    return True

            count += 1
            if count >= 10:  # 只检查前10行
                break

    print("\n❌ 在前10行未找到股票")
    return False

def find_all_stock_files(stock_code="000636"):
    """查找包含指定股票的所有文件"""
    print(f"\n🔍 查找股票 {stock_code} 在所有文件中...")

    found_files = []
    all_files = list(STOCK_DAILY_DIR.glob("*_stocks.jsonl"))

    for file_path in all_files[:20]:  # 只检查前20个文件
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except:
                    continue

                if isinstance(data, list) and len(data) > 2:
                    if data[2] == stock_code:
                        # 解析日期
                        parts = file_path.name.split('_')
                        date_str = parts[1] if len(parts) >= 2 else "未知"
                        found_files.append({
                            'file': file_path.name,
                            'date': date_str,
                            'data': data
                        })
                        break  # 找到后跳出循环

    print(f"找到 {len(found_files)} 个包含股票的文件")
    for item in found_files[:5]:  # 显示前5个
        print(f"  - {item['file']} (日期: {item['date']})")
        if 'data' in item:
            print(f"    收盘价: {item['data'][7]}, 涨跌幅: {item['data'][10]}%")

    return found_files

if __name__ == "__main__":
    print("🧪 测试数据加载...")

    # 测试单个文件
    test_load_stock()

    # 查找所有文件
    find_all_stock_files()