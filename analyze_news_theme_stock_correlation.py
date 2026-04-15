#!/usr/bin/env python3
"""
分析新闻事件与热点题材关联，识别题材涨停潮及其背后的新闻驱动因素
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
EVENT_FEED_DIR = PROJECT_ROOT / "theme_data_complete" / "event_feed"

def load_stocks_from_date(trade_date="2026-04-08"):
    """加载指定日期的所有股票数据"""
    files = list(STOCK_DAILY_DIR.glob(f"*_{trade_date}_stocks.jsonl"))
    if not files:
        print(f"未找到{trade_date}的股票数据文件")
        return []

    print(f"加载{len(files)}个{trade_date}的股票数据文件...")

    all_stocks = []
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

                if isinstance(data, list) and len(data) > 16:
                    stock_info = {
                        'code': data[2] if len(data) > 2 else "unknown",
                        'name': data[3] if len(data) > 3 else "unknown",
                        'pct_chg': data[10] if len(data) > 10 else 0,
                        'subjects': data[16] if len(data) > 16 else [],
                        'file': file_path.name
                    }
                    all_stocks.append(stock_info)

    return all_stocks

def find_limit_up_stocks(stocks, limit_up_threshold=9.9):
    """找出涨停股票"""
    limit_up_stocks = []
    for stock in stocks:
        if stock['pct_chg'] is not None and stock['pct_chg'] >= limit_up_threshold:
            limit_up_stocks.append(stock)
    return limit_up_stocks

def analyze_theme_limit_up_tide(limit_up_stocks):
    """分析题材涨停潮"""
    # 统计每个题材的涨停股票数量
    theme_limit_up_count = defaultdict(list)  # subject_id -> [stock_info]
    theme_names = {}  # subject_id -> subject_name

    for stock in limit_up_stocks:
        for subject in stock['subjects']:
            if isinstance(subject, list) and len(subject) >= 2:
                subject_id = str(subject[0])
                subject_name = subject[1]
                theme_names[subject_id] = subject_name
                theme_limit_up_count[subject_id].append(stock)

    # 找出涨停潮题材（至少2只涨停股票）
    tide_themes = {}
    for subject_id, stocks in theme_limit_up_count.items():
        if len(stocks) >= 2:
            tide_themes[subject_id] = {
                'name': theme_names.get(subject_id, 'unknown'),
                'count': len(stocks),
                'stocks': stocks
            }

    return tide_themes, theme_limit_up_count, theme_names

def load_theme_events(subject_id):
    """加载指定题材的新闻事件"""
    event_file = EVENT_FEED_DIR / f"{subject_id}_events.jsonl"
    if not event_file.exists():
        return []

    events = []
    with open(event_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue

    return events

def filter_recent_events(events, days=7):
    """过滤最近几天的事件"""
    recent_events = []
    today = datetime.date(2026, 4, 8)  # 分析日期
    cutoff_date = today - datetime.timedelta(days=days)

    for event in events:
        event_date_raw = event.get('event_date_raw', '')
        # 尝试解析日期字符串
        try:
            # 常见格式：2025年7月24日
            if '年' in event_date_raw and '月' in event_date_raw and '日' in event_date_raw:
                # 提取中文日期
                import re
                match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', event_date_raw)
                if match:
                    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    event_date = datetime.date(year, month, day)
                    if event_date >= cutoff_date:
                        recent_events.append(event)
        except:
            pass

    return recent_events

def generate_analysis_report(stocks, limit_up_stocks, tide_themes, theme_limit_up_count, theme_names):
    """生成分析报告"""
    print("=" * 120)
    print("新闻事件与热点题材关联分析报告 (2026-04-08)")
    print("=" * 120)

    print(f"\n📊 数据统计:")
    print(f"   总股票数量: {len(stocks)}")
    print(f"   涨停股票数量: {len(limit_up_stocks)} ({len(limit_up_stocks)/len(stocks)*100:.1f}%)")
    print(f"   涉及题材总数: {len(theme_limit_up_count)}")
    print(f"   涨停潮题材数量: {len(tide_themes)}")

    if limit_up_stocks:
        print(f"\n🏆 涨停股票列表 (涨幅≥9.9%):")
        for i, stock in enumerate(limit_up_stocks[:30]):  # 显示前30个
            subject_names = []
            for subject in stock['subjects'][:3]:  # 显示前3个题材
                if isinstance(subject, list) and len(subject) >= 2:
                    subject_names.append(subject[1])
            subjects_str = ", ".join(subject_names)
            if len(stock['subjects']) > 3:
                subjects_str += f" 等{len(stock['subjects'])}个题材"

            print(f"   {i+1:2d}. {stock['code']} {stock['name']}: 涨幅={stock['pct_chg']:.2f}%, 题材={subjects_str}")

    if tide_themes:
        print(f"\n🌊 涨停潮题材分析 (同一题材≥2只涨停股票):")
        for i, (subject_id, theme_info) in enumerate(tide_themes.items()):
            print(f"\n   {i+1}. 题材: {theme_info['name']} (ID: {subject_id})")
            print(f"      涨停股票数量: {theme_info['count']}只")
            print(f"      涨停股票列表:")
            for j, stock in enumerate(theme_info['stocks']):
                print(f"         {j+1}. {stock['code']} {stock['name']} (+{stock['pct_chg']:.2f}%)")

            # 加载并分析新闻事件
            events = load_theme_events(subject_id)
            recent_events = filter_recent_events(events, days=7)

            if recent_events:
                print(f"      最近7天相关新闻事件:")
                for k, event in enumerate(recent_events[:5]):  # 显示最近5个事件
                    event_date = event.get('event_date_raw', 'unknown')
                    text_preview = event.get('text', '')[:80] + "..." if len(event.get('text', '')) > 80 else event.get('text', '')
                    print(f"         {k+1}. [{event_date}] {text_preview}")
            else:
                print(f"      最近7天无相关新闻事件")

    # 单个题材涨停分析
    print(f"\n📈 单个题材涨停统计:")
    sorted_themes = sorted(theme_limit_up_count.items(), key=lambda x: len(x[1]), reverse=True)
    for subject_id, stocks in sorted_themes[:20]:  # 显示前20个题材
        theme_name = theme_names.get(subject_id, 'unknown')
        print(f"   {theme_name} (ID: {subject_id}): {len(stocks)}只涨停股票")

    # 推荐关注题材
    print(f"\n🎯 明日重点关注题材 (基于涨停潮):")
    if tide_themes:
        for subject_id, theme_info in tide_themes.items():
            theme_name = theme_info['name']
            events = load_theme_events(subject_id)
            recent_events = filter_recent_events(events, days=3)

            if recent_events:
                print(f"   ✓ {theme_name}: {theme_info['count']}只涨停，最近3天有{len(recent_events)}条相关新闻")
            else:
                print(f"   ⚠️ {theme_name}: {theme_info['count']}只涨停，但最近3天无新闻催化")
    else:
        print("   今日无明显涨停潮题材")

    print(f"\n📝 分析结论:")
    if tide_themes:
        print("   1. 存在明显的题材涨停潮效应，表明市场资金围绕特定热点集中炒作")
        print("   2. 涨停潮题材通常有近期新闻事件催化，形成正反馈循环")
        print("   3. 关注涨停潮题材中的龙头股和补涨股机会")
    else:
        print("   1. 今日涨停股票分散，无明显集中热点")
        print("   2. 可能是轮动行情或个股独立走势")
        print("   3. 关注涨停股票自身基本面和资金面因素")

def main():
    # 1. 加载股票数据
    stocks = load_stocks_from_date("2026-04-08")
    if not stocks:
        return

    # 2. 找出涨停股票
    limit_up_stocks = find_limit_up_stocks(stocks)

    # 3. 分析题材涨停潮
    tide_themes, theme_limit_up_count, theme_names = analyze_theme_limit_up_tide(limit_up_stocks)

    # 4. 生成报告
    generate_analysis_report(stocks, limit_up_stocks, tide_themes, theme_limit_up_count, theme_names)

if __name__ == "__main__":
    main()