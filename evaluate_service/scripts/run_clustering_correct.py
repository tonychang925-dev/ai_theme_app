#!/usr/bin/env python3
"""
正确的聚类评估脚本 - 使用正确的数据路径
"""
import json
import random
import os
from pathlib import Path
from datetime import datetime
import statistics
from collections import defaultdict, Counter

def load_dataset():
    """加载数据集 - 使用正确的路径"""
    # 正确路径：ai_theme_app/evaluate_service/data/processed/validation_dataset.json
    data_file = Path("evaluate_service/data/processed/validation_dataset.json")
    
    if not data_file.exists():
        print(f"❌ 数据文件不存在: {data_file}")
        print("当前工作目录:", Path.cwd())
        print("尝试查找文件...")
        
        # 在项目目录中查找
        for file_path in Path.cwd().rglob("validation_dataset.json"):
            print(f"找到文件: {file_path}")
            data_file = file_path
            break
    
    print(f"📂 加载数据文件: {data_file}")
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ 加载成功: {len(data)} 个测试案例")
        
        # 统计主题分布
        theme_counts = Counter()
        for case in data:
            theme = case.get("theme", "unknown")
            theme_counts[theme] += 1
        
        print("📊 主题分布:")
        for theme, count in theme_counts.most_common():
            print(f"  {theme}: {count}个案例")
        
        return data
        
    except Exception as e:
        print(f"❌ 加载数据失败: {e}")
        return []

def simulate_ai_results(dataset, accuracy=0.65):
    """模拟AI结果"""
    ai_results = []
    
    # 基于历史测试的主题准确率
    theme_accuracy = {
        "AI/AR眼镜": 0.85,      # 优秀
        "SpaceX": 0.90,         # 优秀
        "可控核聚变": 0.75,      # 良好
        "对日制裁": 0.55,        # 需改进
        "稀土永磁": 0.60,        # 需改进
        "海洋经济": 0.50,        # 需改进
        "光刻胶": 0.70,          # 一般
        "卫星互联": 0.65,        # 一般
        "液冷数据中心": 0.65,    # 一般
        "AI智能体Manus": 0.70   # 一般
    }
    
    # 主题同义词映射
    synonyms = {
        "AI/AR眼镜": ["智能眼镜", "AR眼镜", "混合现实眼镜", "MR眼镜", "XR设备"],
        "卫星互联": ["卫星互联网", "星链", "低轨卫星", "卫星通信", "卫星星座"],
        "光刻胶": ["光刻材料", "光阻剂", "半导体光刻胶", "光刻胶材料", "KrF光刻胶"],
        "稀土永磁": ["钕铁硼", "永磁材料", "稀土磁材", "磁性材料", "高性能磁体"],
        "海洋经济": ["蓝色经济", "海洋产业", "海洋资源", "海洋开发", "海上风电"],
        "对日制裁": ["日本制裁", "出口管制", "贸易限制", "半导体禁运", "技术封锁"],
        "SpaceX": ["太空探索", "商业航天", "火箭发射", "卫星互联网", "马斯克"],
        "可控核聚变": ["核聚变", "人造太阳", "聚变能源", "托卡马克", "ITER"],
        "液冷数据中心": ["液冷服务器", "浸没式冷却", "数据中心冷却", "液冷技术", "绿色数据中心"],
        "AI智能体Manus": ["Manus AI", "人形机器人", "具身智能", "机器人智能体", "通用机器人"]
    }
    
    print("🤖 生成模拟AI结果（基于历史表现）...")
    
    for i, case in enumerate(dataset):
        event_id = case.get("test_id", f"case_{i}")
        true_theme = case.get("theme", "unknown")
        
        discovered = []
        
        # 获取该主题的准确率
        accuracy = theme_accuracy.get(true_theme, 0.65)
        
        # 模拟AI识别
        if random.random() < accuracy:
            # 正确识别
            discovered.append(true_theme)
            
            # 可能添加同义词
            if true_theme in synonyms and random.random() < 0.4:
                discovered.append(random.choice(synonyms[true_theme]))
        else:
            # 错误识别或漏识别
            if random.random() < 0.7:  # 70%概率错误识别
                # 错误识别为其他主题
                other_themes = [t for t in synonyms.keys() if t != true_theme]
                if other_themes:
                    discovered.append(random.choice(other_themes))
            # 30%概率完全漏识别
        
        # 确保至少有一个主题
        if not discovered and random.random() < 0.8:
            discovered.append(true_theme)
        
        ai_results.append({
            "event_id": event_id,
            "discovered_themes": discovered,
            "confidence": random.uniform(0.6, 0.95),
            "true_theme": true_theme  # 用于调试
        })
    
    print(f"✅ 生成 {len(ai_results)} 个AI结果")
    
    # 统计AI结果质量
    correct_count = sum(1 for r in ai_results if r["true_theme"] in r["discovered_themes"])
    print(f"📈 AI准确率: {correct_count/len(ai_results):.1%} ({correct_count}/{len(ai_results)})")
    
    return ai_results

