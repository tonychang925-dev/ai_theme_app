#!/usr/bin/env python3
"""
分析明日重点关注股票，去重并提供详细理由
"""

import json
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"

def extract_and_deduplicate():
    """提取并去重特殊flag股票"""
    files = list(STOCK_DAILY_DIR.glob("*_2026-04-08_stocks.jsonl"))
    if not files:
        return {}

    # 使用字典去重，以股票代码为键
    special_stocks = {
        -1: {},  # flag=-1
        3: {},   # flag=3
        4: {},   # flag=4
    }

    print(f"分析{len(files)}个2026-04-08的数据文件...")

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
                    stock_code = data[2] if len(data) > 2 else "unknown"

                    if flag in [-1, 3, 4] and stock_code != "unknown":
                        if stock_code not in special_stocks[flag]:
                            stock_info = {
                                'code': stock_code,
                                'name': data[3] if len(data) > 3 else "unknown",
                                'flag': flag,
                                'pct_chg': data[10] if len(data) > 10 else None,
                                'amount': data[13] if len(data) > 13 else None,
                                'volume': data[12] if len(data) > 12 else None,
                                'market_cap': data[21] if len(data) > 21 else None,
                                'turnover': data[11] if len(data) > 11 else None,
                                'subjects': data[16] if len(data) > 16 else [],
                                'subject_count': 1,
                                'files': [file_path.name]
                            }

                            # 计算成交额/总市值比例
                            if stock_info['amount'] and stock_info['market_cap'] and stock_info['market_cap'] > 0:
                                stock_info['amount_ratio'] = stock_info['amount'] / stock_info['market_cap'] * 100
                            else:
                                stock_info['amount_ratio'] = None

                            special_stocks[flag][stock_code] = stock_info
                        else:
                            # 更新题材计数
                            special_stocks[flag][stock_code]['subject_count'] += 1

    return special_stocks

def calculate_focus_score(stock):
    """计算股票关注度分数"""
    score = 0
    flag = stock['flag']

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
    if stock['subject_count']:
        score += min(10, stock['subject_count'] * 2)

    return min(100, score)  # 上限100分

def analyze_tomorrow_focus(special_stocks):
    """分析明日重点关注股票"""
    print("\n" + "="*100)
    print("明日重点关注股票分析 (去重版)")
    print("="*100)

    all_stocks = []

    # 收集所有股票并计算关注度
    for flag in [-1, 3, 4]:
        for stock_code, stock in special_stocks[flag].items():
            stock['focus_score'] = calculate_focus_score(stock)
            all_stocks.append(stock)

    # 按关注度排序
    all_stocks.sort(key=lambda x: x['focus_score'], reverse=True)

    # 输出分析
    print(f"\n发现{len(all_stocks)}只特殊flag股票:")
    print(f"  flag=-1: {len(special_stocks[-1])}只 (放量滞涨)")
    print(f"  flag=3: {len(special_stocks[3])}只 (罕见涨停)")
    print(f"  flag=4: {len(special_stocks[4])}只 (罕见涨停)")

    print("\n" + "="*100)
    print("明日重点关注股票TOP 15")
    print("="*100)

    for i, stock in enumerate(all_stocks[:15]):
        ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
        print(f"\n{i+1:2d}. {stock['code']} {stock['name']} (flag={stock['flag']})")
        print(f"    关注度: {stock['focus_score']:.1f}/100")
        print(f"    涨幅: {stock['pct_chg']:.2f}%")
        print(f"    资金流入强度: {ratio_str}")
        print(f"    成交额: {stock['amount']/10000:.0f}万")
        print(f"    涉及题材数: {stock['subject_count']}个")

        # 分析理由
        print(f"    明日关注理由: {get_reason_for_focus(stock)}")

    # 分类分析
    print("\n" + "="*100)
    print("分类投资建议")
    print("="*100)

    print("\n1. flag=-1 股票 (放量滞涨型):")
    print("   - 特征：大资金流入但涨幅有限，可能是主力吸筹")
    print("   - 策略：关注次日开盘竞价和早盘承接力度")
    print("   - 风险：可能是出货，需结合题材热度判断")

    print("\n2. flag=3 股票 (罕见涨停型):")
    print("   - 特征：100%涨停，中等资金流入")
    print("   - 策略：关注连板潜力，观察次日开盘溢价")
    print("   - 风险：高位接力风险")

    print("\n4. flag=4 股票 (无量涨停型):")
    print("   - 特征：100%涨停，极低成交量")
    print("   - 策略：可能是一字板，关注开板后的承接")
    print("   - 风险：流动性差，开板后波动大")

    return all_stocks

def get_reason_for_focus(stock):
    """根据股票特征生成关注理由"""
    flag = stock['flag']
    pct_chg = stock['pct_chg']
    amount_ratio = stock['amount_ratio']

    if flag == -1:
        if amount_ratio and amount_ratio > 20:
            if pct_chg > 10:
                return f"放量大涨({pct_chg:.1f}%)，资金流入极强({amount_ratio:.1f}%)，可能开启主升浪"
            elif pct_chg > 0:
                return f"放量滞涨({pct_chg:.1f}%)，资金流入极强({amount_ratio:.1f}%)，主力吸筹明显"
            elif pct_chg < 0:
                return f"放量下跌({pct_chg:.1f}%)但资金流入强({amount_ratio:.1f}%)，可能是洗盘或调仓"
            else:
                return f"平盘但资金流入极强({amount_ratio:.1f}%)，异动明显"
        else:
            return "资金流入明显，关注次日能否突破"

    elif flag == 3:
        return f"罕见涨停标记，中等资金流入({amount_ratio:.1f}%)，可能预示连续涨停潜力"

    elif flag == 4:
        return f"罕见涨停标记，极低成交量(资金强度{amount_ratio:.1f}%)，可能是一字板或极度惜售"

    return "特殊标记股票，值得关注"

if __name__ == "__main__":
    special_stocks = extract_and_deduplicate()
    if any(len(stocks) > 0 for stocks in special_stocks.values()):
        focus_stocks = analyze_tomorrow_focus(special_stocks)