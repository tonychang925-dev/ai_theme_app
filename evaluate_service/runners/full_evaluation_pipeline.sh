#!/bin/bash
# evaluate_service/runners/full_evaluation_pipeline.sh
# AI题材引擎 - 完整评估流水线（一键执行）

set -e  # 遇到错误立即退出

echo "🚀 AI题材引擎 - 完整评估流水线启动"
echo "=========================================="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "工作目录: $(pwd)"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 进度显示函数
step_counter=1
show_step() {
    echo -e "${BLUE}[步骤 ${step_counter}/6]${NC} $1"
    step_counter=$((step_counter + 1))
}

show_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

show_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

show_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 步骤1: 环境检查
show_step "检查环境与目录结构"
if [ ! -d "data" ]; then
    mkdir -p data/{raw,processed,results/{reports,logs}}
    show_success "创建数据目录结构"
fi

if [ ! -d "scripts" ]; then
    mkdir -p scripts
    show_success "创建脚本目录"
fi

# 步骤2: 检查测试数据文件
show_step "检查测试数据文件"
DATA_FILE="data/raw/test_cases.txt"
if [ ! -f "$DATA_FILE" ]; then
    show_error "测试数据文件不存在: $DATA_FILE"
    echo "请将您的10个题材测试数据保存到该文件"
    echo "格式示例:"
    echo "测试集1:"
    echo "题材名称：AI/AR眼镜"
    echo "- **2025年6月20日，**Meta与Oakley合作开发的智能眼镜..."
    exit 1
fi

# 显示文件信息
FILE_SIZE=$(wc -c < "$DATA_FILE")
FILE_LINES=$(wc -l < "$DATA_FILE")
show_success "找到测试数据文件: $DATA_FILE"
echo "  文件大小: ${FILE_SIZE} 字节"
echo "  行数: ${FILE_LINES} 行"

# 显示文件预览
echo -e "${CYAN}📄 文件内容预览（前5行）:${NC}"
echo "----------------------------------------"
head -5 "$DATA_FILE"
echo "----------------------------------------"

# 步骤3: 创建智能解析器
show_step "创建智能数据解析器"
cat > scripts/smart_data_parser.py << 'PYEOF'
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
PYEOF

show_success "智能解析器创建完成"

# 步骤4: 解析测试数据
show_step "解析测试数据"
python3 scripts/smart_data_parser.py
PARSER_RESULT=$?

if [ $PARSER_RESULT -ne 0 ] || [ ! -f "data/processed/validation_dataset.json" ]; then
    show_error "数据解析失败"
    echo "请手动检查文件格式，或分享文件前20行内容以便调试"
    exit 1
fi

