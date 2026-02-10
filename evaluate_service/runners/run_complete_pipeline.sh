#!/bin/bash

echo "🚀 开始完整的增强系统测试管道..."
echo "="*60

# 设置环境
export PYTHONPATH=.:$PYTHONPATH
mkdir -p data/results/{baseline,enhanced,comparison}
mkdir -p logs

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 步骤1：增强系统评估
echo "📊 步骤1: 运行增强系统评估..."
LOG_ENHANCED="logs/enhanced_pipeline_${TIMESTAMP}.log"
python -m scripts.evaluators.enhanced_evaluator_fixed > "${LOG_ENHANCED}" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ 增强系统评估完成"
else
    echo "❌ 增强系统评估失败"
    exit 1
fi

# 步骤2：运行基线系统评估（如果存在）
echo -e "\n📊 步骤2: 运行基线系统评估..."
if [ -f "scripts/evaluators/baseline_evaluator.py" ]; then
    LOG_BASELINE="logs/baseline_pipeline_${TIMESTAMP}.log"
    python -c "
import sys
sys.path.insert(0, '.')
try:
    from scripts.evaluators.baseline_evaluator import BaselineEvaluator
    import asyncio
    
    async def run_baseline():
        evaluator = BaselineEvaluator()
        results = await evaluator.evaluate_batch_processing(evaluator.test_dataset[:20])
        print(f'基线评估完成: {len(results)}个结果')
    
    asyncio.run(run_baseline())
except Exception as e:
    print(f'基线评估失败: {e}')
    import traceback
    traceback.print_exc()
" > "${LOG_BASELINE}" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ 基线系统评估完成"
    else
        echo "⚠️  基线系统评估有问题，但继续执行"
    fi
else
    echo "⚠️  未找到基线评估器，跳过"
fi

# 步骤3：生成对比报告
echo -e "\n📊 步骤3: 生成对比报告..."
cat > /tmp/comparison_script.py << 'PYTHON_SCRIPT'
import json
from pathlib import Path
from datetime import datetime

def load_results(filepath):
    """加载结果文件"""
    path = Path(filepath)
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载 {filepath} 失败: {e}")
    return None

