#!/usr/bin/env python3
"""
第七步：基于内容的题材分类准确性评估
评估标准：同类型新闻是否被正确聚合，而不是名称是否相同
"""
import json
from pathlib import Path
from collections import defaultdict
import sys
import re
from typing import Dict, List, Set, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def load_datasets():
    """加载数据集"""
    print("=" * 70)
    print("📊 基于内容的题材分类准确性评估")
    print("评估标准：同类型新闻是否被正确聚合（不要求名称相同）")
    print("=" * 70)
    
    # 1. 加载真实数据集
    raw_data_file = Path("evaluate_service/data/raw/validation_dataset.json")
    if not raw_data_file.exists():
        print("❌ 原始数据集文件不存在")
        return None
    
    with open(raw_data_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    print(f"📂 加载真实数据集: {len(raw_data)} 条新闻")
    print(f"📊 真实题材数量: {len(set(item['theme'] for item in raw_data))}")
    
    # 2. 加载AI处理结果
    processed_file = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
    if not processed_file.exists():
        print("❌ AI处理结果文件不存在")
        return None
    
    with open(processed_file, 'r', encoding='utf-8') as f:
        processed_data = json.load(f)
    
    events = processed_data.get('events', [])
    print(f"📂 加载AI处理结果: {len(events)} 个事件")
    
    # 3. 构建真实题材的新闻分组
    true_theme_groups = defaultdict(list)
    for i, item in enumerate(raw_data):
        theme = item['theme']
        event_id = f"news_{i:03d}"
        true_theme_groups[theme].append({
            'event_id': event_id,
            'title': item['title'],
            'content': item['content'],
            'theme': theme
        })
    
    # 4. 构建AI生成题材的新闻分组
    ai_theme_groups = defaultdict(list)
    for event in events:
        event_id = event.get('news_id')
        if not event_id:
            continue
            
        # 获取AI生成的题材名称
        ai_theme = extract_ai_theme(event)
        if not ai_theme:
            continue
            
        # 获取原始新闻内容
        original_data = event.get('original_data', {})
        
        ai_theme_groups[ai_theme].append({
            'event_id': event_id,
            'title': original_data.get('title', ''),
            'content': original_data.get('content', ''),
            'ai_theme': ai_theme
        })
    
    print(f"📊 AI生成题材数量: {len(ai_theme_groups)}")
    
    return {
        'raw_data': raw_data,
        'true_theme_groups': dict(true_theme_groups),
        'ai_theme_groups': dict(ai_theme_groups),
        'events': events
    }

def extract_ai_theme(event):
    """从AI处理结果中提取题材名称"""
    # 优先从impact_industries获取
    impact_industries = event.get('impact_industries', [])
    if impact_industries:
        # 取第一个作为主要题材
        return impact_industries[0]
    
    # 其次从theme_directive获取
    directive = event.get('theme_directive', {})
    theme = directive.get('theme_name')
    if theme:
        return theme
    
    return "未知题材"

def calculate_content_similarity(text1, text2):
    """计算两个文本的简单相似度（基于共同词汇）"""
    # 提取关键词（简单实现）
    words1 = set(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]+', text1.lower()))
    words2 = set(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]+', text2.lower()))
    
    if not words1 or not words2:
        return 0.0
    
    common_words = words1.intersection(words2)
    similarity = len(common_words) / (len(words1) + len(words2) - len(common_words))
    
    return similarity

def evaluate_grouping_accuracy(data):
    """评估分组准确性"""
    print("\n" + "=" * 70)
    print("🎯 基于内容的分组准确性评估")
    print("=" * 70)
    
    true_theme_groups = data['true_theme_groups']
    ai_theme_groups = data['ai_theme_groups']
    
    # 1. 为每个真实题材找到最匹配的AI题材
    theme_mapping = {}
    theme_similarities = {}
    
    for true_theme, true_events in true_theme_groups.items():
        best_match = None
        best_similarity = 0
        
        # 提取真实题材的代表性内容
        true_content = " ".join([e['title'] + " " + e['content'][:200] for e in true_events])
        
        for ai_theme, ai_events in ai_theme_groups.items():
            # 提取AI题材的代表性内容
            ai_content = " ".join([e['title'] + " " + e['content'][:200] for e in ai_events])
            
            # 计算内容相似度
            similarity = calculate_content_similarity(true_content, ai_content)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = ai_theme
        
        if best_match and best_similarity > 0.3:  # 相似度阈值
            theme_mapping[true_theme] = best_match
            theme_similarities[true_theme] = best_similarity
        else:
            theme_mapping[true_theme] = "未匹配"
            theme_similarities[true_theme] = best_similarity
    
    # 2. 显示匹配结果
    print("\n📋 真实题材 vs AI题材 匹配结果:")
    print("-" * 80)
    
    for true_theme, ai_theme in theme_mapping.items():
        similarity = theme_similarities.get(true_theme, 0)
        
        if ai_theme != "未匹配":
            status = "✅" if similarity > 0.5 else "⚠️"
            print(f"{status} {true_theme:<15} → {ai_theme:<20} (相似度: {similarity:.2f})")
        else:
            print(f"❌ {true_theme:<15} → 未匹配 (最高相似度: {similarity:.2f})")
    
    # 3. 评估跨类错误
    print("\n" + "=" * 70)
    print("⚠️ 跨类错误分析")
    print("=" * 70)
    
    # 定义明显错误的分类对
    obvious_mistakes = {
        ("海洋经济", "航天"): 0,
        ("海洋经济", "航空航天"): 0,
        ("海洋经济", "卫星"): 0,
        ("可控核聚变", "半导体"): 0,
        ("稀土永磁", "消费电子"): 0,
        ("对日制裁", "人工智能"): 0,
    }
    
    # 检查是否有明显跨类错误
    cross_category_errors = []
    
    for true_theme, ai_theme in theme_mapping.items():
        # 检查是否是明显错误的匹配
        for (error_true, error_ai) in obvious_mistakes.keys():
            if error_true in true_theme and error_ai in ai_theme:
                cross_category_errors.append({
                    'true_theme': true_theme,
                    'ai_theme': ai_theme,
                    'error_type': f"{error_true}→{error_ai}"
                })
                break
    
    if cross_category_errors:
        print("❌ 发现明显跨类错误:")
        for error in cross_category_errors:
            print(f"  {error['true_theme']} → {error['ai_theme']} ({error['error_type']})")
    else:
        print("✅ 未发现明显跨类错误")
    
    # 4. 计算分组准确性指标
    print("\n" + "=" * 70)
    print("📈 分组准确性指标")
    print("=" * 70)
    
    # 构建事件ID到真实题材的映射
    event_true_theme = {}
    for true_theme, events in true_theme_groups.items():
        for event in events:
            event_true_theme[event['event_id']] = true_theme
    
    # 构建事件ID到AI题材的映射
    event_ai_theme = {}
    for ai_theme, events in ai_theme_groups.items():
        for event in events:
            event_ai_theme[event['event_id']] = ai_theme
    
    # 计算分组一致性
    same_group_in_true = 0
    same_group_in_ai = 0
    total_comparisons = 0
    
    # 对每个真实题材分组内的新闻对
    for true_theme, events in true_theme_groups.items():
        event_ids = [e['event_id'] for e in events]
        
        # 检查该分组内的新闻在AI分类中是否也在同一组
        for i in range(len(event_ids)):
            for j in range(i+1, len(event_ids)):
                id1, id2 = event_ids[i], event_ids[j]
                
                # 检查在AI分类中
                if id1 in event_ai_theme and id2 in event_ai_theme:
                    total_comparisons += 1
                    same_group_in_true += 1
                    
                    if event_ai_theme[id1] == event_ai_theme[id2]:
                        same_group_in_ai += 1
    
    grouping_consistency = same_group_in_ai / same_group_in_true if same_group_in_true > 0 else 0
    
    # 计算反向一致性（AI分组内的新闻在真实分类中是否也在同一组）
    reverse_same_group_in_ai = 0
    reverse_same_group_in_true = 0
    
    for ai_theme, events in ai_theme_groups.items():
        event_ids = [e['event_id'] for e in events]
        
        for i in range(len(event_ids)):
            for j in range(i+1, len(event_ids)):
                id1, id2 = event_ids[i], event_ids[j]
                
                if id1 in event_true_theme and id2 in event_true_theme:
                    reverse_same_group_in_ai += 1
                    
                    if event_true_theme[id1] == event_true_theme[id2]:
                        reverse_same_group_in_true += 1
    
    reverse_consistency = reverse_same_group_in_true / reverse_same_group_in_ai if reverse_same_group_in_ai > 0 else 0
    
    # 计算F1分数
    precision = grouping_consistency
    recall = reverse_consistency
    f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\n📊 评估结果:")
    print(f"  真实题材分组数: {len(true_theme_groups)}")
    print(f"  AI题材分组数: {len(ai_theme_groups)}")
    print(f"  分组一致性 (Precision): {grouping_consistency:.2%}")
    print(f"  反向一致性 (Recall): {reverse_consistency:.2%}")
    print(f"  F1分数: {f1_score:.2%}")
    
    # 5. 详细的错误分析
    print("\n" + "=" * 70)
    print("🔍 详细错误分析")
    print("=" * 70)
    
    # 找出分组错误的案例
    if total_comparisons > 0:
        error_rate = 1 - grouping_consistency
        if error_rate > 0.1:  # 错误率超过10%
            print(f"⚠️ 分组错误率较高: {error_rate:.2%}")
            
            # 分析哪个真实题材错误最多
            theme_error_counts = defaultdict(int)
            
            for true_theme, events in true_theme_groups.items():
                event_ids = [e['event_id'] for e in events]
                errors_in_theme = 0
                total_pairs_in_theme = 0
                
                for i in range(len(event_ids)):
                    for j in range(i+1, len(event_ids)):
                        id1, id2 = event_ids[i], event_ids[j]
                        
                        if id1 in event_ai_theme and id2 in event_ai_theme:
                            total_pairs_in_theme += 1
                            if event_ai_theme[id1] != event_ai_theme[id2]:
                                errors_in_theme += 1
                
                if total_pairs_in_theme > 0:
                    theme_error_rate = errors_in_theme / total_pairs_in_theme
                    if theme_error_rate > 0.3:  # 该题材错误率超过30%
                        theme_error_counts[true_theme] = theme_error_rate
            
            if theme_error_counts:
                print(f"\n📌 高错误率题材:")
                for theme, error_rate in sorted(theme_error_counts.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {theme}: {error_rate:.2%} 错误率")
    
    return {
        'theme_mapping': theme_mapping,
        'theme_similarities': theme_similarities,
        'grouping_consistency': grouping_consistency,
        'reverse_consistency': reverse_consistency,
        'f1_score': f1_score,
        'cross_category_errors': cross_category_errors,
        'precision': precision,
        'recall': recall
    }

def analyze_specific_problems(data, evaluation_results):
    """分析具体问题"""
    print("\n" + "=" * 70)
    print("🔬 具体问题分析")
    print("=" * 70)
    
    true_theme_groups = data['true_theme_groups']
    ai_theme_groups = data['ai_theme_groups']
    theme_mapping = evaluation_results['theme_mapping']
    
    # 分析AI分组过多或过少的问题
    print("\n📊 分组数量分析:")
    
    # 计算平均每组新闻数
    true_avg_size = sum(len(events) for events in true_theme_groups.values()) / len(true_theme_groups)
    ai_avg_size = sum(len(events) for events in ai_theme_groups.values()) / len(ai_theme_groups)
    
    print(f"  真实数据平均每组: {true_avg_size:.1f} 条新闻")
    print(f"  AI分组平均每组: {ai_avg_size:.1f} 条新闻")
    
    if ai_avg_size > true_avg_size * 1.5:
        print("  ⚠️  AI分组过大，可能过度归并")
    elif ai_avg_size < true_avg_size * 0.5:
        print("  ⚠️  AI分组过小，可能过度细分")
    else:
        print("  ✅ 分组大小合理")
    
    # 分析未匹配的题材
    print("\n📌 未匹配或匹配较差的题材:")
    for true_theme, ai_theme in theme_mapping.items():
        similarity = evaluation_results['theme_similarities'].get(true_theme, 0)
        if ai_theme == "未匹配" or similarity < 0.4:
            print(f"  {true_theme}: 匹配到 '{ai_theme}', 相似度 {similarity:.2f}")

def generate_practical_recommendations(evaluation_results):
    """生成实用优化建议"""
    print("\n" + "=" * 70)
    print("🚀 实用优化建议")
    print("=" * 70)
    
    f1_score = evaluation_results['f1_score']
    cross_category_errors = evaluation_results['cross_category_errors']
    
    print(f"\n📈 当前评估结果:")
    print(f"  F1分数: {f1_score:.2%}")
    print(f"  Precision: {evaluation_results['precision']:.2%}")
    print(f"  Recall: {evaluation_results['recall']:.2%}")
    
    if f1_score >= 0.8:
        print("\n✅ 表现优秀！保持当前策略即可。")
    elif f1_score >= 0.6:
        print("\n⚠️  表现良好，但有优化空间。")
    else:
        print("\n❌ 表现不佳，需要重点优化。")
    
    print("\n🎯 基于内容的优化建议:")
    
    # 根据评估结果给出具体建议
    if evaluation_results['precision'] < evaluation_results['recall']:
        print("1. **解决过度归并问题** (Precision较低):")
        print("   • AI把不同类新闻归到同一组，需要提高区分度")
        print("   • 增加题材间的区分关键词")
        print("   • 降低判重引擎的相似度阈值")
    else:
        print("1. **解决过度细分问题** (Recall较低):")
        print("   • AI把同类新闻分到不同组，需要提高聚合能力")
        print("   • 放宽相同题材的判定标准")
        print("   • 增加题材的覆盖范围关键词")
    
    if cross_category_errors:
        print("\n2. **解决跨类错误问题**:")
        print("   • 建立题材间的互斥规则")
        print("   • 为容易混淆的题材设置特殊处理逻辑")
        for error in cross_category_errors[:3]:  # 显示前3个错误
            print(f"   • 禁止 {error['true_theme']} 分类到包含'{error['error_type'].split('→')[1]}'的题材")
    
    print("\n3. **算法优化建议**:")
    print("   • 实现基于内容的相似度聚类")
    print("   • 使用TF-IDF或BERT计算新闻相似度")
    print("   • 建立题材知识图谱，避免逻辑上不相关的归并")
    
    print("\n4. **业务规则优化**:")
    print("   • 明确每个题材的核心定义和边界")
    print("   • 建立'不允许归并'的题材对列表")
    print("   • 设置不同题材的优先级和权重")

def save_evaluation_report(data, evaluation_results):
    """保存评估报告"""
    from datetime import datetime
    
    report_dir = Path("evaluate_service/data/results/content_based_evaluation")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"content_based_evaluation_{timestamp}.json"
    
    # 准备报告数据
    report_data = {
        "metadata": {
            "evaluation_time": datetime.now().isoformat(),
            "evaluation_standard": "基于内容的分组准确性（不要求名称相同）",
            "total_news": len(data['raw_data']),
            "true_theme_count": len(data['true_theme_groups']),
            "ai_theme_count": len(data['ai_theme_groups'])
        },
        "metrics": {
            "precision": evaluation_results['precision'],
            "recall": evaluation_results['recall'],
            "f1_score": evaluation_results['f1_score'],
            "grouping_consistency": evaluation_results['grouping_consistency'],
            "reverse_consistency": evaluation_results['reverse_consistency']
        },
        "theme_mapping": evaluation_results['theme_mapping'],
        "theme_similarities": {k: float(v) for k, v in evaluation_results['theme_similarities'].items()},
        "cross_category_errors": evaluation_results['cross_category_errors'],
        "recommendations": [
            "优先解决跨类错误问题",
            "优化AI的分组逻辑，提高同类别新闻的聚合准确性",
            "不要求名称完全一致，但要求逻辑上正确的分组"
        ]
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 评估报告保存至: {report_file}")
    return report_file

def main():
    """主函数"""
    try:
        # 1. 加载数据
        data = load_datasets()
        if not data:
            return 1
        
        # 2. 基于内容的评估
        evaluation_results = evaluate_grouping_accuracy(data)
        
        # 3. 分析具体问题
        analyze_specific_problems(data, evaluation_results)
        
        # 4. 生成优化建议
        generate_practical_recommendations(evaluation_results)
        
        # 5. 保存报告
        report_file = save_evaluation_report(data, evaluation_results)
        
        print("\n" + "=" * 70)
        print("✅ 基于内容的评估完成！")
        print("=" * 70)
        print(f"\n📋 核心评估标准:")
        print("  1. 同类型新闻是否聚合在一起（最重要）")
        print("  2. 是否出现明显跨类错误（不允许）")
        print("  3. 不要求题材名称完全一致")
        print(f"\n📊 关键指标: F1分数 = {evaluation_results['f1_score']:.2%}")
        print(f"📁 报告文件: {report_file}")
        
    except Exception as e:
        print(f"❌ 评估失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    main()