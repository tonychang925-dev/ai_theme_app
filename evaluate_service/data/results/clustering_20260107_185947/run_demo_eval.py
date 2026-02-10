#!/usr/bin/env python3
"""
演示聚类评估 - 使用模拟数据
"""
import asyncio
import json
import random
from pathlib import Path
from datetime import datetime
import sys

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def generate_demo_dataset():
    """生成演示数据集"""
    themes = ["光刻胶", "卫星互联", "稀土永磁", "海洋经济", "对日制裁", "AI/AR眼镜", "可控核聚变"]
    
    dataset = []
    for i, theme in enumerate(themes):
        for j in range(3):  # 每个主题3个案例
            dataset.append({
                "test_id": f"demo_{theme}_{j}",
                "theme": theme,
                "ground_truth_themes": [theme],
                "title": f"{theme}相关事件示例 {j+1}",
                "content": f"这是关于{theme}的测试内容，用于演示聚类评估。",
                "summary": f"{theme}测试摘要",
                "event_type": "测试事件",
                "impact_industries": ["测试行业"]
            })
    
    return dataset

def generate_ai_results(dataset, accuracy=0.7):
    """生成模拟AI结果"""
    ai_results = []
    
    # 同义词映射
    synonym_map = {
        "光刻胶": ["光刻材料", "半导体材料"],
        "卫星互联": ["卫星互联网", "星链"],
        "稀土永磁": ["钕铁硼", "永磁材料"],
        "海洋经济": ["蓝色经济", "海洋产业"],
        "对日制裁": ["日本制裁", "出口管制"],
        "AI/AR眼镜": ["智能眼镜", "AR眼镜"],
        "可控核聚变": ["核聚变", "人造太阳"]
    }
    
    for case in dataset:
        event_id = case["test_id"]
        true_theme = case["theme"]
        
        discovered = []
        
        # 模拟AI准确率
        if random.random() < accuracy:
            discovered.append(true_theme)
            
            # 添加同义词
            synonyms = synonym_map.get(true_theme, [])
            if synonyms and random.random() < 0.5:
                discovered.append(random.choice(synonyms))
        else:
            # 错误识别
            other_themes = [t for t in synonym_map.keys() if t != true_theme]
            if other_themes:
                discovered.append(random.choice(other_themes))
        
        ai_results.append({
            "event_id": event_id,
            "discovered_themes": discovered,
            "confidence": random.uniform(0.6, 0.95)
        })
    
    return ai_results

async def main():
    print("🎭 聚类评估演示")
    print("=" * 50)
    
    # 生成数据
    dataset = generate_demo_dataset()
    print(f"📊 生成 {len(dataset)} 个演示案例")
    print(f"   覆盖 {len(set(c['theme'] for c in dataset))} 个主题")
    
    # 生成AI结果
    ai_results = generate_ai_results(dataset, accuracy=0.75)
    print(f"🤖 生成 {len(ai_results)} 个模拟AI结果")
    
    # 导入并运行评估器
    from evaluate_service.clustering_eval.clustering_evaluator import ClusteringEvaluator
    
    # 创建评估器
    config_path = Path(__file__).parent / "eval_config.yaml"
    evaluator = ClusteringEvaluator(str(config_path))
    evaluator.load_ground_truth(dataset)
    
    # 运行评估
    report = await evaluator.evaluate_ai_results(ai_results)
    
    # 输出结果
    print(f"\n📊 演示评估结果:")
    print("=" * 40)
    print(f"综合得分: {report['summary']['overall_score']:.3f}/1.0")
    print(f"评估等级: {report['summary']['evaluation_level']}")
    print(f"建议: {report['summary']['recommendation']}")
    
    print(f"\n📈 详细指标:")
    metrics = report['summary']['metrics_summary']
    for name, value in metrics.items():
        desc = {
            "clustering_precision": "聚类精度",
            "collection_completeness": "归集完整性",
            "theme_purity": "主题纯度",
            "theme_separation": "主题分离度",
            "event_coverage": "事件覆盖率"
        }.get(name, name)
        
        print(f"  {desc}: {value:.3f}")
    
    print(f"\n🎯 主题聚类效果:")
    analysis = report['detailed_analysis']
    successful = len(analysis.get('successful_clusters', []))
    mixed = len(analysis.get('mixed_clusters', []))
    problems = len(analysis.get('problem_cases', []))
    
    print(f"  ✅ 成功聚类: {successful} 个主题")
    print(f"  ⚠️  混合聚类: {mixed} 个主题")
    print(f"  ❌ 问题聚类: {problems} 个主题")
    
    print(f"\n💡 优化建议:")
    for suggestion in report['interpretation'].get('optimization_suggestions', [])[:3]:
        print(f"  • {suggestion}")
    
    # 保存演示报告
    output_file = Path(__file__).parent / "demo_report.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 演示报告已保存: {output_file}")
    
    return report

if __name__ == "__main__":
    asyncio.run(main())
