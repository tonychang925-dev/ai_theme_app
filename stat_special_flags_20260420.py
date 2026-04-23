#!/usr/bin/env python3
"""
统计2026-04-20日股票flag<0和flag>2的股票清单
基于extract_special_flag_stocks.py修改
"""

import json
from pathlib import Path
from collections import defaultdict
import csv
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
TARGET_DATE = "2026-04-20"

def extract_special_flag_stocks(target_date=TARGET_DATE):
    """提取特殊flag值的股票"""
    # 查找目标日期的所有文件
    pattern = f"*_{target_date}_stocks.jsonl"
    files = list(STOCK_DAILY_DIR.glob(pattern))
    if not files:
        print(f"未找到{target_date}的数据文件")
        return {}, 0

    print(f"分析{len(files)}个{target_date}的数据文件...")

    # 存储特殊flag股票
    # flag<0: 负值flag
    # flag>2: 大于2的flag值
    special_stocks = {
        "negative": [],  # flag < 0
        "greater_than_2": [],  # flag > 2
        "all_special": []  # 所有符合条件的股票
    }

    # 统计各个flag值的数量
    flag_counts = defaultdict(int)
    total_stocks = 0

    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(data, list) and len(data) > 20:
                    flag = data[20] if len(data) > 20 else None

                    # 统计flag值
                    if flag is not None:
                        flag_counts[flag] += 1

                    # 检查特殊flag
                    is_special = False
                    flag_category = None

                    if flag is not None:
                        if flag < 0:
                            is_special = True
                            flag_category = "negative"
                        elif flag > 2:
                            is_special = True
                            flag_category = "greater_than_2"

                    if is_special and flag_category:
                        stock_info = {
                            'code': data[2] if len(data) > 2 else "unknown",
                            'name': data[3] if len(data) > 3 else "unknown",
                            'flag': flag,
                            'pct_chg': data[10] if len(data) > 10 else None,
                            'amount': data[13] if len(data) > 13 else None,
                            'volume': data[12] if len(data) > 12 else None,
                            'market_cap': data[21] if len(data) > 21 else None,
                            'turnover': data[11] if len(data) > 11 else None,
                            'subjects': data[16] if len(data) > 16 else [],
                            'file': file_path.name
                        }

                        # 计算成交额/总市值比例
                        if stock_info['amount'] and stock_info['market_cap'] and stock_info['market_cap'] > 0:
                            stock_info['amount_ratio'] = stock_info['amount'] / stock_info['market_cap'] * 100
                        else:
                            stock_info['amount_ratio'] = None

                        special_stocks[flag_category].append(stock_info)
                        special_stocks["all_special"].append(stock_info)

                    total_stocks += 1

    # 统计信息
    print(f"\n总股票数: {total_stocks}")
    print(f"flag<0的股票数: {len(special_stocks['negative'])}")
    print(f"flag>2的股票数: {len(special_stocks['greater_than_2'])}")
    print(f"特殊flag股票总数: {len(special_stocks['all_special'])}")

    # 打印flag值分布
    print(f"\nflag值分布:")
    for flag_val in sorted(flag_counts.keys()):
        count = flag_counts[flag_val]
        percentage = count / total_stocks * 100 if total_stocks > 0 else 0
        print(f"  flag={flag_val}: {count}只股票 ({percentage:.2f}%)")

    return special_stocks, total_stocks, flag_counts

