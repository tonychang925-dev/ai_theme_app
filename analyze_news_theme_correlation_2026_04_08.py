#!/usr/bin/env python3
"""
临时分析脚本：将现有新闻事件（2026年4月1日等）与2026年4月8日的热点题材关联分析
"""

import json
from pathlib import Path
from collections import defaultdict
import datetime
import re

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
EVENT_FEED_DIR = PROJECT_ROOT / "theme_data_complete" / "event_feed"
HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"

def load_stocks_from_date(trade_date="2026-04-08"):
    """加载指定日期的所有股票数据，按股票代码去重"""
    files = list(STOCK_DAILY_DIR.glob(f"*_{trade_date}_stocks.jsonl"))
    if not files:
        print(f"未找到{trade_date}的股票数据文件")
        return {}

    print(f"加载{len(files)}个{trade_date}的股票数据文件...")

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

                    if stock_code not in stocks_by_code:
                        stock_info = {
                            'code': stock_code,
                            'name': data[3] if len(data) > 3 else "unknown",
                            'pct_chg': data[10] if len(data) > 10 else 0,
                            'subjects': data[16] if len(data) > 16 else [],
                        }
                        stocks_by_code[stock_code] = stock_info

    print(f"去重后股票数量: {len(stocks_by_code)}")
    return stocks_by_code

def analyze_hot_themes(stocks_by_code, limit_up_threshold=9.9, min_limit_up=2):
    """分析热点题材（涨停集中度）"""
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
        if limit_up_count >= min_limit_up:
            limit_up_ratio = limit_up_count / total_stocks * 100 if total_stocks > 0 else 0
            theme_stats.append({
                'subject_id': subject_id,
                'subject_name': theme_names.get(subject_id, 'unknown'),
                'limit_up_count': limit_up_count,
                'total_stocks': total_stocks,
                'limit_up_ratio': limit_up_ratio,
                'limit_up_stocks': limit_up_stocks
            })

    theme_stats.sort(key=lambda x: (x['limit_up_count'], x['limit_up_ratio']), reverse=True)
    return theme_stats