def generate_comparison_report():
    """生成对比报告"""
    print("生成对比报告...")
    
    # 加载结果
    baseline = load_results("data/results/baseline/latest_results.json")
    enhanced = load_results("data/results/enhanced/latest_results.json")
    
    if not enhanced:
        print("❌ 无增强系统结果")
        return
    
    report = {
        "metadata": {
            "report_id": f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "generated_at": datetime.now().isoformat(),
            "purpose": "优化效果对比分析"
        }
    }
    
    if baseline and enhanced:
        # 对比分析
        report["type"] = "baseline_vs_enhanced"
        
        # 提取关键指标
        baseline_metrics = baseline.get('summary', {}).get('key_metrics', {})
        enhanced_metrics = enhanced.get('summary', {}).get('key_metrics', {})
        
        comparisons = {}
        for metric in ['decision_accuracy', 'avg_response_time_ms', 'theme_duplication_rate']:
            if metric in baseline_metrics and metric in enhanced_metrics:
                b_val = baseline_metrics[metric]
                e_val = enhanced_metrics[metric]
                
                if metric == 'avg_response_time_ms':
                    # 响应时间降低百分比
                    improvement = (b_val - e_val) / b_val * 100 if b_val > 0 else 0
                    comparisons[metric] = {
                        "baseline": b_val,
                        "enhanced": e_val,
                        "improvement_percent": round(improvement, 1),
                        "improvement_direction": "降低" if improvement > 0 else "增加"
                    }
                else:
                    # 其他指标提高百分比
                    improvement = (e_val - b_val) / b_val * 100 if b_val > 0 else 0
                    comparisons[metric] = {
                        "baseline": b_val,
                        "enhanced": e_val,
                        "improvement_percent": round(improvement, 1),
                        "improvement_direction": "提高" if improvement > 0 else "降低"
                    }
        
        report["comparisons"] = comparisons
        
        # 计算总体改进
        if comparisons:
            avg_improvement = sum(c["improvement_percent"] for c in comparisons.values()) / len(comparisons)
            report["summary"] = {
                "average_improvement_percent": round(avg_improvement, 1),
                "overall_assessment": "显著改进" if avg_improvement > 10 else "有改进" if avg_improvement > 0 else "需要优化"
            }
    else:
        # 只有增强结果
        report["type"] = "enhanced_only"
        report["enhanced_results"] = enhanced.get('summary', {})
        report["summary"] = {
            "message": "只有增强系统评估结果",
            "recommendation": "建议运行基线评估进行对比"
        }
    
    # 保存报告
    output_dir = Path("data/results/comparison")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 对比报告已保存: {output_path}")
    
    # 打印摘要
    print("\n" + "="*60)
    print("对比报告摘要")
    print("="*60)
    
    if report["type"] == "baseline_vs_enhanced":
        print("基线 vs 增强 对比结果:")
        for metric_name, comp in report.get("comparisons", {}).items():
            metric_display = {
                'decision_accuracy': '决策准确率',
                'avg_response_time_ms': '响应时间(ms)',
                'theme_duplication_rate': '题材重复率'
            }.get(metric_name, metric_name)
            
            print(f"  {metric_display}:")
            print(f"    基线: {comp['baseline']:.3f}")
            print(f"    增强: {comp['enhanced']:.3f}")
            print(f"    改进: {comp['improvement_percent']}% ({comp['improvement_direction']})")
        
        summary = report.get("summary", {})
        print(f"\n  平均改进: {summary.get('average_improvement_percent', 0)}%")
        print(f"  总体评估: {summary.get('overall_assessment', 'N/A')}")
    
    else:
        enhanced_results = report.get("enhanced_results", {})
        print("增强系统独立评估结果:")
        print(f"  综合得分: {enhanced_results.get('overall_score', 0):.3f}")
        print(f"  评估等级: {enhanced_results.get('evaluation_level', 'N/A')}")
        print(f"  建议: {enhanced_results.get('recommendation', 'N/A')}")
    
    print("="*60)

if __name__ == "__main__":
    generate_comparison_report()
PYTHON_SCRIPT

python /tmp/comparison_script.py

# 步骤4：显示最终结果
echo -e "\n🎉 测试管道完成!"
echo "="*60
echo "📁 结果文件:"
echo "  增强评估: data/results/enhanced/latest_results.json"
echo "  对比报告: data/results/comparison/latest_*.json"
echo -e "\n📋 增强系统关键指标:"

python -c "
import json
try:
    with open('data/results/enhanced/latest_results.json', 'r') as f:
        data = json.load(f)
    
    summary = data.get('summary', {})
    metrics = summary.get('key_metrics', {})
    targets = data.get('target_comparison', {})
    
    print(f'  综合得分: {summary.get(\"overall_score\", 0):.3f}/1.0')
    print(f'  评估等级: {summary.get(\"evaluation_level\", \"N/A\")}')
    print()
    print(f'  决策准确率: {metrics.get(\"decision_accuracy\", 0):.1%}')
    print(f'    目标: {targets.get(\"decision_accuracy_target\", 0):.0%}')
    print(f'    达成: {\"✅\" if targets.get(\"meets_accuracy_target\") else \"❌\"}')
    print()
    print(f'  响应时间: {metrics.get(\"avg_response_time_ms\", 0):.0f}ms')
    print(f'    目标: ≤{targets.get(\"response_time_target_ms\", 0)}ms')
    print(f'    达成: {\"✅\" if targets.get(\"meets_response_target\") else \"❌\"}')
    print()
    print(f'  题材重复率: {metrics.get(\"theme_duplication_rate\", 0):.1%}')
    print(f'    目标: ≤{targets.get(\"duplication_rate_target\", 0):.0%}')
    print(f'    达成: {\"✅\" if targets.get(\"meets_duplication_target\") else \"❌\"}')
    
except Exception as e:
    print(f'读取结果失败: {e}')
"

echo "="*60