def save_to_csv(special_stocks, filename_prefix="special_flags_20260420"):
    """将结果保存为CSV文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存所有特殊flag股票
    all_stocks_file = f"{filename_prefix}_all_{timestamp}.csv"
    with open(all_stocks_file, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = ['code', 'name', 'flag', 'pct_chg', 'amount', 'volume',
                     'market_cap', 'turnover', 'amount_ratio', 'subjects_count', 'file']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for stock in special_stocks['all_special']:
            row = {
                'code': stock['code'],
                'name': stock['name'],
                'flag': stock['flag'],
                'pct_chg': stock['pct_chg'],
                'amount': stock['amount'],
                'volume': stock['volume'],
                'market_cap': stock['market_cap'],
                'turnover': stock['turnover'],
                'amount_ratio': stock['amount_ratio'],
                'subjects_count': len(stock['subjects']) if stock['subjects'] else 0,
                'file': stock['file']
            }
            writer.writerow(row)

    print(f"\n所有特殊flag股票已保存到: {all_stocks_file}")

    # 保存flag<0的股票
    if special_stocks['negative']:
        negative_file = f"{filename_prefix}_negative_{timestamp}.csv"
        with open(negative_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for stock in special_stocks['negative']:
                row = {
                    'code': stock['code'],
                    'name': stock['name'],
                    'flag': stock['flag'],
                    'pct_chg': stock['pct_chg'],
                    'amount': stock['amount'],
                    'volume': stock['volume'],
                    'market_cap': stock['market_cap'],
                    'turnover': stock['turnover'],
                    'amount_ratio': stock['amount_ratio'],
                    'subjects_count': len(stock['subjects']) if stock['subjects'] else 0,
                    'file': stock['file']
                }
                writer.writerow(row)

        print(f"flag<0的股票已保存到: {negative_file}")

    # 保存flag>2的股票
    if special_stocks['greater_than_2']:
        greater_file = f"{filename_prefix}_greater_than_2_{timestamp}.csv"
        with open(greater_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for stock in special_stocks['greater_than_2']:
                row = {
                    'code': stock['code'],
                    'name': stock['name'],
                    'flag': stock['flag'],
                    'pct_chg': stock['pct_chg'],
                    'amount': stock['amount'],
                    'volume': stock['volume'],
                    'market_cap': stock['market_cap'],
                    'turnover': stock['turnover'],
                    'amount_ratio': stock['amount_ratio'],
                    'subjects_count': len(stock['subjects']) if stock['subjects'] else 0,
                    'file': stock['file']
                }
                writer.writerow(row)

        print(f"flag>2的股票已保存到: {greater_file}")

    return all_stocks_file

def print_detailed_analysis(special_stocks):
    """打印详细分析"""
    print("\n" + "="*80)
    print(f"2026-04-20特殊flag股票详细分析")
    print("="*80)

    # 分析flag<0的股票
    print(f"\n1. flag<0的股票分析 (共{len(special_stocks['negative'])}只):")
    if special_stocks['negative']:
        # 按flag值分组
        flag_groups = defaultdict(list)
        for stock in special_stocks['negative']:
            flag_groups[stock['flag']].append(stock)

        for flag_val in sorted(flag_groups.keys()):
            stocks = flag_groups[flag_val]
            print(f"  flag={flag_val}: {len(stocks)}只股票")

            # 显示前5只
            for i, stock in enumerate(stocks[:5]):
                ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
                print(f"    {i+1}. {stock['code']} {stock['name']}: "
                      f"涨幅={stock['pct_chg']:.2f}%, 资金强度={ratio_str}, "
                      f"题材数={len(stock['subjects']) if stock['subjects'] else 0}")

            if len(stocks) > 5:
                print(f"    ... 还有{len(stocks)-5}只股票")

    # 分析flag>2的股票
    print(f"\n2. flag>2的股票分析 (共{len(special_stocks['greater_than_2'])}只):")
    if special_stocks['greater_than_2']:
        # 按flag值分组
        flag_groups = defaultdict(list)
        for stock in special_stocks['greater_than_2']:
            flag_groups[stock['flag']].append(stock)

        for flag_val in sorted(flag_groups.keys()):
            stocks = flag_groups[flag_val]
            print(f"  flag={flag_val}: {len(stocks)}只股票")

            # 显示前5只
            for i, stock in enumerate(stocks[:5]):
                ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
                print(f"    {i+1}. {stock['code']} {stock['name']}: "
                      f"涨幅={stock['pct_chg']:.2f}%, 资金强度={ratio_str}, "
                      f"题材数={len(stock['subjects']) if stock['subjects'] else 0}")

            if len(stocks) > 5:
                print(f"    ... 还有{len(stocks)-5}只股票")

    # 综合统计
    print(f"\n3. 综合统计:")
    print(f"   总特殊flag股票数: {len(special_stocks['all_special'])}")

    # 按涨幅分布
    pct_groups = {'跌停': 0, '大跌': 0, '小跌': 0, '小涨': 0, '大涨': 0, '涨停': 0}
    for stock in special_stocks['all_special']:
        if stock['pct_chg'] is not None:
            if stock['pct_chg'] <= -9.9:
                pct_groups['跌停'] += 1
            elif stock['pct_chg'] <= -5:
                pct_groups['大跌'] += 1
            elif stock['pct_chg'] < 0:
                pct_groups['小跌'] += 1
            elif stock['pct_chg'] < 5:
                pct_groups['小涨'] += 1
            elif stock['pct_chg'] < 9.9:
                pct_groups['大涨'] += 1
            else:
                pct_groups['涨停'] += 1

    print(f"   涨幅分布:")
    for category, count in pct_groups.items():
        if count > 0:
            percentage = count / len(special_stocks['all_special']) * 100
            print(f"     {category}: {count}只 ({percentage:.1f}%)")

if __name__ == "__main__":
    print(f"开始统计{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标日期: {TARGET_DATE}")

    special_stocks, total_stocks, flag_counts = extract_special_flag_stocks()

    if special_stocks['all_special']:
        print_detailed_analysis(special_stocks)
        csv_file = save_to_csv(special_stocks)

        print(f"\n统计完成!")
        print(f"CSV文件已生成: {csv_file}")
    else:
        print(f"\n未找到符合条件的特殊flag股票")