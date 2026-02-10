#!/usr/bin/env python3
"""
真实AI引擎评估器 - 连接实际的ThemeDiscoveryEngine
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("🎯 AI题材引擎真实评估")
print("=" * 50)

class RealThemeEvaluator:
    def __init__(self):
        self.engine = None
        self.initialized = False
    
    async def initialize(self):
        """初始化真实的ThemeDiscoveryEngine"""
        try:
            print("1. 🔧 导入真实AI引擎模块...")
            from theme_service.services.ai_client import AIThemeClient
            from theme_service.services.theme_discovery import ThemeDiscoveryEngine
            from theme_service.config import settings
            
            print("2. 🤖 创建AI客户端...")
            ai_client = AIThemeClient(settings)
            
            print("3. 🎯 创建主题发现引擎...")
            self.engine = ThemeDiscoveryEngine(ai_client)
            self.initialized = True
            
            # 检查是否使用模拟分析器
            if hasattr(ai_client, '_analyzer') and hasattr(ai_client._analyzer, 'mock'):
                print("   ⚠️  使用模拟分析器（可能缺少AI API配置）")
                return "mock"
            else:
                print("   ✅ 使用真实AI分析器")
                return "real"
            
        except ImportError as e:
            print(f"❌ 导入模块失败: {e}")
            print("请确保:")
            print("1. theme_service 模块在Python路径中")
            print("2. 所有依赖已安装")
            print("3. 数据库连接正常")
            return "error"
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            return "error"
    
    async def evaluate_single_event(self, test_case: Dict) -> Dict:
        """使用真实引擎评估单个事件"""
        if not self.initialized:
            mode = await self.initialize()
            if mode == "error":
                return {"error": "初始化失败", "success": False}
        
        # 构建模拟的news_event
        mock_event = {
            "id": test_case.get("test_id", "test_001"),
            "title": test_case.get("title", ""),
            "summary": test_case.get("content", "")[:200],
            "content": test_case.get("content", ""),
            "impact_industries": test_case.get("impact_industries", []),
            "event_type": test_case.get("event_type", "行业新闻")
        }
        
        theme = test_case.get("theme", "unknown")
        
        try:
            # 调用真实引擎
            result = await self.engine.process_single_event(mock_event)
            
            discovered = result.get("themes_found", [])
            confidence = result.get("confidence", 0.5)
            ground_truth = test_case.get("ground_truth_themes", [])
            
            # 检查是否正确识别
            is_correct = any(theme in discovered for theme in ground_truth)
            
            return {
                "test_id": test_case.get("test_id", "unknown"),
                "theme": theme,
                "discovered": discovered,
                "confidence": confidence,
                "ground_truth": ground_truth,
                "is_correct": is_correct,
                "success": True
            }
            
        except Exception as e:
            print(f"❌ 评估失败 {theme}: {e}")
            return {
                "test_id": test_case.get("test_id", "unknown"),
                "theme": theme,
                "error": str(e),
                "success": False
            }
    
    def calculate_metrics(self, results: List[Dict]) -> Dict:
        """计算评估指标"""
        theme_stats = {}
        total_cases = len(results)
        successful_cases = 0
        correct_cases = 0
        
        for result in results:
            if not result.get("success", False):
                continue
                
            theme = result["theme"]
            if theme not in theme_stats:
                theme_stats[theme] = {
                    "total": 0,
                    "correct": 0,
                    "discovered_list": [],
                    "ground_truth_list": []
                }
            
            theme_stats[theme]["total"] += 1
            
            # 检查是否正确识别
            if result.get("is_correct", False):
                theme_stats[theme]["correct"] += 1
                correct_cases += 1
            
            theme_stats[theme]["discovered_list"].append(result.get("discovered", []))
            theme_stats[theme]["ground_truth_list"].append(result.get("ground_truth", []))
            successful_cases += 1
        
        # 计算各题材指标
        theme_metrics = {}
        for theme, stats in theme_stats.items():
            total = stats["total"]
            correct = stats["correct"]
            
            if total > 0:
                accuracy = correct / total
            else:
                accuracy = 0
            
            theme_metrics[theme] = {
                "test_count": total,
                "correct_count": correct,
                "accuracy": round(accuracy, 3)
            }
        
        # 计算整体指标
        overall_accuracy = correct_cases / successful_cases if successful_cases > 0 else 0
        
        overall_metrics = {
            "total_cases": total_cases,
            "successful_cases": successful_cases,
            "correct_cases": correct_cases,
            "overall_accuracy": round(overall_accuracy, 3)
        }
        
        return {
            "theme_wise_metrics": theme_metrics,
            "overall_metrics": overall_metrics,
            "detailed_results": results
        }

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='真实AI引擎评估')
    parser.add_argument('--data_path', default='data/processed/validation_dataset.json', 
                       help='测试数据集路径')
    parser.add_argument('--output_dir', default='data/results', 
                       help='输出目录')
    parser.add_argument('--sample_size', type=int, default=20, 
                       help='采样数量（测试用）')
    args = parser.parse_args()
    
    # 加载测试数据
    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"❌ 数据文件不存在: {data_path}")
        return 1
    
    with open(data_path, 'r', encoding='utf-8') as f:
        all_cases = json.load(f)
    
    # 采样测试
    sample_size = min(args.sample_size, len(all_cases))
    sample_cases = all_cases[:sample_size]
    print(f"\n📊 使用 {len(sample_cases)} 个测试用例进行采样评估")
    
    # 初始化评估器
    evaluator = RealThemeEvaluator()
    
    # 运行评估
    print("🔬 开始真实评估...")
    results = []
    
    for i, test_case in enumerate(sample_cases, 1):
        theme = test_case.get("theme", f"测试{i}")
        print(f"  [{i}/{len(sample_cases)}] 处理: {theme}")
        result = await evaluator.evaluate_single_event(test_case)
        results.append(result)
    
    # 计算指标
    metrics = evaluator.calculate_metrics(results)
    
    # 保存结果
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = asyncio.get_event_loop().time()
    metrics_file = output_path / f"real_metrics_{int(timestamp)}.json"
    
    with open(metrics_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    # 生成摘要
    print(f"\n✅ 真实评估完成!")
    print(f"   结果保存至: {metrics_file}")
    
    overall = metrics["overall_metrics"]
    print(f"\n📊 评估结果摘要:")
    print(f"   总测试用例: {overall['total_cases']}")
    print(f"   成功处理数: {overall['successful_cases']}")
    print(f"   正确识别数: {overall['correct_cases']}")
    print(f"   整体准确率: {overall['overall_accuracy']:.1%}")
    
    # 显示各题材表现
    theme_metrics = metrics.get("theme_wise_metrics", {})
    if theme_metrics:
        print(f"\n🎯 各题材表现 (前5名):")
        sorted_themes = sorted(theme_metrics.items(), 
                              key=lambda x: x[1].get("accuracy", 0), 
                              reverse=True)
        
        for i, (theme, metrics_data) in enumerate(sorted_themes[:5], 1):
            acc = metrics_data.get("accuracy", 0)
            correct = metrics_data.get("correct_count", 0)
            total = metrics_data.get("test_count", 0)
            rank_icon = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'][i-1]
            print(f"   {rank_icon} {theme}: {acc:.1%} ({correct}/{total})")
    
    # 显示一些详细结果
    detailed_results = metrics.get("detailed_results", [])
    if detailed_results:
        correct_examples = [r for r in detailed_results if r.get("success") and r.get("is_correct")]
        wrong_examples = [r for r in detailed_results if r.get("success") and not r.get("is_correct")]
        
        if correct_examples:
            print(f"\n✅ 正确识别示例:")
            for r in correct_examples[:2]:
                print(f"   • {r.get('theme', 'unknown')}")
                print(f"     真实题材: {r.get('ground_truth', [])}")
                print(f"     发现题材: {r.get('discovered', [])}")
                print(f"     置信度: {r.get('confidence', 'N/A')}")
        
        if wrong_examples:
            print(f"\n❌ 错误识别示例:")
            for r in wrong_examples[:2]:
                print(f"   • {r.get('theme', 'unknown')}")
                print(f"     真实题材: {r.get('ground_truth', [])}")
                print(f"     发现题材: {r.get('discovered', [])}")
    
    return 0

if __name__ == '__main__':
    asyncio.run(main())
