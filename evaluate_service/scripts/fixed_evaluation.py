#!/usr/bin/env python3
"""
修复配置后的评估测试
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def create_fixed_config():
    """创建修复后的判重引擎配置"""
    fixed_config = {
        "thresholds": {
            "exact_match": 1.0,
            "inclusion_match": 0.6,
            "semantic_similarity": 0.55,
            "auto_merge": 0.65
        },
        "weights": {
            "name_similarity": 0.35,
            "keyword_overlap": 0.35,
            "industry_match": 0.20,
            "semantic_similarity": 0.10
        },
        "strategies": {
            "enable_exact_match": True,
            "enable_inclusion_check": True,
            "enable_semantic_analysis": True,  # 修复这个
            "use_jieba": True
        }
    }
    
    # 保存配置
    config_dir = Path("theme_service/config")
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = config_dir / "dedup_config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(fixed_config, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 修复配置已保存: {config_file}")
    return fixed_config

async def run_fixed_evaluation():
    """运行修复后的评估"""
    print("=" * 60)
    print("🔧 修复配置后的评估测试")
    print("=" * 60)
    
    # 1. 创建修复配置
    config = create_fixed_config()
    
    # 2. 加载数据
    dataset_path = "evaluate_service/data/processed/validation_events_enhanced.json"
    
    print("\n📂 加载数据集中...")
    with open(dataset_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    events = data.get('events', []) if isinstance(data, dict) else data
    test_events = events[:30]  # 测试30个事件
    
    print(f"✅ 加载 {len(test_events)} 个测试事件")
    
    # 3. 创建修复后的引擎
    try:
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        
        print("\n⚙️ 创建修复后的引擎...")
        dedup_engine = ThemeDeduplicationEngine(config=config)
        
        # 改进的AI客户端
        class ImprovedAIClient:
            async def analyze_event_with_context(self, event_data, related_themes):
                title = event_data.get('title', '').lower()
                
                # 基于内容的简单分类
                if '半导体' in title or '芯片' in title:
                    theme = "半导体"
                elif '人工智能' in title or 'AI' in title:
                    theme = "人工智能"
                elif '消费电子' in title or '智能穿戴' in title:
                    theme = "消费电子"
                elif '数据中心' in title or '云计算' in title:
                    theme = "数据中心"
                elif '卫星' in title or '航天' in title:
                    theme = "卫星通信"
                elif '核聚变' in title or '新能源' in title:
                    theme = "可控核聚变"
                elif '商业航天' in title or '火箭' in title:
                    theme = "商业航天"
                elif '深海' in title or '海洋' in title:
                    theme = "深海经济"
                elif '新材料' in title:
                    theme = "新材料"
                elif '高端制造' in title:
                    theme = "高端制造"
                else:
                    theme = "其他"
                
                return {
                    "decision": "CREATE_NEW",
                    "target_theme_name": f"{theme}主题",
                    "confidence": 0.8,
                    "reason": f"基于内容分类: {theme}",
                    "source": "improved_ai"
                }
        
        ai_client = ImprovedAIClient()
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            dedup_engine=dedup_engine,
            config={
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3
            }
        )
        
        print("✅ 引擎创建成功")
        
        # 4. 处理事件并分析
        print("\n🔄 处理事件中...")
        theme_results = {}
        
        for i, event in enumerate(test_events):
            # 显示进度
            percent = (i + 1) / len(test_events) * 100
            print(f"  进度: {i+1}/{len(test_events)} ({percent:.0f}%)", end='\r')
            
            # 添加theme_directive
            if 'theme_directive' not in event:
                event['theme_directive'] = {
                    "action": "CREATE_NEW",
                    "confidence": 0.8,
                    "reason": "评估测试"
                }
            
            # 处理事件
            try:
                result = await engine.process_single_event(event)
                
                # 记录主题分配
                theme_name = result.get('target_theme', 'unknown')
                if theme_name == 'unknown':
                    # 从AI决策中获取
                    ai_decision = result.get('ai_decision', {})
                    theme_name = ai_decision.get('target_theme_name', 'unknown')
                
                event_title = event.get('title', f'事件{i}')[:20]
                theme_results[event_title] = theme_name
                
            except Exception as e:
                print(f"\n   事件 {i} 处理失败: {e}")
                continue
        
        print(f"\n✅ 处理完成!")
        
        # 5. 分析结果
        print("\n📊 结果分析:")
        print("-" * 40)
        
        # 统计主题分布
        theme_distribution = {}
        for theme in theme_results.values():
            theme_distribution[theme] = theme_distribution.get(theme, 0) + 1
        
        # 显示主题分布
        print(f"检测到的主题数: {len(theme_distribution)}")
        print(f"期望的主题数: 10")
        print("\n主题分布:")
        for theme, count in sorted(theme_distribution.items(), key=lambda x: x[1], reverse=True):
            percentage = count / len(test_events) * 100
            print(f"  {theme}: {count} 个事件 ({percentage:.1f}%)")
        
        # 6. 检查聚类一致性
        print("\n🔍 聚类一致性检查:")
        print("-" * 40)
        
        # 按主题分组事件
        events_by_theme = {}
        for event_title, theme in theme_results.items():
            if theme not in events_by_theme:
                events_by_theme[theme] = []
            events_by_theme[theme].append(event_title)
        
        # 显示每个聚类的内容
        for theme, event_list in events_by_theme.items():
            print(f"\n📁 主题: {theme} ({len(event_list)}个事件)")
            for i, event in enumerate(event_list[:3]):  # 只显示前3个
                print(f"  {i+1}. {event}")
            if len(event_list) > 3:
                print(f"  ... 还有{len(event_list)-3}个事件")
        
        # 7. 评估指标
        print("\n📈 评估指标:")
        print("-" * 40)
        
        detected_theme_count = len(theme_distribution)
        expected_theme_count = 10
        
        print(f"1. 主题数量: {detected_theme_count}/10")
        if detected_theme_count < expected_theme_count:
            print(f"   ❌ 比期望少{expected_theme_count - detected_theme_count}个主题")
            print(f"   可能原因: 相似主题被合并")
        elif detected_theme_count > expected_theme_count:
            print(f"   ⚠️  比期望多{detected_theme_count - expected_theme_count}个主题")
            print(f"   可能原因: 主题划分过细")
        else:
            print(f"   ✅ 主题数量匹配")
        
        # 检查是否有明显错误分配
        error_examples = []
        for event_title, theme in theme_results.items():
            event_lower = event_title.lower()
            theme_lower = theme.lower()
            
            # 检查深海经济分配到AI/AR的错误
            if ('深海' in event_lower or '海洋' in event_lower) and ('ai' in theme_lower or 'ar' in theme_lower):
                error_examples.append({
                    "event": event_title,
                    "assigned_theme": theme,
                    "issue": "深海经济分配到AI/AR"
                })
        
        if error_examples:
            print(f"\n2. 发现 {len(error_examples)} 个错误分配:")
            for error in error_examples[:3]:
                print(f"   ❌ {error['event']}")
                print(f"     分配: {error['assigned_theme']}")
                print(f"     问题: {error['issue']}")
        else:
            print(f"\n2. ✅ 未发现明显的错误分配")
        
        # 8. 保存结果
        print("\n💾 保存结果中...")
        results_dir = Path("evaluate_service/data/results/fixed_evaluation")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = results_dir / f"fixed_evaluation_{timestamp}.json"
        
        results = {
            "metadata": {
                "test_time": datetime.now().isoformat(),
                "test_type": "修复配置评估",
                "total_events": len(test_events)
            },
            "config_used": config,
            "theme_distribution": theme_distribution,
            "events_by_theme": events_by_theme,
            "error_examples": error_examples,
            "metrics": {
                "detected_theme_count": detected_theme_count,
                "expected_theme_count": expected_theme_count,
                "theme_count_difference": abs(detected_theme_count - expected_theme_count),
                "error_count": len(error_examples)
            },
            "recommendations": [
                "1. 调整判重阈值以控制主题合并程度",
                "2. 改进AI决策逻辑以提高分类准确性",
                "3. 增加事件特征提取以提高聚类纯度"
            ]
        }
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 结果已保存: {results_file}")
        
        # 9. 最终建议
        print("\n" + "=" * 60)
        print("🎯 最终结论与建议")
        print("=" * 60)
        
        if detected_theme_count < 5:
            print(f"\n⚠️  主题数量过少 ({detected_theme_count}/10)")
            print("建议:")
            print("  1. 降低判重合并阈值")
            print("  2. 减少AI决策的合并倾向")
            print("  3. 增加新主题创建的敏感性")
        
        elif detected_theme_count > 15:
            print(f"\n⚠️  主题数量过多 ({detected_theme_count}/10)")
            print("建议:")
            print("  1. 提高判重合并阈值")
            print("  2. 增加AI决策的合并倾向")
            print("  3. 提高新主题创建的阈值")
        
        else:
            print(f"\n✅ 主题数量合理 ({detected_theme_count}/10)")
            print("建议:")
            print("  1. 微调参数优化聚类纯度")
            print("  2. 监控错误分配情况")
            print("  3. 持续优化AI分类逻辑")
        
        if error_examples:
            print(f"\n❌ 发现 {len(error_examples)} 个错误分配")
            print("建议:")
            print("  1. 加强领域知识识别")
            print("  2. 增加事件上下文分析")
            print("  3. 优化主题相似度计算")
        
        print(f"\n📋 下一步:")
        print("  1. 查看详细结果: {results_file}")
        print("  2. 根据建议调整系统参数")
        print("  3. 运行更多测试验证改进效果")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 评估失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("🔍 系统检查...")
    
    try:
        import json
        print("✅ 基础依赖正常")
    except Exception as e:
        print(f"❌ 依赖检查失败: {e}")
        return 1
    
    print("\n🚀 开始修复配置后的评估...")
    success = await run_fixed_evaluation()
    
    if success:
        print("\n🎉 评估完成！")
        return 0
    else:
        print("\n❌ 评估失败")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断")
        sys.exit(0)