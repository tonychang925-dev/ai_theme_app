#!/usr/bin/env python3
"""
智能测试数据解析器 - 支持多种格式
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SmartDataParser:
    def __init__(self):
        self.theme_keywords = {
            "眼镜": "AI/AR眼镜",
            "AR": "AI/AR眼镜",
            "SpaceX": "SpaceX",
            "核聚变": "可控核聚变",
            "聚变": "可控核聚变",
            "制裁": "对日制裁",
            "稀土": "稀土永磁",
            "海洋": "海洋经济",
            "光刻胶": "光刻胶",
            "卫星": "卫星互联",
            "液冷": "液冷数据中心",
            "Manus": "AI智能体Manus",
            "智能体": "AI智能体Manus"
        }
    
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """解析测试数据文件"""
        if not file_path.exists():
            logger.error(f"文件不存在: {file_path}")
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"读取文件: {file_path} (共 {len(content)} 字符)")
        
        # 尝试多种解析策略
        test_cases = []
        
        # 策略1: 标准格式解析
        test_cases = self._parse_standard_format(content)
        if test_cases:
            logger.info(f"策略1成功: 找到 {len(test_cases)} 个测试用例")
            return test_cases
        
        # 策略2: 简单格式解析
        test_cases = self._parse_simple_format(content)
        if test_cases:
            logger.info(f"策略2成功: 找到 {len(test_cases)} 个测试用例")
            return test_cases
        
        # 策略3: 自由文本解析
        test_cases = self._parse_free_text(content)
        if test_cases:
            logger.info(f"策略3成功: 找到 {len(test_cases)} 个测试用例")
            return test_cases
        
        logger.warning("所有解析策略都失败")
        return []
    
    def _parse_standard_format(self, content: str) -> List[Dict[str, Any]]:
        """解析标准格式: 测试集 + 题材名称 + 新闻列表"""
        test_cases = []
        
        # 查找所有测试集
        test_set_pattern = r'测试集\d+:(.*?)(?=测试集\d+:|$)'
        test_sets = re.findall(test_set_pattern, content, re.DOTALL)
        
        for set_index, test_set in enumerate(test_sets, 1):
            # 提取题材名称
            theme_match = re.search(r'题材名称[：:]\s*(.+)', test_set)
            if not theme_match:
                continue
            
            theme_name = theme_match.group(1).strip()
            logger.info(f"测试集{set_index}: 题材 '{theme_name}'")
            
            # 提取新闻项
            news_items = []
            lines = test_set.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or '题材名称' in line:
                    continue
                
                # 识别新闻行（以 - • * 开头或包含日期）
                if line.startswith('-') or line.startswith('•') or line.startswith('*') or re.search(r'\d{4}年\d{1,2}月\d{1,2}日', line):
                    # 清理格式标记
                    clean_line = re.sub(r'^[-•*]\s*\*{0,2}', '', line)
                    clean_line = re.sub(r'\*{2}(.+?)\*{2}', r'\1', clean_line)
                    clean_line = clean_line.strip()
                    
                    if clean_line and len(clean_line) > 10:  # 过滤太短的行
                        news_items.append(clean_line)
            
            # 为每个新闻项创建测试用例
            for i, news in enumerate(news_items[:10]):  # 每个题材最多10条
                test_case = self._create_test_case(theme_name, news, i+1)
                test_cases.append(test_case)
        
        return test_cases
    
    def _parse_simple_format(self, content: str) -> List[Dict[str, Any]]:
        """解析简单格式: 题材: 内容"""
        test_cases = []
        lines = content.split('\n')
        current_theme = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测题材行
            theme_match = re.match(r'^(?:题材[：:]|)(.+?)[：:]\s*$', line)
            if theme_match:
                current_theme = theme_match.group(1).strip()
                logger.info(f"发现题材: {current_theme}")
                continue
            
            # 如果是新闻行且有当前题材
            if current_theme and (line.startswith('-') or re.search(r'\d{4}年', line)):
                test_case = self._create_test_case(current_theme, line, len(test_cases)+1)
                test_cases.append(test_case)
        
        return test_cases
    
    def _parse_free_text(self, content: str) -> List[Dict[str, Any]]:
        """解析自由文本: 自动识别题材"""
        test_cases = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or len(line) < 20:
                continue
            
            # 尝试识别题材
            detected_theme = None
            
            # 1. 从关键词识别
            for keyword, theme in self.theme_keywords.items():
                if keyword in line:
                    detected_theme = theme
                    break
            
            # 2. 从已知题材列表识别
            known_themes = list(self.theme_keywords.values())
            for theme in known_themes:
                if theme in line:
                    detected_theme = theme
                    break
            
            if detected_theme:
                test_case = self._create_test_case(detected_theme, line, len(test_cases)+1)
                test_cases.append(test_case)
        
        return test_cases
    
    def _create_test_case(self, theme: str, content: str, index: int) -> Dict[str, Any]:
        """创建标准测试用例"""
        # 提取日期
        date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', content)
        date_str = date_match.group(1) if date_match else "2025-01-01"
        
        # 清理内容
        clean_content = re.sub(r'^\d{4}年\d{1,2}月\d{1,2}日[，,]\s*', '', content)
        clean_content = re.sub(r'^[-•*]\s*', '', clean_content).strip()
        
        # 确定影响行业
        industry_map = {
            "AI/AR眼镜": ["消费电子", "人工智能"],
            "SpaceX": ["商业航天", "国防"],
            "可控核聚变": ["新能源", "高端装备"],
            "对日制裁": ["国际贸易", "稀土"],
            "稀土永磁": ["稀土", "磁性材料"],
            "海洋经济": ["海洋工程", "航运"],
            "光刻胶": ["半导体", "化学材料"],
            "卫星互联": ["卫星通信", "物联网"],
            "液冷数据中心": ["数据中心", "散热技术"],
            "AI智能体Manus": ["人工智能", "软件"]
        }
        
        return {
            "test_id": f"{theme.replace('/', '_')}_{index:03d}",
            "theme": theme,
            "title": f"{theme}相关新闻",
            "content": clean_content,
            "date": date_str,
            "ground_truth_themes": [theme],
            "impact_industries": industry_map.get(theme, ["科技", "制造业"]),
            "event_type": "行业新闻",
            "source_line": content[:100] + "..." if len(content) > 100 else content
        }

def main():
    parser = SmartDataParser()
    
    # 输入输出文件
    input_file = Path("data/raw/test_cases.txt")
    output_file = Path("data/processed/validation_dataset.json")
    
    # 解析数据
    test_cases = parser.parse_file(input_file)
    
    if not test_cases:
        print("❌ 未能解析出任何测试用例")
        print("请检查文件格式，确保包含'测试集'、'题材名称'等关键词")
        return 1
    
    # 保存结果
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)
    
    # 统计信息
    themes_count = {}
    for case in test_cases:
        theme = case["theme"]
        themes_count[theme] = themes_count.get(theme, 0) + 1
    
    print(f"\n✅ 解析完成!")
    print(f"   创建了 {len(test_cases)} 个测试用例")
    print(f"   覆盖 {len(themes_count)} 个题材")
    print(f"\n📊 题材分布:")
    for theme, count in sorted(themes_count.items()):
        print(f"   • {theme}: {count} 条")
    
    print(f"\n📁 输出文件: {output_file}")
    
    # 显示样本
    if test_cases:
        print(f"\n📋 样本数据:")
        sample = test_cases[0]
        print(f"   主题: {sample['theme']}")
        print(f"   内容: {sample['content'][:80]}...")
        print(f"   标准答案: {sample['ground_truth_themes']}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
