#!/usr/bin/env python3
"""
统计任意交易日股票flag<0和flag>2的股票清单（通用版）
支持命令行参数指定日期
"""

import json
from pathlib import Path
from collections import defaultdict
import csv
from datetime import datetime
import sys
import argparse

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='统计特殊flag股票')
    parser.add_argument('--date', type=str, default=None,
                       help='目标日期，格式: YYYY-MM-DD (例如: 2026-04-20)')
    parser.add_argument('--output', type=str, default=None,
                       help='输出文件名前缀')
    parser.add_argument('--dedup', action='store_true',
                       help='是否去重（默认不去重）')
    parser.add_argument('--list-dates', action='store_true',
                       help='列出可用的日期')
    
    return parser.parse_args()

def list_available_dates():
    """列出可用的日期"""
    files = list(STOCK_DAILY_DIR.glob("*_*_stocks.jsonl"))
    dates = set()
    
    for file_path in files:
        # 从文件名提取日期：prefix_YYYY-MM-DD_stocks.jsonl
        name = file_path.name
        parts = name.split('_')
        if len(parts) >= 3:
            date_part = parts[1]
            # 检查是否为日期格式
            if len(date_part) == 10 and date_part[4] == '-' and date_part[7] == '-':
                dates.add(date_part)
    
    sorted_dates = sorted(dates)
    print(f"可用的日期 ({len(sorted_dates)}个):")
    for date in sorted_dates:
        print(f"  {date}")
    
    return sorted_dates

def find_latest_date():
    """查找最新的日期"""
    dates = list_available_dates()
    if dates:
        return dates[-1]
    return None

