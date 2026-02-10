#!/usr/bin/env python3
import json, re, argparse, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_test_data(raw_text):
    test_cases = []
    lines = raw_text.strip().split('\n')
    current_theme = None
    current_items = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if re.match(r'^测试集\d+:\s*$', line):
            if current_theme and current_items:
                test_cases.extend(create_cases(current_theme, current_items))
                current_items = []
            continue
            
        theme_match = re.match(r'^题材名称[：:]\s*(.+)$', line)
        if theme_match:
            current_theme = theme_match.group(1).strip()
            logger.info(f"发现题材: {current_theme}")
            continue
            
        if line.startswith('-') or line.startswith('•'):
            clean_line = re.sub(r'\*\*|\*', '', line.lstrip('-• ')).strip()
            if clean_line: current_items.append(clean_line)
    
    if current_theme and current_items:
        test_cases.extend(create_cases(current_theme, current_items))
    
    return test_cases

def create_cases(theme_name, news_items):
    test_cases = []
    for i, news in enumerate(news_items[:5]):
        test_cases.append({
            "test_id": f"{theme_name}_{i+1:03d}",
            "theme": theme_name,
            "title": f"{theme_name}相关新闻{i+1}",
            "content": re.sub(r'^(\d{4}年\d{1,2}月\d{1,2}日[，,]\s*)', '', news),
            "ground_truth_themes": [theme_name],
            "impact_industries": ["科技", "制造业"]
        })
    return test_cases

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data/raw/test_cases.txt')
    parser.add_argument('--output', default='data/processed/validation_dataset.json')
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"请先创建测试数据: {input_path}")
        exit(1)
    
    with open(input_path, 'r', encoding='utf-8') as f:
        test_cases = parse_test_data(f.read())
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 数据格式化完成: {len(test_cases)} 个测试用例")
