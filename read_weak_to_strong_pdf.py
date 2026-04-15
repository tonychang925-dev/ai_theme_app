#!/usr/bin/env python3
"""
读取弱转强买入法PDF文档
提取关键规则和技术特征，用于优化弱转强策略
"""

import pypdfium2 as pdfium
import re
import sys

def extract_text_from_pdf(pdf_path):
    """从PDF提取文本"""
    pdf = pdfium.PdfDocument(pdf_path)
    full_text = []

    for i in range(len(pdf)):
        page = pdf[i]
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        full_text.append(f"--- 第{i+1}页 ---\n{text}")
        textpage.close()
        page.close()

    pdf.close()
    return "\n".join(full_text)

def analyze_weak_to_strong_rules(text):
    """分析弱转强规则"""
    print("=== 弱转强买入法PDF分析 ===")
    print()

    # 搜索关键概念
    keywords = [
        "弱转强", "分歧回流", "支撑反弹", "放量转强", "资金回流",
        "缺口", "支撑位", "前一日", "下跌", "涨停", "放量",
        "龙头", "板块", "集合竞价", "分时"
    ]

    print("关键词出现频率:")
    for keyword in keywords:
        count = len(re.findall(keyword, text))
        if count > 0:
            print(f"  {keyword}: {count}次")

    print()

    # 提取关键段落
    print("关键段落:")
    lines = text.split('\n')
    key_sections = []

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ["弱转强", "买入法", "策略", "特征"]):
            # 获取上下文
            start = max(0, i-2)
            end = min(len(lines), i+3)
            context = "\n    ".join(lines[start:end])
            key_sections.append(f"第{i+1}行附近:\n    {context}\n")

    for section in key_sections[:10]:  # 显示前10个关键段落
        print(section)

    # 提取具体规则
    print("具体规则提取:")
    rules = []

    # 寻找规则模式
    rule_patterns = [
        r"([一二三四五六七八九十]、[^。]+。)",  # 中文编号规则
        r"(\d+\.\s*[^。]+。)",  # 数字编号规则
        r"(.*[应|要|需|必须].*。)",  # 要求类规则
    ]

    for pattern in rule_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) > 10 and any(keyword in match for keyword in ["弱转强", "分歧", "支撑", "放量"]):
                rules.append(match)

    # 去重并显示
    unique_rules = []
    seen = set()
    for rule in rules:
        if rule not in seen and len(rule) < 200:  # 过滤过长的规则
            unique_rules.append(rule)
            seen.add(rule)

    for i, rule in enumerate(unique_rules[:20], 1):
        print(f"{i}. {rule}")

    return {
        "text": text,
        "keywords": {k: len(re.findall(k, text)) for k in keywords if len(re.findall(k, text)) > 0},
        "key_sections": key_sections[:10],
        "rules": unique_rules[:20]
    }

def extract_technical_patterns(text):
    """提取技术形态特征"""
    print("\n=== 技术形态特征 ===")

    patterns = []

    # K线形态
    kline_patterns = re.findall(r"([^。]*[阴线|阳线|缺口|支撑|压力|涨停|跌停][^。]*。)", text)
    for pattern in kline_patterns[:15]:
        if "弱转强" in pattern or "分歧" in pattern or "支撑" in pattern:
            patterns.append(f"K线形态: {pattern}")

    # 成交量特征
    volume_patterns = re.findall(r"([^。]*[放量|缩量|量比|换手][^。]*。)", text)
    for pattern in volume_patterns[:10]:
        patterns.append(f"成交量: {pattern}")

    # 资金流向
    capital_patterns = re.findall(r"([^。]*[资金|主力|净流入|净流出][^。]*。)", text)
    for pattern in capital_patterns[:10]:
        patterns.append(f"资金流向: {pattern}")

    # 分时特征
    intraday_patterns = re.findall(r"([^。]*[分时|集合竞价|早盘|盘中|尾盘][^。]*。)", text)
    for pattern in intraday_patterns[:10]:
        patterns.append(f"分时: {pattern}")

    # 去重显示
    seen = set()
    for pattern in patterns:
        if pattern not in seen:
            print(f"• {pattern}")
            seen.add(pattern)

    return patterns