def standardize_theme_name(theme):
    """标准化主题名称"""
    synonym_map = {
        "智能眼镜": "AI/AR眼镜",
        "AR眼镜": "AI/AR眼镜",
        "AI眼镜": "AI/AR眼镜",
        "卫星互联网": "卫星互联",
        "星链": "卫星互联",
        "光刻材料": "光刻胶",
        "光阻剂": "光刻胶",
        "稀土磁材": "稀土永磁",
        "钕铁硼": "稀土永磁",
        "蓝色经济": "海洋经济",
        "海洋产业": "海洋经济",
        "日本制裁": "对日制裁",
        "出口管制": "对日制裁",
        "太空探索": "SpaceX",
        "商业航天": "SpaceX",
        "核聚变": "可控核聚变",
        "人造太阳": "可控核聚变",
        "液冷服务器": "液冷数据中心",
        "浸没式冷却": "液冷数据中心",
        "Manus AI": "AI智能体Manus",
        "人形机器人": "AI智能体Manus"
    }
    return synonym_map.get(theme, theme)

def evaluate_clustering(dataset, ai_results):
    """评估聚类效果"""
    print("\n🔍 开始聚类评估...")
    print("评估重点：事件归集能力，而非名称相似度")
    
    # 1. 建立真实标签映射
    true_theme_events = defaultdict(set)
    event_true_themes = {}
    
    for i, case in enumerate(dataset):
        event_id = case.get("test_id", f"case_{i}")
        true_theme = case.get("theme", "unknown")
        ground_truth = case.get("ground_truth_themes", [true_theme])
        
        event_true_themes[event_id] = ground_truth
        for theme in ground_truth:
            true_theme_events[theme].add(event_id)
    
    print(f"📊 真实主题: {len(true_theme_events)} 个")
    
    # 2. 建立AI聚类映射
    ai_theme_events = defaultdict(set)
    event_ai_themes = {}
    
    for result in ai_results:
        event_id = result["event_id"]
        discovered = result["discovered_themes"]
        
        # 标准化AI主题名称
        standardized = [standardize_theme_name(t) for t in discovered]
        event_ai_themes[event_id] = standardized
        
        for theme in standardized:
            ai_theme_events[theme].add(event_id)
    
    print(f"📊 AI发现主题: {len(ai_theme_events)} 个")
    
    # 3. 计算聚类精度（同一真实主题的事件被归到同一AI主题的比例）
    print("\n📈 计算聚类精度...")
    clustering_scores = []
    theme_clustering_details = {}
    
    for true_theme, true_events in true_theme_events.items():
        if len(true_events) < 2:
            continue  # 需要至少2个事件才能评估聚类
        
        # 统计这些事件在AI中的主题分布
        theme_counter = Counter()
        for event_id in true_events:
            if event_id in event_ai_themes:
                for ai_theme in event_ai_themes[event_id]:
                    theme_counter[ai_theme] += 1
        
        if not theme_counter:
            clustering_scores.append(0.0)
            theme_clustering_details[true_theme] = {
                "score": 0.0,
                "reason": "无AI主题匹配",
                "event_count": len(true_events)
            }
            continue
        
        # 计算主要AI主题的覆盖率
        most_common_ai, most_common_count = theme_counter.most_common(1)[0]
        precision = most_common_count / len(true_events)
        clustering_scores.append(precision)
        
        theme_clustering_details[true_theme] = {
            "score": precision,
            "primary_ai_theme": most_common_ai,
            "coverage": f"{most_common_count}/{len(true_events)}",
            "ai_themes": dict(theme_counter.most_common(3)),
            "event_count": len(true_events)
        }
    
    clustering_precision = statistics.mean(clustering_scores) if clustering_scores else 0.0
    
    # 4. 计算归集完整性（真实主题的事件有多少被AI发现）
    print("📈 计算归集完整性...")
    completeness_scores = []
    
    for true_theme, true_events in true_theme_events.items():
        matched_events = set()
        std_true_theme = standardize_theme_name(true_theme)
        
        # 查找AI中对应的主题
        for ai_theme, ai_events in ai_theme_events.items():
            std_ai_theme = standardize_theme_name(ai_theme)
            if std_true_theme == std_ai_theme:
                matched_events.update(ai_events)
        
        # 计算覆盖率
        if true_events:
            coverage = len(matched_events & true_events) / len(true_events)
            completeness_scores.append(coverage)
    
    collection_completeness = statistics.mean(completeness_scores) if completeness_scores else 0.0
    
    # 5. 计算事件覆盖率
    print("📈 计算事件覆盖率...")
    covered_events = 0
    for event_id, true_themes in event_true_themes.items():
        if event_id not in event_ai_themes:
            continue
        
        ai_themes = event_ai_themes[event_id]
        matched = False
        
        for true_theme in true_themes:
            std_true_theme = standardize_theme_name(true_theme)
            for ai_theme in ai_themes:
                std_ai_theme = standardize_theme_name(ai_theme)
                if std_true_theme == std_ai_theme:
                    matched = True
                    break
            if matched:
                break
        
        if matched:
            covered_events += 1
    
    event_coverage = covered_events / len(event_true_themes) if event_true_themes else 0.0
    
    # 6. 综合得分
    overall_score = (
        clustering_precision * 0.5 +
        collection_completeness * 0.3 +
        event_coverage * 0.2
    )
    
    # 7. 分析各主题表现
    theme_performance = {}
    problem_themes = []
    good_themes = []
    
    for true_theme, details in theme_clustering_details.items():
        if details["event_count"] >= 3:  # 只分析有足够事件的真实主题
            consistency = details["score"]
            theme_performance[true_theme] = {
                "consistency": consistency,
                "event_count": details["event_count"],
                "primary_ai_theme": details.get("primary_ai_theme", "无"),
                "coverage": details.get("coverage", "0/0")
            }
            
            if consistency >= 0.7:
                good_themes.append(true_theme)
            elif consistency < 0.5:
                problem_themes.append(true_theme)
    
    return {
        "clustering_precision": clustering_precision,
        "collection_completeness": collection_completeness,
        "event_coverage": event_coverage,
        "overall_score": overall_score,
        "theme_performance": theme_performance,
        "theme_clustering_details": theme_clustering_details,
        "problem_themes": problem_themes,
        "good_themes": good_themes,
        "ai_clusters": len(ai_theme_events),
        "true_clusters": len(true_theme_events)
    }

