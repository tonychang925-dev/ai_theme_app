#!/usr/bin/env python3
"""
临时脚本：读取PDF文件内容
"""

import argparse
import os
import sys

def read_pdf_content(pdf_path):
    """尝试使用多种方法读取PDF内容"""
    pdf_path = os.path.abspath(pdf_path)
    if not os.path.exists(pdf_path):
        print(f"PDF文件不存在: {pdf_path}")
        return None

    print(f"正在读取PDF: {pdf_path}")
    print(f"文件大小: {os.path.getsize(pdf_path)} bytes")

    # 方法1: 尝试使用pdfplumber
    try:
        import pdfplumber
        print("使用pdfplumber库...")
        content = ""
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    content += f"=== 第{i+1}页 ===\n{text}\n\n"
        if content.strip():
            print(f"成功提取 {len(pdf.pages)} 页内容")
            return content
        else:
            print("pdfplumber未能提取文本")
    except ImportError as e:
        print(f"pdfplumber不可用: {e}")
    except Exception as e:
        print(f"pdfplumber读取失败: {e}")

    # 方法2: 尝试使用PyPDF2
    try:
        import PyPDF2
        print("使用PyPDF2库...")
        content = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for i, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                if text:
                    content += f"=== 第{i+1}页 ===\n{text}\n\n"
        if content.strip():
            print(f"成功提取 {len(pdf_reader.pages)} 页内容")
            return content
        else:
            print("PyPDF2未能提取文本")
    except ImportError as e:
        print(f"PyPDF2不可用: {e}")
    except Exception as e:
        print(f"PyPDF2读取失败: {e}")

    # 方法3: 使用strings命令提取文本
    print("使用strings命令提取文本...")
    try:
        import subprocess
        result = subprocess.run(['strings', pdf_path],
                               capture_output=True, text=True, timeout=10)
        if result.stdout:
            print(f"strings提取到 {len(result.stdout)} 字符")
            # 过滤出中文和有意义的内容
            lines = result.stdout.split('\n')
            chinese_lines = [line for line in lines if any('\u4e00' <= c <= '\u9fff' for c in line)]
            if chinese_lines:
                content = '\n'.join(chinese_lines[:200])  # 取前200行
                return content
    except Exception as e:
        print(f"strings命令失败: {e}")

    return None

def analyze_pdf_content(pdf_content, keywords=None):
    """按关键词分析 PDF 内容"""
    if not pdf_content:
        print("没有PDF内容可分析")
        return

    print("\n" + "="*80)
    print("分析 PDF 关键词线索")
    print("="*80)

    if not keywords:
        keywords = []

    found_sections = []
    lines = pdf_content.split('\n')

    for i, line in enumerate(lines):
        line_lower = line.lower()
        for keyword in keywords:
            if keyword in line:
                # 获取上下文
                start = max(0, i-2)
                end = min(len(lines), i+3)
                context = '\n'.join(lines[start:end])
                found_sections.append((keyword, context))
                break

    if found_sections:
        print(f"找到 {len(found_sections)} 处相关线索:")
        for keyword, context in found_sections[:10]:  # 只显示前10个
            print(f"\n关键词: {keyword}")
            print(f"上下文:\n{context}")
            print("-"*60)
    else:
        print("未找到关键词直接相关线索")

    # 分析PDF整体内容结构
    print("\n" + "="*80)
    print("PDF内容结构分析")
    print("="*80)

    # 检查常见的分析框架
    frameworks = ['五维度', '五个维度', '基本面', '技术面', '资金面', '题材面', '消息面',
                  '龙头股', '强势股', '题材正宗性', '行业地位', '业绩弹性', '估值']

    framework_hits = {}
    for framework in frameworks:
        if framework in pdf_content:
            # 查找框架出现的位置和上下文
            import re
            pattern = re.compile(f'.{{0,50}}{framework}.{{0,50}}', re.DOTALL)
            matches = pattern.findall(pdf_content)
            if matches:
                framework_hits[framework] = matches[:3]  # 取前3个匹配

    if framework_hits:
        print("发现的分析框架:")
        for framework, matches in framework_hits.items():
            print(f"\n{framework}:")
            for match in matches:
                print(f"  - {match.strip()}")
    else:
        print("未识别到标准分析框架")

    # 尝试识别PDF的整体分析逻辑
    print("\n" + "="*80)
    print("尝试提取PDF核心分析逻辑")
    print("="*80)

    # 查找可能的章节标题
    section_patterns = [
        r'第[一二三四五六七八九十\d]+[章章节节]',
        r'\d+\.\s+[^\n]+',
        r'[一二三四五六七八九十]、[^\n]+',
        r'[A-Za-z]\.\s+[^\n]+'
    ]

    sections = []
    for pattern in section_patterns:
        import re
        matches = re.findall(pattern, pdf_content)
        if matches:
            sections.extend(matches)

    if sections:
        print(f"识别到 {len(sections)} 个可能章节:")
        for section in sections[:15]:
            print(f"  - {section}")
    else:
        print("未能识别章节结构")


def build_parser():
    parser = argparse.ArgumentParser(description="临时读取 PDF 文本内容并保存摘录")
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default="/Users/admin/Desktop/ai_theme_app/A股题材&强势股跟踪.pdf",
        help="PDF 文件路径",
    )
    parser.add_argument(
        "--save-txt",
        default="/tmp/pdf_content_temp.txt",
        help="将提取内容前 N 字符保存到指定 txt 文件",
    )
    parser.add_argument(
        "--save-limit",
        type=int,
        default=10000,
        help="保存到 txt 的最大字符数",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="可重复传入的关键词，用于提取上下文",
    )
    return parser

if __name__ == "__main__":
    args = build_parser().parse_args()
    pdf_path = args.pdf_path

    if not os.path.exists(pdf_path):
        pdf_files = [f for f in os.listdir('/Users/admin/Desktop/ai_theme_app/') if f.lower().endswith('.pdf')]
        print(f"未找到指定PDF，当前目录PDF文件: {pdf_files}")
        if pdf_files:
            pdf_path = os.path.join('/Users/admin/Desktop/ai_theme_app/', pdf_files[0])
            print(f"使用第一个PDF文件: {pdf_path}")

    content = read_pdf_content(pdf_path)

    if content:
        temp_file = args.save_txt
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content[:args.save_limit])
        print(f"\nPDF内容已保存到: {temp_file} (前{args.save_limit}字符)")
        print(f"总内容长度: {len(content)} 字符")

        analyze_pdf_content(content, keywords=args.keyword)
    else:
        print("无法读取PDF内容")