def extract_special_flag_stocks(target_date, dedup=False):
    """提取特殊flag值的股票"""
    # 查找目标日期的所有文件
    pattern = f"*_{target_date}_stocks.jsonl"
    files = list(STOCK_DAILY_DIR.glob(pattern))
    if not files:
        print(f"未找到{target_date}的数据文件")
        return {}, 0, 0, {}

    print(f"分析{len(files)}个{target_date}的数据文件...")

    if dedup:
        # 去重模式
        negative_stocks = {}  # flag < 0
        greater_stocks = {}   # flag > 2
        all_special_stocks = {}  # 所有符合条件的股票
    else:
        # 不去重模式
        negative_stocks = []  # flag < 0
        greater_stocks = []   # flag > 2
        all_special_stocks = []  # 所有符合条件的股票

    # 统计各个flag值的数量（不去重）
    flag_counts = defaultdict(int)
    total_records = 0  # 总记录数（含重复）
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

                    total_records += 1

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
                        stock_code = data[2] if len(data) > 2 else "unknown"
                        stock_name = data[3] if len(data) > 3 else "unknown"

                        stock_info = {
                            'code': stock_code,
                            'name': stock_name,
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

                        if dedup:
                            # 去重模式
                            if flag_category == "negative":
                                if stock_code in negative_stocks:
                                    # 如果已存在，更新出现次数
                                    negative_stocks[stock_code]['count'] += 1
                                else:
                                    stock_info['count'] = 1
                                    negative_stocks[stock_code] = stock_info
                            elif flag_category == "greater_than_2":
                                if stock_code in greater_stocks:
                                    greater_stocks[stock_code]['count'] += 1
                                else:
                                    stock_info['count'] = 1
                                    greater_stocks[stock_code] = stock_info

                            # 存储到所有特殊股票
                            if stock_code in all_special_stocks:
                                all_special_stocks[stock_code]['count'] += 1
                            else:
                                stock_info['count'] = 1
                                all_special_stocks[stock_code] = stock_info
                        else:
                            # 不去重模式
                            stock_info['count'] = 1
                            if flag_category == "negative":
                                negative_stocks.append(stock_info)
                            elif flag_category == "greater_than_2":
                                greater_stocks.append(stock_info)
                            
                            all_special_stocks.append(stock_info)

                    total_stocks += 1

    # 准备返回结果
    if dedup:
        special_stocks = {
            "negative": list(negative_stocks.values()),
            "greater_than_2": list(greater_stocks.values()),
            "all_special": list(all_special_stocks.values())
        }
    else:
        special_stocks = {
            "negative": negative_stocks,
            "greater_than_2": greater_stocks,
            "all_special": all_special_stocks
        }

    # 统计信息
    print(f"\n统计结果:")
    print(f"  总记录数（含重复）: {total_records}")
    print(f"  总股票数: {total_stocks}")
    print(f"  flag<0的股票数: {len(special_stocks['negative'])}")
    print(f"  flag>2的股票数: {len(special_stocks['greater_than_2'])}")
    print(f"  特殊flag股票总数: {len(special_stocks['all_special'])}")

    # 打印flag值分布
    print(f"\nflag值分布（含重复）:")
    for flag_val in sorted(flag_counts.keys()):
        count = flag_counts[flag_val]
        percentage = count / total_records * 100 if total_records > 0 else 0
        print(f"  flag={flag_val}: {count}次 ({percentage:.2f}%)")

    return special_stocks, total_stocks, total_records, flag_counts

def save_to_csv(special_stocks, filename_prefix, dedup=False):
    """将结果保存为CSV文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_str = filename_prefix.split('_')[-1] if '_' in filename_prefix else timestamp

    # 保存所有特殊flag股票
    all_stocks_file = f"{filename_prefix}_all_{timestamp}.csv"
    
    if dedup:
        fieldnames = ['code', 'name', 'flag', 'pct_chg', 'amount', 'volume',
                     'market_cap', 'turnover', 'amount_ratio', 'subjects_count', 'count']
    else:
        fieldnames = ['code', 'name', 'flag', 'pct_chg', 'amount', 'volume',
                     'market_cap', 'turnover', 'amount_ratio', 'subjects_count', 'file']

    with open(all_stocks_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for stock in special_stocks['all_special']:
            if dedup:
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
                    'count': stock['count']
                }
            else:
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
    return all_stocks_file

def print_summary(special_stocks, target_date, dedup=False):
    """打印简要摘要"""
    print(f"\n{'='*80}")
    print(f"{target_date}特殊flag股票统计摘要")
    print(f"{'='*80}")
    
    negative = special_stocks['negative']
    greater = special_stocks['greater_than_2']
    all_special = special_stocks['all_special']
    
    print(f"\n1. flag<0的股票: {len(negative)}只")
    if negative:
        flag_dist = defaultdict(int)
        for stock in negative:
            flag_dist[stock['flag']] += 1
        
        for flag_val in sorted(flag_dist.keys()):
            count = flag_dist[flag_val]
            print(f"   flag={flag_val}: {count}只")
    
    print(f"\n2. flag>2的股票: {len(greater)}只")
    if greater:
        flag_dist = defaultdict(int)
        for stock in greater:
            flag_dist[stock['flag']] += 1
        
        for flag_val in sorted(flag_dist.keys()):
            count = flag_dist[flag_val]
            print(f"   flag={flag_val}: {count}只")
    
    print(f"\n3. 总特殊flag股票: {len(all_special)}只")

def main():
    """主函数"""
    args = parse_arguments()
    
    if args.list_dates:
        list_available_dates()
        return
    
    if args.date:
        target_date = args.date
    else:
        # 使用最新日期
        target_date = find_latest_date()
        if not target_date:
            print("未找到任何数据文件")
            return
        print(f"未指定日期，使用最新日期: {target_date}")
    
    if not target_date:
        print("请指定日期或使用--list-dates查看可用日期")
        return
    
    print(f"开始统计{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标日期: {target_date}")
    print(f"去重模式: {'是' if args.dedup else '否'}")
    
    special_stocks, total_stocks, total_records, flag_counts = extract_special_flag_stocks(
        target_date, args.dedup
    )
    
    if not special_stocks['all_special']:
        print(f"\n未找到符合条件的特殊flag股票")
        return
    
    # 打印摘要
    print_summary(special_stocks, target_date, args.dedup)
    
    # 保存结果
    if args.output:
        filename_prefix = args.output
    else:
        filename_prefix = f"special_flags_{target_date}{'_dedup' if args.dedup else ''}"
    
    csv_file = save_to_csv(special_stocks, filename_prefix, args.dedup)
    
    print(f"\n统计完成!")
    print(f"CSV文件已生成: {csv_file}")

if __name__ == "__main__":
    main()
