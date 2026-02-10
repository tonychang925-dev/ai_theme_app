#!/bin/bash
# 一键设置评估环境
set -e

echo "🚀 设置AI题材引擎评估环境"
echo "========================================"

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "工作目录: $BASE_DIR"

# 1. 创建目录结构
echo "1. 创建目录结构..."
mkdir -p "$BASE_DIR"/{data/{raw,processed,results/{reports,logs}},scripts,config,runners}

# 2. 创建核心脚本
echo "2. 创建核心脚本..."

# data_formatter.py
cat > "$BASE_DIR/scripts/data_formatter.py" << 'PYEOF'
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
PYEOF

# report_generator.py
cat > "$BASE_DIR/scripts/report_generator.py" << 'PYEOF2'
#!/usr/bin/env python3
import json, argparse
from pathlib import Path

def generate_html_report(metrics, output_path):
    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>AI题材引擎评估报告</title>
<style>
body {{ font-family: Arial; margin: 40px; }}
.header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; }}
.metric-card {{ background: #f8f9fa; padding: 15px; margin: 15px 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
.good {{ color: #27ae60; }} .medium {{ color: #f39c12; }} .poor {{ color: #e74c3c; }}
</style></head>
<body>
<div class="header"><h1>📊 AI题材引擎评估报告</h1></div>
<div class="metric-card"><h2>📈 总体指标</h2>
<p>测试用例数: {metrics.get('total_cases', 0)}</p>
</div>
<div class="metric-card"><h2>🎯 各题材表现</h2><table>
<tr><th>题材</th><th>测试用例数</th></tr>"""
    
    for theme, scores in metrics.get('theme_wise_metrics', {}).items():
        html += f"<tr><td>{theme}</td><td>{scores.get('test_count', 0)}</td></tr>"
    
    html += """</table></div></body></html>"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ HTML报告已生成: {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--result_file', required=True)
    parser.add_argument('--output_file', default='report.html')
    args = parser.parse_args()
    
    result_path = Path(args.result_file)
    if result_path.exists():
        with open(result_path, 'r', encoding='utf-8') as f:
            metrics = json.load(f)
        generate_html_report(metrics, Path(args.output_file))
    else:
        print(f"创建示例报告...")
        generate_html_report({'total_cases': 10, 'theme_wise_metrics': {}}, Path(args.output_file))
PYEOF2

# 3. 创建简化的评估器（用于演示）
echo "3. 创建演示评估器..."
cat > "$BASE_DIR/scripts/evaluator.py" << 'PYEOF3'
#!/usr/bin/env python3
import json, asyncio, argparse
from pathlib import Path

class MockEvaluator:
    async def evaluate_dataset(self, data_path):
        with open(data_path, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
        
        results = []
        for case in test_cases[:3]:  # 只测试前3个
            results.append({
                "test_id": case["test_id"],
                "discovered": [case["theme"]],  # 模拟完美识别
                "ground_truth": case["ground_truth_themes"],
                "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0}
            })
        
        return {
            "total_cases": len(test_cases),
            "evaluated_cases": len(results),
            "overall_precision": 1.0,
            "overall_recall": 1.0,
            "overall_f1": 1.0,
            "results": results
        }

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_path', default='data/processed/validation_dataset.json')
    parser.add_argument('--output_dir', default='data/results/reports/demo')
    args = parser.parse_args()
    
    evaluator = MockEvaluator()
    results = await evaluator.evaluate_dataset(args.data_path)
    
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    with open(output_path / 'metrics.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 演示评估完成! 结果保存至: {output_path}/metrics.json")
    
    # 生成报告
    import sys
    sys.path.append(str(Path(__file__).parent))
    from report_generator import generate_html_report
    generate_html_report(results, output_path / 'report.html')

if __name__ == '__main__':
    asyncio.run(main())
PYEOF3

# 4. 创建批处理脚本
echo "4. 创建批处理运行器..."

# run_baseline.sh (更新版)
cat > "$BASE_DIR/runners/run_baseline.sh" << 'BASELINE'
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "🔬 AI题材引擎 - 基线评估"
echo "================================"

# 检查数据
if [ ! -f "data/raw/test_cases.txt" ]; then
    echo "❌ 测试数据不存在: data/raw/test_cases.txt"
    echo "请先运行 ./runners/setup_data.sh 准备数据"
    exit 1
fi

# 1. 格式化数据
echo "1. 格式化测试数据..."
python3 scripts/data_formatter.py \
    --input "data/raw/test_cases.txt" \
    --output "data/processed/validation_dataset.json"

# 2. 运行评估
echo "2. 运行演示评估..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/results/reports/baseline_${TIMESTAMP}"
python3 scripts/evaluator.py \
    --data_path "data/processed/validation_dataset.json" \
    --output_dir "$OUTPUT_DIR"

# 3. 生成报告
echo "3. 生成评估报告..."
python3 scripts/report_generator.py \
    --result_file "$OUTPUT_DIR/metrics.json" \
    --output_file "$OUTPUT_DIR/report.html"

echo ""
echo "📊 评估完成!"
echo "   报告文件: $(pwd)/$OUTPUT_DIR/report.html"
echo "   数据文件: $(pwd)/$OUTPUT_DIR/metrics.json"
echo ""
echo "🚀 下一步: 连接真实AI引擎进行完整评估"
BASELINE

# setup_data.sh - 数据准备脚本
cat > "$BASE_DIR/runners/setup_data.sh" << 'SETUPDATA'
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "📝 准备测试数据"
echo "================================"

DATA_FILE="data/raw/test_cases.txt"
if [ -f "$DATA_FILE" ]; then
    echo "✅ 测试数据已存在: $DATA_FILE"
    echo "   行数: $(wc -l < "$DATA_FILE")"
    echo "   如需重新准备，请先删除此文件"
    exit 0
fi

echo "创建示例测试数据..."
cat > "$DATA_FILE" << 'DATAEOF'
测试集1:
题材名称：AI/AR眼镜
- **2025年6月20日，**Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会。
- **2025年6月17日，**Meta联手Oakley推出智能眼镜，为运动设计挑战运动相机。

测试集2:
题材名称：SpaceX
- **2025年12月25日，**据报道，白宫考虑将部分联邦野生动物保护用地划拨给SpaceX用于扩建火箭发射与生产基地。
- **2025年12月25日，**据美国《空天部队》杂志网站12月19日报道，美国太空军下属的太空发展局当天宣布...

测试集3:
题材名称：可控核聚变
- 中国科学院合肥物质科学研究院等离子体物理研究所科研团队宣布，有"人造太阳"之称的全超导托卡马克核聚变实验装置（EAST）实验证实托卡马克密度自由区的存在。
DATAEOF

echo "✅ 示例数据已创建: $DATA_FILE"
echo "请将您的完整测试数据(10个题材)添加到此文件中"
echo "当前内容预览:"
head -20 "$DATA_FILE"
SETUPDATA

# 5. 设置权限
echo "5. 设置脚本权限..."
chmod +x "$BASE_DIR"/scripts/*.py
chmod +x "$BASE_DIR"/runners/*.sh

echo ""
echo "✅ 评估环境设置完成!"
echo ""
echo "📋 可用命令:"
echo "   ./runners/setup_data.sh      # 准备测试数据"
echo "   ./runners/run_baseline.sh    # 运行基线评估"
echo ""
echo "🚀 快速开始:"
echo "   1. 将您的10个题材数据添加到 data/raw/test_cases.txt"
echo "   2. 运行 ./runners/run_baseline.sh"
echo ""
