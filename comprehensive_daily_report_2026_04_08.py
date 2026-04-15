#!/usr/bin/env python3
"""
2026-04-08日综合投资分析报告
整合：主线/支线分析、新闻事件、题材热点、资金流入、换手率、资金性质、技术形态
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"

# 导入现有模块
try:
    from generate_flag_stocks_md import extract_unique_special_flag_stocks, get_flag_description
    print("✓ generate_flag_stocks_md 已加载")
except ImportError:
    print("⚠ generate_flag_stocks_md 导入失败")
    # 简单定义备用函数
    def get_flag_description(flag):
        descriptions = {
            -1: "放量滞涨",
            0: "正常波动",
            1: "涨停",
            2: "连续涨停",
            3: "罕见涨停（尾盘竞价抢筹）",
            4: "无量涨停（异常资金强化）"
        }
        return descriptions.get(flag, f"未知({flag})")

def load_2026_04_08_stocks():
    """加载2026-04-08所有股票数据（去重）"""
    files = list(STOCK_DAILY_DIR.glob("*_2026-04-08_stocks.jsonl"))
    if not files:
        print("❌ 未找到2026-04-08数据文件")
        return []

    stocks_by_code = {}  # 使用股票代码作为键去重
    total_count = 0

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
                    total_count += 1

                    code = data[2] if len(data) > 2 else ''
                    if not code or code == 'unknown':
                        continue

                    # 如果已经存在，合并题材信息（去重）
                    if code in stocks_by_code:
                        existing = stocks_by_code[code]
                        # 合并题材（去重）
                        existing_subjects = existing['subjects']
                        new_subjects = data[16] if len(data) > 16 and isinstance(data[16], list) else []
                        # 简单合并，实际可能需要更复杂的去重
                        existing['subjects'].extend([s for s in new_subjects if s not in existing['subjects']])
                        # 其他字段以第一个为准（通常相同）
                        continue

                    # 解析股票信息
                    stock = {
                        'code': code,
                        'name': data[3] if len(data) > 3 else '',
                        'trade_date': data[0] if len(data) > 0 else '',
                        'open': float(data[4]) if len(data) > 4 and data[4] is not None else 0,
                        'high': float(data[5]) if len(data) > 5 and data[5] is not None else 0,
                        'low': float(data[6]) if len(data) > 6 and data[6] is not None else 0,
                        'close': float(data[7]) if len(data) > 7 and data[7] is not None else 0,
                        'pct_chg': float(data[10]) if len(data) > 10 and data[10] is not None else 0,
                        'volume': float(data[12]) if len(data) > 12 and data[12] is not None else 0,
                        'amount': float(data[13]) if len(data) > 13 and data[13] is not None else 0,
                        'turnover': float(data[15]) if len(data) > 15 and data[15] is not None else 0,
                        'subjects': data[16] if len(data) > 16 and isinstance(data[16], list) else [],
                        'flag': data[20] if len(data) > 20 else 0,
                        'market_cap': float(data[21]) if len(data) > 21 and data[21] is not None else 0,
                        'circulating_cap': float(data[35]) if len(data) > 35 and data[35] is not None else 0,
                    }

                    # 计算资金流入强度
                    if stock['market_cap'] > 0:
                        stock['amount_ratio'] = stock['amount'] / stock['market_cap'] * 100
                    else:
                        stock['amount_ratio'] = 0

                    # 提取题材名称列表
                    subject_names = []
                    for subject in stock['subjects']:
                        if isinstance(subject, list) and len(subject) >= 2:
                            subject_name = subject[1]
                            # 过滤复盘类题材
                            if '复盘' not in subject_name and '热门题材' not in subject_name and '盘前必读' not in subject_name:
                                subject_names.append(subject_name)
                    stock['subject_names'] = subject_names

                    stocks_by_code[code] = stock

    stocks = list(stocks_by_code.values())
    print(f"✓ 加载 {len(stocks)}/{total_count} 只股票数据（去重后）")
    return stocks

def analyze_main_themes(stocks):
    """分析主线题材和支线题材"""
    # 统计题材出现频率
    theme_counter = Counter()
    theme_stocks = defaultdict(list)
    theme_amount = defaultdict(float)  # 题材总成交额
    theme_up_count = defaultdict(int)  # 题材上涨股票数
    theme_zt_count = defaultdict(int)  # 题材涨停股票数

    for stock in stocks:
        for theme in stock['subject_names']:
            theme_counter[theme] += 1
            theme_stocks[theme].append(stock)
            theme_amount[theme] += stock['amount']
            if stock['pct_chg'] > 0:
                theme_up_count[theme] += 1
            if stock['pct_chg'] >= 9.9:
                theme_zt_count[theme] += 1

    # 计算题材强度评分
    theme_scores = {}
    for theme in theme_counter:
        if theme_counter[theme] < 3:  # 至少3只股票才考虑
            continue

        score = 0

        # 1. 题材广度（股票数量）20分
        count = theme_counter[theme]
        score += min(20, count * 2)

        # 2. 资金关注度（总成交额）30分
        total_amount = theme_amount[theme]
        amount_score = min(30, np.log10(max(1, total_amount/1e8)) * 10)  # 每10亿得10分
        score += amount_score

        # 3. 赚钱效应（上涨比例）25分
        if count > 0:
            up_ratio = theme_up_count[theme] / count
            score += up_ratio * 25

        # 4. 涨停效应（涨停数量）25分
        zt_score = min(25, theme_zt_count[theme] * 5)  # 每只涨停得5分
        score += zt_score

        theme_scores[theme] = {
            'score': round(score, 1),
            'count': count,
            'total_amount': round(total_amount / 1e8, 2),  # 单位：亿元
            'up_ratio': round(theme_up_count[theme] / count * 100, 1) if count > 0 else 0,
            'zt_count': theme_zt_count[theme],
            'stocks': theme_stocks[theme]
        }

    # 按评分排序
    sorted_themes = sorted(theme_scores.items(), key=lambda x: x[1]['score'], reverse=True)

    # 分类：主线（前3）、支线（4-10）、其他
    main_themes = []
    sub_themes = []

    for i, (theme, info) in enumerate(sorted_themes[:10]):
        theme_info = {
            'theme': theme,
            **info
        }
        if i < 3:
            main_themes.append(theme_info)
        else:
            sub_themes.append(theme_info)

    return {
        'main_themes': main_themes,
        'sub_themes': sub_themes,
        'all_themes': theme_scores
    }

def load_news_events():
    """加载4月8日新闻事件"""
    news_events = []

    # 查找所有历史文件
    history_files = list(HISTORY_DIR.glob("*_history.jsonl"))
    if not history_files:
        print("⚠ 未找到历史文件")
        return news_events

    print(f"📁 扫描 {len(history_files)} 个历史文件中的新闻事件...")

    for file_path in history_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        # 确保是新闻事件（type=3）且日期为2026-04-08
                        if isinstance(event, dict) and event.get('type') == 3:
                            rank_date = event.get('rankDate') or event.get('rank_date')
                            if rank_date and rank_date.startswith('2026-04-08'):
                                news_events.append(event)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            continue

    # 去重：基于description和rankDate
    unique_news = []
    seen_keys = set()
    for event in news_events:
        description = event.get('description', '')
        rank_date = event.get('rankDate') or event.get('rank_date', '')
        key = f"{description[:100]}_{rank_date}"
        if key not in seen_keys:
            seen_keys.add(key)
            unique_news.append(event)

    print(f"✓ 加载 {len(unique_news)} 条2026-04-08新闻事件")
    return unique_news

def analyze_capital_nature(stock):
    """分析资金性质（游资/机构）"""
    # 基于市值、换手率、成交额等特征判断
    features = []

    # 1. 市值特征
    if stock['market_cap'] < 50e8:  # 小于50亿
        features.append('小市值')
    elif stock['market_cap'] < 200e8:  # 50-200亿
        features.append('中市值')
    else:  # 大于200亿
        features.append('大市值')

    # 2. 换手率特征
    if stock['turnover'] > 15:
        features.append('高换手')
    elif stock['turnover'] > 5:
        features.append('中换手')
    else:
        features.append('低换手')

    # 3. 成交额特征
    amount_100m = stock['amount'] / 1e8  # 亿元
    if amount_100m > 10:
        features.append('高成交')
    elif amount_100m > 1:
        features.append('中成交')
    else:
        features.append('低成交')

    # 4. flag信号
    if stock['flag'] in [3, 4]:
        features.append('异常资金')
    elif stock['flag'] == -1:
        features.append('分歧资金')

    # 综合判断
    capital_type = "未知"
    reason = ""

    # 游资特征：小/中市值 + 高换手 + 高成交
    if '小市值' in features and '高换手' in features and '高成交' in features:
        capital_type = "游资主导"
        reason = "小市值+高换手+高成交，游资特征明显"
    elif '中市值' in features and '高换手' in features and '高成交' in features:
        capital_type = "游资+机构混合"
        reason = "中市值+高换手+高成交，可能为游资机构合力"
    elif '大市值' in features and '中换手' in features and '高成交' in features:
        capital_type = "机构主导"
        reason = "大市值+中等换手+高成交，机构特征明显"
    elif '异常资金' in features:
        capital_type = "游资/机构抢筹"
        reason = "flag=3/4显示异常资金强化"
    elif '分歧资金' in features and '高成交' in features:
        capital_type = "分歧资金"
        reason = "flag=-1+高成交，资金分歧明显"
    else:
        capital_type = "普通资金"
        reason = "无明显特征"

    return {
        'type': capital_type,
        'reason': reason,
        'features': features
    }

def analyze_technical_condition_simple(stock, stocks_data):
    """简单技术形态分析（基于单日数据）"""
    # 注：这里使用简单规则，完整技术分析需要历史K线数据
    condition = {
        'trend': '未知',
        'volume_trend': '未知',
        'key_levels': '未知'
    }

    # 1. 涨幅判断趋势
    if stock['pct_chg'] >= 9.9:
        condition['trend'] = '涨停强势'
    elif stock['pct_chg'] >= 5:
        condition['trend'] = '强势上涨'
    elif stock['pct_chg'] >= 0:
        condition['trend'] = '温和上涨'
    elif stock['pct_chg'] >= -5:
        condition['trend'] = '弱势调整'
    else:
        condition['trend'] = '大幅调整'

    # 2. 量价关系
    if stock['pct_chg'] > 0 and stock['turnover'] > 5:
        condition['volume_trend'] = '价量齐升'
    elif stock['pct_chg'] > 0 and stock['turnover'] <= 5:
        condition['volume_trend'] = '缩量上涨'
    elif stock['pct_chg'] < 0 and stock['turnover'] > 5:
        condition['volume_trend'] = '放量下跌'
    else:
        condition['volume_trend'] = '量价正常'

    # 3. 关键价位（简单估算）
    if stock['close'] > stock['high'] * 0.98:  # 接近最高点
        condition['key_levels'] = '突破前高'
    elif stock['close'] < stock['low'] * 1.02:  # 接近最低点
        condition['key_levels'] = '测试支撑'
    else:
        condition['key_levels'] = '区间震荡'

    return condition

def identify_focus_stocks(stocks, theme_analysis, news_events):
    """识别重点关注股票"""
    focus_stocks = []

    for stock in stocks:
        # 计算综合关注度分数
        score = 0
        reasons = []

        # 1. 涨幅得分 (0-20)
        if stock['pct_chg'] >= 9.9:
            score += 20
            reasons.append("涨停")
        elif stock['pct_chg'] >= 7:
            score += 15
            reasons.append("大涨")
        elif stock['pct_chg'] >= 5:
            score += 10
            reasons.append("中阳")
        elif stock['pct_chg'] >= 0:
            score += 5
            reasons.append("上涨")

        # 2. 资金流入得分 (0-25)
        if stock['amount_ratio'] > 10:
            score += 25
            reasons.append(f"资金强度{stock['amount_ratio']:.1f}%")
        elif stock['amount_ratio'] > 5:
            score += 15
            reasons.append(f"资金强度{stock['amount_ratio']:.1f}%")
        elif stock['amount_ratio'] > 2:
            score += 10
            reasons.append(f"资金强度{stock['amount_ratio']:.1f}%")

        # 3. 换手率得分 (0-15)
        if stock['turnover'] > 15:
            score += 15
            reasons.append(f"高换手{stock['turnover']:.1f}%")
        elif stock['turnover'] > 8:
            score += 10
            reasons.append(f"中高换手{stock['turnover']:.1f}%")
        elif stock['turnover'] > 3:
            score += 5
            reasons.append(f"活跃换手{stock['turnover']:.1f}%")

        # 4. flag信号得分 (0-20)
        if stock['flag'] in [3, 4]:
            score += 20
            reasons.append(f"flag={stock['flag']}(异常资金)")
        elif stock['flag'] == -1:
            score += 10
            reasons.append(f"flag={stock['flag']}(放量滞涨)")
        elif stock['flag'] == 1:
            score += 15
            reasons.append(f"flag={stock['flag']}(涨停)")

        # 5. 题材热度得分 (0-20)
        theme_hotness = 0
        main_theme_involved = False
        for theme in stock['subject_names']:
            # 检查是否属于主线题材
            for main_theme in theme_analysis['main_themes']:
                if theme == main_theme['theme']:
                    theme_hotness += 10
                    main_theme_involved = True
                    reasons.append(f"主线题材:{theme}")
                    break
            # 检查是否属于支线题材
            if not main_theme_involved:
                for sub_theme in theme_analysis['sub_themes']:
                    if theme == sub_theme['theme']:
                        theme_hotness += 5
                        reasons.append(f"支线题材:{theme}")
                        break

        score += min(20, theme_hotness)

        # 资金性质分析
        capital_info = analyze_capital_nature(stock)

        # 技术形态分析
        tech_info = analyze_technical_condition_simple(stock, stocks)

        # 添加到重点关注列表（分数>40）
        if score >= 40:
            focus_stock = {
                'code': stock['code'],
                'name': stock['name'],
                'score': score,
                'reasons': reasons,
                'pct_chg': stock['pct_chg'],
                'amount_ratio': stock['amount_ratio'],
                'turnover': stock['turnover'],
                'flag': stock['flag'],
                'flag_desc': get_flag_description(stock['flag']),
                'capital_type': capital_info['type'],
                'capital_reason': capital_info['reason'],
                'trend': tech_info['trend'],
                'volume_trend': tech_info['volume_trend'],
                'key_levels': tech_info['key_levels'],
                'subjects': stock['subject_names'][:3],  # 取前3个题材
                'amount_100m': round(stock['amount'] / 1e8, 2)  # 成交额(亿元)
            }
            focus_stocks.append(focus_stock)

    # 按分数排序
    focus_stocks.sort(key=lambda x: x['score'], reverse=True)

    print(f"✓ 识别 {len(focus_stocks)} 只重点关注股票（分数≥40）")
    return focus_stocks[:50]  # 返回前50只

def generate_daily_report(stocks, theme_analysis, news_events, focus_stocks):
    """生成日报"""
    report = []

    # 标题和基本信息
    report.append("# 📊 2026-04-08日综合投资分析报告")
    report.append("")
    report.append(f"**报告日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**分析基准日**: 2026-04-08")
    report.append(f"**分析股票数**: {len(stocks)}")
    report.append("")

    # 第一部分：市场概况
    report.append("## 📈 市场概况")
    report.append("")

    # 统计信息
    total_amount = sum(s['amount'] for s in stocks) / 1e8  # 亿元
    up_count = sum(1 for s in stocks if s['pct_chg'] > 0)
    down_count = sum(1 for s in stocks if s['pct_chg'] < 0)
    zt_count = sum(1 for s in stocks if s['pct_chg'] >= 9.9)
    avg_pct = sum(s['pct_chg'] for s in stocks) / len(stocks) if stocks else 0

    report.append(f"**总成交额**: {total_amount:,.2f}亿元")
    report.append(f"**上涨家数**: {up_count} ({up_count/len(stocks)*100:.1f}%)")
    report.append(f"**下跌家数**: {down_count} ({down_count/len(stocks)*100:.1f}%)")
    report.append(f"**涨停家数**: {zt_count}")
    report.append(f"**平均涨跌幅**: {avg_pct:.2f}%")
    report.append("")

    # 第二部分：主线题材分析
    report.append("## 🎯 主线题材分析")
    report.append("")

    report.append("### 核心主线（前3）")
    report.append("")
    report.append("| 排名 | 题材 | 强度评分 | 股票数量 | 总成交额(亿) | 上涨比例 | 涨停数 |")
    report.append("|------|------|----------|----------|--------------|----------|--------|")

    for i, theme_info in enumerate(theme_analysis['main_themes']):
        report.append(f"| {i+1} | {theme_info['theme']} | {theme_info['score']} | {theme_info['count']} | {theme_info['total_amount']} | {theme_info['up_ratio']}% | {theme_info['zt_count']} |")

    report.append("")

    # 支线题材
    if theme_analysis['sub_themes']:
        report.append("### 强势支线（4-10名）")
        report.append("")
        report.append("| 排名 | 题材 | 强度评分 | 股票数量 | 总成交额(亿) | 上涨比例 | 涨停数 |")
        report.append("|------|------|----------|----------|--------------|----------|--------|")

        for i, theme_info in enumerate(theme_analysis['sub_themes'][:7]):  # 最多7个
            report.append(f"| {i+4} | {theme_info['theme']} | {theme_info['score']} | {theme_info['count']} | {theme_info['total_amount']} | {theme_info['up_ratio']}% | {theme_info['zt_count']} |")

        report.append("")

    # 第三部分：新闻事件摘要
    report.append("## 📰 新闻事件摘要")
    report.append("")

    if news_events:
        # 按题材分组统计
        theme_news = defaultdict(list)
        for news in news_events:
            subject_name = news.get('subjectName', '未知题材')
            description = news.get('description', '')
            theme_news[subject_name].append(description)

        # 显示前10个题材
        report.append("### 热门题材新闻驱动")
        report.append("")

        for i, (subject_name, descriptions) in enumerate(sorted(theme_news.items(), key=lambda x: len(x[1]), reverse=True)[:10]):
            report.append(f"{i+1}. **{subject_name}** ({len(descriptions)}条)")
            # 显示第一条新闻的摘要
            if descriptions:
                desc = descriptions[0]
                if len(desc) > 120:
                    desc = desc[:120] + "..."
                report.append(f"   - {desc}")
            report.append("")

        # 显示最重要的5条新闻详情
        report.append("### 重要新闻详情")
        report.append("")

        # 按描述长度排序（简单的重要性判断）
        sorted_news = sorted(news_events, key=lambda x: len(x.get('description', '')), reverse=True)[:5]

        for i, news in enumerate(sorted_news):
            subject_name = news.get('subjectName', '未知题材')
            description = news.get('description', '无描述')

            # 截取描述
            if len(description) > 150:
                description = description[:150] + "..."

            report.append(f"**{i+1}. [{subject_name}]**")
            report.append(f"   {description}")
            report.append("")
    else:
        report.append("⚠ 未找到相关新闻事件数据")
        report.append("")

    # 第四部分：重点关注股票清单
    report.append("## 🏆 重点关注股票清单")
    report.append("")
    report.append("**筛选标准**: 综合关注度分数≥40（涨幅+资金+换手+flag+题材）")
    report.append("")

    report.append("| 排名 | 代码 | 名称 | 涨幅 | 资金强度 | 换手率 | Flag | 资金性质 | 技术形态 | 题材热点 | 关注度 |")
    report.append("|------|------|------|------|----------|--------|------|----------|----------|----------|--------|")

    for i, stock in enumerate(focus_stocks[:30]):  # 显示前30只
        # 格式化数据
        pct_str = f"{stock['pct_chg']:.2f}%"
        ratio_str = f"{stock['amount_ratio']:.1f}%" if stock['amount_ratio'] > 0 else "N/A"
        turnover_str = f"{stock['turnover']:.1f}%"

        # 题材热点（取前2个）
        subjects_str = ", ".join(stock['subjects'][:2]) if stock['subjects'] else "无"

        report.append(f"| {i+1} | `{stock['code']}` | {stock['name']} | {pct_str} | {ratio_str} | {turnover_str} | `{stock['flag']}`({stock['flag_desc']}) | {stock['capital_type']} | {stock['trend']}/{stock['volume_trend']} | {subjects_str} | **{stock['score']}** |")

    report.append("")

    # 第五部分：资金流向分析
    report.append("## 💰 资金流向分析")
    report.append("")

    # 资金性质统计
    capital_types = Counter()
    for stock in focus_stocks:
        capital_types[stock['capital_type']] += 1

    report.append("### 重点关注股票资金性质分布")
    report.append("")
    for cap_type, count in capital_types.most_common():
        percentage = count / len(focus_stocks) * 100 if focus_stocks else 0
        report.append(f"- **{cap_type}**: {count}只 ({percentage:.1f}%)")

    report.append("")

    # 成交额排名
    report.append("### 成交额前10名")
    report.append("")

    # 从所有股票中选成交额前10
    top_amount_stocks = sorted(stocks, key=lambda x: x['amount'], reverse=True)[:10]

    report.append("| 排名 | 代码 | 名称 | 成交额(亿) | 涨幅 | 换手率 | 资金性质 |")
    report.append("|------|------|------|------------|------|--------|----------|")

    for i, stock in enumerate(top_amount_stocks):
        amount_100m = stock['amount'] / 1e8
        pct_str = f"{stock['pct_chg']:.2f}%"
        turnover_str = f"{stock['turnover']:.1f}%"

        capital_info = analyze_capital_nature(stock)

        report.append(f"| {i+1} | `{stock['code']}` | {stock['name']} | {amount_100m:.2f} | {pct_str} | {turnover_str} | {capital_info['type']} |")

    report.append("")

    # 第六部分：投资建议
    report.append("## 💡 投资建议与策略")
    report.append("")

    report.append("### 主线题材跟踪策略")
    if theme_analysis['main_themes']:
        for i, theme_info in enumerate(theme_analysis['main_themes']):
            report.append(f"{i+1}. **{theme_info['theme']}** (强度:{theme_info['score']})")
            report.append(f"   - 相关股票: {theme_info['count']}只，涨停: {theme_info['zt_count']}只")
            report.append(f"   - 策略: 关注龙头股，把握板块轮动机会")
            report.append("")

    report.append("### 重点关注股票策略")
    report.append("")
    report.append("1. **高关注度股票（分数≥60）**:")
    high_score_stocks = [s for s in focus_stocks if s['score'] >= 60]
    if high_score_stocks:
        for stock in high_score_stocks[:5]:
            report.append(f"   - `{stock['code']}` {stock['name']}: {stock['reasons'][:3]}")
    else:
        report.append("   - 暂无分数≥60的股票")

    report.append("")
    report.append("2. **技术形态优良股票**:")
    tech_good_stocks = [s for s in focus_stocks if '强势' in s['trend'] and '价量齐升' in s['volume_trend']]
    if tech_good_stocks:
        for stock in tech_good_stocks[:5]:
            report.append(f"   - `{stock['code']}` {stock['name']}: {stock['trend']}, {stock['volume_trend']}")
    else:
        report.append("   - 暂无技术形态优良的股票")

    report.append("")
    report.append("3. **资金流入明显股票**:")
    capital_strong_stocks = [s for s in focus_stocks if s['amount_ratio'] > 5]
    if capital_strong_stocks:
        for stock in capital_strong_stocks[:5]:
            report.append(f"   - `{stock['code']}` {stock['name']}: 资金强度{stock['amount_ratio']:.1f}%")
    else:
        report.append("   - 暂无资金流入明显的股票")

    report.append("")

    # 第七部分：风险提示
    report.append("## ⚠️ 风险提示")
    report.append("")
    report.append("1. **市场风险**: 股市有风险，投资需谨慎")
    report.append("2. **数据延迟**: 本报告基于历史数据，存在滞后性")
    report.append("3. **技术风险**: 技术分析仅为参考，需结合基本面")
    report.append("4. **流动性风险**: 高换手率股票波动可能较大")
    report.append("5. **题材轮动**: 热点题材切换较快，注意节奏把握")
    report.append("")
    report.append(f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return "\n".join(report)

def main():
    print("🔍 开始生成2026-04-08日综合投资分析报告...")
    print("=" * 80)

    # 1. 加载股票数据
    print("1️⃣ 加载2026-04-08股票数据...")
    stocks = load_2026_04_08_stocks()
    if not stocks:
        print("❌ 无法加载股票数据")
        return

    # 2. 分析主线题材
    print("2️⃣ 分析主线题材和支线题材...")
    theme_analysis = analyze_main_themes(stocks)

    print(f"   主线题材: {len(theme_analysis['main_themes'])}个")
    for i, theme in enumerate(theme_analysis['main_themes'][:3]):
        print(f"     {i+1}. {theme['theme']} (强度:{theme['score']})")

    print(f"   支线题材: {len(theme_analysis['sub_themes'])}个")

    # 3. 加载新闻事件
    print("3️⃣ 加载新闻事件数据...")
    news_events = load_news_events()

    # 4. 识别重点关注股票
    print("4️⃣ 识别重点关注股票...")
    focus_stocks = identify_focus_stocks(stocks, theme_analysis, news_events)

    print(f"   重点关注股票: {len(focus_stocks)}只")
    if focus_stocks:
        print(f"   最高分: {focus_stocks[0]['score']} ({focus_stocks[0]['code']} {focus_stocks[0]['name']})")

    # 5. 生成报告
    print("5️⃣ 生成综合投资分析报告...")
    report = generate_daily_report(stocks, theme_analysis, news_events, focus_stocks)

    # 输出报告摘要
    print("\n" + "=" * 80)
    print(report[:1500] + "..." if len(report) > 1500 else report)
    print("=" * 80)

    # 6. 保存报告
    output_file = f"daily_comprehensive_report_2026_04_08_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n💾 综合报告已保存至: {output_file}")

    # 简要统计
    print("\n📊 简要统计:")
    print(f"   总分析股票: {len(stocks)}")
    print(f"   主线题材: {len(theme_analysis['main_themes'])}个")
    print(f"   支线题材: {len(theme_analysis['sub_themes'])}个")
    print(f"   新闻事件: {len(news_events)}条")
    print(f"   重点关注股票: {len(focus_stocks)}只")

    if focus_stocks:
        print(f"\n🏆 关注度前5名:")
        for i, stock in enumerate(focus_stocks[:5]):
            print(f"   {i+1}. {stock['code']} {stock['name']} ({stock['score']}分): {', '.join(stock['reasons'][:3])}")

if __name__ == "__main__":
    main()