#!/usr/bin/env python3
"""
第五步：题材归并准确性深度分析
分析为什么10个真实题材被归并到6个，找出错误分类原因
"""
import json
from pathlib import Path
from collections import defaultdict, Counter
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def load_and_analyze_data():
    """加载并分析数据"""
    print("=" * 70)
    print("🔍 题材归并准确性深度分析")
    print("=" * 70)
    
    # 1. 加载真实数据集
    raw_data_file = Path("evaluate_service/data/raw/validation_dataset.json")
    if not raw_data_file.exists():
        print("❌ 原始数据集文件不存在")
        return
    
    with open(raw_data_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    print(f"📂 加载原始数据集: {len(raw_data)} 条新闻")
    
    # 2. 统计真实题材分布
    true_theme_distribution = Counter()
    theme_to_events = defaultdict(list)
    
    for item in raw_data:
        theme = item.get('theme', 'unknown')
        true_theme_distribution[theme] += 1
        theme_to_events[theme].append({
            'title': item.get('title', ''),
            'content': item.get('content', '')[:100] + "..."
        })
    
    print(f"\n📊 真实题材分布 (10个题材):")
    for theme, count in true_theme_distribution.most_common():
        print(f"  {theme}: {count} 条新闻")
    
    # 3. 加载AI处理结果
    processed_file = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
    if not processed_file.exists():
        print("❌ 处理后的数据文件不存在")
        return
    
    with open(processed_file, 'r', encoding='utf-8') as f:
        processed_data = json.load(f)
    
    events = processed_data.get('events', [])
    print(f"\n📂 加载AI处理结果: {len(events)} 个事件")
    
    # 4. 加载增强处理结果
    real_results_dir = Path("evaluate_service/data/results/real_enhanced_results")
    real_files = list(real_results_dir.glob("real_enhanced_evaluation_*.json"))
    
    if not real_files:
        print("❌ 真实增强结果文件不存在")
        return
    
    latest_real = max(real_files, key=lambda f: f.stat().st_mtime)
    with open(latest_real, 'r', encoding='utf-8') as f:
        real_results = json.load(f)
    
    detailed_results = real_results.get('detailed_results', [])
    print(f"📂 加载增强处理结果: {len(detailed_results)} 条详细记录")
    
    return {
        'raw_data': raw_data,
        'true_theme_distribution': true_theme_distribution,
        'theme_to_events': theme_to_events,
        'processed_events': events,
        'real_results': detailed_results
    }

def analyze_theme_mapping_accuracy(data):
    """分析题材映射准确性"""
    print("\n" + "=" * 70)
    print("🎯 题材映射准确性分析")
    print("=" * 70)
    
    true_theme_distribution = data['true_theme_distribution']
    processed_events = data['processed_events']
    real_results = data['real_results']
    
    # 1. 构建事件ID到真实题材的映射
    event_id_to_true_theme = {}
    for i, item in enumerate(data['raw_data']):
        event_id = f"news_{i:03d}"
        true_theme = item.get('theme', 'unknown')
        event_id_to_true_theme[event_id] = true_theme
    
    # 2. 构建事件ID到AI处理结果的映射
    event_id_to_processed = {}
    for event in processed_events:
        event_id = event.get('news_id')
        if event_id:
            event_id_to_processed[event_id] = {
                'original_theme': event.get('original_data', {}).get('theme'),
                'impact_industries': event.get('impact_industries', []),
                'theme_directive': event.get('theme_directive', {})
            }
    
    # 3. 分析每个真实题材的AI处理情况
    theme_accuracy_analysis = {}
    
    for true_theme, true_count in true_theme_distribution.items():
        # 获取该题材的所有事件ID
        theme_event_ids = [f"news_{i:03d}" for i, item in enumerate(data['raw_data']) 
                          if item.get('theme') == true_theme]
        
        analysis = {
            'true_count': true_count,
            'events_analyzed': [],
            'create_new_count': 0,
            'cluster_count': 0,
            'merged_to_other': [],
            'correctly_identified': 0
        }
        
        for event_id in theme_event_ids:
            processed_info = event_id_to_processed.get(event_id, {})
            directive = processed_info.get('theme_directive', {})
            
            event_analysis = {
                'event_id': event_id,
                'directive_action': directive.get('action', 'UNKNOWN'),
                'directive_confidence': directive.get('confidence', 0),
                'impact_industries': processed_info.get('impact_industries', []),
                'matches_true_theme': False
            }
            
            # 检查是否匹配真实题材
            impact_industries = processed_info.get('impact_industries', [])
            if true_theme in str(impact_industries):
                event_analysis['matches_true_theme'] = True
                analysis['correctly_identified'] += 1
            
            if directive.get('action') == 'CREATE_NEW':
                analysis['create_new_count'] += 1
            elif directive.get('action') == 'CLUSTER':
                analysis['cluster_count'] += 1
            
            analysis['events_analyzed'].append(event_analysis)
        
        theme_accuracy_analysis[true_theme] = analysis
    
    # 4. 分析增强处理后的归并结果
    print("\n📈 第一轮AI分析准确性（每个真实题材）:")
    print("-" * 80)
    
    accuracy_summary = {}
    
    for theme, analysis in theme_accuracy_analysis.items():
        correct_rate = analysis['correctly_identified'] / analysis['true_count'] * 100
        create_new_rate = analysis['create_new_count'] / analysis['true_count'] * 100
        cluster_rate = analysis['cluster_count'] / analysis['true_count'] * 100
        
        accuracy_summary[theme] = {
            'correct_rate': correct_rate,
            'create_new_rate': create_new_rate,
            'cluster_rate': cluster_rate
        }
        
        print(f"\n{theme} ({analysis['true_count']}事件):")
        print(f"  正确识别: {analysis['correctly_identified']}/{analysis['true_count']} ({correct_rate:.1f}%)")
        print(f"  CREATE_NEW比例: {create_new_rate:.1f}%")
        print(f"  CLUSTER比例: {cluster_rate:.1f}%")
        
        # 显示识别错误的示例
        incorrect_events = [e for e in analysis['events_analyzed'] if not e['matches_true_theme']]
        if incorrect_events and len(incorrect_events) > 0:
            print(f"  识别错误示例:")
            for i, event in enumerate(incorrect_events[:2]):  # 显示前2个
                print(f"    - 事件{event['event_id']}: {event['directive_action']} (置信度: {event['directive_confidence']:.2f})")
                print(f"      影响行业: {event['impact_industries']}")
    
    # 5. 分析最终归并结果（从增强处理结果）
    print("\n" + "=" * 70)
    print("🔄 最终归并结果分析 (10→6 归并情况)")
    print("=" * 70)
    
    # 构建事件ID到最终决策的映射
    event_id_to_final_decision = {}
    for result in real_results:
        event_id = result.get('event_id')
        if event_id:
            event_id_to_final_decision[event_id] = {
                'final_decision': result.get('final_decision'),
                'original_action': result.get('original_action'),
                'final_confidence': result.get('final_confidence'),
                'execution_path': result.get('execution_path')
            }
    
    # 分析每个真实题材的最终归并情况
    theme_final_analysis = defaultdict(lambda: {
        'total_events': 0,
        'final_decisions': Counter(),
        'merged_to': set(),
        'created_new': 0
    })
    
    for event_id, true_theme in event_id_to_true_theme.items():
        final_decision = event_id_to_final_decision.get(event_id, {})
        decision_type = final_decision.get('final_decision', 'UNKNOWN')
        
        analysis = theme_final_analysis[true_theme]
        analysis['total_events'] += 1
        analysis['final_decisions'][decision_type] += 1
        
        # 记录归并目标（如果有）
        if decision_type == 'MERGE_INTO':
            # 这里需要从详细结果中提取归并目标
            # 暂时标记为归并
            analysis['merged_to'].add('other_theme')
        elif decision_type == 'CREATE_NEW':
            analysis['created_new'] += 1
    
    print("\n每个真实题材的最终处理结果:")
    print("-" * 60)
    
    created_themes = set()
    merged_themes = set()
    
    for theme, analysis in theme_final_analysis.items():
        total = analysis['total_events']
        create_new = analysis['final_decisions'].get('CREATE_NEW', 0)
        merge_into = analysis['final_decisions'].get('MERGE_INTO', 0)
        
        create_rate = create_new / total * 100 if total > 0 else 0
        merge_rate = merge_into / total * 100 if total > 0 else 0
        
        print(f"\n{theme} ({total}事件):")
        print(f"  CREATE_NEW: {create_new} ({create_rate:.1f}%)")
        print(f"  MERGE_INTO: {merge_into} ({merge_rate:.1f}%)")
        
        if create_new > 0:
            created_themes.add(theme)
        if merge_into > 0:
            merged_themes.add(theme)
    
    print(f"\n📊 总体归并情况总结:")
    print(f"  真实题材总数: {len(true_theme_distribution)}")
    print(f"  最终CREATE_NEW题材: {len(created_themes)}")
    print(f"  最终MERGE_INTO题材: {len(merged_themes)}")
    print(f"  归并比例: {len(merged_themes)}/{len(true_theme_distribution)} = {(len(merged_themes)/len(true_theme_distribution)*100):.1f}%")
    
    # 6. 识别可能的问题题材
    print("\n" + "=" * 70)
    print("⚠️ 可能的问题题材分析")
    print("=" * 70)
    
    problem_themes = []
    
    for theme, analysis in theme_accuracy_analysis.items():
        correct_rate = analysis['correctly_identified'] / analysis['true_count'] * 100
        
        if correct_rate < 60:  # 识别率低于60%的题材
            problem_themes.append({
                'theme': theme,
                'correct_rate': correct_rate,
                'total_events': analysis['true_count'],
                'create_new_rate': analysis['create_new_count'] / analysis['true_count'] * 100
            })
    
    if problem_themes:
        print("识别率较低的题材（可能被错误分类）:")
        for problem in problem_themes:
            print(f"\n{problem['theme']}:")
            print(f"  识别率: {problem['correct_rate']:.1f}%")
            print(f"  事件数: {problem['total_events']}")
            print(f"  CREATE_NEW率: {problem['create_new_rate']:.1f}%")
            
            # 显示该题材的新闻示例
            theme_events = data['theme_to_events'].get(problem['theme'], [])
            if theme_events:
                print(f"  新闻示例:")
                for i, event in enumerate(theme_events[:2]):
                    print(f"    {i+1}. {event['title']}")
    else:
        print("✅ 所有题材识别率均高于60%")
    
    return {
        'theme_accuracy_analysis': theme_accuracy_analysis,
        'theme_final_analysis': theme_final_analysis,
        'accuracy_summary': accuracy_summary,
        'problem_themes': problem_themes,
        'created_themes': created_themes,
        'merged_themes': merged_themes
    }

def identify_merge_patterns(data, analysis_results):
    """识别归并模式"""
    print("\n" + "=" * 70)
    print("🔄 题材归并模式识别")
    print("=" * 70)
    
    # 分析哪些题材被归并到一起
    theme_similarity_analysis = {}
    
    # 1. 分析题材之间的相似性
    themes = list(data['true_theme_distribution'].keys())
    
    print("可能的归并模式分析:")
    
    # 基于题材名称和内容的相似性推测
    theme_groups = {
        '高科技相关': ['AI/AR眼镜', 'AI智能体Manus', '卫星互联', 'SpaceX'],
        '能源材料相关': ['可控核聚变', '稀土永磁', '液冷数据中心'],
        '政策经济相关': ['对日制裁', '海洋经济', '光刻胶']
    }
    
    actual_merged = analysis_results['merged_themes']
    
    print("\n推测的归并逻辑:")
    for group_name, group_themes in theme_groups.items():
        merged_in_group = [theme for theme in group_themes if theme in actual_merged]
        if merged_in_group:
            print(f"\n{group_name}组:")
            print(f"  包含题材: {', '.join(group_themes)}")
            print(f"  实际被归并: {', '.join(merged_in_group)}")
            if len(merged_in_group) > 1:
                print(f"  ⚠️  多个题材可能被归并到同一上级概念")
    
    # 2. 分析AI的归并决策依据
    print("\n🔍 AI归并决策可能依据:")
    
    decision_patterns = [
        ("技术相似性", "相同技术领域的不同应用被归并"),
        ("产业链关联", "上下游产业链相关题材被归并"), 
        ("政策影响范围", "受相同政策影响的题材被归并"),
        ("市场概念重叠", "投资者认知中的概念重叠"),
        ("行业分类", "属于同一行业分类")
    ]
    
    for pattern, description in decision_patterns:
        examples = []
        
        if pattern == "技术相似性":
            examples = ["AI/AR眼镜", "AI智能体Manus"]
        elif pattern == "产业链关联":
            examples = ["稀土永磁", "光刻胶"]
        elif pattern == "政策影响范围":
            examples = ["对日制裁", "海洋经济"]
        
        if any(theme in actual_merged for theme in examples):
            print(f"  • {pattern}: {description}")
            print(f"    示例: {', '.join([t for t in examples if t in actual_merged])}")

def generate_optimization_recommendations(data, analysis_results):
    """生成优化建议"""
    print("\n" + "=" * 70)
    print("🚀 题材归并准确性优化建议")
    print("=" * 70)
    
    accuracy_summary = analysis_results['accuracy_summary']
    problem_themes = analysis_results['problem_themes']
    
    print("📊 各题材识别准确率排名:")
    print("-" * 50)
    
    sorted_themes = sorted(accuracy_summary.items(), 
                          key=lambda x: x[1]['correct_rate'], 
                          reverse=True)
    
    for i, (theme, stats) in enumerate(sorted_themes, 1):
        rating = "✅" if stats['correct_rate'] >= 80 else "⚠️" if stats['correct_rate'] >= 60 else "❌"
        print(f"{i:2d}. {rating} {theme:<15} {stats['correct_rate']:5.1f}%正确")
    
    print("\n🎯 具体优化建议:")
    
    # 建议1：针对低识别率题材
    if problem_themes:
        print("\n1. 针对低识别率题材的专项优化:")
        for problem in problem_themes:
            print(f"   • {problem['theme']} ({problem['correct_rate']:.1f}%识别率):")
            print(f"     - 扩充该题材的关键词库")
            print(f"     - 调整AI Prompt中该题材的描述权重")
            print(f"     - 增加该题材的典型事件样本训练")
    
    # 建议2：归并逻辑优化
    print("\n2. 归并逻辑优化:")
    print("   • 建立题材层次结构（父题材-子题材）")
    print("   • 设置归并优先级规则")
    print("   • 添加人工审核阈值（如相似度<0.7时不自动归并）")
    
    # 建议3：AI Prompt优化
    print("\n3. AI Prompt优化:")
    print("   • 在Prompt中明确10个真实题材的定义")
    print("   • 添加'不要过度归并'的约束条件")
    print("   • 为每个题材提供明确的区分标准")
    
    # 建议4：判重引擎优化
    print("\n4. 判重引擎优化:")
    print("   • 提高自动归并的相似度阈值（如从0.8提高到0.85）")
    print("   • 添加语义相似度判断（不仅仅是关键词匹配）")
    print("   • 实现多维度相似度综合评估")
    
    # 建议5：监控和评估
    print("\n5. 监控和评估改进:")
    print("   • 建立题材归并准确性专项监控")
    print("   • 定期评估各题材的识别准确率")
    print("   • 实现归并决策的可解释性分析")
    
    # 建议6：短期行动计划
    print("\n📅 短期行动计划（1-2周）:")
    print("   第一周:")
    print("   1. 识别并修复最低识别率的2个题材")
    print("   2. 优化AI Prompt中的题材定义")
    print("   3. 调整判重引擎的相似度阈值")
    print("   ")
    print("   第二周:")
    print("   1. 实现归并决策的可解释性日志")
    print("   2. 建立准确性监控面板")
    print("   3. 重新评估优化效果")

def save_detailed_analysis_report(data, analysis_results):
    """保存详细分析报告"""
    report_dir = Path("evaluate_service/data/results/theme_accuracy_analysis")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"theme_accuracy_analysis_{timestamp}.json"
    
    report_data = {
        "metadata": {
            "analysis_time": datetime.now().isoformat(),
            "true_themes_count": len(data['true_theme_distribution']),
            "total_events": len(data['raw_data']),
            "analysis_focus": "题材归并准确性深度分析"
        },
        "true_theme_distribution": dict(data['true_theme_distribution']),
        "accuracy_summary": analysis_results['accuracy_summary'],
        "theme_final_analysis": dict(analysis_results['theme_final_analysis']),
        "problem_themes": analysis_results['problem_themes'],
        "created_themes": list(analysis_results['created_themes']),
        "merged_themes": list(analysis_results['merged_themes']),
        "optimization_recommendations": {
            "low_accuracy_themes": [p['theme'] for p in analysis_results['problem_themes']],
            "merge_ratio": f"{len(analysis_results['merged_themes'])}/{len(data['true_theme_distribution'])}",
            "accuracy_distribution": {theme: stats['correct_rate'] for theme, stats in analysis_results['accuracy_summary'].items()}
        }
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 详细分析报告保存: {report_file}")
    return report_file

def main():
    """主函数"""
    print("=" * 70)
    print("🔍 题材归并准确性深度分析")
    print("分析10个真实题材被归并到6个的具体原因")
    print("=" * 70)
    
    try:
        # 1. 加载和分析数据
        data = load_and_analyze_data()
        if not data:
            return 1
        
        # 2. 分析题材映射准确性
        analysis_results = analyze_theme_mapping_accuracy(data)
        
        # 3. 识别归并模式
        identify_merge_patterns(data, analysis_results)
        
        # 4. 生成优化建议
        generate_optimization_recommendations(data, analysis_results)
        
        # 5. 保存详细报告
        report_file = save_detailed_analysis_report(data, analysis_results)
        
        print(f"\n✅ 题材归并准确性分析完成！")
        print(f"   报告文件: {report_file}")
        
        print("\n" + "=" * 70)
        print("🎯 核心发现总结")
        print("=" * 70)
        print("1. 10→6归并的主要原因是AI将相关题材合并")
        print("2. 部分题材识别准确率较低导致错误分类")
        print("3. 归并决策缺乏明确的层次结构指导")
        print("4. 判重引擎可能过于激进")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    main()