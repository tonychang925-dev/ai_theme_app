#!/usr/bin/env python3
"""
生成flag异常股票的Markdown格式报告
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"

def extract_unique_special_flag_stocks():
    """提取去重后的特殊flag股票"""
    files = list(STOCK_DAILY_DIR.glob("*_2026-04-08_stocks.jsonl"))
    if not files:
        print("未找到2026-04-08的数据文件")
        return None

    print(f"分析{len(files)}个2026-04-08的数据文件...")

    # 存储特殊flag股票，使用code作为键去重
    special_stocks = {
        -1: {},  # flag=-1: 放量滞涨，code -> stock_info
        3: {},   # flag=3: 罕见涨停标记
        4: {},   # flag=4: 罕见涨停标记
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
                        code = data[2] if len(data) > 2 else "unknown"

                        # 如果已经存在，合并题材信息（去重）
                        if code in special_stocks[flag]:
                            existing = special_stocks[flag][code]
                            # 合并题材（去重）
                            existing_subjects = {tuple(s) for s in existing['subjects']}
                            new_subjects = {tuple(s) for s in data[16] if len(data) > 16 and isinstance(data[16], list)}
                            all_subjects = list(existing_subjects.union(new_subjects))
                            existing['subjects'] = all_subjects
                        else:
                            # 创建新记录
                            stock_info = {
                                'code': code,
                                'name': data[3] if len(data) > 3 else "unknown",
                                'flag': flag,
                                'pct_chg': data[10] if len(data) > 10 else None,
                                'amount': data[13] if len(data) > 13 else None,
                                'volume': data[12] if len(data) > 12 else None,
                                'market_cap': data[21] if len(data) > 21 else None,
                                'turnover': data[11] if len(data) > 11 else None,
                                'subjects': data[16] if len(data) > 16 and isinstance(data[16], list) else [],
                            }

                            # 计算成交额/总市值比例
                            if stock_info['amount'] and stock_info['market_cap'] and stock_info['market_cap'] > 0:
                                stock_info['amount_ratio'] = stock_info['amount'] / stock_info['market_cap'] * 100
                            else:
                                stock_info['amount_ratio'] = None

                            special_stocks[flag][code] = stock_info

                    total_stocks += 1

    # 转换为列表形式
    result = {
        -1: list(special_stocks[-1].values()),
        3: list(special_stocks[3].values()),
        4: list(special_stocks[4].values())
    }

    # 统计信息
    print(f"\n总股票数: {total_stocks}")
    for flag in [-1, 3, 4]:
        count = len(result[flag])
        print(f"flag={flag}: {count}只唯一股票 ({count/total_stocks*100:.2f}%)")

    return result

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

def get_flag_description(flag):
    """获取flag描述"""
    descriptions = {
        -1: "放量滞涨",
        0: "正常波动",
        1: "涨停",
        2: "连续涨停",
        3: "罕见涨停（尾盘竞价抢筹）",
        4: "无量涨停（异常资金强化）"
    }
    return descriptions.get(flag, f"未知({flag})")

def generate_markdown_report(special_stocks):
    """生成Markdown格式报告"""
    md_lines = []

    # 标题和统计信息
    md_lines.append("# 🚨 Flag异常股票分析报告")
    md_lines.append("")
    md_lines.append(f"**报告日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append(f"**分析基准日**: 2026-04-08")
    md_lines.append("")

    # 统计摘要
    total_unique = sum(len(stocks) for stocks in special_stocks.values())
    md_lines.append("## 📊 统计摘要")
    md_lines.append("")
    md_lines.append("| Flag | 描述 | 数量 | 占比 |")
    md_lines.append("|------|------|------|------|")
    for flag in [-1, 3, 4]:
        count = len(special_stocks[flag])
        percentage = count / total_unique * 100 if total_unique > 0 else 0
        description = get_flag_description(flag)
        md_lines.append(f"| `{flag}` | {description} | {count} | {percentage:.2f}% |")
    md_lines.append("")

    # 为每个flag类型生成详细表格
    for flag in [-1, 3, 4]:
        stocks = special_stocks[flag]
        if not stocks:
            continue

        description = get_flag_description(flag)
        md_lines.append(f"## 📋 Flag={flag} - {description}")
        md_lines.append("")

        # 计算关注度分数
        for stock in stocks:
            stock['focus_score'] = calculate_focus_score(stock, flag)

        # 排序：flag=-1按资金流入强度排序，flag=3/4按关注度排序
        if flag == -1:
            sorted_stocks = sorted(
                [s for s in stocks if s['amount_ratio'] is not None],
                key=lambda x: x['amount_ratio'],
                reverse=True
            )
        else:
            sorted_stocks = sorted(stocks, key=lambda x: x.get('focus_score', 0), reverse=True)

        md_lines.append("### 详细列表")
        md_lines.append("")

        if flag == -1:
            md_lines.append("| 排名 | 代码 | 名称 | 涨幅 | 资金流入强度 | 成交额(亿) | 关注度 | 主要题材 |")
            md_lines.append("|------|------|------|------|-------------|-----------|--------|----------|")

            for i, stock in enumerate(sorted_stocks[:30]):  # 显示前30个
                # 格式化数据
                pct_str = f"{stock['pct_chg']:.2f}%" if stock['pct_chg'] is not None else "N/A"
                ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
                amount_str = f"{stock['amount']/100000000:.2f}" if stock['amount'] is not None else "N/A"
                score_str = f"{stock['focus_score']:.1f}"

                # 提取主要题材（前3个）
                subjects = stock['subjects']
                if subjects and len(subjects) > 0:
                    # 过滤掉复盘类题材
                    main_subjects = []
                    for subject in subjects[:5]:
                        if isinstance(subject, list) and len(subject) >= 2:
                            subject_name = subject[1]
                            if '复盘' not in subject_name and '热门题材' not in subject_name:
                                main_subjects.append(subject_name)

                    if main_subjects:
                        subjects_str = ", ".join(main_subjects[:3])
                        if len(main_subjects) > 3:
                            subjects_str += f" 等{len(main_subjects)}个题材"
                    else:
                        subjects_str = "无核心题材"
                else:
                    subjects_str = "无题材"

                md_lines.append(f"| {i+1} | `{stock['code']}` | {stock['name']} | {pct_str} | {ratio_str} | {amount_str} | {score_str} | {subjects_str} |")

        else:  # flag=3或4
            md_lines.append("| 排名 | 代码 | 名称 | 涨幅 | 资金流入强度 | 成交额(亿) | 关注度 | 主要题材 |")
            md_lines.append("|------|------|------|------|-------------|-----------|--------|----------|")

            for i, stock in enumerate(sorted_stocks):
                # 格式化数据
                pct_str = f"{stock['pct_chg']:.2f}%" if stock['pct_chg'] is not None else "N/A"
                ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
                amount_str = f"{stock['amount']/100000000:.2f}" if stock['amount'] is not None else "N/A"
                score_str = f"{stock['focus_score']:.1f}"

                # 提取主要题材（前3个）
                subjects = stock['subjects']
                if subjects and len(subjects) > 0:
                    # 过滤掉复盘类题材
                    main_subjects = []
                    for subject in subjects[:5]:
                        if isinstance(subject, list) and len(subject) >= 2:
                            subject_name = subject[1]
                            if '复盘' not in subject_name and '热门题材' not in subject_name:
                                main_subjects.append(subject_name)

                    if main_subjects:
                        subjects_str = ", ".join(main_subjects[:3])
                        if len(main_subjects) > 3:
                            subjects_str += f" 等{len(main_subjects)}个题材"
                    else:
                        subjects_str = "无核心题材"
                else:
                    subjects_str = "无题材"

                md_lines.append(f"| {i+1} | `{stock['code']}` | {stock['name']} | {pct_str} | {ratio_str} | {amount_str} | {score_str} | {subjects_str} |")

        md_lines.append("")

    # 综合关注度排名
    md_lines.append("## 🏆 综合关注度排名")
    md_lines.append("")

    # 合并所有股票并计算关注度
    all_stocks = []
    for flag in [-1, 3, 4]:
        for stock in special_stocks[flag]:
            stock_copy = stock.copy()
            stock_copy['focus_score'] = calculate_focus_score(stock_copy, flag)
            all_stocks.append(stock_copy)

    # 按关注度排序
    sorted_all = sorted(all_stocks, key=lambda x: x['focus_score'], reverse=True)

    md_lines.append("| 综合排名 | 代码 | 名称 | Flag | 涨幅 | 资金强度 | 成交额(亿) | 关注度 |")
    md_lines.append("|----------|------|------|------|------|----------|-----------|--------|")

    for i, stock in enumerate(sorted_all[:20]):  # 显示前20个
        pct_str = f"{stock['pct_chg']:.2f}%" if stock['pct_chg'] is not None else "N/A"
        ratio_str = f"{stock['amount_ratio']:.2f}%" if stock['amount_ratio'] is not None else "N/A"
        amount_str = f"{stock['amount']/100000000:.2f}" if stock['amount'] is not None else "N/A"
        score_str = f"{stock['focus_score']:.1f}"

        md_lines.append(f"| {i+1} | `{stock['code']}` | {stock['name']} | `{stock['flag']}` | {pct_str} | {ratio_str} | {amount_str} | **{score_str}** |")

    md_lines.append("")

    # 投资建议部分
    md_lines.append("## 💡 投资建议")
    md_lines.append("")

    md_lines.append("### Flag=-1（放量滞涨）")
    md_lines.append("- **特征**: 成交额大幅放大但涨幅有限，可能是主力吸筹或题材预热")
    md_lines.append("- **策略**: 重点关注资金流入强度高的股票，观察次日是否突破")
    md_lines.append("- **风险**: 放量不涨可能预示调整，需谨慎")
    md_lines.append("")

    md_lines.append("### Flag=3（罕见涨停）")
    md_lines.append("- **特征**: 100%涨停，中等资金流入，可能预示连续涨停潜力")
    md_lines.append("- **策略**: 关注题材正宗性，观察板块联动效应")
    md_lines.append("- **风险**: 注意涨停板打开风险")
    md_lines.append("")

    md_lines.append("### Flag=4（无量涨停）")
    md_lines.append("- **特征**: 100%涨停，成交量极低，可能是一字板或极度惜售")
    md_lines.append("- **策略**: 观察次日竞价情况，一字板可能延续")
    md_lines.append("- **风险**: 成交量过低，流动性风险")
    md_lines.append("")

    # 注意事项
    md_lines.append("## ⚠️ 注意事项")
    md_lines.append("")
    md_lines.append("1. 本报告基于2026-04-08数据，请结合最新市场情况判断")
    md_lines.append("2. flag信号仅为参考指标，需结合其他技术面和基本面分析")
    md_lines.append("3. 投资有风险，决策需谨慎")
    md_lines.append("")

    return "\n".join(md_lines)

def main():
    print("🔍 开始提取并生成flag异常股票Markdown报告...")

    # 提取去重后的特殊flag股票
    special_stocks = extract_unique_special_flag_stocks()
    if not special_stocks:
        print("❌ 无法提取股票数据")
        return

    # 生成Markdown报告
    print("\n📝 生成Markdown格式报告...")
    md_report = generate_markdown_report(special_stocks)

    # 保存报告
    output_file = f"flag_abnormal_stocks_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md_report)

    print(f"✅ Markdown报告已保存至: {output_file}")

    # 显示简要统计
    print("\n📊 简要统计:")
    for flag in [-1, 3, 4]:
        count = len(special_stocks[flag])
        description = get_flag_description(flag)
        print(f"  Flag={flag} ({description}): {count}只股票")

    # 显示综合关注度前5名
    print("\n🏆 综合关注度前5名:")
    all_stocks = []
    for flag in [-1, 3, 4]:
        for stock in special_stocks[flag]:
            stock_copy = stock.copy()
            stock_copy['focus_score'] = calculate_focus_score(stock_copy, flag)
            all_stocks.append(stock_copy)

    sorted_all = sorted(all_stocks, key=lambda x: x['focus_score'], reverse=True)
    for i, stock in enumerate(sorted_all[:5]):
        print(f"  {i+1}. {stock['code']} {stock['name']} (flag={stock['flag']}): 关注度={stock['focus_score']:.1f}, 涨幅={stock['pct_chg']:.2f}%")

if __name__ == "__main__":
    main()