#!/usr/bin/env python3
"""
性能分析工具 - 分析优化后系统的性能
"""
import json
import os
import pandas as pd
from datetime import datetime

def analyze_latest_test():
    """分析最新的测试结果"""
    print("\n" + "="*80)
    print("🔍 AI题材系统性能分析")
    print("="*80)
    
    # 找到最新的测试结果
    results_dir = 'evaluate_service/data/results/integrated_evaluation'
    
    if not os.path.exists(results_dir):
        print(f"❌ 结果目录不存在: {results_dir}")
        return
    
    # 找到最新的评估报告
    json_files = [f for f in os.listdir(results_dir) if f.endswith('.json') and 'evaluation_report' in f]
    if not json_files:
        print(f"❌ 未找到评估报告")
        
        # 尝试找quick test结果
        quick_dir = 'evaluate_service/data/results/quick_tests'
        if os.path.exists(quick_dir):
            quick_files = [f for f in os.listdir(quick_dir) if f.endswith('.json')]
            if quick_files:
                latest_quick = max(quick_files, key=lambda x: os.path.getctime(os.path.join(quick_dir, x)))
                print(f"📁 找到快速测试结果: {latest_quick}")
                analyze_quick_test(os.path.join(quick_dir, latest_quick))
        return
    
    latest_file = max(json_files, key=lambda x: os.path.getctime(os.path.join(results_dir, x)))
    report_path = os.path.join(results_dir, latest_file)
    
    print(f"📄 分析报告: {latest_file}")
    
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # 提取关键指标
    metrics = report['performance_metrics']
    summary = report['executive_summary']
    
    print(f"\n📊 性能指标:")
    print(f"   处理事件总数: {metrics.get('total_events', 0)}")
    print(f"   成功率: {summary['success_rate_percentage']}")
    print(f"   独特主题数: {summary['unique_themes_generated']}")
    print(f"   平均处理时间: {summary['average_processing_time']}")
    print(f"   评估等级: {summary['assessment_grade']} {summary['grade_emoji']}")
    
    # 主题分布分析
    print(f"\n🏷️ 主题分布分析:")
    theme_stats = report.get('theme_analysis', [])
    if theme_stats:
        print(f"   生成主题数量: {len(theme_stats)}")
        print(f"   前5大主题:")
        for i, theme in enumerate(theme_stats[:5], 1):
            print(f"     {i}. {theme['theme_name']}: {theme['event_count']} 个事件 ({theme['percentage']:.1f}%)")
    
    # 与基线对比
    print(f"\n📈 与基线系统对比:")
    comp = report['comparative_analysis']
    
    if comp.get('baseline_system'):
        baseline = comp['baseline_system']
        optimized = comp['optimized_system']
        
        print(f"   主题数量:")
        print(f"     - 优化后: {optimized['unique_themes']}")
        print(f"     - 基线: {baseline.get('unique_themes', 'N/A')}")
        print(f"     - Ground Truth: {comp['ground_truth'].get('unique_themes', 'N/A')}")
        
        if 'success_rate' in optimized and 'comprehensive_score' in baseline:
            improvement = (optimized['success_rate'] - baseline['comprehensive_score']) / baseline['comprehensive_score'] * 100
            print(f"   成功率改进: {improvement:+.1f}%")
    
    # 详细发现
    print(f"\n🔍 主要发现:")
    for i, finding in enumerate(report.get('detailed_findings', [])[:3], 1):
        print(f"   {i}. [{finding['category']}] {finding['finding']}")
    
    # 建议
    print(f"\n💡 优化建议:")
    for i, rec in enumerate(report.get('recommendations', [])[:3], 1):
        print(f"   {i}. [{rec['priority']}优先级] {rec['recommendation']}")
    
    print(f"\n📁 完整报告位置: {report_path}")
    print("="*80)

def analyze_quick_test(filepath):
    """分析快速测试结果"""
    print(f"\n📊 快速测试结果分析:")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    theme_assignments = data['theme_assignments']
    
    # 统计
    total = len(theme_assignments)
    success_count = sum(1 for theme in theme_assignments.values() 
                       if theme not in ['FAILED', 'ERROR', 'UNASSIGNED'])
    success_rate = success_count / total if total > 0 else 0
    
    unique_themes = set(theme_assignments.values())
    unique_themes.discard('FAILED')
    unique_themes.discard('ERROR')
    unique_themes.discard('UNASSIGNED')
    
    print(f"   事件总数: {total}")
    print(f"   成功分配: {success_count}")
    print(f"   成功率: {success_rate*100:.1f}%")
    print(f"   独特主题: {len(unique_themes)}")
    
    # 主题分布
    print(f"\n   主题分布:")
    theme_counts = {}
    for theme in theme_assignments.values():
        if theme not in ['FAILED', 'ERROR', 'UNASSIGNED']:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
    
    for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"     {theme}: {count} 个事件")

def check_system_health():
    """检查系统健康状况"""
    print(f"\n🔧 系统健康检查:")
    
    # 检查必要的目录
    required_dirs = [
        'evaluate_service/data/processed',
        'evaluate_service/data/results',
        'evaluate_service/config'
    ]
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"   ✅ {dir_path}")
        else:
            print(f"   ❌ {dir_path} - 目录不存在")
    
    # 检查必要的文件
    required_files = [
        'evaluate_service/data/processed/validation_events_enhanced.json',
        'evaluate_service/config/ground_truth_correct.json'
    ]
    
    for file_path in required_files:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path) / 1024  # KB
            print(f"   ✅ {file_path} ({size:.1f} KB)")
        else:
            print(f"   ❌ {file_path} - 文件不存在")
    
    # 检查API密钥
    if os.getenv('DEEPSEEK_API_KEY'):
        print(f"   ✅ DEEPSEEK_API_KEY: 已设置")
    else:
        print(f"   ❌ DEEPSEEK_API_KEY: 未设置")

def main():
    """主函数"""
    print("🔍 开始分析系统性能...")
    
    # 1. 系统健康检查
    check_system_health()
    
    # 2. 分析最新的测试结果
    analyze_latest_test()
    
    print(f"\n📋 下一步建议:")
    print("   1. 如果API密钥未设置，请运行: export DEEPSEEK_API_KEY='your-key'")
    print("   2. 运行快速测试: python evaluate_service/scripts/quick_test_runner.py")
    print("   3. 运行完整测试: python evaluate_service/scripts/integrated_test_runner_fixed.py")
    print("   4. 查看结果: python evaluate_service/scripts/compare_results.py")

if __name__ == "__main__":
    main()