def generate_improvement_suggestions(analysis):
    """根据PDF分析生成改进建议"""
    print("\n=== 弱转强策略改进建议 ===")

    suggestions = []

    # 检查当前实现缺少的特征
    current_features = ["分歧回流", "支撑反弹", "放量转强", "资金回流", "缺口支撑"]

    text_lower = analysis["text"].lower()

    for feature in current_features:
        if feature in text_lower:
            # 该特征在PDF中有提及
            suggestions.append(f"✅ {feature}: PDF中有详细描述，当前实现已包含")
        else:
            suggestions.append(f"⚠️  {feature}: 当前实现有，但PDF中未重点提及")

    # 从PDF中提取新特征
    new_features = []

    # 查找可能的新特征
    feature_patterns = [
        r"([^。]*该弱不弱[^。]*。)",  # 核心原则
        r"([^。]*集合竞价[^。]*。)",  # 集合竞价特征
        r"([^。]*分时弱转强[^。]*。)",  # 分时特征
        r"([^。]*龙头股[^。]*。)",  # 龙头股特征
        r"([^。]*板块效应[^。]*。)",  # 板块效应
    ]

    for pattern in feature_patterns:
        matches = re.findall(pattern, analysis["text"])
        for match in matches:
            if len(match) > 5 and "弱转强" in match:
                new_features.append(match)

    if new_features:
        print("\nPDF中提到的新特征:")
        for i, feature in enumerate(new_features[:10], 1):
            print(f"{i}. {feature}")
            suggestions.append(f"📝 新特征: {feature[:50]}...")

    # 生成具体改进点
    print("\n具体改进方向:")
    improvement_areas = [
        "1. 增强缺口支撑检测逻辑",
        "2. 添加集合竞价弱转强识别",
        "3. 完善分时模式分析",
        "4. 加强龙头股和板块效应判断",
        "5. 优化'该弱不弱'核心原则的实现",
        "6. 添加更多技术形态验证",
        "7. 改进成交量分析算法",
        "8. 增强资金流向判断"
    ]

    for area in improvement_areas:
        print(f"• {area}")

    return suggestions

def main():
    """主函数"""
    pdf_path = "docs/architecture/弱转强买入法.pdf"

    print("弱转强买入法PDF分析工具")
    print("=" * 60)

    try:
        # 提取文本
        print("正在读取PDF...")
        text = extract_text_from_pdf(pdf_path)
        print(f"PDF读取成功，共{len(text)}字符")
        print()

        # 分析规则
        analysis = analyze_weak_to_strong_rules(text)

        # 提取技术形态
        technical_patterns = extract_technical_patterns(text)

        # 生成改进建议
        suggestions = generate_improvement_suggestions(analysis)

        print("\n" + "=" * 60)
        print("分析完成!")
        print()

        # 保存分析结果
        with open("weak_to_strong_pdf_analysis.txt", "w", encoding="utf-8") as f:
            f.write("弱转强买入法PDF分析报告\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"PDF路径: {pdf_path}\n")
            f.write(f"文本长度: {len(text)}字符\n\n")

            f.write("关键词统计:\n")
            for keyword, count in analysis["keywords"].items():
                f.write(f"  {keyword}: {count}次\n")

            f.write("\n关键规则:\n")
            for i, rule in enumerate(analysis["rules"], 1):
                f.write(f"{i}. {rule}\n")

            f.write("\n技术形态特征:\n")
            for pattern in technical_patterns[:20]:
                f.write(f"• {pattern}\n")

        print(f"分析结果已保存到: weak_to_strong_pdf_analysis.txt")

    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()