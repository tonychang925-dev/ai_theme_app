#!/usr/bin/env python3
"""
测试神剑股份K线数据
验证弱转强模式：4/7缺口回补，4/8涨停
"""
import json
from datetime import datetime, date
from typing import List, Dict, Any

def load_kline_data(stock_id: str, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
    """加载股票K线数据"""
    file_path = f"/Users/admin/Desktop/ai_theme_app/theme_data_complete/_stock_kline/tushare/daily_bar/{stock_id}.jsonl"

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        data = []
        for line in lines:
            record = json.loads(line.strip())

            # 日期过滤
            trade_date = record['trade_date']
            if start_date and trade_date < start_date:
                continue
            if end_date and trade_date > end_date:
                continue

            data.append(record)

        # 按日期排序
        data.sort(key=lambda x: x['trade_date'])
        return data
    except FileNotFoundError:
        print(f"文件不存在: {file_path}")
        return []
    except Exception as e:
        print(f"加载K线数据失败: {e}")
        return []

def analyze_weak_to_strong(kline_data: List[Dict[str, Any]], target_date: str) -> Dict[str, Any]:
    """分析弱转强模式"""
    # 找到目标日期和前一日
    dates = [d['trade_date'] for d in kline_data]

    if target_date not in dates:
        return {"error": f"目标日期 {target_date} 不在数据中"}

    # 找到目标日期的索引
    target_idx = dates.index(target_date)
    if target_idx == 0:
        return {"error": "无前一日数据"}

    prev_day = kline_data[target_idx - 1]
    today = kline_data[target_idx]

    # 计算关键指标
    prev_pct_chg = prev_day['pct_chg']
    today_pct_chg = today['pct_chg']

    # 判断前一日是否弱势
    prev_day_weak = False
    weak_reasons = []

    if prev_pct_chg < -2.0:
        prev_day_weak = True
        weak_reasons.append(f"跌幅 > 2% ({prev_pct_chg:.2f}%)")

    # 检查是否有上影线
    if prev_day['high_price'] > prev_day['open_price'] * 1.02:  # 上影线超过2%
        weak_reasons.append(f"上影线明显: 最高{prev_day['high_price']:.2f}, 开盘{prev_day['open_price']:.2f}")

    # 检查缺口
    gap_filled = False
    if target_idx >= 2:
        day_before = kline_data[target_idx - 2]
        # 检查前两日是否有缺口
        if prev_day['low_price'] < day_before['close_price'] * 0.98:  # 缺口回补
            gap_filled = True
            weak_reasons.append(f"缺口回补: 前日收盘{day_before['close_price']:.2f}, 今日最低{prev_day['low_price']:.2f}")

    # 判断今日是否转强
    today_strong = False
    strong_reasons = []

    if today_pct_chg >= 9.9:  # 涨停
        today_strong = True
        strong_reasons.append(f"涨停 ({today_pct_chg:.2f}%)")
    elif today_pct_chg > 0 and today_pct_chg > prev_pct_chg + 5.0:  # 大幅反弹
        today_strong = True
        strong_reasons.append(f"大幅反弹: 前日{prev_pct_chg:.2f}% → 今日{today_pct_chg:.2f}%")

    # 检查成交量
    volume_ratio = today['volume'] / prev_day['volume'] if prev_day['volume'] > 0 else 1.0
    if volume_ratio > 1.5:
        strong_reasons.append(f"放量: 成交量比{volume_ratio:.2f}")

    # 计算弱转强评分
    score = 0
    if prev_day_weak and today_strong:
        score = 70  # 基础分

        # 跌幅越大，反弹越强，分数越高
        if prev_pct_chg < -5.0:
            score += 10
        elif prev_pct_chg < -3.0:
            score += 5

        if today_pct_chg >= 9.9:
            score += 15
        elif today_pct_chg > 5.0:
            score += 10

        if gap_filled:
            score += 10

        if volume_ratio > 2.0:
            score += 5

        # 限制在0-100之间
        score = min(100, score)

    return {
        'stock_id': today['stock_id'],
        'prev_date': prev_day['trade_date'],
        'today_date': today['trade_date'],
        'prev_pct_chg': prev_pct_chg,
        'today_pct_chg': today_pct_chg,
        'prev_day_weak': prev_day_weak,
        'today_strong': today_strong,
        'gap_filled': gap_filled,
        'volume_ratio': volume_ratio,
        'weak_reasons': weak_reasons,
        'strong_reasons': strong_reasons,
        'score': score,
        'is_weak_to_strong': prev_day_weak and today_strong,
        'analysis': {
            'open_price': today['open_price'],
            'high_price': today['high_price'],
            'low_price': today['low_price'],
            'close_price': today['close_price'],
            'volume': today['volume'],
            'amount': today['amount']
        }
    }

def main():
    print("测试神剑股份弱转强模式")
    print("=" * 70)

    stock_id = "002361.SZ"
    target_date = "2026-04-08"  # 涨停日

    print(f"股票: {stock_id}")
    print(f"目标日期: {target_date} (预期涨停)")

    # 加载K线数据
    print(f"\n加载K线数据...")
    kline_data = load_kline_data(stock_id, start_date="2026-03-01", end_date="2026-04-10")

    if not kline_data:
        print("❌ 未找到K线数据")
        return

    print(f"加载到 {len(kline_data)} 条K线记录")
    print(f"日期范围: {kline_data[0]['trade_date']} 至 {kline_data[-1]['trade_date']}")

    # 显示最近5天数据
    print(f"\n最近5个交易日数据:")
    for i, day in enumerate(kline_data[-5:], 1):
        print(f"  {day['trade_date']}: 开盘{day['open_price']:.2f}, 最高{day['high_price']:.2f}, "
              f"最低{day['low_price']:.2f}, 收盘{day['close_price']:.2f}, 涨跌幅{day['pct_chg']:.2f}%")

    # 分析弱转强
    print(f"\n分析弱转强模式...")
    analysis = analyze_weak_to_strong(kline_data, target_date)

    if 'error' in analysis:
        print(f"❌ 分析失败: {analysis['error']}")
        return

    # 显示结果
    print(f"\n分析结果:")
    print(f"  股票: {analysis['stock_id']}")
    print(f"  前一日: {analysis['prev_date']}, 涨跌幅: {analysis['prev_pct_chg']:.2f}%")
    print(f"  今日: {analysis['today_date']}, 涨跌幅: {analysis['today_pct_chg']:.2f}%")

    print(f"\n  弱势分析:")
    if analysis['prev_day_weak']:
        print(f"    ✅ 前一日弱势")
        for reason in analysis['weak_reasons']:
            print(f"        - {reason}")
    else:
        print(f"    ❌ 前一日不弱势")

    print(f"\n  转强分析:")
    if analysis['today_strong']:
        print(f"    ✅ 今日转强")
        for reason in analysis['strong_reasons']:
            print(f"        - {reason}")
    else:
        print(f"    ❌ 今日未转强")

    print(f"\n  技术特征:")
    print(f"    - 缺口回补: {'✅' if analysis['gap_filled'] else '❌'}")
    print(f"    - 成交量比: {analysis['volume_ratio']:.2f}")

    print(f"\n  弱转强判断:")
    if analysis['is_weak_to_strong']:
        print(f"    ✅ 符合弱转强模式!")
        print(f"    评分: {analysis['score']}/100")
    else:
        print(f"    ❌ 不符合弱转强模式")
        print(f"    评分: {analysis['score']}/100")

    # 检查缺口具体数据
    print(f"\n缺口分析:")
    target_idx = [d['trade_date'] for d in kline_data].index(target_date)

    if target_idx >= 2:
        day_before = kline_data[target_idx - 2]
        prev_day = kline_data[target_idx - 1]
        today = kline_data[target_idx]

        print(f"  {day_before['trade_date']}: 收盘价 {day_before['close_price']:.2f}")
        print(f"  {prev_day['trade_date']}: 最低价 {prev_day['low_price']:.2f}, 收盘价 {prev_day['close_price']:.2f}")
        print(f"  {today['trade_date']}: 开盘价 {today['open_price']:.2f}, 最高价 {today['high_price']:.2f}")

        # 计算缺口
        gap_before = day_before['close_price'] - prev_day['low_price']
        gap_after = prev_day['close_price'] - today['open_price']

        if gap_before > 0:
            print(f"  ✅ 存在向下缺口: {gap_before:.2f} (前日收盘{day_before['close_price']:.2f} > 今日最低{prev_day['low_price']:.2f})")
        if gap_after > 0:
            print(f"  ✅ 存在向上缺口: {gap_after:.2f} (前日收盘{prev_day['close_price']:.2f} > 今日开盘{today['open_price']:.2f})")

    print(f"\n" + "=" * 70)
    print(f"测试完成")

if __name__ == "__main__":
    main()