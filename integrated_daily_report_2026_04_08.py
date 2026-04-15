#!/usr/bin/env python3
"""
4月8日整合分析报告
整合综合报告、技术形态筛选报告和异常信号分析
"""

import re
import json
from datetime import datetime
from pathlib import Path

def parse_table_from_md(content, start_marker=None):
    """从Markdown内容中解析表格"""
    lines = content.split('\n')
    tables = []
    current_table = []
    in_table = False
    header = None

    for line in lines:
        line = line.strip()

        # 检测表格开始
        if start_marker and start_marker in line:
            in_table = True
            continue
        elif line.startswith('|') and '---' not in line and not start_marker:
            in_table = True

        if in_table:
            if line.startswith('|'):
                # 解析表格行
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if '---' in line:
                    # 表头分隔线，跳过
                    continue
                elif not header:
                    header = parts
                else:
                    row = {}
                    for i, col in enumerate(parts):
                        if i < len(header):
                            row[header[i]] = col
                    current_table.append(row)
            elif line and not line.startswith('|'):
                # 表格结束
                if current_table:
                    tables.append(current_table)
                    current_table = []
                    header = None
                    in_table = False

    if current_table:
        tables.append(current_table)

    return tables

def load_tech_report():
    """加载技术形态筛选报告"""
    with open('flag_technical_patterns_report_20260409_094041.md', 'r', encoding='utf-8') as f:
        content = f.read()

    # 查找表格
    tables = parse_table_from_md(content)
    tech_stocks = {}

    for table in tables:
        for row in table:
            if '代码' in row and '名称' in row:
                code = row['代码'].strip().strip('`')
                if code.isdigit() and len(code) == 6:
                    tech_stocks[code] = {
                        'name': row['名称'],
                        'flag': row.get('Flag', '').strip().strip('`'),
                        'pct_chg': row.get('涨幅', ''),
                        'capital_strength': row.get('资金强度', ''),
                        'tech_score': row.get('技术形态得分', ''),
                        'low_position': row.get('低位', ''),
                        'high_volume': row.get('放量', ''),
                        'breakout': row.get('突破', ''),
                        'tech_summary': row.get('技术信号摘要', '')
                    }

    return tech_stocks

