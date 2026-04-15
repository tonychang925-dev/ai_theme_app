#!/usr/bin/env python3
"""
测试数据加载模块
用于加载test_cases.txt中的测试数据
"""

import os
import re
from typing import Dict, List


def load_test_cases(file_path: str = None) -> Dict[str, List[str]]:
    """
    加载测试用例数据
    
    Args:
        file_path: 测试数据文件路径，默认为同目录下的test_cases.txt
    
    Returns:
        字典格式的测试数据，键为主题名称，值为新闻列表
    """
    if file_path is None:
        file_path = os.path.join(os.path.dirname(__file__), "test_cases.txt")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"测试数据文件不存在: {file_path}")
    
    test_cases = {}
    current_theme = None
    current_news = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否是新的测试集
            theme_match = re.match(r'测试集\d+:题材名称:(.+)', line)
            if theme_match:
                # 保存前一个主题的数据
                if current_theme and current_news:
                    test_cases[current_theme] = current_news
                
                # 开始新的主题
                current_theme = theme_match.group(1).strip()
                current_news = []
                continue
            
            # 检查是否是新闻项
            if line.startswith('- '):
                news_content = line[2:].strip()
                if news_content:
                    current_news.append(news_content)
            elif current_theme and line:
                # 处理没有"- "前缀的新闻
                current_news.append(line)
    
    # 保存最后一个主题的数据
    if current_theme and current_news:
        test_cases[current_theme] = current_news
    
    return test_cases


def get_theme_names() -> List[str]:
    """
    获取所有主题名称
    
    Returns:
        主题名称列表
    """
    test_cases = load_test_cases()
    return list(test_cases.keys())


def get_news_by_theme(theme_name: str) -> List[str]:
    """
    获取指定主题的新闻
    
    Args:
        theme_name: 主题名称
    
    Returns:
        该主题的新闻列表
    """
    test_cases = load_test_cases()
    return test_cases.get(theme_name, [])


def get_all_news() -> List[str]:
    """
    获取所有新闻
    
    Returns:
        所有新闻的扁平化列表
    """
    test_cases = load_test_cases()
    all_news = []
    for news_list in test_cases.values():
        all_news.extend(news_list)
    return all_news


def get_test_statistics() -> Dict[str, any]:
    """
    获取测试数据统计信息
    
    Returns:
        包含统计信息的字典
    """
    test_cases = load_test_cases()
    
    total_themes = len(test_cases)
    total_news = sum(len(news_list) for news_list in test_cases.values())
    
    # 计算每个主题的新闻数量
    theme_stats = {}
    for theme, news_list in test_cases.items():
        theme_stats[theme] = len(news_list)
    
    # 计算平均新闻长度
    all_news = get_all_news()
    avg_news_length = sum(len(news) for news in all_news) / len(all_news) if all_news else 0
    
    return {
        "total_themes": total_themes,
        "total_news": total_news,
        "theme_statistics": theme_stats,
        "average_news_length": avg_news_length,
        "themes": list(test_cases.keys())
    }


def print_test_summary():
    """打印测试数据摘要"""
    stats = get_test_statistics()
    
    print("测试数据摘要:")
    print(f"总主题数: {stats['total_themes']}")
    print(f"总新闻数: {stats['total_news']}")
    print(f"平均新闻长度: {stats['average_news_length']:.1f} 字符")
    print("\n主题详情:")
    for theme, count in stats['theme_statistics'].items():
        print(f"  - {theme}: {count} 条新闻")


if __name__ == "__main__":
    # 测试模块功能
    print_test_summary()
    
    # 示例用法
    print("\n示例: 获取'AI/AR眼镜'主题的新闻")
    ai_news = get_news_by_theme("AI/AR眼镜")
    for i, news in enumerate(ai_news[:3], 1):
        print(f"  {i}. {news[:50]}...")
