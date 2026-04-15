#!/usr/bin/env python3
"""
风华高科（000636）综合投资分析报告
整合：PDF框架分析 + 技术分析 + 数据基本面
"""

import subprocess
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).resolve().parent

def load_stock_basic_info():
    """加载股票基本信息"""
    from analyze_fenghuagaoke_framework import load_fenghuagaoke_data
    stock_data = load_fenghuagaoke_data("2026-04-08")
    if not stock_data:
        return None

    # 提取关键信息
    info = {
        'code': stock_data[2],
        'name': stock_data[3],
        'trade_date': stock_data[0],
        'close': stock_data[7],
        'pct_chg': stock_data[10],
        'amount': stock_data[13],
        'turnover': stock_data[15],
        'high': stock_data[5],
        'low': stock_data[6],
        'amplitude': stock_data[11],
        'flag': stock_data[20] if len(stock_data) > 20 else None,
        'subjects': stock_data[16] if len(stock_data) > 16 else [],
        'market_cap': stock_data[21] if len(stock_data) > 21 else None,  # 总市值
        'circulating_cap': stock_data[35] if len(stock_data) > 35 else stock_data[36] if len(stock_data) > 36 else None  # 流通市值
    }
    return info

def run_pdf_framework_analysis():
    """运行PDF框架分析"""
    print("运行PDF框架分析...")
    try:
        # 直接导入并运行
        import analyze_fenghuagaoke_framework as pdf_analysis
        stock_data = pdf_analysis.load_fenghuagaoke_data("2026-04-08")
        if stock_data:
            analysis = pdf_analysis.analyze_by_framework(stock_data)
            return analysis
    except Exception as e:
        print(f"PDF框架分析出错: {e}")

    return None

def run_technical_analysis():
    """运行技术分析"""
    print("运行技术分析...")
    try:
        # 直接导入并运行
        import enhanced_technical_analysis as tech_analysis
        df = tech_analysis.load_stock_history("000636", days=20)
        if not df.empty:
            df_ta = tech_analysis.calculate_technical_indicators(df)
            assessment = tech_analysis.assess_technical_condition(df_ta)
            return {
                'assessment': assessment,
                'data': df_ta,
                'period': f"{df_ta.index[0].date()} 至 {df_ta.index[-1].date()}"
            }
    except Exception as e:
        print(f"技术分析出错: {e}")

    return None

