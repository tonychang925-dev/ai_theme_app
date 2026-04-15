#!/usr/bin/env python3
"""
分析新闻驱动的热点题材，准确统计涨停集中度
"""

import json
from pathlib import Path
from collections import defaultdict
import datetime
import re

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
EVENT_FEED_DIR = PROJECT_ROOT / "theme_data_complete" / "event_feed"

def is_system_generated_theme(theme_name):
    """判断是否为系统生成的题材标签"""
    system_patterns = [
        r'复盘$',
        r'盘前必读$',
        r'热门题材复盘$',
        r'月\d+日',
        r'年\d+月',
        r'事件前瞻$',
        r'投资日历$',
        r'科技春晚$',
        r'十大巨头$',
        r'五大核心$',
        r'20强$',
        r'独角兽',
    ]

    for pattern in system_patterns:
        if re.search(pattern, theme_name):
            return True
    return False

def load_stocks_from_date(trade_date="2026-04-08"):
    """加载指定日期的所有股票数据，按股票代码去重"""
    files = list(STOCK_DAILY_DIR.glob(f"*_{trade_date}_stocks.jsonl"))
    if not files:
        print(f"未找到{trade_date}的股票数据文件")
        return {}

    print(f"加载{len(files)}个{trade_date}的股票数据文件...")

    # 按股票代码去重，取最新或完整的数据
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

                if isinstance(data, list) and len(data) > 16:
                    stock_code = data[2] if len(data) > 2 else "unknown"
                    if stock_code == "unknown":
                        continue

                    # 如果股票已存在，合并题材（去重）
                    if stock_code in stocks_by_code:
                        existing = stocks_by_code[stock_code]
                        # 合并题材，避免重复
                        existing_subjects = {(str(s[0]), s[1]) for s in existing['subjects']}
                        new_subjects = {(str(s[0]), s[1]) for s in data[16]} if len(data) > 16 else set()
                        all_subjects = list(existing_subjects.union(new_subjects))
                        # 转换回原始格式
                        existing['subjects'] = [[int(sid) if sid.isdigit() else sid, name, 1] for (sid, name) in all_subjects]
                    else:
                        stock_info = {
                            'code': stock_code,
                            'name': data[3] if len(data) > 3 else "unknown",
                            'pct_chg': data[10] if len(data) > 10 else 0,
                            'subjects': data[16] if len(data) > 16 else [],
                            'files': [file_path.name]
                        }
                        stocks_by_code[stock_code] = stock_info

    print(f"去重后股票数量: {len(stocks_by_code)}")
    return stocks_by_code

