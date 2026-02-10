#!/usr/bin/env python3
"""
对比分析脚本 - 比较优化前后系统性能
"""
import os
import sys
import json
import pandas as pd
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(current_dir))

def load_latest_results():
    """加载最新的测试结果"""
    results_dir = os.path.join(current_dir, '..', 'data', 'results', 'integrated_evaluation')
    
    if not os.path.exists(results_dir):
        print(f"❌ 结果目录不存在: {results_dir}")
        return None
    
    # 找到最新的结果文件
    json_files = [f for f in os.listdir(results_dir) if f.endswith('.json') and 'evaluation_report' in f]
    if not json_files:
        print(f"❌ 未找到评估报告文件")
        return None
    
    latest_file = max(json_files, key=lambda x: os.path.getctime(os.path.join(results_dir, x)))
    report_path = os.path.join(results_dir, latest_file)
    
    with open(report_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_baseline_results():
    """加载基线结果"""
    baseline_path = os.path.join(current_dir, '..', 'data', 'results', 'clustering_evaluation_results', 
                                'clustering_report_20260107_192548.json')
    
    if not os.path.exists(baseline_path):
        print(f"❌ 基线结果文件不存在: {baseline_path}")
        return None
    
    with open(baseline_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_comparison_report(optimized_report, baseline_report):
    """生成对比报告"""
    print("\n" + "="*80)
    print("📊 AI题材系统优化前后对比报告")
    print("="*80)
    
    # 提取关键指标
    opt_metrics = optimized_report['performance_metrics']
    baseline_summary = baseline_report.get('summary', {})
    
    # 创建对比表格
    comparison_data = []
    
    # 1. 主题数量对比
    comparison_data.append({
        '指标': '主题数量',
        '优化后系统': opt_metrics.get('unique_themes_count', 0),
        '基线系统': len(baseline_report.get('theme_performance', {})),
        'Ground Truth': optimized_report['comparative_analysis']['ground_truth'].get('unique_themes', 10),
        '单位': '个',
        '改进': calculate_improvement(
            opt_metrics.get('unique_themes_count', 0),
            len(baseline_report.get('theme_performance', {})),
            optimized_report['comparative_analysis']['ground_truth'].get('unique_themes', 10)
        )
    })
    
    # 2. 成功率/综合得分对比
    comparison_data.append({
        '指标': '成功率/综合得分',
        '优化后系统': f"{opt_metrics.get('success_rate', 0)*100:.1f}%",
        '基线系统': f"{baseline_summary.get('comprehensive_score', 0)*100:.1f}%",
        'Ground Truth': '100.0%',
        '单位': '百分比',
        '改进': calculate_score_improvement(
            opt_metrics.get('success_rate', 0),
            baseline_summary.get('comprehensive_score', 0)
        )
    })
    
    # 3. 聚类精度对比
    comparison_data.append({
        '指标': '聚类精度',
        '优化后系统': '待计算',
        '基线系统': f"{baseline_summary.get('clustering_accuracy', 0)*100:.1f}%",
        'Ground Truth': '100.0%',
        '单位': '百分比',
        '改进': '需要详细分析'
    })
    
    # 4. 处理事件数对比
    comparison_data.append({
        '指标': '处理事件数',
        '优化后系统': opt_metrics.get('total_events', 0),
        '基线系统': baseline_summary.get('total_events', 0),
        'Ground Truth': optimized_report['comparative_analysis']['ground_truth'].get('total_events', 76),
        '单位': '个',
        '改进': '数据完整性验证'
    })
    
    # 转换为DataFrame并显示
    df = pd.DataFrame(comparison_data)
    print("\n📈 关键指标对比:")
    print(df.to_string(index=False))
    
    # 生成改进总结
    generate_improvement_summary(optimized_report, baseline_report, df)

def calculate_improvement(optimized, baseline, ground_truth):
    """计算改进程度"""
    if baseline == 0:
        return "N/A"
    
    # 计算与ground truth的距离
    opt_distance = abs(optimized - ground_truth)
    baseline_distance = abs(baseline - ground_truth)
    
    if opt_distance < baseline_distance:
        improvement = ((baseline_distance - opt_distance) / baseline_distance) * 100
        return f"改进 {improvement:.1f}%"
    else:
        degradation = ((opt_distance - baseline_distance) / baseline_distance) * 100
        return f"退步 {degradation:.1f}%"

def calculate_score_improvement(optimized_score, baseline_score):
    """计算得分改进"""
    if baseline_score == 0:
        return "N/A"
    
    improvement = ((optimized_score - baseline_score) / baseline_score) * 100
    if improvement > 0:
        return f"提升 {improvement:.1f}%"
    else:
        return f"下降 {abs(improvement):.1f}%"

def generate_improvement_summary(optimized_report, baseline_report, comparison_df):
    """生成改进总结"""
    print("\n" + "="*80)
    print("🎯 优化效果总结")
    print("="*80)
    
    # 提取关键信息
    opt_themes = optimized_report['performance_metrics'].get('unique_themes_count', 0)
    baseline_themes = len(baseline_report.get('theme_performance', {}))
    gt_themes = optimized_report['comparative_analysis']['ground_truth'].get('unique_themes', 10)
    
    opt_success = optimized_report['performance_metrics'].get('success_rate', 0)
    baseline_score = baseline_report.get('summary', {}).get('comprehensive_score', 0)
    
    # 分析主题数量收敛
    print("\n📊 主题数量收敛分析:")
    print(f"   Ground Truth主题数: {gt_themes}")
    print(f"   基线系统主题数: {baseline_themes} (偏差: {abs(baseline_themes - gt_themes)})")
    print(f"   优化后主题数: {opt_themes} (偏差: {abs(opt_themes - gt_themes)})")
    
    if abs(opt_themes - gt_themes) < abs(baseline_themes - gt_themes):
        improvement = ((abs(baseline_themes - gt_themes) - abs(opt_themes - gt_themes)) / abs(baseline_themes - gt_themes)) * 100
        print(f"   ✅ 主题收敛度改进: {improvement:.1f}%")
    else:
        print(f"   ⚠️  主题收敛度需要进一步优化")
    
    # 分析成功率改进
    print(f"\n📈 成功率/综合得分分析:")
    print(f"   基线系统得分: {baseline_score*100:.1f}%")
    print(f"   优化后成功率: {opt_success*100:.1f}%")
    
    if opt_success > baseline_score:
        improvement = ((opt_success - baseline_score) / baseline_score) * 100
        print(f"   ✅ 成功率提升: {improvement:.1f}%")
    else:
        print(f"   ⚠️  成功率需要进一步优化")
    
    # 列出主要改进点
    print(f"\n🔧 主要架构改进:")
    print("   1. ✅ 从批量聚类改为实时AI相似性分析")
    print("   2. ✅ 引入上下文感知的二次决策机制")
    print("   3. ✅ 实现重复主题自动处理")
    print("   4. ✅ 增强错误处理和事务安全性")
    
    # 生成建议
    print(f"\n💡 后续优化建议:")
    for rec in optimized_report['recommendations'][:3]:
        print(f"   • [{rec['priority']}优先级] {rec['recommendation']}")

def main():
    """主函数"""
    print("🔍 加载测试结果进行对比分析...")
    
    # 加载优化后结果
    optimized_report = load_latest_results()
    if not optimized_report:
        return
    
    # 加载基线结果
    baseline_report = load_baseline_results()
    if not baseline_report:
        return
    
    # 生成对比报告
    generate_comparison_report(optimized_report, baseline_report)
    
    print("\n" + "="*80)
    print("📄 详细报告位置:")
    print(f"   优化后系统报告: {optimized_report['files_generated']['raw_results']}")
    print(f"   基线系统报告: evaluate_service/data/results/clustering_evaluation_results/clustering_report_20260107_192548.json")
    print("="*80)

if __name__ == "__main__":
    main()