# 统计测试用例数量
TEST_COUNT=$(python3 -c "
import json
try:
    with open('data/processed/validation_dataset.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(len(data))
except Exception as e:
    print(f'0 # 错误: {e}')
")

if [ "$TEST_COUNT" -eq "0" ]; then
    show_error "解析器运行但未生成测试用例"
    exit 1
fi

show_success "解析成功: 创建了 ${TEST_COUNT} 个测试用例"

# 步骤5: 运行评估
show_step "运行评估引擎"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="data/results/reports/full_pipeline_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

# 检查评估器是否存在，如果不存在则创建演示评估器
if [ ! -f "scripts/evaluator.py" ]; then
    show_warning "评估器不存在，创建演示版本"
    cat > scripts/evaluator.py << 'EVALEOF'
#!/usr/bin/env python3
"""演示评估器 - 模拟完整评估流程"""
import json
import asyncio
import argparse
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

class DemoEvaluator:
    async def evaluate(self, test_cases: List[Dict]) -> Dict:
        """模拟评估过程"""
        results = []
        correct = 0
        
        for case in test_cases:
            # 模拟AI分析（完美识别）
            discovered = case["ground_truth_themes"]
            
            # 计算指标
            ground_truth = case["ground_truth_themes"]
            precision = 1.0 if discovered else 0.0
            recall = 1.0 if discovered else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            if discovered:
                correct += 1
            
            results.append({
                "test_id": case["test_id"],
                "theme": case["theme"],
                "discovered": discovered,
                "ground_truth": ground_truth,
                "metrics": {
                    "precision": precision,
                    "recall": recall,
                    "f1": f1
                }
            })
        
        # 汇总统计
        theme_metrics = {}
        for case in test_cases:
            theme = case["theme"]
            if theme not in theme_metrics:
                theme_metrics[theme] = {
                    "test_count": 0,
                    "correct_count": 0,
                    "precision_sum": 0,
                    "recall_sum": 0
                }
            theme_metrics[theme]["test_count"] += 1
        
        for result in results:
            theme = result["theme"]
            theme_metrics[theme]["correct_count"] += 1
            theme_metrics[theme]["precision_sum"] += result["metrics"]["precision"]
            theme_metrics[theme]["recall_sum"] += result["metrics"]["recall"]
        
        # 计算各题材指标
        for theme, metrics in theme_metrics.items():
            metrics["precision"] = metrics["precision_sum"] / metrics["test_count"] if metrics["test_count"] > 0 else 0
            metrics["recall"] = metrics["recall_sum"] / metrics["test_count"] if metrics["test_count"] > 0 else 0
            metrics["f1"] = 2 * metrics["precision"] * metrics["recall"] / (metrics["precision"] + metrics["recall"]) if (metrics["precision"] + metrics["recall"]) > 0 else 0
            del metrics["precision_sum"]
            del metrics["recall_sum"]
        
        overall_precision = correct / len(test_cases) if test_cases else 0
        overall_recall = overall_precision
        overall_f1 = overall_precision
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(test_cases),
            "successful_cases": correct,
            "overall_precision": overall_precision,
            "overall_recall": overall_recall,
            "overall_f1": overall_f1,
            "theme_wise_metrics": theme_metrics,
            "results": results
        }

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_path', required=True)
    parser.add_argument('--output_dir', required=True)
    args = parser.parse_args()
    
    # 加载测试数据
    with open(args.data_path, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
    
    # 运行评估
    evaluator = DemoEvaluator()
    metrics = await evaluator.evaluate(test_cases)
    
    # 保存结果
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    metrics_file = output_path / "metrics.json"
    with open(metrics_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 评估完成! 结果保存至: {metrics_file}")
    
    # 生成摘要报告
    summary = f"""
评估报告摘要
============
评估时间: {metrics['timestamp']}
测试用例总数: {metrics['total_cases']}
整体F1分数: {metrics['overall_f1']:.3f}
整体准确率: {metrics['overall_precision']:.3f}
整体召回率: {metrics['overall_recall']:.3f}

各题材表现:
"""
    
    for theme, theme_metrics in metrics['theme_wise_metrics'].items():
        summary += f"  {theme}: F1={theme_metrics['f1']:.3f}, 准确率={theme_metrics['precision']:.3f}, 召回率={theme_metrics['recall']:.3f}\n"
    
    summary_file = output_path / "summary.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary)
    
    print(summary)
    
    return 0

if __name__ == '__main__':
    asyncio.run(main())
EVALEOF
    chmod +x scripts/evaluator.py
fi

# 运行评估
echo "  运行评估器..."
python3 scripts/evaluator.py \
    --data_path "data/processed/validation_dataset.json" \
    --output_dir "$OUTPUT_DIR"

if [ $? -eq 0 ] && [ -f "$OUTPUT_DIR/metrics.json" ]; then
    show_success "评估完成，结果保存在: $OUTPUT_DIR/"
else
    show_warning "评估器运行但可能未生成完整结果"
fi

# 步骤6: 生成HTML报告
show_step "生成可视化报告"
if [ ! -f "scripts/report_generator.py" ]; then
    # 创建简单的报告生成器
    cat > scripts/report_generator.py << 'REPORTEOF'
#!/usr/bin/env python3
"""简单报告生成器"""
import json
from pathlib import Path
import sys

def generate_html_report(metrics_file, output_file):
    with open(metrics_file, 'r', encoding='utf-8') as f:
        metrics = json.load(f)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AI题材引擎评估报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; }}
        .metric {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-left: 4px solid #3498db; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .good {{ color: #27ae60; }} .medium {{ color: #f39c12; }} .poor {{ color: #e74c3c; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 AI题材引擎评估报告</h1>
        <p>生成时间: {metrics.get('timestamp', '未知')}</p>
    </div>
    
    <div class="metric">
        <h2>📈 总体指标</h2>
        <p>测试用例总数: {metrics.get('total_cases', 0)}</p>
        <p>整体F1分数: <span class="{get_score_class(metrics.get('overall_f1', 0))}">{metrics.get('overall_f1', 0):.3f}</span></p>
        <p>整体准确率: {metrics.get('overall_precision', 0):.3f}</p>
        <p>整体召回率: {metrics.get('overall_recall', 0):.3f}</p>
    </div>
    
    <div class="metric">
        <h2>🎯 各题材表现</h2>
        <table>
            <tr><th>题材</th><th>测试数</th><th>F1分数</th><th>准确率</th><th>召回率</th></tr>"""
    
    for theme, theme_metrics in metrics.get('theme_wise_metrics', {}).items():
        f1 = theme_metrics.get('f1', 0)
        html += f"""
            <tr>
                <td>{theme}</td>
                <td>{theme_metrics.get('test_count', 0)}</td>
                <td class="{get_score_class(f1)}">{f1:.3f}</td>
                <td>{theme_metrics.get('precision', 0):.3f}</td>
                <td>{theme_metrics.get('recall', 0):.3f}</td>
            </tr>"""
    
    html += """
        </table>
    </div>
</body>
</html>"""
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML报告已生成: {output_file}")

def get_score_class(score):
    if score >= 0.7: return "good"
    elif score >= 0.4: return "medium"
    else: return "poor"

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("用法: python3 report_generator.py <metrics.json> <output.html>")
        sys.exit(1)
    
    metrics_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])
    
    if not metrics_file.exists():
        print(f"错误: 指标文件不存在 {metrics_file}")
        sys.exit(1)
    
    generate_html_report(metrics_file, output_file)
REPORTEOF
    chmod +x scripts/report_generator.py
fi

# 生成HTML报告
if [ -f "$OUTPUT_DIR/metrics.json" ]; then
    python3 scripts/report_generator.py \
        "$OUTPUT_DIR/metrics.json" \
        "$OUTPUT_DIR/report.html"
    show_success "HTML报告已生成"
else
    show_warning "未找到评估结果，跳过报告生成"
fi

# 最终输出
echo ""
echo "=========================================="
echo -e "${GREEN}🚀 完整评估流水线执行完成!${NC}"
echo "=========================================="
echo ""
echo "📊 执行摘要:"
echo "  测试数据: ${FILE_LINES} 行 → ${TEST_COUNT} 个测试用例"
echo "  输出目录: ${OUTPUT_DIR}"
echo ""
echo "📁 生成的文件:"
find "$OUTPUT_DIR" -type f -name "*.*" | while read file; do
    file_size=$(wc -c < "$file" 2>/dev/null || echo "?")
    echo "  • $(basename "$file") (${file_size} 字节)"
done
echo ""
echo "🔍 查看报告:"
echo "  cat $OUTPUT_DIR/summary.txt"
echo "  或在浏览器中打开: $OUTPUT_DIR/report.html"
echo ""
echo "🎯 下一步建议:"
echo "  1. 检查解析结果: data/processed/validation_dataset.json"
echo "  2. 连接真实AI引擎替换演示评估器"
echo "  3. 根据评估结果优化算法参数"
echo ""
echo "💡 快速验证:"
echo "  # 查看前3个测试用例"
echo "  python3 -m json.tool data/processed/validation_dataset.json | head -100"
echo ""