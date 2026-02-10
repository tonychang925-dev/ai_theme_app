# evaluate_service/scripts/collect_baseline_results.py
#!/usr/bin/env python3
"""
收集基线系统结果并标准化格式
"""
import json
import sys
from pathlib import Path

# 加载基线测试结果
baseline_report_path = "evaluate_service/data/results/clustering_evaluation_results/clustering_report_20260107_192548.json"

if Path(baseline_report_path).exists():
    with open(baseline_report_path, 'r', encoding='utf-8') as f:
        baseline_report = json.load(f)
    
    # 提取事件-题材映射
    event_theme_mapping = {}
    for result in baseline_report.get('evaluation_results', []):
        event_id = result.get('event_id')
        ai_theme = result.get('ai_theme')
        if event_id and ai_theme:
            event_theme_mapping[event_id] = ai_theme
    
    # 保存为标准化格式
    baseline_results = {
        'system': 'baseline_clustering',
        'event_theme_mapping': event_theme_mapping,
        'total_events': len(event_theme_mapping),
        'unique_themes': len(set(event_theme_mapping.values())),
        'source_report': baseline_report_path
    }
    
    output_path = "evaluate_service/results/baseline_system_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(baseline_results, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 基线结果已保存到: {output_path}")
    print(f"  事件数: {len(event_theme_mapping)}")
    print(f"  题材数: {len(set(event_theme_mapping.values()))}")
else:
    print(f"❌ 基线报告文件不存在: {baseline_report_path}")
    sys.exit(1)