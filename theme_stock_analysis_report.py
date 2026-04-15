#!/usr/bin/env python3
"""
主题股票分析综合报告 - 2026-04-08
整合特殊flag股票分析和题材涨停潮分析
"""

import json
from pathlib import Path
from collections import defaultdict
import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"

def load_and_deduplicate_stocks(trade_date="2026-04-08"):
    """加载并去重股票数据"""
    files = list(STOCK_DAILY_DIR.glob(f"*_{trade_date}_stocks.jsonl"))
    if not files:
        return {}

    stocks_by_code = {}
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
                    stock_code = data[2] if len(data) > 2 else "unknown"
                    if stock_code == "unknown":
                        continue

                    if stock_code not in stocks_by_code:
                        stock_info = {
                            'code': stock_code,
                            'name': data[3] if len(data) > 3 else "unknown",
                            'pct_chg': data[10] if len(data) > 10 else 0,
                            'amount': data[13] if len(data) > 13 else None,
                            'volume': data[12] if len(data) > 12 else None,
                            'market_cap': data[21] if len(data) > 21 else None,
                            'subjects': data[16] if len(data) > 16 else [],
                            'flag': data[20] if len(data) > 20 else None
                        }
                        stocks_by_code[stock_code] = stock_info

    return stocks_by_code

def analyze_special_flag_stocks(stocks_by_code):
    """分析特殊flag股票"""
    special_stocks = {
        -1: [],  # flag=-1
        3: [],   # flag=3
        4: [],   # flag=4
    }

    for stock_code, stock in stocks_by_code.items():
        flag = stock.get('flag')
        if flag in [-1, 3, 4]:
            # 计算资金流入强度
            amount_ratio = None
            if stock['amount'] and stock['market_cap'] and stock['market_cap'] > 0:
                amount_ratio = stock['amount'] / stock['market_cap'] * 100

            stock_info = {
                'code': stock['code'],
                'name': stock['name'],
                'flag': flag,
                'pct_chg': stock['pct_chg'],
                'amount_ratio': amount_ratio,
                'amount': stock['amount'],
                'subjects': stock['subjects']
            }
            special_stocks[flag].append(stock_info)

    return special_stocks

def analyze_theme_limit_up_concentration(stocks_by_code, limit_up_threshold=9.9):
    """分析题材涨停集中度"""
    theme_to_stocks = defaultdict(set)
    theme_names = {}

    for stock_code, stock in stocks_by_code.items():
        for subject in stock['subjects']:
            if isinstance(subject, list) and len(subject) >= 2:
                subject_id = str(subject[0])
                subject_name = subject[1]
                theme_names[subject_id] = subject_name
                theme_to_stocks[subject_id].add(stock_code)

    theme_stats = []
    for subject_id, stock_codes in theme_to_stocks.items():
        limit_up_count = 0
        limit_up_stocks = []
        for stock_code in stock_codes:
            stock = stocks_by_code.get(stock_code)
            if stock and stock['pct_chg'] >= limit_up_threshold:
                limit_up_count += 1
                limit_up_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'pct_chg': stock['pct_chg']
                })

        total_stocks = len(stock_codes)
        if total_stocks >= 10 and limit_up_count >= 3:  # 至少有10只股票，其中3只涨停
            limit_up_ratio = limit_up_count / total_stocks * 100
            theme_stats.append({
                'subject_id': subject_id,
                'subject_name': theme_names.get(subject_id, 'unknown'),
                'limit_up_count': limit_up_count,
                'total_stocks': total_stocks,
                'limit_up_ratio': limit_up_ratio,
                'limit_up_stocks': limit_up_stocks[:5]  # 只保留前5个
            })

    theme_stats.sort(key=lambda x: x['limit_up_count'], reverse=True)
    return theme_stats

def calculate_focus_score(stock):
    """计算股票关注度分数（与analyze_tomorrow_focus.py一致）"""
    score = 0
    flag = stock['flag']

    # 基础分数
    if flag == -1:
        score += 70
        if stock['amount_ratio']:
            score += min(30, stock['amount_ratio'] * 3)
    elif flag == 3:
        score += 85
        if stock['amount_ratio']:
            score += min(15, stock['amount_ratio'] * 2)
    elif flag == 4:
        score += 80

    # 涨幅加分
    if stock['pct_chg']:
        if stock['pct_chg'] >= 9.9:
            score += 20
        elif stock['pct_chg'] >= 7:
            score += 10
        elif stock['pct_chg'] >= 5:
            score += 5

    return min(100, score)