def generate_report(results, dataset):
    """生成评估报告"""
    print("\n" + "=" * 60)
    print("📊 聚类评估结果")
    print("=" * 60)
    
    overall = results["overall_score"]
    precision = results["clustering_precision"]
    completeness = results["collection_completeness"]
    coverage = results["event_coverage"]
    
    print(f"综合得分: {overall:.3f}/1.0")
    print(f"聚类精度: {precision:.3f}")
    print(f"归集完整性: {completeness:.3f}")
    print(f"事件覆盖率: {coverage:.3f}")
    
    # 评估等级
    if overall >= 0.8:
        level = "✅ 优秀"
        recommendation = "可以直接用于生产环境"
        color = "#4CAF50"
        business_value = "主题聚类效果优秀，可以支持自动化投资组合构建和主题跟踪"
    elif overall >= 0.7:
        level = "⚠️  良好"
        recommendation = "可以在监控下用于生产"
        color = "#8BC34A"
        business_value = "主题聚类效果良好，可以支持半自动化的主题投资分析"
    elif overall >= 0.6:
        level = "📝 一般"
        recommendation = "需要人工复核和优化"
        color = "#FFC107"
        business_value = "主题聚类效果一般，需要结合人工判断进行投资决策"
    else:
        level = "❌ 需改进"
        recommendation = "需要重点优化后再评估"
        color = "#F44336"
        business_value = "主题聚类效果需要改进，暂时不建议直接用于投资决策"
    
    print(f"\n🎯 评估等级: {level}")
    print(f"💡 建议: {recommendation}")
    print(f"💼 业务价值: {business_value}")
    
    # 主题表现
    print(f"\n📈 各主题聚类表现:")
    theme_perf = results["theme_performance"]
    
    sorted_themes = sorted(
        theme_perf.items(),
        key=lambda x: x[1]["consistency"],
        reverse=True
    )
    
    for theme, perf in sorted_themes:
        consistency = perf["consistency"]
        count = perf["event_count"]
        primary_ai = perf["primary_ai_theme"]
        
        if consistency >= 0.8:
            rating = "✅ 优秀"
        elif consistency >= 0.6:
            rating = "⚠️  良好"
        elif consistency >= 0.4:
            rating = "📝 一般"
        else:
            rating = "❌ 需改进"
        
        print(f"  {rating} {theme}: {consistency:.1%} ({count}事件) → {primary_ai}")
    
    # 问题主题
    if results["problem_themes"]:
        print(f"\n🔧 需要重点优化的主题:")
        for theme in results["problem_themes"][:5]:
            perf = theme_perf.get(theme, {})
            consistency = perf.get("consistency", 0)
            print(f"  • {theme}: 聚类一致性仅{consistency:.1%}")
    
    # 良好主题
    if results["good_themes"]:
        print(f"\n🎉 表现良好的主题:")
        for theme in results["good_themes"][:5]:
            perf = theme_perf.get(theme, {})
            consistency = perf.get("consistency", 0)
            print(f"  • {theme}: 聚类一致性{consistency:.1%}")
    
    # 生成HTML报告
    print(f"\n💾 生成报告...")
    
    # 创建报告目录
    report_dir = Path("clustering_evaluation_results")
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 保存详细JSON报告
    json_report = {
        "metadata": {
            "evaluation_id": f"clustering_eval_{timestamp}",
            "evaluation_time": datetime.now().isoformat(),
            "evaluation_focus": "事件归集能力评估",
            "dataset_size": len(dataset),
            "data_source": "evaluate_service/data/processed/validation_dataset.json"
        },
        "summary": {
            "overall_score": overall,
            "clustering_precision": precision,
            "collection_completeness": completeness,
            "event_coverage": coverage,
            "evaluation_level": level,
            "recommendation": recommendation,
            "business_value": business_value
        },
        "theme_analysis": {
            "total_themes": len(theme_perf),
            "good_themes": len(results["good_themes"]),
            "problem_themes": len(results["problem_themes"]),
            "theme_performance": theme_perf,
            "clustering_details": results["theme_clustering_details"]
        },
        "cluster_stats": {
            "true_clusters": results["true_clusters"],
            "ai_clusters": results["ai_clusters"],
            "clusters_ratio": results["ai_clusters"] / results["true_clusters"] if results["true_clusters"] > 0 else 0
        }
    }
    
    json_file = report_dir / f"clustering_report_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False, default=str)
    
    # 生成HTML报告
    html_content = generate_html_report(json_report, color)
    html_file = report_dir / f"clustering_report_{timestamp}.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✅ 报告已生成:")
    print(f"  📄 JSON报告: {json_file}")
    print(f"  🌐 HTML报告: {html_file}")
    
    return json_file, html_file

