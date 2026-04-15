#!/usr/bin/env python3
"""
筛选flag异常股票中符合低位、放量、K线突破技术形态的股票
集成：flag异常筛选 + 技术形态分析
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# 导入现有模块
try:
    from generate_flag_stocks_md import extract_unique_special_flag_stocks, get_flag_description
    print("✓ generate_flag_stocks_md 已加载")
except ImportError as e:
    print(f"⚠ generate_flag_stocks_md 导入失败: {e}")
    print("尝试直接定义必要函数...")
    # 这里可以添加备用定义，但为了简洁，先假设能导入

try:
    import enhanced_technical_analysis as ta
    print("✓ enhanced_technical_analysis 已加载")
except ImportError as e:
    print(f"⚠ enhanced_technical_analysis 导入失败: {e}")
    exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent

def assess_technical_patterns(df):
    """
    评估技术形态：低位、放量、K线突破
    """
    if df.empty or len(df) < 20:
        return {"error": "数据不足，至少需要20个交易日"}

    latest = df.iloc[-1]

    patterns = {
        'low_position': False,
        'high_volume': False,
        'breakout': False,
        'details': {}
    }

    # 1. 低位判断 (Low Position)
    # 条件1: 收盘价低于20日均线
    if 'SMA_20' in df.columns and pd.notna(latest['SMA_20']):
        below_sma20 = latest['close'] < latest['SMA_20']
        patterns['details']['below_sma20'] = below_sma20
        patterns['details']['sma20'] = round(latest['SMA_20'], 2)
    else:
        below_sma20 = False

    # 条件2: RSI低于40（超卖区域）
    if 'RSI_14' in df.columns and pd.notna(latest['RSI_14']):
        rsi_low = latest['RSI_14'] < 40
        patterns['details']['rsi_low'] = rsi_low
        patterns['details']['rsi'] = round(latest['RSI_14'], 2)
    else:
        rsi_low = False

    # 条件3: 价格处于布林带下轨附近（低于中轨）
    if 'BB_lower' in df.columns and 'BB_middle' in df.columns:
        if pd.notna(latest['BB_lower']) and pd.notna(latest['BB_middle']):
            near_bb_lower = latest['close'] < latest['BB_middle']
            bb_distance = (latest['close'] - latest['BB_lower']) / (latest['BB_middle'] - latest['BB_lower']) * 100 if latest['BB_middle'] > latest['BB_lower'] else 100
            patterns['details']['near_bb_lower'] = near_bb_lower
            patterns['details']['bb_distance_pct'] = round(bb_distance, 1)
            patterns['details']['bb_lower'] = round(latest['BB_lower'], 2)
            patterns['details']['bb_middle'] = round(latest['BB_middle'], 2)
        else:
            near_bb_lower = False
    else:
        near_bb_lower = False

    # 综合低位判断：满足任意一个条件
    patterns['low_position'] = below_sma20 or rsi_low or near_bb_lower

    # 2. 放量判断 (High Volume)
    if 'volume_ratio' in df.columns and pd.notna(latest['volume_ratio']):
        # 成交量比率大于1.5
        volume_ratio_high = latest['volume_ratio'] > 1.5
        patterns['details']['volume_ratio_high'] = volume_ratio_high
        patterns['details']['volume_ratio'] = round(latest['volume_ratio'], 2)

        # 成交量大于5日均量
        if 'volume_ma5' in df.columns and pd.notna(latest['volume_ma5']):
            volume_above_ma5 = latest['volume'] > latest['volume_ma5']
            patterns['details']['volume_above_ma5'] = volume_above_ma5
            patterns['details']['volume_ma5'] = round(latest['volume_ma5'], 0)
        else:
            volume_above_ma5 = False
    else:
        volume_ratio_high = False
        volume_above_ma5 = False

    # 综合放量判断：满足任意一个条件
    patterns['high_volume'] = volume_ratio_high or volume_above_ma5

    # 3. 突破判断 (Breakout)
    # 条件1: 突破布林带上轨
    if 'BB_upper' in df.columns and pd.notna(latest['BB_upper']):
        bb_breakout = latest['close'] > latest['BB_upper']
        patterns['details']['bb_breakout'] = bb_breakout
        patterns['details']['bb_upper'] = round(latest['BB_upper'], 2)
    else:
        bb_breakout = False

    # 条件2: 突破近期高点（10日高点）
    if len(df) >= 10:
        recent_high = df['high'].iloc[-10:-1].max()  # 排除今日
        breakthrough_high = latest['close'] > recent_high
        patterns['details']['breakthrough_high'] = breakthrough_high
        patterns['details']['recent_high'] = round(recent_high, 2)
    else:
        breakthrough_high = False

    # 条件3: 突破平台（价格在窄幅震荡后突破）
    if len(df) >= 20:
        # 计算最近10日的波动率（最高-最低）
        recent_range = df['high'].iloc[-10:].max() - df['low'].iloc[-10:].min()
        avg_range = df['high'].iloc[-20:-10].max() - df['low'].iloc[-20:-10].min()

        # 如果近期波动率小于前期平均波动率的70%，视为平台整理
        platform_consolidation = recent_range < avg_range * 0.7 if avg_range > 0 else False

        # 平台突破：今日收盘价突破平台最高点
        platform_high = df['high'].iloc[-10:-1].max()  # 平台期间最高价（排除今日）
        platform_breakout = platform_consolidation and latest['close'] > platform_high

        patterns['details']['platform_consolidation'] = platform_consolidation
        patterns['details']['platform_breakout'] = platform_breakout
        patterns['details']['platform_high'] = round(platform_high, 2) if platform_consolidation else None
        patterns['details']['recent_range'] = round(recent_range, 2)
        patterns['details']['avg_range'] = round(avg_range, 2)
    else:
        platform_breakout = False

    # 条件4: K线模式突破（吞没形态、锤子线等）
    candle_pattern_breakout = False
    if 'candle_patterns' in latest:
        # 检查是否有看涨的K线模式
        bullish_patterns = ['hammer', 'inverted_hammer', 'engulfing', 'morning_star']
        for pattern in bullish_patterns:
            if pattern in latest['candle_patterns']:
                candle_pattern_breakout = True
                patterns['details']['candle_pattern'] = pattern
                break

    # 综合突破判断：满足任意一个条件
    patterns['breakout'] = bb_breakout or breakthrough_high or platform_breakout or candle_pattern_breakout

    # 综合评分
    pattern_score = 0
    if patterns['low_position']:
        pattern_score += 1
    if patterns['high_volume']:
        pattern_score += 1
    if patterns['breakout']:
        pattern_score += 1

    patterns['pattern_score'] = pattern_score
    patterns['pattern_met'] = pattern_score >= 2  # 至少满足2个条件

    return patterns

def filter_stocks_by_technical_patterns(stock_list, end_date="2026-04-08"):
    """
    筛选符合技术形态的股票
    """
    qualified_stocks = []

    total = len(stock_list)
    print(f"\n🔍 开始技术形态筛选，共 {total} 只股票...")

    for i, stock in enumerate(stock_list):
        code = stock['code']
        name = stock['name']
        flag = stock['flag']

        print(f"  [{i+1}/{total}] {name} ({code}) flag={flag}", end="")

        # 加载历史数据（最近60个交易日，以便计算指标）
        try:
            df = ta.load_stock_history(code, days=60, end_date=end_date)
            if df.empty:
                print(" - 无历史数据")
                continue

            # 计算技术指标
            df_ta = ta.calculate_technical_indicators(df)
            if df_ta.empty:
                print(" - 技术指标计算失败")
                continue

            # 评估技术形态
            patterns = assess_technical_patterns(df_ta)

            if 'error' in patterns:
                print(f" - {patterns['error']}")
                continue

            # 检查是否满足至少2个条件
            if patterns['pattern_met']:
                stock_with_patterns = stock.copy()
                stock_with_patterns['technical_patterns'] = patterns
                stock_with_patterns['pattern_score'] = patterns['pattern_score']
                stock_with_patterns['df_ta'] = df_ta  # 保存技术指标数据
                qualified_stocks.append(stock_with_patterns)
                print(f" - ✓ 符合 (得分: {patterns['pattern_score']}/3)")
            else:
                print(f" - ✗ 不符合 (得分: {patterns['pattern_score']}/3)")

        except Exception as e:
            print(f" - 错误: {str(e)[:50]}")
            continue

    print(f"\n✅ 技术形态筛选完成，{len(qualified_stocks)}/{total} 只股票符合条件")
    return qualified_stocks

def generate_technical_pattern_report(qualified_stocks):
    """
    生成技术形态筛选报告
    """
    if not qualified_stocks:
        return "⚠ 未找到符合技术形态的股票"

    report = []
    report.append("# 📊 Flag异常股票技术形态筛选报告")
    report.append("")
    report.append(f"**报告日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**分析基准日**: 2026-04-08")
    report.append(f"**筛选条件**: 低位、放量、K线突破（至少满足2个条件）")
    report.append("")

    # 按pattern_score排序
    sorted_stocks = sorted(qualified_stocks, key=lambda x: x['pattern_score'], reverse=True)

    # 统计信息
    report.append("## 📈 统计摘要")
    report.append("")
    report.append(f"**符合条件股票数**: {len(qualified_stocks)}")
    report.append(f"**最高得分**: {max(s['pattern_score'] for s in qualified_stocks)}/3")
    report.append(f"**平均得分**: {sum(s['pattern_score'] for s in qualified_stocks)/len(qualified_stocks):.2f}/3")
    report.append("")

    # 按flag分类统计
    flag_stats = {-1: 0, 3: 0, 4: 0}
    for stock in qualified_stocks:
        flag_stats[stock['flag']] += 1

    report.append("| Flag | 描述 | 数量 | 占比 |")
    report.append("|------|------|------|------|")
    total_qualified = len(qualified_stocks)
    for flag in [-1, 3, 4]:
        count = flag_stats[flag]
        percentage = count / total_qualified * 100 if total_qualified > 0 else 0
        description = get_flag_description(flag)
        report.append(f"| `{flag}` | {description} | {count} | {percentage:.1f}% |")
    report.append("")

    # 详细表格
    report.append("## 📋 符合条件股票详细列表")
    report.append("")
    report.append("| 综合排名 | 代码 | 名称 | Flag | 涨幅 | 资金强度 | 技术形态得分 | 低位 | 放量 | 突破 | 技术信号摘要 |")
    report.append("|----------|------|------|------|------|----------|------------|------|------|------|--------------|")

    for i, stock in enumerate(sorted_stocks):
        code = stock['code']
        name = stock['name']
        flag = stock['flag']
        pct_chg = stock['pct_chg']
        amount_ratio = stock['amount_ratio']

        # 格式化数据
        pct_str = f"{pct_chg:.2f}%" if pct_chg is not None else "N/A"
        ratio_str = f"{amount_ratio:.2f}%" if amount_ratio is not None else "N/A"

        patterns = stock['technical_patterns']
        pattern_score = patterns['pattern_score']
        low_pos = "✓" if patterns['low_position'] else "✗"
        high_vol = "✓" if patterns['high_volume'] else "✗"
        breakout = "✓" if patterns['breakout'] else "✗"

        # 生成技术信号摘要
        signals = []
        details = patterns.get('details', {})

        if details.get('below_sma20'):
            signals.append(f"SMA20↓")
        if details.get('rsi_low'):
            signals.append(f"RSI{details.get('rsi', 0):.0f}")
        if details.get('near_bb_lower'):
            signals.append(f"BB↓")
        if details.get('volume_ratio_high'):
            signals.append(f"量比{details.get('volume_ratio', 0):.1f}")
        if details.get('bb_breakout'):
            signals.append("BB↑")
        if details.get('breakthrough_high'):
            signals.append("前高突破")
        if details.get('platform_breakout'):
            signals.append("平台突破")

        signals_str = ", ".join(signals) if signals else "无明确信号"

        report.append(f"| {i+1} | `{code}` | {name} | `{flag}` | {pct_str} | {ratio_str} | **{pattern_score}/3** | {low_pos} | {high_vol} | {breakout} | {signals_str} |")

    report.append("")

    # 投资建议
    report.append("## 💡 投资建议与策略")
    report.append("")

    report.append("### 重点关注策略")
    report.append("1. **得分3/3的股票**: 低位+放量+突破三重信号，短期爆发潜力最大")
    report.append("2. **得分2/3的股票**: 需结合具体信号判断，重点关注突破信号明确的标的")
    report.append("3. **旗形整理突破**: 关注平台突破+放量的组合信号")
    report.append("4. **资金强度优先**: 在同等技术形态下，优先选择资金流入强度高的股票")
    report.append("")

    report.append("### 风险控制要点")
    report.append("1. **低位确认**: 确保股票确实处于相对低位，而非下跌中继")
    report.append("2. **放量验证**: 成交量放大需持续，避免一日游行情")
    report.append("3. **突破有效性**: 突破需有成交量配合，假突破风险需防范")
    report.append("4. **止损设置**: 建议以突破平台低点或关键均线作为止损位")
    report.append("")

    # 详细技术分析
    report.append("## 🔍 重点关注股票技术分析")
    report.append("")

    # 取前5名进行详细分析
    for i, stock in enumerate(sorted_stocks[:5]):
        code = stock['code']
        name = stock['name']
        flag = stock['flag']
        patterns = stock['technical_patterns']
        df_ta = stock['df_ta']

        report.append(f"### {i+1}. {name} ({code}) - flag={flag}")
        report.append("")

        # 技术指标摘要
        latest = df_ta.iloc[-1]

        report.append("**关键指标**:")
        if 'SMA_20' in df_ta.columns and pd.notna(latest['SMA_20']):
            sma20 = latest['SMA_20']
            close = latest['close']
            sma20_status = "低于" if close < sma20 else "高于"
            report.append(f"  - 收盘价: {close:.2f}元 ({sma20_status}20日均线{sma20:.2f}元)")

        if 'RSI_14' in df_ta.columns and pd.notna(latest['RSI_14']):
            rsi = latest['RSI_14']
            rsi_status = "超卖" if rsi < 30 else "低位" if rsi < 40 else "正常" if rsi < 70 else "超买"
            report.append(f"  - RSI(14): {rsi:.1f} ({rsi_status})")

        if 'volume_ratio' in df_ta.columns and pd.notna(latest['volume_ratio']):
            vol_ratio = latest['volume_ratio']
            vol_status = "明显放量" if vol_ratio > 2 else "温和放量" if vol_ratio > 1.5 else "正常"
            report.append(f"  - 量比: {vol_ratio:.2f} ({vol_status})")

        if 'BB_upper' in df_ta.columns and 'BB_lower' in df_ta.columns:
            if pd.notna(latest['BB_upper']) and pd.notna(latest['BB_lower']):
                bb_position = "突破上轨" if latest['close'] > latest['BB_upper'] else "跌破下轨" if latest['close'] < latest['BB_lower'] else "轨道内"
                report.append(f"  - 布林带: {bb_position}")

        report.append("")

        # 形态信号
        report.append("**形态信号**:")
        details = patterns.get('details', {})

        if patterns['low_position']:
            low_signals = []
            if details.get('below_sma20'):
                low_signals.append("低于20日均线")
            if details.get('rsi_low'):
                low_signals.append(f"RSI低位({details.get('rsi', 0):.1f})")
            if details.get('near_bb_lower'):
                low_signals.append(f"布林带下轨附近({details.get('bb_distance_pct', 0):.1f}%)")
            if low_signals:
                report.append(f"  - 低位确认: {', '.join(low_signals)}")

        if patterns['high_volume']:
            volume_signals = []
            if details.get('volume_ratio_high'):
                volume_signals.append(f"量比{details.get('volume_ratio', 0):.2f}")
            if details.get('volume_above_ma5'):
                volume_signals.append("成交量突破5日均量")
            if volume_signals:
                report.append(f"  - 放量确认: {', '.join(volume_signals)}")

        if patterns['breakout']:
            breakout_signals = []
            if details.get('bb_breakout'):
                breakout_signals.append("突破布林带上轨")
            if details.get('breakthrough_high'):
                breakout_signals.append(f"突破近期高点{details.get('recent_high', 0):.2f}")
            if details.get('platform_breakout'):
                breakout_signals.append(f"平台突破({details.get('recent_range', 0):.2f}窄幅整理)")
            if breakout_signals:
                report.append(f"  - 突破确认: {', '.join(breakout_signals)}")

        report.append("")

        # 操作建议
        report.append("**操作建议**:")
        if patterns['pattern_score'] == 3:
            report.append("  - 强烈关注，三重信号共振，短期爆发潜力大")
        elif patterns['pattern_score'] == 2:
            report.append("  - 重点关注，等待信号进一步确认")

        # 具体建议基于信号组合
        if patterns['low_position'] and patterns['breakout']:
            report.append("  - 低位突破，适合激进型投资者参与")
        elif patterns['high_volume'] and patterns['breakout']:
            report.append("  - 放量突破，资金推动明确，适合趋势跟踪")

        report.append("  - 建议设置止损位，控制风险")
        report.append("")

    # 报告结尾
    report.append("## ⚠️ 风险提示")
    report.append("")
    report.append("1. 本报告基于历史数据和技术分析，仅供参考")
    report.append("2. 股市有风险，投资需谨慎")
    report.append("3. 技术分析存在滞后性，需结合实时市场情况")
    report.append("4. 建议设置止损，控制单笔投资风险")
    report.append("")
    report.append(f"**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return "\n".join(report)

def main():
    print("🔍 开始筛选Flag异常股票中符合技术形态的股票...")
    print("=" * 80)

    # 1. 提取flag异常股票
    print("1️⃣ 提取flag异常股票...")
    special_stocks = extract_unique_special_flag_stocks()
    if not special_stocks:
        print("❌ 无法提取flag异常股票")
        return

    # 合并所有flag类型的股票
    all_flag_stocks = []
    for flag in [-1, 3, 4]:
        all_flag_stocks.extend(special_stocks[flag])

    print(f"   共提取 {len(all_flag_stocks)} 只flag异常股票")

    # 2. 技术形态筛选
    print("\n2️⃣ 执行技术形态筛选...")
    qualified_stocks = filter_stocks_by_technical_patterns(all_flag_stocks)

    # 3. 生成报告
    print("\n3️⃣ 生成技术形态筛选报告...")
    report = generate_technical_pattern_report(qualified_stocks)

    # 输出报告
    print("\n" + "=" * 80)
    print(report[:1000] + "..." if len(report) > 1000 else report)
    print("=" * 80)

    # 4. 保存报告
    output_file = f"flag_technical_patterns_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n💾 技术形态筛选报告已保存至: {output_file}")

    # 5. 简要统计
    print("\n📊 简要统计:")
    print(f"   总flag异常股票: {len(all_flag_stocks)}")
    print(f"   符合技术形态: {len(qualified_stocks)} ({len(qualified_stocks)/len(all_flag_stocks)*100:.1f}%)")

    if qualified_stocks:
        print(f"   最高得分: {max(s['pattern_score'] for s in qualified_stocks)}/3")
        print(f"   平均得分: {sum(s['pattern_score'] for s in qualified_stocks)/len(qualified_stocks):.2f}/3")

        print("\n🏆 得分3/3的股票:")
        perfect_stocks = [s for s in qualified_stocks if s['pattern_score'] == 3]
        for i, stock in enumerate(perfect_stocks[:5]):
            print(f"   {i+1}. {stock['code']} {stock['name']} (flag={stock['flag']})")

if __name__ == "__main__":
    main()