def generate_report(stocks_by_code, special_stocks, theme_stats):
    """生成综合报告"""
    print("=" * 120)
    print("主题股票分析综合报告 - 2026-04-08")
    print("=" * 120)

    # 基础统计
    total_stocks = len(stocks_by_code)
    limit_up_stocks = [s for s in stocks_by_code.values() if s['pct_chg'] >= 9.9]
    limit_up_count = len(limit_up_stocks)

    print(f"\n📊 市场概况:")
    print(f"   总股票数量: {total_stocks}")
    print(f"   涨停股票数量: {limit_up_count} ({limit_up_count/total_stocks*100:.1f}%)")

    # 特殊flag股票统计
    flag_counts = {flag: len(stocks) for flag, stocks in special_stocks.items()}
    print(f"\n🚩 特殊flag股票统计:")
    print(f"   flag=-1 (放量滞涨): {flag_counts[-1]}只")
    print(f"   flag=3 (罕见涨停): {flag_counts[3]}只")
    print(f"   flag=4 (无量涨停): {flag_counts[4]}只")

    # 明日重点关注股票（特殊flag）
    print(f"\n🎯 明日重点关注股票 (特殊flag):")
    all_special = []
    for flag in [-1, 3, 4]:
        for stock in special_stocks[flag]:
            stock['focus_score'] = calculate_focus_score(stock)
            all_special.append(stock)

    all_special.sort(key=lambda x: x['focus_score'], reverse=True)

    for i, stock in enumerate(all_special[:10]):
        ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] else "N/A"
        print(f"   {i+1:2d}. {stock['code']} {stock['name']} (flag={stock['flag']})")
        print(f"       关注度: {stock['focus_score']:.1f}/100, 涨幅: {stock['pct_chg']:.2f}%, 资金强度: {ratio_str}")

        # 显示题材
        if stock['subjects']:
            subject_names = [s[1] for s in stock['subjects'][:2] if isinstance(s, list) and len(s) >= 2]
            if subject_names:
                print(f"       主要题材: {', '.join(subject_names)}")

    # 热点题材分析
    print(f"\n🔥 热点题材分析 (涨停集中度TOP 10):")
    for i, theme in enumerate(theme_stats[:10]):
        print(f"\n   {i+1:2d}. {theme['subject_name']}")
        print(f"       涨停股票: {theme['limit_up_count']}只 / 总股票: {theme['total_stocks']}只")
        print(f"       涨停率: {theme['limit_up_ratio']:.1f}%")

        # 显示涨停股票
        if theme['limit_up_stocks']:
            stock_str = ", ".join([f"{s['code']} {s['name']}" for s in theme['limit_up_stocks'][:3]])
            print(f"       代表股票: {stock_str}")

    # 交叉分析：特殊flag股票所属的热点题材
    print(f"\n🔗 交叉分析: 特殊flag股票与热点题材关联")
    special_stocks_by_theme = defaultdict(list)

    for flag in [-1, 3, 4]:
        for stock in special_stocks[flag]:
            for subject in stock['subjects']:
                if isinstance(subject, list) and len(subject) >= 2:
                    subject_id = str(subject[0])
                    subject_name = subject[1]
                    # 检查该题材是否在热点题材中
                    for theme in theme_stats[:20]:
                        if theme['subject_id'] == subject_id:
                            special_stocks_by_theme[subject_name].append({
                                'code': stock['code'],
                                'name': stock['name'],
                                'flag': stock['flag'],
                                'pct_chg': stock['pct_chg']
                            })
                            break

    if special_stocks_by_theme:
        print(f"   特殊flag股票集中的热点题材:")
        for theme_name, stocks in list(special_stocks_by_theme.items())[:5]:
            flag_counts = defaultdict(int)
            for stock in stocks:
                flag_counts[stock['flag']] += 1

            flag_str = ", ".join([f"flag={flag}({count}只)" for flag, count in flag_counts.items()])
            stock_codes = ", ".join([s['code'] for s in stocks[:3]])
            print(f"   • {theme_name}: {len(stocks)}只特殊flag股票 [{flag_str}]")
            print(f"     代表股票: {stock_codes}")
    else:
        print(f"   特殊flag股票未明显集中在热点题材中")

    # 投资建议
    print(f"\n" + "=" * 120)
    print("投资建议与策略")
    print("=" * 120)

    print(f"\n🎯 明日重点关注:")
    print(f"   1. 特殊flag股票:")
    print(f"      • flag=-1: 关注放量滞涨股，如 {', '.join([s['code'] for s in all_special[:3] if s['flag'] == -1])}")
    print(f"      • flag=3/4: 关注罕见涨停股，可能有连板潜力")

    print(f"\n   2. 热点题材:")
    for i, theme in enumerate(theme_stats[:3]):
        print(f"      • {theme['subject_name']}: {theme['limit_up_count']}只涨停，关注龙头股")

    print(f"\n📝 操作策略:")
    print(f"   1. 对于flag=-1股票: 关注次日开盘竞价和早盘承接力度，结合题材热度判断")
    print(f"   2. 对于flag=3/4股票: 观察次日开盘溢价和连板潜力，注意高位接力风险")
    print(f"   3. 对于热点题材: 关注涨停潮题材的持续性和扩散效应")
    print(f"   4. 风险控制: 设置止损位，避免追高风险")

    print(f"\n⚠️ 风险提示:")
    print(f"   1. flag=-1可能是主力出货，需结合其他技术指标判断")
    print(f"   2. 涨停潮题材可能快速轮动，注意及时止盈")
    print(f"   3. 市场整体情绪和成交量变化会影响题材持续性")

    print(f"\n" + "=" * 120)
    print("报告生成时间:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 120)

def main():
    print("正在生成综合报告...")

    # 1. 加载股票数据
    stocks_by_code = load_and_deduplicate_stocks("2026-04-08")
    if not stocks_by_code:
        print("未找到股票数据")
        return

    # 2. 分析特殊flag股票
    special_stocks = analyze_special_flag_stocks(stocks_by_code)

    # 3. 分析题材涨停集中度
    theme_stats = analyze_theme_limit_up_concentration(stocks_by_code)

    # 4. 生成报告
    generate_report(stocks_by_code, special_stocks, theme_stats)

if __name__ == "__main__":
    main()