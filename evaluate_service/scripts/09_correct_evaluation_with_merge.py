#!/usr/bin/env python3
"""
第九步：正确评估（考虑题材归并后的结果）
评估归并后的题材群组，而不是初步分析的独立题材
"""
import json
from pathlib import Path
from collections import defaultdict, Counter
import sys
import re

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def load_merged_results():
    """加载归并后的结果"""
    print("=" * 70)
    print("📊 正确评估：归并后的题材群组准确性")
    print("评估标准：同类型新闻是否被正确聚合（考虑归并后结果）")
    print("=" * 70)
    
    # 1. 加载真实数据集
    raw_data_file = Path("evaluate_service/data/raw/validation_dataset.json")
    if not raw_data_file.exists():
        print("❌ 原始数据集文件不存在")
        return None
    
    with open(raw_data_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    print(f"📂 加载真实数据集: {len(raw_data)} 条新闻")
    
    # 2. 加载增强处理结果（这是归并后的结果！）
    real_results_dir = Path("evaluate_service/data/results/real_enhanced_results")
    real_files = list(real_results_dir.glob("real_enhanced_evaluation_*.json"))
    
    if not real_files:
        print("❌ 增强处理结果文件不存在")
        return None
    
    latest_real = max(real_files, key=lambda f: f.stat().st_mtime)
    with open(latest_real, 'r', encoding='utf-8') as f:
        real_results = json.load(f)
    
    detailed_results = real_results.get('detailed_results', [])
    print(f"📂 加载增强处理结果: {len(detailed_results)} 条记录")
    
    # 3. 从归并结果中提取最终的题材群组
    print("\n📊 分析归并后的题材群组...")
    
    # 提取所有事件及其最终决策
    event_decisions = {}
    theme_groups = defaultdict(list)  # 最终的题材群组
    
    for result in detailed_results:
        event_id = result.get('event_id')
        if not event_id:
            continue
            
        final_decision = result.get('final_decision')
        original_action = result.get('original_action')
        final_theme = result.get('final_theme', '未知')
        
        event_decisions[event_id] = {
            'final_decision': final_decision,
            'final_theme': final_theme,
            'original_action': original_action
        }
        
        # 如果是CREATE_NEW或CLUSTER，记录到题材群组
        if final_decision in ['CREATE_NEW', 'CLUSTER']:
            theme_groups[final_theme].append(event_id)
    
    print(f"📈 归并后题材群组数量: {len(theme_groups)}")
    
    # 4. 显示归并后的题材群组
    print("\n📋 归并后的题材群组分布:")
    print("-" * 50)
    
    for theme, events in sorted(theme_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {theme:<30}: {len(events):2d} 条新闻")
    
    # 5. 构建真实题材分组
    true_theme_groups = defaultdict(list)
    for i, item in enumerate(raw_data):
        event_id = f"news_{i:03d}"
        true_theme = item['theme']
        true_theme_groups[true_theme].append(event_id)
    
    print(f"\n📋 真实题材分组分布:")
    print("-" * 50)
    for theme, events in sorted(true_theme_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {theme:<20}: {len(events):2d} 条新闻")
    
    return {
        'raw_data': raw_data,
        'true_theme_groups': dict(true_theme_groups),
        'ai_theme_groups': dict(theme_groups),
        'event_decisions': event_decisions,
        'detailed_results': detailed_results
    }

def calculate_grouping_metrics(true_groups, ai_groups):
    """计算分组准确性指标"""
    print("\n" + "=" * 70)
    print("📈 分组准确性计算（基于归并后结果）")
    print("=" * 70)
    
    # 构建事件ID到分组的映射
    true_event_to_group = {}
    for theme, events in true_groups.items():
        for event_id in events:
            true_event_to_group[event_id] = theme
    
    ai_event_to_group = {}
    for theme, events in ai_groups.items():
        for event_id in events:
            ai_event_to_group[event_id] = theme
    
    # 计算所有可能的事件对
    all_event_pairs = []
    
    # 1. 对每个真实分组内的新闻对
    same_in_true = 0
    same_in_ai = 0
    total_true_pairs = 0
    
    for true_theme, events in true_groups.items():
        event_ids = list(events)
        for i in range(len(event_ids)):
            for j in range(i+1, len(event_ids)):
                event1, event2 = event_ids[i], event_ids[j]
                all_event_pairs.append((event1, event2, 'same_true'))
                
                if event1 in ai_event_to_group and event2 in ai_event_to_group:
                    total_true_pairs += 1
                    same_in_true += 1
                    
                    if ai_event_to_group[event1] == ai_event_to_group[event2]:
                        same_in_ai += 1
    
    # 2. 对每个AI分组内的新闻对
    same_in_ai_groups = 0
    same_in_true_groups = 0
    total_ai_pairs = 0
    
    for ai_theme, events in ai_groups.items():
        event_ids = list(events)
        for i in range(len(event_ids)):
            for j in range(i+1, len(event_ids)):
                event1, event2 = event_ids[i], event_ids[j]
                all_event_pairs.append((event1, event2, 'same_ai'))
                
                if event1 in true_event_to_group and event2 in true_event_to_group:
                    total_ai_pairs += 1
                    same_in_ai_groups += 1
                    
                    if true_event_to_group[event1] == true_event_to_group[event2]:
                        same_in_true_groups += 1
    
    # 计算指标
    precision = same_in_ai / same_in_true if same_in_true > 0 else 0
    recall = same_in_true_groups / same_in_ai_groups if same_in_ai_groups > 0 else 0
    f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\n📊 评估指标:")
    print(f"  真实分组内新闻对总数: {same_in_true}")
    print(f"  AI也同组的新闻对数: {same_in_ai}")
    print(f"  Precision (同真实分组且同AI分组): {precision:.2%}")
    
    print(f"\n  AI分组内新闻对总数: {same_in_ai_groups}")
    print(f"  真实也同组的新闻对数: {same_in_true_groups}")
    print(f"  Recall (同AI分组且同真实分组): {recall:.2%}")
    
    print(f"\n  F1 Score: {f1_score:.2%}")
    
    return {
        'precision': precision,
        'recall': recall,
        'f1_score': f1_score,
        'total_true_pairs': total_true_pairs,
        'same_in_ai': same_in_ai,
        'total_ai_pairs': total_ai_pairs,
        'same_in_true_groups': same_in_true_groups
    }

def analyze_theme_mapping(data, metrics):
    """分析题材映射关系"""
    print("\n" + "=" * 70)
    print("🔄 题材映射关系分析")
    print("=" * 70)
    
    true_groups = data['true_theme_groups']
    ai_groups = data['ai_theme_groups']
    
    # 构建事件ID到真实题材的映射
    event_to_true_theme = {}
    for theme, events in true_groups.items():
        for event_id in events:
            event_to_true_theme[event_id] = theme
    
    # 构建事件ID到AI题材的映射
    event_to_ai_theme = {}
    for theme, events in ai_groups.items():
        for event_id in events:
            event_to_ai_theme[event_id] = theme
    
    # 分析每个真实题材被分到哪些AI题材
    print("\n📊 真实题材 → AI题材 映射分析:")
    print("-" * 60)
    
    theme_mapping_quality = {}
    
    for true_theme, true_events in true_groups.items():
        ai_distribution = Counter()
        
        for event_id in true_events:
            if event_id in event_to_ai_theme:
                ai_theme = event_to_ai_theme[event_id]
                ai_distribution[ai_theme] += 1
        
        if ai_distribution:
            total = len(true_events)
            # 计算集中度
            most_common = ai_distribution.most_common(1)[0]
            concentration = most_common[1] / total * 100
            
            print(f"\n{true_theme} ({total}条):")
            for ai_theme, count in ai_distribution.most_common(3):
                percentage = count / total * 100
                print(f"  → {ai_theme:<25}: {count}/{total} ({percentage:.1f}%)")
            
            if concentration >= 70:
                print(f"  ✅ 集中度良好: {concentration:.1f}%")
                theme_mapping_quality[true_theme] = 'good'
            elif concentration >= 50:
                print(f"  ⚠️  集中度一般: {concentration:.1f}%")
                theme_mapping_quality[true_theme] = 'fair'
            else:
                print(f"  ❌ 分散度过高: 最高占比仅 {concentration:.1f}%")
                theme_mapping_quality[true_theme] = 'poor'
        else:
            print(f"\n{true_theme}: ❌ 未找到AI分类")
            theme_mapping_quality[true_theme] = 'none'
    
    # 分析跨类错误
    print("\n" + "=" * 70)
    print("⚠️ 跨类错误分析")
    print("=" * 70)
    
    # 定义明显错误的分类对
    error_pairs = [
        ("海洋经济", "航天"), ("海洋经济", "卫星"), ("海洋经济", "太空"),
        ("可控核聚变", "消费电子"), ("稀土永磁", "互联网"),
        ("对日制裁", "人工智能"), ("光刻胶", "旅游")
    ]
    
    cross_errors = []
    
    for true_theme, ai_dist in theme_mapping_quality.items():
        if ai_dist == 'none':
            continue
            
        # 获取该真实题材的主要AI题材
        events = true_groups[true_theme]
        ai_themes = []
        for event_id in events:
            if event_id in event_to_ai_theme:
                ai_themes.append(event_to_ai_theme[event_id])
        
        if not ai_themes:
            continue
            
        main_ai_theme = Counter(ai_themes).most_common(1)[0][0]
        
        # 检查是否是明显错误
        for (error_true, error_ai) in error_pairs:
            if error_true in true_theme and error_ai in main_ai_theme:
                cross_errors.append({
                    'true_theme': true_theme,
                    'ai_theme': main_ai_theme,
                    'error_type': f"{error_true}→{error_ai}"
                })
                break
    
    if cross_errors:
        print("❌ 发现明显跨类错误:")
        for error in cross_errors[:5]:  # 显示前5个
            print(f"  {error['true_theme']} → {error['ai_theme']}")
    else:
        print("✅ 未发现明显跨类错误")
    
    return {
        'theme_mapping_quality': theme_mapping_quality,
        'cross_errors': cross_errors
    }

def analyze_grouping_problems(data, mapping_analysis):
    """分析分组问题"""
    print("\n" + "=" * 70)
    print("🔍 分组问题详细分析")
    print("=" * 70)
    
    true_groups = data['true_theme_groups']
    ai_groups = data['ai_theme_groups']
    
    # 分析哪些真实题材分散在多个AI分组中
    print("\n📌 分散度较高的真实题材:")
    print("-" * 50)
    
    for true_theme, quality in mapping_analysis['theme_mapping_quality'].items():
        if quality == 'poor':
            events = true_groups[true_theme]
            
            # 统计分布到哪些AI分组
            ai_distribution = Counter()
            for event_id in events:
                if event_id in data['event_decisions']:
                    decision = data['event_decisions'][event_id]
                    ai_theme = decision.get('final_theme', '未知')
                    ai_distribution[ai_theme] += 1
            
            if ai_distribution:
                total = len(events)
                print(f"\n{true_theme} ({total}条):")
                for ai_theme, count in ai_distribution.most_common():
                    percentage = count / total * 100
                    print(f"  {ai_theme:<25}: {count}条 ({percentage:.1f}%)")
    
    # 分析哪些AI分组混合了多个真实题材
    print("\n📌 混合了多个真实题材的AI分组:")
    print("-" * 50)
    
    mixed_groups = []
    
    for ai_theme, ai_events in ai_groups.items():
        true_distribution = Counter()
        
        for event_id in ai_events:
            if event_id in true_groups:
                # 找到这个事件属于哪个真实题材
                for true_theme, true_events in true_groups.items():
                    if event_id in true_events:
                        true_distribution[true_theme] += 1
                        break
        
        if len(true_distribution) > 1:  # 混合了多个真实题材
            mixed_groups.append((ai_theme, true_distribution))
    
    if mixed_groups:
        for ai_theme, true_dist in sorted(mixed_groups, key=lambda x: len(x[1]), reverse=True)[:5]:
            print(f"\n{ai_theme}:")
            for true_theme, count in true_dist.most_common():
                print(f"  {true_theme}: {count}条")
    else:
        print("✅ 所有AI分组都只包含单一真实题材")

def generate_optimization_suggestions(metrics, mapping_analysis):
    """生成优化建议"""
    print("\n" + "=" * 70)
    print("🚀 优化建议")
    print("=" * 70)
    
    f1_score = metrics['f1_score']
    
    print(f"\n📈 当前性能:")
    print(f"  F1分数: {f1_score:.2%}")
    print(f"  Precision: {metrics['precision']:.2%}")
    print(f"  Recall: {metrics['recall']:.2%}")
    
    if f1_score >= 0.7:
        print("\n✅ 表现良好！")
    elif f1_score >= 0.5:
        print("\n⚠️  表现一般，有优化空间")
    else:
        print("\n❌ 表现不佳，需要重点优化")
    
    print("\n🎯 基于当前结果的优化建议:")
    
    # 根据指标给出建议
    if metrics['precision'] < metrics['recall']:
        print("1. **解决过度归并问题** (Precision较低):")
        print("   • AI把不同真实题材的新闻归并到了同一组")
        print("   • 需要提高判重引擎的区分度")
        print("   • 降低相似度阈值，避免不相关的归并")
    else:
        print("1. **解决过度细分问题** (Recall较低):")
        print("   • AI把相同真实题材的新闻分到了不同组")
        print("   • 需要提高同类新闻的识别能力")
        print("   • 增加题材的关键词覆盖范围")
    
    if mapping_analysis['cross_errors']:
        print("\n2. **解决跨类错误问题**:")
        print("   • 建立题材互斥规则")
        print("   • 禁止逻辑上不相关的题材归并")
        for error in mapping_analysis['cross_errors'][:3]:
            print(f"   • 禁止 {error['true_theme']} → 包含'{error['error_type'].split('→')[1]}'的题材")
    
    # 分析theme_mapping_quality给出具体建议
    poor_themes = [theme for theme, quality in mapping_analysis['theme_mapping_quality'].items() 
                  if quality in ['poor', 'none']]
    
    if poor_themes:
        print(f"\n3. **针对低质量映射的题材优化**:")
        for theme in poor_themes[:3]:  # 优先处理前3个
            print(f"   • {theme}: 加强该题材的特征识别")
    
    print("\n4. **算法优化方向**:")
    print("   • 实现基于语义的题材匹配")
    print("   • 建立题材知识图谱")
    print("   • 优化判重引擎的相似度计算")

def save_final_report(data, metrics, mapping_analysis):
    """保存最终评估报告"""
    from datetime import datetime
    
    report_dir = Path("evaluate_service/data/results/final_evaluation")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"final_evaluation_with_merge_{timestamp}.json"
    
    report_data = {
        "metadata": {
            "evaluation_time": datetime.now().isoformat(),
            "evaluation_scope": "归并后的题材群组准确性",
            "total_news": len(data['raw_data']),
            "true_theme_count": len(data['true_theme_groups']),
            "ai_theme_count": len(data['ai_theme_groups'])
        },
        "performance_metrics": {
            "f1_score": metrics['f1_score'],
            "precision": metrics['precision'],
            "recall": metrics['recall']
        },
        "theme_mapping_quality": mapping_analysis['theme_mapping_quality'],
        "cross_category_errors": mapping_analysis['cross_errors'],
        "key_findings": [
            "基于归并后结果的评估",
            "重点考察同类新闻是否聚合",
            "允许题材名称不同，但要求逻辑正确"
        ],
        "recommendations": [
            "优化判重引擎的相似度计算",
            "加强题材特征的识别",
            "建立题材互斥规则"
        ]
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 最终评估报告保存至: {report_file}")
    return report_file

def main():
    """主函数"""
    try:
        # 1. 加载归并后的结果
        data = load_merged_results()
        if not data:
            return 1
        
        # 2. 计算分组准确性指标
        metrics = calculate_grouping_metrics(data['true_theme_groups'], data['ai_theme_groups'])
        
        # 3. 分析题材映射关系
        mapping_analysis = analyze_theme_mapping(data, metrics)
        
        # 4. 分析分组问题
        analyze_grouping_problems(data, mapping_analysis)
        
        # 5. 生成优化建议
        generate_optimization_suggestions(metrics, mapping_analysis)
        
        # 6. 保存报告
        report_file = save_final_report(data, metrics, mapping_analysis)
        
        print("\n" + "=" * 70)
        print("✅ 正确评估完成！")
        print("=" * 70)
        print(f"\n📊 核心结论:")
        print(f"  1. 归并后AI题材群组数: {len(data['ai_theme_groups'])}")
        print(f"  2. 分组准确性F1分数: {metrics['f1_score']:.2%}")
        print(f"  3. 跨类错误数: {len(mapping_analysis['cross_errors'])}")
        print(f"\n📁 报告文件: {report_file}")
        
    except Exception as e:
        print(f"❌ 评估失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    main()