def generate_html_report(report_data, color):
    """生成HTML报告"""
    summary = report_data["summary"]
    theme_analysis = report_data["theme_analysis"]
    
    # 生成主题条形图HTML
    theme_bars = ""
    sorted_perf = sorted(
        theme_analysis["theme_performance"].items(),
        key=lambda x: x[1]["consistency"],
        reverse=True
    )
    
    for theme, perf in sorted_perf[:15]:  # 最多显示15个
        consistency = perf["consistency"]
        width = consistency * 100
        
        if consistency >= 0.8:
            bar_color = "#4CAF50"
            rating = "✅ 优秀"
        elif consistency >= 0.6:
            bar_color = "#FF9800"
            rating = "⚠️ 良好"
        elif consistency >= 0.4:
            bar_color = "#FFC107"
            rating = "📝 一般"
        else:
            bar_color = "#F44336"
            rating = "❌ 需改进"
        
        theme_bars += f'''
        <div style="display: flex; align-items: center; margin: 10px 0;">
            <div style="width: 180px; font-weight: bold;">{theme}</div>
            <div style="flex: 1; height: 20px; background: #e0e0e0; border-radius: 10px; overflow: hidden; margin: 0 20px;">
                <div style="width: {width}%; height: 100%; background: {bar_color};"></div>
            </div>
            <div style="width: 100px; text-align: right;">
                <span style="font-weight: bold;">{consistency:.1%}</span>
                <div style="font-size: 12px; color: #666;">{rating}</div>
            </div>
        </div>
        '''
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>AI主题聚类评估报告</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .header {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 30px; }}
            .score-display {{ text-align: center; margin: 40px 0; }}
            .score {{ font-size: 96px; font-weight: 800; margin: 0; color: {color}; line-height: 1; }}
            .rating {{ font-size: 28px; font-weight: 600; margin: 10px 0 20px; color: {color}; }}
            .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin: 40px 0; }}
            .metric-card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
            .metric-value {{ font-size: 42px; font-weight: 700; margin: 10px 0; }}
            .metric-label {{ font-size: 16px; color: #666; margin-top: 5px; }}
            .theme-chart {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 30px 0; }}
            .recommendation {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 30px 0; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 20px 0; }}
            h1, h2, h3 {{ color: #333; }}
            h1 {{ font-size: 32px; margin-bottom: 10px; }}
            h2 {{ font-size: 24px; margin: 30px 0 20px; }}
            h3 {{ font-size: 18px; margin: 20px 0 10px; }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: 600; }}
            .badge-success {{ background: #4CAF50; color: white; }}
            .badge-warning {{ background: #FF9800; color: white; }}
            .badge-error {{ background: #F44336; color: white; }}
            .badge-info {{ background: #2196F3; color: white; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 AI主题聚类能力评估报告</h1>
                <p style="color: #666; font-size: 16px; margin-top: 5px;">
                    评估时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 
                    数据集: {report_data['metadata']['dataset_size']}个案例 |
                    评估重点: 事件归集能力（非名称相似度）
                </p>
            </div>
            
            <div class="score-display">
                <div class="score">{summary['overall_score']:.3f}</div>
                <div class="rating">{summary['evaluation_level']}</div>
                <p style="font-size: 18px; color: #666; max-width: 600px; margin: 0 auto;">
                    {summary['recommendation']}
                </p>
            </div>
            
            <div class="metrics">
                <div class="metric-card">
                    <div class="metric-value" style="color: #4CAF50;">{summary['clustering_precision']:.3f}</div>
                    <div class="metric-label">聚类精度</div>
                    <p style="color: #666; margin-top: 10px; font-size: 14px;">
                        同一真实主题的事件被归到同一AI主题的比例
                    </p>
                </div>
                
                <div class="metric-card">
                    <div class="metric-value" style="color: #2196F3;">{summary['collection_completeness']:.3f}</div>
                    <div class="metric-label">归集完整性</div>
                    <p style="color: #666; margin-top: 10px; font-size: 14px;">
                        真实主题的事件被AI发现的比例
                    </p>
                </div>
                
                <div class="metric-card">
                    <div class="metric-value" style="color: #9C27B0;">{summary['event_coverage']:.3f}</div>
                    <div class="metric-label">事件覆盖率</div>
                    <p style="color: #666; margin-top: 10px; font-size: 14px;">
                        被正确标记的事件比例
                    </p>
                </div>
            </div>
            
            <div class="stat-card">
                <h3>📊 集群统计</h3>
                <div style="display: flex; gap: 30px; margin-top: 15px;">
                    <div>
                        <div style="font-size: 28px; font-weight: 700;">{theme_analysis['total_themes']}</div>
                        <div style="color: #666;">总主题数</div>
                    </div>
                    <div>
                        <div style="font-size: 28px; font-weight: 700; color: #4CAF50;">{theme_analysis['good_themes']}</div>
                        <div style="color: #666;">良好主题</div>
                    </div>
                    <div>
                        <div style="font-size: 28px; font-weight: 700; color: #F44336;">{theme_analysis['problem_themes']}</div>
                        <div style="color: #666;">问题主题</div>
                    </div>
                    <div>
                        <div style="font-size: 28px; font-weight: 700; color: #2196F3;">{report_data['cluster_stats']['ai_clusters']}</div>
                        <div style="color: #666;">AI发现主题</div>
                    </div>
                </div>
            </div>
            
            <div class="theme-chart">
                <h2>📈 各主题聚类表现</h2>
                <p style="color: #666; margin-bottom: 20px;">
                    显示各主题的聚类一致性（同一主题事件被归到同一AI主题的比例）
                </p>
                {theme_bars}
            </div>
            
            <div class="recommendation">
                <h2>💡 业务价值与优化建议</h2>
                <p style="font-size: 16px; line-height: 1.6; margin: 15px 0;">
                    <strong>业务价值:</strong> {summary['business_value']}
                </p>
                
                <h3 style="margin-top: 25px;">优化建议:</h3>
                <ol style="line-height: 1.8; padding-left: 20px;">
    '''
    
    # 添加优化建议
    suggestions = []
    
    if summary['overall_score'] < 0.7:
        suggestions.append("重点优化问题主题的识别算法，提高聚类一致性")
    
    if summary['clustering_precision'] < 0.7:
        suggestions.append("优化同类事件的归集精度，减少主题分散")
    
    if summary['collection_completeness'] < 0.7:
        suggestions.append("扩展同义词库和关键词匹配，提高事件发现率")
    
    if theme_analysis['problem_themes'] > 0:
        suggestions.append("针对问题主题进行专项优化和测试")
    
    suggestions.append("集成真实AI模型进行正式评估和验证")
    suggestions.append("建立持续评估、监控和优化流程")
    
    for suggestion in suggestions:
        html += f'<li>{suggestion}</li>\n'
    
    html += '''
                </ol>
            </div>
            
            <div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-top: 30px;">
                <h3>📋 评估说明</h3>
                <p style="color: #666; line-height: 1.6;">
                    • 此评估基于76个真实测试案例，涵盖10个投资主题<br>
                    • 评估重点为<strong>事件归集能力</strong>，而非名称相似度<br>
                    • AI结果基于历史表现模拟生成，用于验证评估框架<br>
                    • 实际应用前需集成真实AI模型进行正式评估
                </p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return html

def main():
    print("🎯 AI主题聚类能力评估")
    print("=" * 60)
    print("评估重点：事件归集能力，而非名称相似度")
    print("数据路径：evaluate_service/data/processed/validation_dataset.json")
    print("=" * 60)
    
    # 1. 加载数据
    dataset = load_dataset()
    if not dataset:
        print("❌ 无法加载数据集，程序退出")
        return
    
    # 2. 模拟AI结果（基于历史表现）
    ai_results = simulate_ai_results(dataset)
    
    # 3. 评估聚类效果
    results = evaluate_clustering(dataset, ai_results)
    
    # 4. 生成报告
    json_file, html_file = generate_report(results, dataset)
    
    print("\n" + "=" * 60)
    print("🎉 评估完成!")
    print(f"   综合得分: {results['overall_score']:.3f}/1.0")
    print(f"   评估等级: {results['overall_score']:.3f} -> ", end="")
    if results['overall_score'] >= 0.8:
        print("✅ 优秀")
    elif results['overall_score'] >= 0.7:
        print("⚠️  良好")
    elif results['overall_score'] >= 0.6:
        print("📝 一般")
    else:
        print("❌ 需改进")
    print(f"   报告文件: {json_file}, {html_file}")
    print("=" * 60)
    
    # 打开HTML报告
    try:
        import webbrowser
        webbrowser.open(f"file://{html_file.absolute()}")
        print("🌐 正在浏览器中打开HTML报告...")
    except:
        print(f"📁 请手动打开HTML报告: {html_file}")

if __name__ == "__main__":
    main()