def load_comprehensive_report():
    """加载综合报告"""
    with open('daily_comprehensive_report_2026_04_08_20260409_094021.md', 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取市场概况
    market_info = {}
    market_patterns = {
        '总成交额': r'总成交额.*?([\d,]+\.?\d*)亿元',
        '上涨家数': r'上涨家数.*?(\d+)\s*\(([\d.]+)%\)',
        '下跌家数': r'下跌家数.*?(\d+)\s*\(([\d.]+)%\)',
        '涨停家数': r'涨停家数.*?(\d+)',
        '平均涨跌幅': r'平均涨跌幅.*?([\d.]+)%'
    }

    for key, pattern in market_patterns.items():
        match = re.search(pattern, content)
        if match:
            if key == '上涨家数' or key == '下跌家数':
                market_info[key] = f"{match.group(1)} ({match.group(2)}%)"
            elif key == '总成交额':
                market_info[key] = f"{match.group(1)}亿元"
            else:
                market_info[key] = match.group(1)

    # 提取主线题材
    themes = []
    theme_section_start = content.find('核心主线（前3）')
    if theme_section_start != -1:
        theme_section = content[theme_section_start:theme_section_start+2000]
        theme_tables = parse_table_from_md(theme_section)
        for table in theme_tables:
            for row in table:
                if '排名' in row:
                    themes.append({
                        'rank': row.get('排名', ''),
                        'theme': row.get('题材', ''),
                        'score': row.get('强度评分', ''),
                        'stock_count': row.get('股票数量', ''),
                        'amount': row.get('总成交额(亿)', ''),
                        'up_ratio': row.get('上涨比例', ''),
                        'zt_count': row.get('涨停数', '')
                    })

    # 提取新闻事件
    news = []
    news_section_start = content.find('新闻事件摘要')
    if news_section_start != -1:
        news_section = content[news_section_start:news_section_start+3000]
        # 提取新闻列表
        news_lines = []
        for line in news_section.split('\n'):
            if line.strip().startswith('1. **') or line.strip().startswith('**1. ['):
                news_lines.append(line.strip())

        for line in news_lines:
            # 提取新闻标题和内容
            match = re.search(r'(\d+)\.\s*\*\*(.*?)\*\*', line)
            if match:
                news.append({
                    'index': match.group(1),
                    'title': match.group(2),
                    'content': line
                })

    # 提取重点关注股票
    focus_stocks = {}
    focus_section_start = content.find('重点关注股票清单')
    if focus_section_start != -1:
        focus_section = content[focus_section_start:focus_section_start+4000]
        tables = parse_table_from_md(focus_section)
        for table in tables:
            for row in table:
                if '代码' in row and '名称' in row:
                    code = row['代码'].strip().strip('`')
                    if code.isdigit() and len(code) == 6:
                        focus_stocks[code] = {
                            'rank': row.get('排名', ''),
                            'name': row['名称'],
                            'pct_chg': row.get('涨幅', ''),
                            'capital_strength': row.get('资金强度', ''),
                            'turnover_rate': row.get('换手率', ''),
                            'flag': row.get('Flag', '').replace('`', ''),
                            'capital_nature': row.get('资金性质', ''),
                            'tech_pattern': row.get('技术形态', ''),
                            'themes': row.get('题材热点', ''),
                            'attention_score': row.get('关注度', '').strip('*')
                        }

    return {
        'market_info': market_info,
        'themes': themes[:10],  # 前10个主题
        'news': news[:10],      # 前10条新闻
        'focus_stocks': focus_stocks
    }

def analyze_overlap(tech_stocks, comp_stocks):
    """分析重叠股票"""
    overlap_codes = set(tech_stocks.keys()) & set(comp_stocks.keys())
    overlap_stocks = []

    for code in overlap_codes:
        tech = tech_stocks[code]
        comp = comp_stocks[code]
        overlap_stocks.append({
            'code': code,
            'name': tech['name'],
            'tech_flag': tech['flag'],
            'comp_flag': comp['flag'],
            'tech_pct': tech['pct_chg'],
            'comp_pct': comp['pct_chg'],
            'tech_score': tech['tech_score'],
            'comp_rank': comp['rank'],
            'tech_summary': tech['tech_summary'],
            'comp_themes': comp['themes'],
            'attention_score': comp['attention_score']
        })

    return overlap_stocks

def generate_integrated_report(tech_stocks, comp_data, overlap_stocks):
    """生成整合报告"""
    report = []
    report.append("# 📊 2026-04-08日整合投资分析报告")
    report.append("")
    report.append("**报告日期**: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    report.append("**分析基准日**: 2026-04-08")
    report.append("")

    # 市场概况
    report.append("## 📈 市场概况")
    report.append("")
    market = comp_data['market_info']
    report.append(f"- **总成交额**: {market.get('总成交额', 'N/A')}")
    report.append(f"- **上涨家数**: {market.get('上涨家数', 'N/A')}")
    report.append(f"- **下跌家数**: {market.get('下跌家数', 'N/A')}")
    report.append(f"- **涨停家数**: {market.get('涨停家数', 'N/A')}")
    report.append(f"- **平均涨跌幅**: {market.get('平均涨跌幅', 'N/A')}")
    report.append("")

    # 主线题材
    report.append("## 🎯 核心主线题材")
    report.append("")
    themes = comp_data['themes']
    for theme in themes[:3]:  # 前3个核心主线
        report.append(f"**{theme['rank']}. {theme['theme']}** (强度: {theme['score']})")
        report.append(f"  - 股票数量: {theme['stock_count']}只")
        report.append(f"  - 总成交额: {theme['amount']}亿元")
        report.append(f"  - 上涨比例: {theme['up_ratio']}")
        report.append(f"  - 涨停数: {theme['zt_count']}只")
        report.append("")

    # 新闻驱动
    report.append("## 📰 关键新闻事件驱动")
    report.append("")
    news = comp_data['news']
    for item in news[:5]:  # 前5条新闻
        report.append(f"**{item['index']}. {item['title']}**")
        # 提取简要内容
        content = item['content']
        if len(content) > 150:
            content = content[:150] + "..."
        report.append(f"  {content}")
        report.append("")

    # 技术形态筛选结果
    report.append("## 🔍 技术形态筛选结果")
    report.append("")
    report.append(f"**符合条件股票数**: {len(tech_stocks)}只")
    report.append(f"**筛选条件**: 低位、放量、K线突破（至少满足2个条件）")
    report.append("")

    # 技术形态筛选股票列表（前10只）
    tech_list = list(tech_stocks.items())[:10]
    report.append("| 代码 | 名称 | Flag | 涨幅 | 技术形态得分 | 低位 | 放量 | 突破 | 技术信号摘要 |")
    report.append("|------|------|------|------|------------|------|------|------|--------------|")
    for code, data in tech_list:
        report.append(f"| `{code}` | {data['name']} | `{data['flag']}` | {data['pct_chg']} | {data['tech_score']} | {data['low_position']} | {data['high_volume']} | {data['breakout']} | {data['tech_summary']} |")
    report.append("")

    # 重点关注股票
    report.append("## 🏆 综合重点关注股票")
    report.append("")
    report.append(f"**筛选标准**: 综合关注度分数≥40（涨幅+资金+换手+flag+题材）")
    report.append(f"**股票数量**: {len(comp_data['focus_stocks'])}只")
    report.append("")

    # 重点关注股票列表（前15只）
    focus_items = list(comp_data['focus_stocks'].items())
    focus_items_sorted = sorted(focus_items, key=lambda x: int(x[1]['rank']) if x[1]['rank'].isdigit() else 999)[:15]

    report.append("| 排名 | 代码 | 名称 | 涨幅 | 资金强度 | 换手率 | Flag | 资金性质 | 技术形态 | 关注度 |")
    report.append("|------|------|------|------|----------|--------|------|----------|----------|--------|")
    for code, data in focus_items_sorted:
        report.append(f"| {data['rank']} | `{code}` | {data['name']} | {data['pct_chg']} | {data['capital_strength']} | {data['turnover_rate']} | `{data['flag']}` | {data['capital_nature']} | {data['tech_pattern']} | **{data['attention_score']}** |")
    report.append("")

    # 双重确认股票分析
    report.append("## ⭐ 双重确认重点关注股票")
    report.append("")
    if overlap_stocks:
        report.append(f"**发现 {len(overlap_stocks)} 只股票同时满足技术形态筛选和综合关注度要求**")
        report.append("")

        for stock in overlap_stocks:
            report.append(f"### {stock['code']} {stock['name']}")
            report.append("")
            report.append("**双重确认信号**:")
            report.append(f"- **技术形态筛选**: Flag=`{stock['tech_flag']}`，技术形态得分={stock['tech_score']}")
            report.append(f"- **综合关注度**: 排名#{stock['comp_rank']}，关注度分数={stock['attention_score']}")
            report.append(f"- **技术信号**: {stock['tech_summary']}")
            report.append(f"- **题材热点**: {stock['comp_themes']}")
            report.append("")

            # 特别分析智动力
            if stock['code'] == '300686':
                report.append("**智动力 (300686) 深度分析**:")
                report.append("1. **flag=-1 (放量滞涨)**: 成交量放大但涨幅有限，可能存在资金吸筹")
                report.append("2. **技术形态优良**: 满足放量和突破条件，量比3.0显示强烈资金关注")
                report.append("3. **题材正宗**: 消费电子+AI手机，符合当前市场主线")
                report.append("4. **资金强度高**: 16.4%的资金强度，显示主力资金关注")
                report.append("5. **换手率适中**: 32.9%的换手率，显示交投活跃")
                report.append("")
                report.append("**投资建议**:")
                report.append("- 重点关注，可作为短期跟踪标的")
                report.append("- 突破信号明确，适合趋势投资者")
                report.append("- 注意止损设置，防范放量滞涨风险")
                report.append("")
    else:
        report.append("**未发现双重确认股票**")
        report.append("")

    # 投资策略建议
    report.append("## 💡 投资策略建议")
    report.append("")
    report.append("### 1. 主线题材跟踪策略")
    report.append("- **AI手机/昇腾384超节点**: 关注龙头股，把握板块轮动机会")
    report.append("- **芯片/存储**: 关注涨价预期和国产替代逻辑")
    report.append("- **PCB/CPO**: 关注技术升级和需求增长")
    report.append("")
    report.append("### 2. 技术形态筛选策略")
    report.append("- **低位+放量**: 重点关注技术形态得分3/3的标的")
    report.append("- **突破确认**: 结合成交量验证突破有效性")
    report.append("- **风险控制**: 以突破平台低点或关键均线作为止损位")
    report.append("")
    report.append("### 3. 资金面分析策略")
    report.append("- **机构主导**: 关注机构净买入且换手适中的股票")
    report.append("- **游资+机构混合**: 关注资金合力推动的标的")
    report.append("- **尾盘抢筹**: 关注flag=3/4的异常资金强化信号")
    report.append("")

    # 风险提示
    report.append("## ⚠️ 风险提示")
    report.append("")
    report.append("1. **市场风险**: 股市有风险，投资需谨慎")
    report.append("2. **数据延迟**: 本报告基于历史数据，存在滞后性")
    report.append("3. **技术风险**: 技术分析仅为参考，需结合基本面")
    report.append("4. **题材轮动**: 热点题材切换较快，注意节奏把握")
    report.append("5. **异常信号风险**: flag异常股票可能存在特殊风险，需仔细甄别")
    report.append("")

    report.append(f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return '\n'.join(report)

def main():
    """主函数"""
    print("正在加载技术形态筛选报告...")
    tech_stocks = load_tech_report()
    print(f"加载 {len(tech_stocks)} 只技术形态筛选股票")

    print("正在加载综合报告...")
    comp_data = load_comprehensive_report()
    print(f"加载 {len(comp_data['focus_stocks'])} 只重点关注股票")

    print("分析重叠股票...")
    overlap_stocks = analyze_overlap(tech_stocks, comp_data['focus_stocks'])
    print(f"发现 {len(overlap_stocks)} 只双重确认股票")

    print("生成整合报告...")
    report = generate_integrated_report(tech_stocks, comp_data, overlap_stocks)

    # 保存报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"integrated_daily_report_2026_04_08_{timestamp}.md"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"报告已保存: {output_file}")

    # 打印关键发现
    print("\n=== 关键发现 ===")
    print(f"1. 技术形态筛选股票: {len(tech_stocks)}只")
    print(f"2. 综合重点关注股票: {len(comp_data['focus_stocks'])}只")
    print(f"3. 双重确认股票: {len(overlap_stocks)}只")
    if overlap_stocks:
        print("   双重确认股票列表:")
        for stock in overlap_stocks:
            print(f"   - {stock['code']} {stock['name']} (技术形态得分: {stock['tech_score']}, 综合排名: {stock['comp_rank']})")

if __name__ == "__main__":
    main()