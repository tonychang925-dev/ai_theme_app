#!/usr/bin/env python3
"""
提取flag=-1和flag>2的股票清单，分析明日重点关注股票
"""

import json
from pathlib import Path
from collections import defaultdict
import statistics

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"

def extract_special_flag_stocks():
    """提取特殊flag值的股票"""
    files = list(STOCK_DAILY_DIR.glob("*_2026-04-08_stocks.jsonl"))
    if not files:
        print("未找到2026-04-08的数据文件")
        return

    print(f"分析{len(files)}个2026-04-08的数据文件...")

    # 存储特殊flag股票
    special_stocks = {
        -1: [],  # flag=-1: 放量滞涨
        3: [],   # flag=3: 罕见涨停标记
        4: [],   # flag=4: 罕见涨停标记
    }

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

                    if flag in [-1, 3, 4]:
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

                        special_stocks[flag].append(stock_info)

                    total_stocks += 1

    # 统计信息
    print(f"\n总股票数: {total_stocks}")
    for flag in [-1, 3, 4]:
        count = len(special_stocks[flag])
        print(f"flag={flag}: {count}只股票 ({count/total_stocks*100:.2f}%)")

    return special_stocks

def analyze_stocks_for_tomorrow(special_stocks):
    """分析明日需要重点关注的股票"""
    print("\n" + "="*80)
    print("明日重点关注股票分析")
    print("="*80)

    all_focus_stocks = []

    # 1. flag=-1 股票分析 (放量滞涨)
    print(f"\n1. flag=-1 股票分析 (放量滞涨 - {len(special_stocks[-1])}只):")
    print("  特征：大资金流入但涨幅有限，可能是主力吸筹或题材预热")

    if special_stocks[-1]:
        # 按成交额/总市值比例排序（资金流入强度）
        sorted_stocks = sorted(
            [s for s in special_stocks[-1] if s['amount_ratio'] is not None],
            key=lambda x: x['amount_ratio'],
            reverse=True
        )

        print(f"  重点股票（按资金流入强度排序）:")
        for i, stock in enumerate(sorted_stocks[:15]):  # 显示前15个
            focus_score = calculate_focus_score(stock, flag=-1)
            stock['focus_score'] = focus_score
            all_focus_stocks.append(stock)

            print(f"    {i+1:2d}. {stock['code']} {stock['name']}: flag={stock['flag']}, "
                  f"涨幅={stock['pct_chg']:.2f}%, 资金流入强度={stock['amount_ratio']:.2f}%, "
                  f"成交额={stock['amount']/10000:.0f}万, 关注度={focus_score:.1f}")

            # 显示题材信息
            if stock['subjects'] and len(stock['subjects']) > 0:
                subjects_str = ", ".join([f"{s[1]}" for s in stock['subjects'][:3]])
                if len(stock['subjects']) > 3:
                    subjects_str += f" 等{len(stock['subjects'])}个题材"
                print(f"        题材: {subjects_str}")

    # 2. flag=3 股票分析 (罕见涨停标记)
    print(f"\n2. flag=3 股票分析 (罕见涨停标记 - {len(special_stocks[3])}只):")
    print("  特征：100%涨停，中等资金流入，可能预示连续涨停潜力")

    if special_stocks[3]:
        for i, stock in enumerate(special_stocks[3]):
            focus_score = calculate_focus_score(stock, flag=3)
            stock['focus_score'] = focus_score
            all_focus_stocks.append(stock)

            ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
            print(f"    {i+1:2d}. {stock['code']} {stock['name']}: flag={stock['flag']}, "
                  f"涨幅={stock['pct_chg']:.2f}%, 资金流入强度={ratio_str}, "
                  f"成交额={stock['amount']/10000:.0f}万, 关注度={focus_score:.1f}")

            # 显示题材信息
            if stock['subjects'] and len(stock['subjects']) > 0:
                subjects_str = ", ".join([f"{s[1]}" for s in stock['subjects'][:5]])
                if len(stock['subjects']) > 5:
                    subjects_str += f" 等{len(stock['subjects'])}个题材"
                print(f"        题材: {subjects_str}")

    # 3. flag=4 股票分析 (罕见涨停标记)
    print(f"\n3. flag=4 股票分析 (罕见涨停标记 - {len(special_stocks[4])}只):")
    print("  特征：100%涨停，极低成交量，可能是一字板或极度惜售")

    if special_stocks[4]:
        for i, stock in enumerate(special_stocks[4]):
            focus_score = calculate_focus_score(stock, flag=4)
            stock['focus_score'] = focus_score
            all_focus_stocks.append(stock)

            ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
            print(f"    {i+1:2d}. {stock['code']} {stock['name']}: flag={stock['flag']}, "
                  f"涨幅={stock['pct_chg']:.2f}%, 资金流入强度={ratio_str}, "
                  f"成交额={stock['amount']/10000:.0f}万, 关注度={focus_score:.1f}")

            # 显示题材信息
            if stock['subjects'] and len(stock['subjects']) > 0:
                subjects_str = ", ".join([f"{s[1]}" for s in stock['subjects'][:5]])
                if len(stock['subjects']) > 5:
                    subjects_str += f" 等{len(stock['subjects'])}个题材"
                print(f"        题材: {subjects_str}")

    # 综合排序
    print("\n" + "="*80)
    print("综合关注度排序（明日重点关注）")
    print("="*80)

    # 按关注度排序
    sorted_focus = sorted(all_focus_stocks, key=lambda x: x['focus_score'], reverse=True)

    for i, stock in enumerate(sorted_focus[:20]):  # 显示前20个
        ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
        print(f"  {i+1:2d}. {stock['code']} {stock['name']} (flag={stock['flag']}): "
              f"关注度={stock['focus_score']:.1f}, 涨幅={stock['pct_chg']:.2f}%, "
              f"资金强度={ratio_str}")

    return sorted_focus

def calculate_focus_score(stock, flag):
    """计算股票关注度分数"""
    score = 0

    # 基础分数
    if flag == -1:
        score += 70  # flag=-1基础分
        # 资金流入强度加分 (0-30分)
        if stock['amount_ratio']:
            score += min(30, stock['amount_ratio'] * 3)
    elif flag == 3:
        score += 85  # flag=3基础分
        # 资金流入强度加分 (0-15分)
        if stock['amount_ratio']:
            score += min(15, stock['amount_ratio'] * 2)
    elif flag == 4:
        score += 80  # flag=4基础分
        # 对于flag=4，成交量极低可能是一字板，关注度稍低

    # 涨幅加分
    if stock['pct_chg']:
        if stock['pct_chg'] >= 9.9:  # 涨停
            score += 20
        elif stock['pct_chg'] >= 7:
            score += 10
        elif stock['pct_chg'] >= 5:
            score += 5

    # 题材丰富度加分
    if stock['subjects']:
        subject_count = len(stock['subjects'])
        score += min(10, subject_count * 0.5)

    return min(100, score)  # 上限100分

if __name__ == "__main__":
    special_stocks = extract_special_flag_stocks()
    if special_stocks:
        focus_stocks = analyze_stocks_for_tomorrow(special_stocks)