def load_existing_events():
    """加载现有的所有事件数据，优先从history目录加载"""
    events_by_subject = defaultdict(list)

    # 首先从history目录加载（包含更近的事件）
    history_files = list(HISTORY_DIR.glob("*_history.jsonl"))
    print(f"找到{len(history_files)}个history文件")

    for history_file in history_files[:200]:  # 限制数量
        with open(history_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    subject_id = event.get('subjectId')  # history格式使用subjectId
                    if subject_id:
                        # 转换字段名以保持兼容性
                        event['subject_id'] = subject_id
                        event['text'] = event.get('description', '')
                        event['event_date_raw'] = event.get('rankDate', event.get('createTime', ''))
                        events_by_subject[str(subject_id)].append(event)
                except json.JSONDecodeError:
                    continue

    # 如果history目录没有数据，则从event_feed目录加载
    if not events_by_subject:
        event_files = list(EVENT_FEED_DIR.glob("*_events.jsonl"))
        print(f"找到{len(event_files)}个event_feed文件")
        for event_file in event_files[:100]:
            with open(event_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        subject_id = event.get('subject_id')
                        if subject_id:
                            events_by_subject[str(subject_id)].append(event)
                    except json.JSONDecodeError:
                        continue

    return events_by_subject

def parse_chinese_date(date_str):
    """解析多种日期字符串格式"""
    if not date_str:
        return None

    # 尝试标准日期时间格式：2026-04-07 15:07:32
    try:
        # 提取日期部分（忽略时间）
        date_part = date_str.split()[0]
        year, month, day = map(int, date_part.split('-'))
        return datetime.date(year, month, day)
    except:
        pass

    # 尝试中文日期格式
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

def filter_recent_events(events, days=7, base_date=datetime.date(2026, 4, 8)):
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
    print("=" * 120)
    print("新闻事件与热点题材关联分析 (2026-04-08)")
    print("=" * 120)

    # 1. 加载股票数据
    print("\n1. 加载2026-04-08股票数据...")
    stocks_by_code = load_stocks_from_date("2026-04-08")
    if not stocks_by_code:
        return

    # 2. 分析热点题材
    print("\n2. 分析热点题材（涨停集中度）...")
    hot_themes = analyze_hot_themes(stocks_by_code, min_limit_up=3)
    print(f"   发现{len(hot_themes)}个热点题材（至少3只涨停股票）")

    # 3. 加载现有事件数据
    print("\n3. 加载现有事件数据...")
    events_by_subject = load_existing_events()
    print(f"   共加载{len(events_by_subject)}个题材的事件数据")

    # 4. 关联分析
    print("\n4. 关联分析：热点题材与新闻事件")
    print("=" * 80)

    news_driven_themes = []
    no_news_themes = []

    for theme in hot_themes[:20]:  # 前20个热点题材
        subject_id = theme['subject_id']
        events = events_by_subject.get(subject_id, [])
        recent_events = filter_recent_events(events, days=30)  # 最近30天

        if recent_events:
            # 计算新闻驱动强度
            latest_event_date = None
            for event in recent_events:
                event_date_raw = event.get('event_date_raw', '')
                event_date = parse_chinese_date(event_date_raw)
                if event_date:
                    if latest_event_date is None or event_date > latest_event_date:
                        latest_event_date = event_date

            # 新闻驱动强度 = 涨停率 * 最近新闻天数权重
            days_diff = 30
            if latest_event_date:
                days_diff = (datetime.date(2026, 4, 8) - latest_event_date).days
                days_diff = max(1, min(30, days_diff))

            news_strength = theme['limit_up_ratio'] * (30 - days_diff) / 30

            news_driven_themes.append({
                'theme': theme,
                'event_count': len(recent_events),
                'latest_event_date': latest_event_date,
                'days_since_last_event': days_diff,
                'news_strength': news_strength,
                'recent_events': recent_events[:2]  # 最近2个事件
            })
        else:
            no_news_themes.append(theme)

    # 5. 输出结果
    print("\n🎯 新闻驱动型热点题材（有近期新闻事件）：")
    print("-" * 80)

    if news_driven_themes:
        # 按新闻驱动强度排序
        news_driven_themes.sort(key=lambda x: x['news_strength'], reverse=True)

        for i, item in enumerate(news_driven_themes[:10]):
            theme = item['theme']
            print(f"\n{i+1}. {theme['subject_name']} (ID: {theme['subject_id']})")
            print(f"   涨停强度: {theme['limit_up_count']}只涨停 ({theme['limit_up_ratio']:.1f}%)")
            print(f"   新闻驱动强度: {item['news_strength']:.1f}/100")
            print(f"   近期事件: {item['event_count']}条（最近事件: {item['latest_event_date']}，{item['days_since_last_event']}天前）")

            if item['recent_events']:
                print(f"   最新新闻事件:")
                for j, event in enumerate(item['recent_events']):
                    event_date = event.get('event_date_raw', 'unknown')
                    text_preview = event.get('text', '')[:80] + "..." if len(event.get('text', '')) > 80 else event.get('text', '')
                    print(f"     {j+1}. [{event_date}] {text_preview}")

            # 显示部分涨停股票
            if theme['limit_up_stocks']:
                stock_names = [f"{s['code']} {s['name']}" for s in theme['limit_up_stocks'][:3]]
                print(f"   代表涨停股票: {', '.join(stock_names)}")
    else:
        print("⚠️ 前20大热点题材均无近期新闻事件")

    print("\n⚠️ 纯资金驱动型热点题材（无近期新闻事件）：")
    print("-" * 80)

    if no_news_themes[:5]:
        for i, theme in enumerate(no_news_themes[:5]):
            print(f"\n{i+1}. {theme['subject_name']} (ID: {theme['subject_id']})")
            print(f"   涨停强度: {theme['limit_up_count']}只涨停 ({theme['limit_up_ratio']:.1f}%)")
            print(f"   可能为纯资金驱动或技术性反弹")

            if theme['limit_up_stocks']:
                stock_names = [f"{s['code']} {s['name']}" for s in theme['limit_up_stocks'][:3]]
                print(f"   代表涨停股票: {', '.join(stock_names)}")

    # 6. 投资建议
    print("\n" + "=" * 80)
    print("投资建议")
    print("=" * 80)

    if news_driven_themes:
        print("\n🎯 重点关注（新闻驱动型）：")
        for i, item in enumerate(news_driven_themes[:3]):
            theme = item['theme']
            print(f"{i+1}. {theme['subject_name']}: {theme['limit_up_count']}只涨停 + {item['event_count']}条近期新闻")
            print(f"   关注龙头股: {', '.join([s['code'] for s in theme['limit_up_stocks'][:2]])}")

    print("\n📝 操作策略:")
    print("1. 新闻驱动型题材: 关注新闻的持续性和市场反应，寻找龙头股机会")
    print("2. 纯资金驱动型题材: 注意轮动风险，关注技术面和资金面变化")
    print("3. 风险提示: 注意高涨停率题材的持续性，设置止损位")

    # 7. 数据问题说明
    print("\n" + "=" * 80)
    print("数据问题说明")
    print("=" * 80)
    print("当前事件数据主要来自2024-2025年，缺少2026年4月8日当日新闻事件。")
    print("主要原因为新闻采集系统存在以下问题:")
    print("1. theme_collector.py使用单题材接口而非全局事件流接口")
    print("2. 接口响应读取的是data字段而非rows字段")
    print("3. 现有event_feed数据可能不是从全局事件流采集而来")
    print("\n建议修复方案:")
    print("1. 运行: python sync_jyhf_to_local.py --types=history --history-mode=incremental")
    print("2. 或运行: python sync_jyhf_to_local.py --types=history --history-backfill-date=2026-04-08")
    print("3. 需要有效的JYHF Authorization token")

if __name__ == "__main__":
    main()