#!/usr/bin/env python3
"""
分析题材涨停集中度，找出真正的热点题材
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

def analyze_theme_concentration(stocks, limit_up_threshold=9.9):
    """分析题材涨停集中度"""
    # 统计每个题材的涨停股票
    theme_limit_up = defaultdict(list)  # subject_id -> [涨停股票]
    theme_all_stocks = defaultdict(list)  # subject_id -> [所有股票]
    theme_names = {}  # subject_id -> subject_name

    # 首先构建题材到所有股票的映射
    for stock in stocks:
        for subject in stock['subjects']:
            if isinstance(subject, list) and len(subject) >= 2:
                subject_id = str(subject[0])
                subject_name = subject[1]
                theme_names[subject_id] = subject_name
                theme_all_stocks[subject_id].append(stock['code'])

                # 如果是涨停股票
                if stock['pct_chg'] >= limit_up_threshold:
                    theme_limit_up[subject_id].append({
                        'code': stock['code'],
                        'name': stock['name'],
                        'pct_chg': stock['pct_chg']
                    })

    # 计算每个题材的涨停集中度指标
    theme_stats = []
    for subject_id in theme_all_stocks:
        limit_up_count = len(theme_limit_up.get(subject_id, []))
        total_count = len(set(theme_all_stocks[subject_id]))  # 去重
        if total_count > 0:
            limit_up_ratio = limit_up_count / total_count * 100
        else:
            limit_up_ratio = 0

        if limit_up_count >= 3:  # 至少3只涨停才考虑
            theme_stats.append({
                'subject_id': subject_id,
                'subject_name': theme_names.get(subject_id, 'unknown'),
                'limit_up_count': limit_up_count,
                'total_stocks': total_count,
                'limit_up_ratio': limit_up_ratio,
                'limit_up_stocks': theme_limit_up.get(subject_id, [])
            })

    # 按涨停数量和涨停率排序
    theme_stats.sort(key=lambda x: (x['limit_up_count'], x['limit_up_ratio']), reverse=True)

    return theme_stats

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

def filter_recent_events(events, days=3):
    """过滤最近几天的事件"""
    recent_events = []
    today = datetime.date(2026, 4, 8)  # 分析日期
    cutoff_date = today - datetime.timedelta(days=days)

    for event in events:
        event_date_raw = event.get('event_date_raw', '')
        # 尝试解析中文日期格式
        try:
            if '年' in event_date_raw and '月' in event_date_raw and '日' in event_date_raw:
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

def main():
    # 1. 加载股票数据
    print("=" * 100)
    print("题材涨停集中度分析 (2026-04-08)")
    print("=" * 100)

    stocks = load_stocks_from_date("2026-04-08")
    if not stocks:
        return

    # 2. 计算涨停股票
    limit_up_stocks = [s for s in stocks if s['pct_chg'] >= 9.9]
    print(f"\n📊 基础统计:")
    print(f"   总股票数量: {len(stocks)}")
    print(f"   涨停股票数量: {len(limit_up_stocks)} ({len(limit_up_stocks)/len(stocks)*100:.1f}%)")

    # 3. 分析题材涨停集中度
    print(f"\n🔍 分析题材涨停集中度...")
    theme_stats = analyze_theme_concentration(stocks)

    print(f"\n🏆 涨停潮题材TOP 20 (至少3只涨停股票):")
    print("=" * 100)

    for i, theme in enumerate(theme_stats[:20]):
        print(f"\n{i+1:2d}. {theme['subject_name']} (ID: {theme['subject_id']})")
        print(f"    涨停股票: {theme['limit_up_count']}只 / 总股票: {theme['total_stocks']}只")
        print(f"    涨停率: {theme['limit_up_ratio']:.1f}%")

        # 显示部分涨停股票
        print(f"    涨停股票列表:")
        for j, stock in enumerate(theme['limit_up_stocks'][:5]):  # 显示前5个
            print(f"       {stock['code']} {stock['name']} (+{stock['pct_chg']:.2f}%)")
        if len(theme['limit_up_stocks']) > 5:
            print(f"       ... 等{len(theme['limit_up_stocks'])}只涨停股票")

        # 检查新闻事件
        events = load_theme_events(theme['subject_id'])
        recent_events = filter_recent_events(events, days=3)

        if recent_events:
            print(f"    📰 最近3天相关新闻事件 ({len(recent_events)}条):")
            for k, event in enumerate(recent_events[:3]):  # 显示最近3个
                event_date = event.get('event_date_raw', 'unknown')
                text = event.get('text', '')
                preview = text[:60] + "..." if len(text) > 60 else text
                print(f"       {k+1}. [{event_date}] {preview}")
        else:
            print(f"    ℹ️ 最近3天无相关新闻事件")

        # 检查更早的事件
        older_events = filter_recent_events(events, days=7)
        if len(older_events) > len(recent_events):
            print(f"    📅 最近7天共有{len(older_events)}条相关新闻")

    # 4. 新闻事件与涨停关联分析
    print(f"\n" + "=" * 100)
    print("新闻事件驱动分析")
    print("=" * 100)

    high_impact_themes = []
    for theme in theme_stats[:10]:  # 前10个题材
        events = load_theme_events(theme['subject_id'])
        recent_events = filter_recent_events(events, days=3)

        if recent_events:
            high_impact_themes.append({
                'theme': theme,
                'event_count': len(recent_events),
                'events': recent_events[:2]  # 取最近2个事件
            })

    if high_impact_themes:
        print(f"\n💡 有明显新闻催化的涨停潮题材:")
        for item in high_impact_themes:
            theme = item['theme']
            print(f"\n   📈 {theme['subject_name']}: {theme['limit_up_count']}只涨停")
            print(f"      涨停率: {theme['limit_up_ratio']:.1f}%, 最近3天新闻: {item['event_count']}条")

            for event in item['events']:
                event_date = event.get('event_date_raw', 'unknown')
                text_preview = event.get('text', '')[:80] + "..." if len(event.get('text', '')) > 80 else event.get('text', '')
                print(f"      • [{event_date}] {text_preview}")
    else:
        print(f"\n⚠️ 前10大涨停潮题材最近3天均无明显新闻催化")

    # 5. 投资建议
    print(f"\n" + "=" * 100)
    print("投资建议")
    print("=" * 100)

    if theme_stats:
        print(f"\n🎯 明日重点关注题材:")
        for i, theme in enumerate(theme_stats[:5]):
            events = load_theme_events(theme['subject_id'])
            recent_events = filter_recent_events(events, days=3)

            if recent_events:
                print(f"   {i+1}. {theme['subject_name']}: {theme['limit_up_count']}只涨停 + 新闻催化")
                print(f"      关注股票: {', '.join([s['code'] for s in theme['limit_up_stocks'][:3]])}")
            else:
                print(f"   {i+1}. {theme['subject_name']}: {theme['limit_up_count']}只涨停 (纯资金驱动)")

        print(f"\n📝 操作策略:")
        print(f"   1. 优先关注有新闻催化的涨停潮题材")
        print(f"   2. 在涨停潮题材中寻找龙头股和补涨机会")
        print(f"   3. 注意高涨停率题材的持续性")
    else:
        print(f"\n今日无明显涨停潮题材，建议关注个股独立行情")

if __name__ == "__main__":
    main()