def analyze_theme_concentration(stocks_by_code, limit_up_threshold=9.9):
    """分析题材涨停集中度，准确统计"""
    # 构建题材到股票代码的映射
    theme_to_stocks = defaultdict(set)  # subject_id -> set of stock_codes
    theme_names = {}  # subject_id -> subject_name
    theme_is_system = {}  # subject_id -> is_system_generated

    for stock_code, stock in stocks_by_code.items():
        for subject in stock['subjects']:
            if isinstance(subject, list) and len(subject) >= 2:
                subject_id = str(subject[0])
                subject_name = subject[1]
                theme_names[subject_id] = subject_name
                theme_is_system[subject_id] = is_system_generated_theme(subject_name)
                theme_to_stocks[subject_id].add(stock_code)

    # 统计每个题材的涨停股票
    theme_stats = []
    for subject_id, stock_codes in theme_to_stocks.items():
        # 跳过系统生成的题材
        if theme_is_system.get(subject_id, False):
            continue

        # 统计涨停股票数量
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
        if total_stocks >= 5 and limit_up_count >= 2:  # 至少有5只股票，其中2只涨停
            limit_up_ratio = limit_up_count / total_stocks * 100

            theme_stats.append({
                'subject_id': subject_id,
                'subject_name': theme_names.get(subject_id, 'unknown'),
                'limit_up_count': limit_up_count,
                'total_stocks': total_stocks,
                'limit_up_ratio': limit_up_ratio,
                'limit_up_stocks': limit_up_stocks
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

def parse_chinese_date(date_str):
    """解析中文日期字符串"""
    if not date_str:
        return None

    patterns = [
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
        r'(\d{4})/(\d{1,2})/(\d{1,2})',
    ]

    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return datetime.date(year, month, day)
            except:
                pass
    return None

def filter_recent_events(events, days=3, base_date=datetime.date(2026, 4, 8)):
    """过滤最近几天的事件"""
    recent_events = []
    cutoff_date = base_date - datetime.timedelta(days=days)

    for event in events:
        event_date_raw = event.get('event_date_raw', '')
        event_date = parse_chinese_date(event_date_raw)
        if event_date and event_date >= cutoff_date:
            recent_events.append(event)

    return recent_events

def main():
    print("=" * 100)
    print("新闻驱动热点题材分析 (2026-04-08)")
    print("=" * 100)

    # 1. 加载并去重股票数据
    stocks_by_code = load_stocks_from_date("2026-04-08")
    if not stocks_by_code:
        return

    # 2. 计算涨停股票
    limit_up_stocks = {code: stock for code, stock in stocks_by_code.items() if stock['pct_chg'] >= 9.9}
    print(f"\n📊 基础统计:")
    print(f"   总股票数量: {len(stocks_by_code)}")
    print(f"   涨停股票数量: {len(limit_up_stocks)} ({len(limit_up_stocks)/len(stocks_by_code)*100:.1f}%)")

    # 3. 分析题材涨停集中度（过滤系统生成题材）
    print(f"\n🔍 分析非系统题材的涨停集中度...")
    theme_stats = analyze_theme_concentration(stocks_by_code)

    print(f"\n📈 非系统题材涨停集中度TOP 20:")
    print("=" * 100)

    for i, theme in enumerate(theme_stats[:20]):
        print(f"\n{i+1:2d}. {theme['subject_name']} (ID: {theme['subject_id']})")
        print(f"    涨停股票: {theme['limit_up_count']}只 / 总股票: {theme['total_stocks']}只")
        print(f"    涨停率: {theme['limit_up_ratio']:.1f}%")

        # 显示涨停股票
        if theme['limit_up_stocks']:
            print(f"    涨停股票:")
            for j, stock in enumerate(theme['limit_up_stocks'][:5]):
                print(f"       {stock['code']} {stock['name']} (+{stock['pct_chg']:.2f}%)")
            if len(theme['limit_up_stocks']) > 5:
                print(f"       ... 等{len(theme['limit_up_stocks'])}只涨停股票")

        # 检查新闻事件
        events = load_theme_events(theme['subject_id'])
        recent_events = filter_recent_events(events, days=7)

        if recent_events:
            print(f"    📰 最近7天相关新闻事件 ({len(recent_events)}条):")
            for k, event in enumerate(recent_events[:2]):  # 显示最近2个
                event_date = event.get('event_date_raw', 'unknown')
                text = event.get('text', '')
                preview = text[:80] + "..." if len(text) > 80 else text
                print(f"       {k+1}. [{event_date}] {preview}")
        else:
            print(f"    ℹ️ 最近7天无相关新闻事件")

    # 4. 新闻事件与涨停关联分析
    print(f"\n" + "=" * 100)
    print("新闻事件驱动强度分析")
    print("=" * 100)

    news_driven_themes = []
    for theme in theme_stats[:15]:  # 前15个题材
        events = load_theme_events(theme['subject_id'])
        recent_events = filter_recent_events(events, days=7)

        if recent_events:
            # 计算新闻驱动强度：涨停率 * 新闻数量（归一化）
            news_strength = min(100, theme['limit_up_ratio'] * len(recent_events) / 10)
            news_driven_themes.append({
                'theme': theme,
                'event_count': len(recent_events),
                'news_strength': news_strength,
                'recent_events': recent_events[:3]
            })

    if news_driven_themes:
        # 按新闻驱动强度排序
        news_driven_themes.sort(key=lambda x: x['news_strength'], reverse=True)

        print(f"\n💥 高新闻驱动强度题材:")
        for i, item in enumerate(news_driven_themes[:10]):
            theme = item['theme']
            print(f"\n   {i+1:2d}. {theme['subject_name']}")
            print(f"      涨停强度: {theme['limit_up_count']}只涨停 ({theme['limit_up_ratio']:.1f}%)")
            print(f"      新闻强度: {item['event_count']}条新闻 (强度值: {item['news_strength']:.1f}/100)")

            if item['recent_events']:
                print(f"      最新新闻:")
                for event in item['recent_events'][:2]:
                    event_date = event.get('event_date_raw', 'unknown')
                    text_preview = event.get('text', '')[:60] + "..." if len(event.get('text', '')) > 60 else event.get('text', '')
                    print(f"      • [{event_date}] {text_preview}")
    else:
        print(f"\n⚠️ 前15大非系统题材最近7天均无明显新闻催化")

    # 5. 投资建议
    print(f"\n" + "=" * 100)
    print("投资建议")
    print("=" * 100)

    if news_driven_themes:
        print(f"\n🎯 明日重点关注题材 (新闻驱动型):")
        for i, item in enumerate(news_driven_themes[:5]):
            theme = item['theme']
            print(f"\n   {i+1}. {theme['subject_name']}")
            print(f"      涨停股票: {theme['limit_up_count']}只，涨停率: {theme['limit_up_ratio']:.1f}%")
            print(f"      新闻催化: {item['event_count']}条")

            # 推荐龙头股
            if theme['limit_up_stocks']:
                # 按涨幅排序
                sorted_stocks = sorted(theme['limit_up_stocks'], key=lambda x: x['pct_chg'], reverse=True)
                print(f"      关注龙头: {', '.join([f'{s['code']} {s['name']} (+{s['pct_chg']:.1f}%)' for s in sorted_stocks[:3]])}")

        print(f"\n📝 操作策略:")
        print(f"   1. 优先关注新闻驱动强度高的题材")
        print(f"   2. 在新闻驱动题材中寻找涨幅领先的龙头股")
        print(f"   3. 关注新闻发布时间与股票启动时间的关联")
        print(f"   4. 注意新闻的持续性和市场反应")
    else:
        print(f"\n今日无明显新闻驱动型涨停潮题材，可能为纯资金驱动或技术性反弹")

if __name__ == "__main__":
    main()