def generate_integrated_report(basic_info, pdf_analysis, tech_analysis):
    """生成综合报告"""
    report = []

    # 报告标题
    report.append("=" * 120)
    report.append("📊 风华高科（000636）综合投资分析报告")
    report.append("=" * 120)
    report.append(f"报告日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"分析基准日: {basic_info['trade_date']}")
    report.append("=" * 120)

    # 第一部分：核心摘要
    report.append("\n📋 核心摘要")
    report.append("-" * 80)

    # 关键数据
    circulating_ratio = basic_info['circulating_cap'] / basic_info['market_cap'] * 100 if basic_info['circulating_cap'] and basic_info['market_cap'] else 0
    report.append(f"💰 关键数据:")
    report.append(f"   收盘价: {basic_info['close']}元")
    report.append(f"   涨跌幅: {basic_info['pct_chg']}%")
    report.append(f"   成交额: {basic_info['amount']/100000000:.2f}亿元")
    report.append(f"   换手率: {basic_info['turnover']}%")
    report.append(f"   总市值: {basic_info['market_cap']/100000000:.2f}亿元")
    report.append(f"   流通市值: {basic_info['circulating_cap']/100000000:.2f}亿元")
    report.append(f"   流通比例: {circulating_ratio:.2f}%")
    report.append(f"   flag信号: {basic_info['flag']} ({get_flag_description(basic_info['flag'])})")

    # 投资评级
    report.append(f"\n⭐ 综合投资评级: {calculate_investment_rating(basic_info, pdf_analysis, tech_analysis)}")

    # 第二部分：PDF框架分析摘要
    if pdf_analysis:
        report.append("\n🔍 PDF框架分析摘要")
        report.append("-" * 80)

        # 题材正宗性
        if '是否正宗' in pdf_analysis:
            zhengzong = pdf_analysis['是否正宗']
            report.append(f"📌 题材正宗性: {zhengzong['正宗性评估']}")
            report.append(f"   核心题材: {', '.join(zhengzong['核心题材'])}")

        # 龙头属性
        if '龙头属性' in pdf_analysis:
            longtou = pdf_analysis['龙头属性']
            report.append(f"👑 龙头属性: {longtou['行业地位']}, {longtou['龙头类型']}")
            report.append(f"   龙头成色: {longtou['龙头成色']}")

        # 资金性质
        if '资金性质' in pdf_analysis:
            capital = pdf_analysis['资金性质']
            report.append(f"💰 资金性质: {capital['资金类型']}")
            report.append(f"   主力行为: {capital['主力行为']}")

        # 市场情绪
        if '市场情绪判定' in pdf_analysis:
            emotion = pdf_analysis['市场情绪判定']
            report.append(f"🎭 市场情绪: {emotion['是否属于主线']}")
            report.append(f"   阶段判断: {', '.join([f'{k}:{v}' for k, v in emotion['阶段判断'].items()][:3])}")

    # 第三部分：技术分析摘要
    if tech_analysis and 'assessment' in tech_analysis:
        report.append("\n📈 技术分析摘要")
        report.append("-" * 80)
        report.append(f"分析周期: {tech_analysis.get('period', '未知')}")

        assessment = tech_analysis['assessment']

        # 趋势
        if 'trend' in assessment:
            trend = assessment['trend']
            report.append(f"📊 趋势分析: {trend.get('price_position', '未知')}")
            report.append(f"   均线排列: {trend.get('ma_alignment', '未知')}")

        # RSI
        if 'rsi' in assessment:
            rsi = assessment['rsi']
            report.append(f"📈 RSI指标: {rsi.get('status', '未知')} ({rsi.get('value', 'N/A')})")

        # 布林带
        if 'bollinger' in assessment:
            bb = assessment['bollinger']
            report.append(f"🎪 布林带: {bb.get('position', '未知')}")
            report.append(f"   波动率: {bb.get('volatility', '未知')}")

        # 成交量
        if 'volume' in assessment:
            volume = assessment['volume']
            report.append(f"📦 成交量: 量比{volume.get('volume_ratio', 'N/A')}, {volume.get('trend', '未知')}")

        # 关键价位
        if 'key_levels' in assessment:
            levels = assessment['key_levels']
            report.append(f"🔑 关键价位: 支撑{levels.get('support', 'N/A')}元, 压力{levels.get('resistance', 'N/A')}元")

    # 第四部分：多维评估矩阵
    report.append("\n🎯 多维评估矩阵")
    report.append("-" * 80)

    dimensions = {
        '题材正宗性': evaluate_dimension('theme_authenticity', pdf_analysis),
        '行业地位': evaluate_dimension('industry_position', pdf_analysis),
        '资金关注度': evaluate_dimension('capital_attention', basic_info, pdf_analysis),
        '技术形态': evaluate_dimension('technical_pattern', tech_analysis),
        '估值水平': evaluate_dimension('valuation', basic_info),
        '风险控制': evaluate_dimension('risk_control', basic_info, pdf_analysis)
    }

    for dim_name, dim_value in dimensions.items():
        score, level, description = dim_value
        report.append(f"{dim_name}: {'★' * score}{'☆' * (5-score)} ({level}) - {description}")

    # 第五部分：投资策略建议
    report.append("\n💡 投资策略建议")
    report.append("-" * 80)

    # 基于综合评估的建议
    total_score = sum([dim[0] for dim in dimensions.values()])
    max_score = len(dimensions) * 5
    score_percentage = total_score / max_score * 100

    # 考虑flag=-1的特殊情况，降低评级
    flag = basic_info['flag']
    if flag == -1:
        # flag=-1时，下调一个等级
        if score_percentage >= 80:
            score_percentage = 70  # 从强势看好降到谨慎乐观
        elif score_percentage >= 60:
            score_percentage = 50  # 从谨慎乐观降到中性/谨慎观望

    if score_percentage >= 80:  # 80%以上
        report.append("✅ 强势看好")
        report.append("   1. 短期: 积极关注突破机会")
        report.append("   2. 中期: 分批建仓，趋势持股")
        report.append("   3. 长期: 国产替代核心标的，长期持有")
    elif score_percentage >= 60:  # 60%-80%
        report.append("🟡 谨慎乐观")
        report.append("   1. 短期: 等待技术信号确认")
        report.append("   2. 中期: 回调至关键支撑位布局")
        report.append("   3. 长期: 观察行业景气度变化")
    else:
        report.append("🔴 谨慎观望")
        report.append("   1. 短期: 规避调整风险")
        report.append("   2. 中期: 等待基本面改善信号")
        report.append("   3. 长期: 关注行业拐点")

    # 具体操作建议
    report.append("\n📋 具体操作建议:")

    # 基于flag信号
    flag = basic_info['flag']
    if flag == -1:
        report.append("   1. flag=-1（放量滞涨），短期需谨慎")
        report.append("   2. 观察次日开盘竞价情况")
        report.append("   3. 等待flag信号化解（放量上涨或缩量调整）")
    elif flag in [3, 4]:
        report.append("   1. flag=3/4（异常资金强化），关注资金持续性")
        report.append("   2. 观察板块联动效应")
        report.append("   3. 设置止损位防范风险")

    # 基于技术分析
    if tech_analysis and 'assessment' in tech_analysis:
        assessment = tech_analysis['assessment']
        if 'trend' in assessment and '弱势下跌' in assessment['trend'].get('price_position', ''):
            report.append("   4. 技术面弱势，等待企稳信号")
        if 'rsi' in assessment and assessment['rsi'].get('oversold'):
            report.append("   5. RSI超卖，可能出现技术性反弹")

    # 第六部分：风险提示与监控要点
    report.append("\n⚠️ 风险提示与监控要点")
    report.append("-" * 80)

    report.append("🔴 高风险因素:")
    report.append("   1. flag=-1信号未化解前，短期调整风险")
    report.append("   2. 流通比例仅5.04%，流动性风险")
    report.append("   3. 电子行业周期性波动风险")

    report.append("\n🟡 中风险因素:")
    report.append("   1. 估值偏高（PE 75倍），需业绩验证")
    report.append("   2. 题材轮动风险，资金关注度变化")

    report.append("\n🟢 低风险因素:")
    report.append("   1. 国企背景，政策风险较低")
    report.append("   2. MLCC国产替代趋势明确，长期逻辑通顺")

    report.append("\n👀 关键监控指标:")
    report.append("   1. 次日开盘竞价情况")
    report.append("   2. MLCC板块整体表现")
    report.append("   3. 成交额是否持续放大")
    report.append("   4. 关键价位突破情况（20.5元压力位）")

    # 第七部分：催化剂与关键事件
    report.append("\n🚀 潜在催化剂与关键事件")
    report.append("-" * 80)

    report.append("📅 近期催化剂:")
    report.append("   1. AI手机新品发布（MLCC用量增加）")
    report.append("   2. 电子材料涨价通知")
    report.append("   3. 国企改革政策推进")
    report.append("   4. 一季度业绩预告")

    report.append("\n🔍 关键决策节点:")
    report.append("   ✅ 积极信号: 突破20.5元并放量确认")
    report.append("   ⚠️ 中性信号: 在19-20.5元区间震荡")
    report.append("   ❌ 风险信号: 连续3日收盘低于19元")

    # 报告结尾
    report.append("\n" + "=" * 120)
    report.append("📅 报告生成时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    report.append("💡 重要声明: 本报告仅供参考，不构成投资建议")
    report.append("=" * 120)

    return "\n".join(report)

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

def calculate_investment_rating(basic_info, pdf_analysis, tech_analysis):
    """计算综合投资评级"""
    score = 0
    max_score = 10

    # 1. 涨幅评分 (0-2分)
    pct_chg = abs(basic_info['pct_chg'])
    if pct_chg >= 9.9:
        score += 2  # 涨停
    elif pct_chg >= 5:
        score += 1  # 大涨
    elif pct_chg >= 0:
        score += 0.5  # 上涨

    # 2. 成交额评分 (0-2分)
    amount_billion = basic_info['amount'] / 100000000
    if amount_billion > 10:
        score += 2  # 高成交
    elif amount_billion > 5:
        score += 1  # 中等成交
    elif amount_billion > 1:
        score += 0.5  # 低成交

    # 3. flag信号评分 (0-2分)
    flag = basic_info['flag']
    if flag in [3, 4]:
        score += 2  # 异常资金强化
    elif flag == 1:
        score += 1.5  # 涨停
    elif flag == -1:
        score += 0.5  # 放量滞涨（有分歧）

    # 4. 题材评分 (0-2分)
    if pdf_analysis and '是否正宗' in pdf_analysis:
        if pdf_analysis['是否正宗']['正宗性评估'] == '高度正宗':
            score += 2
        elif '正宗' in pdf_analysis['是否正宗']['正宗性评估']:
            score += 1

    # 5. 技术面评分 (0-2分)
    if tech_analysis and 'assessment' in tech_analysis:
        assessment = tech_analysis['assessment']
        if 'trend' in assessment:
            trend = assessment['trend']
            if '强势上涨' in trend.get('price_position', ''):
                score += 2
            elif '震荡整理' in trend.get('price_position', ''):
                score += 1

    # 转换为评级
    rating_percentage = score / max_score * 100

    if rating_percentage >= 80:
        return "⭐⭐⭐⭐⭐ (强烈推荐)"
    elif rating_percentage >= 70:
        return "⭐⭐⭐⭐ (推荐)"
    elif rating_percentage >= 60:
        return "⭐⭐⭐ (谨慎推荐)"
    elif rating_percentage >= 50:
        return "⭐⭐ (中性)"
    else:
        return "⭐ (谨慎)"

def evaluate_dimension(dimension_name, *args):
    """评估各个维度"""
    if dimension_name == 'theme_authenticity':
        pdf_analysis = args[0] if args else None
        if pdf_analysis and '是否正宗' in pdf_analysis:
            if pdf_analysis['是否正宗']['正宗性评估'] == '高度正宗':
                return 5, '优秀', '题材高度正宗，主业突出'
            elif '正宗' in pdf_analysis['是否正宗']['正宗性评估']:
                return 4, '良好', '题材较为正宗'
        return 3, '一般', '题材一般'

    elif dimension_name == 'industry_position':
        pdf_analysis = args[0] if args else None
        if pdf_analysis and '龙头属性' in pdf_analysis:
            if '国内第二' in pdf_analysis['龙头属性']['行业地位']:
                return 4, '良好', '行业第二，细分龙头'
        return 3, '一般', '行业地位一般'

    elif dimension_name == 'capital_attention':
        basic_info = args[0] if len(args) > 0 else None
        amount_billion = basic_info['amount'] / 100000000 if basic_info else 0
        if amount_billion > 20:
            return 5, '优秀', '资金关注度极高'
        elif amount_billion > 10:
            return 4, '良好', '资金关注度高'
        elif amount_billion > 5:
            return 3, '一般', '资金关注度一般'
        else:
            return 2, '较低', '资金关注度较低'

    elif dimension_name == 'technical_pattern':
        tech_analysis = args[0] if args else None
        if tech_analysis and 'assessment' in tech_analysis:
            assessment = tech_analysis['assessment']
            if 'trend' in assessment:
                if '强势上涨' in assessment['trend'].get('price_position', ''):
                    return 4, '良好', '技术形态向好'
                elif '弱势下跌' in assessment['trend'].get('price_position', ''):
                    return 2, '较差', '技术形态偏弱'
        return 3, '一般', '技术形态中性'

    elif dimension_name == 'valuation':
        basic_info = args[0] if args else None
        # 简单估值判断（基于流通比例和成交额）
        circulating_ratio = basic_info['circulating_cap'] / basic_info['market_cap'] * 100 if basic_info['circulating_cap'] and basic_info['market_cap'] else 0
        if circulating_ratio < 30:
            return 3, '一般', '流通盘较小，估值弹性大'
        else:
            return 4, '良好', '流通盘适中，估值合理'

    elif dimension_name == 'risk_control':
        basic_info = args[0] if len(args) > 0 else None
        flag = basic_info['flag'] if basic_info else None
        if flag == -1:
            return 2, '较高', 'flag=-1显示风险较高'
        elif flag in [3, 4]:
            return 3, '中等', '异常资金信号需警惕'
        else:
            return 4, '可控', '风险相对可控'

    return 3, '一般', '待评估'

def main():
    print("🔍 风华高科（000636）综合投资分析报告生成中...")
    print("=" * 80)

    # 1. 加载基本信息
    print("1️⃣ 加载股票基本信息...")
    basic_info = load_stock_basic_info()
    if not basic_info:
        print("❌ 无法加载股票基本信息")
        return

    print(f"   股票: {basic_info['name']} ({basic_info['code']})")
    print(f"   日期: {basic_info['trade_date']}")
    print(f"   收盘价: {basic_info['close']}元, 涨跌幅: {basic_info['pct_chg']}%")

    # 2. PDF框架分析
    print("\n2️⃣ 执行PDF框架分析...")
    pdf_analysis = run_pdf_framework_analysis()
    if pdf_analysis:
        print("   ✅ PDF框架分析完成")
    else:
        print("   ⚠ PDF框架分析失败或部分失败")

    # 3. 技术分析
    print("\n3️⃣ 执行技术分析...")
    tech_analysis = run_technical_analysis()
    if tech_analysis:
        print(f"   ✅ 技术分析完成（{tech_analysis.get('period', '未知')}）")
    else:
        print("   ⚠ 技术分析失败或部分失败")

    # 4. 生成综合报告
    print("\n4️⃣ 生成综合投资分析报告...")
    report = generate_integrated_report(basic_info, pdf_analysis, tech_analysis)

    # 输出报告
    print("\n" + report)

    # 5. 保存报告
    output_file = f"comprehensive_report_000636_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n💾 综合报告已保存至: {output_file}")

if __name__ == "__main__":
    main()