#!/usr/bin/env python3
"""
快速针对性评估测试 - 带进度显示
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging
from collections import defaultdict

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 简化日志
logging.basicConfig(
    level=logging.WARNING,  # 降低日志级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class FastTargetedEvaluation:
    """快速评估版本"""
    
    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path)
        self.results_dir = Path("evaluate_service/data/results/fast_evaluation")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 简化配置
        self.dedup_config = {
            "thresholds": {
                "exact_match": 1.0,
                "inclusion_match": 0.6,
                "auto_merge": 0.65
            },
            "strategies": {
                "enable_exact_match": True,
                "enable_inclusion_check": True,
                "use_jieba": False  # 禁用分词以加速
            }
        }
    
    def load_dataset_quick(self):
        """快速加载数据集"""
        print("📂 快速加载数据集中...")
        
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            events = []
            if isinstance(data, dict) and 'events' in data:
                events = data['events']
            elif isinstance(data, list):
                events = data
            
            print(f"✅ 加载 {len(events)} 个事件")
            
            # 为每个事件分配一个简单的ground truth
            ground_truth = {}
            theme_categories = [
                '半导体', '人工智能', '消费电子', '新材料', '高端制造',
                '数据中心', '卫星通信', '可控核聚变', '商业航天', '深海经济'
            ]
            
            for i, event in enumerate(events):
                event_id = event.get('id', f'event_{i}')
                # 根据标题简单分配题材
                title = event.get('title', '').lower()
                
                assigned_theme = '其他'
                for theme in theme_categories:
                    if theme in title:
                        assigned_theme = theme
                        break
                
                ground_truth[event_id] = assigned_theme
            
            return {
                "events": events[:50],  # 只测试前50个以加速
                "ground_truth": ground_truth,
                "total_events": min(50, len(events))
            }
            
        except Exception as e:
            print(f"❌ 加载失败: {e}")
            return {"events": [], "ground_truth": {}, "total_events": 0}
    
    async def quick_evaluate(self, dataset_info):
        """快速评估"""
        print(f"\n🚀 开始快速评估 ({dataset_info['total_events']}个事件)")
        
        try:
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            
            # 创建简化引擎
            dedup_engine = ThemeDeduplicationEngine(config=self.dedup_config)
            
            class SimpleAIClient:
                async def analyze_event_with_context(self, event_data, related_themes):
                    # 简化AI决策
                    return {
                        "decision": "CREATE_NEW",
                        "target_theme_name": "测试主题",
                        "confidence": 0.7,
                        "reason": "快速测试",
                        "source": "fast_ai"
                    }
            
            ai_client = SimpleAIClient()
            engine = EnhancedThemeDiscoveryEngine(
                ai_client=ai_client,
                dedup_engine=dedup_engine,
                config={'fast_track_threshold': 0.9, 'review_threshold': 0.7}
            )
            
            print("✅ 引擎创建成功")
            
            # 处理事件（带进度显示）
            results = []
            theme_clusters = defaultdict(list)
            
            total = dataset_info['total_events']
            for i, event in enumerate(dataset_info['events']):
                # 显示进度
                percent = (i + 1) / total * 100
                print(f"  进度: {i+1}/{total} ({percent:.0f}%)", end='\r')
                
                # 处理事件
                try:
                    if 'theme_directive' not in event:
                        event['theme_directive'] = {
                            "action": "CREATE_NEW",
                            "confidence": 0.7,
                            "reason": "快速测试"
                        }
                    
                    result = await engine.process_single_event(event)
                    results.append(result)
                    
                    # 记录聚类结果
                    theme_name = result.get('target_theme', 'unknown')
                    event_id = event.get('id', f'event_{i}')
                    theme_clusters[theme_name].append(event_id)
                    
                except Exception as e:
                    print(f"\n   事件 {i} 处理失败: {e}")
                    continue
            
            print(f"\n✅ 处理完成!")
            
            # 简单分析结果
            analysis = self.quick_analysis(dataset_info['ground_truth'], theme_clusters)
            
            # 保存结果
            self.save_quick_results(analysis, dataset_info)
            
            return analysis
            
        except ImportError as e:
            print(f"❌ 导入模块失败: {e}")
            return {"error": "模块导入失败"}
        except Exception as e:
            print(f"❌ 评估失败: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    def quick_analysis(self, ground_truth, theme_clusters):
        """快速分析"""
        print("\n🔍 快速分析聚类结果...")
        
        # 1. 统计基本信息
        total_events = sum(len(cluster) for cluster in theme_clusters.values())
        theme_count = len(theme_clusters)
        
        print(f"   事件总数: {total_events}")
        print(f"   聚类数量: {theme_count}")
        print(f"   期望聚类: 10")
        
        # 2. 简单的一致性检查
        consistency_score = 0
        if theme_clusters:
            # 计算每个聚类的主要题材
            for theme_name, event_ids in theme_clusters.items():
                if event_ids:
                    # 统计这些事件在ground truth中的题材分布
                    theme_counts = defaultdict(int)
                    for event_id in event_ids:
                        if event_id in ground_truth:
                            theme_counts[ground_truth[event_id]] += 1
                    
                    if theme_counts:
                        # 主要题材的比例
                        main_theme, main_count = max(theme_counts.items(), key=lambda x: x[1])
                        purity = main_count / len(event_ids)
                        consistency_score += purity
            
            consistency_score /= len(theme_clusters)
        
        # 3. 错误示例
        error_examples = []
        for theme_name, event_ids in theme_clusters.items():
            if len(event_ids) > 0:
                # 检查第一个事件
                sample_id = event_ids[0]
                if sample_id in ground_truth:
                    expected = ground_truth[sample_id]
                    error_examples.append({
                        "event_id": sample_id,
                        "assigned_theme": theme_name,
                        "expected_theme": expected
                    })
        
        return {
            "total_events": total_events,
            "detected_themes": theme_count,
            "expected_themes": 10,
            "consistency_score": consistency_score,
            "error_examples": error_examples[:5],  # 只显示前5个
            "theme_sizes": {k: len(v) for k, v in theme_clusters.items()}
        }
    
    def save_quick_results(self, analysis, dataset_info):
        """保存快速结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        report = {
            "metadata": {
                "test_time": datetime.now().isoformat(),
                "test_type": "快速聚类评估",
                "total_events": dataset_info['total_events']
            },
            "results": analysis,
            "recommendations": self.generate_quick_recommendations(analysis)
        }
        
        # 保存JSON
        json_file = self.results_dir / f"quick_report_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 结果已保存: {json_file}")
        
        # 打印摘要
        self.print_quick_summary(analysis)
        
        return json_file
    
    def generate_quick_recommendations(self, analysis):
        """生成快速建议"""
        recommendations = []
        
        theme_diff = analysis['expected_themes'] - analysis['detected_themes']
        
        if theme_diff > 0:
            recommendations.append(
                f"检测到{analysis['detected_themes']}个主题，比期望少{theme_diff}个。"
                "可能原因：1) 相似主题被合并；2) 事件特征不足；3) 判重阈值过高"
            )
        elif theme_diff < 0:
            recommendations.append(
                f"检测到{analysis['detected_themes']}个主题，比期望多{-theme_diff}个。"
                "可能原因：1) 主题划分过细；2) 事件特征识别过于敏感；3) 判重阈值过低"
            )
        
        if analysis['consistency_score'] < 0.7:
            recommendations.append(
                f"聚类一致性较低({analysis['consistency_score']:.1%})，建议："
                "1. 优化事件特征提取；2. 调整相似度计算；3. 改进AI决策逻辑"
            )
        
        return recommendations
    
    def print_quick_summary(self, analysis):
        """打印快速摘要"""
        print("\n" + "=" * 60)
        print("📊 快速评估摘要")
        print("=" * 60)
        
        print(f"\n🎯 核心指标:")
        print(f"   事件总数: {analysis['total_events']}")
        print(f"   检测主题数: {analysis['detected_themes']}")
        print(f"   期望主题数: {analysis['expected_themes']}")
        print(f"   一致性得分: {analysis['consistency_score']:.1%}")
        
        print(f"\n📈 聚类大小分布:")
        for theme, size in sorted(analysis['theme_sizes'].items(), 
                                key=lambda x: x[1], reverse=True)[:5]:
            print(f"   {theme}: {size} 个事件")
        
        if analysis.get('error_examples'):
            print(f"\n⚠️  错误示例:")
            for error in analysis['error_examples'][:3]:
                print(f"   事件 {error['event_id'][:20]}...")
                print(f"     分配到: {error['assigned_theme']}")
                print(f"     期望是: {error['expected_theme']}")
        
        print(f"\n💡 建议:")
        recommendations = self.generate_quick_recommendations(analysis)
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
        
        print("\n✅ 快速评估完成！")
    
    async def run(self):
        """运行快速评估"""
        print("=" * 60)
        print("⚡ 快速聚类一致性评估")
        print("=" * 60)
        
        # 1. 快速加载数据
        dataset = self.load_dataset_quick()
        if not dataset['events']:
            return False
        
        # 2. 快速评估
        analysis = await self.quick_evaluate(dataset)
        
        if 'error' in analysis:
            print(f"❌ 评估失败: {analysis['error']}")
            return False
        
        return True


async def main():
    """主函数"""
    # 检查基本依赖
    try:
        print("🔍 检查系统状态...")
        import json
        print("✅ 基础依赖正常")
    except Exception as e:
        print(f"❌ 依赖检查失败: {e}")
        return 1
    
    # 数据集路径
    dataset_path = "evaluate_service/data/processed/validation_events_enhanced.json"
    
    if not Path(dataset_path).exists():
        print(f"❌ 数据集不存在: {dataset_path}")
        return 1
    
    # 创建评估器
    evaluator = FastTargetedEvaluation(dataset_path)
    
    try:
        print("\n⏳ 开始快速评估...")
        success = await evaluator.run()
        
        if success:
            print("\n🎉 快速评估成功完成！")
            print("\n📋 下一步:")
            print("   1. 查看生成的JSON报告")
            print("   2. 根据建议调整系统参数")
            print("   3. 运行完整评估获取详细分析")
            return 0
        else:
            print("\n❌ 快速评估失败")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断评估")
        return 1
    except Exception as e:
        print(f"\n❌ 评估异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # 设置异步事件循环
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
        sys.exit(0)