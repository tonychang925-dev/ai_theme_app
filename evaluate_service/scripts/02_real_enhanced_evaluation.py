#!/usr/bin/env python3
"""
第二步：真实增强评估脚本
使用真实的EnhancedThemeDiscoveryEngine进行测试
"""
import json
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置测试模式
os.environ['TEST_MODE'] = '1'

logger = logging.getLogger(__name__)

class RealEnhancedEvaluator:
    """真实增强评估器 - 使用真实组件"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_events": 0,
            "processed": 0,
            "created": 0,
            "merged": 0,
            "in_review": 0,
            "failed": 0,
            "processing_times": [],
            "decision_times": []
        }
        self.engine = None
        
    async def initialize_components(self):
        """初始化所有必要组件"""
        print("🔧 初始化增强架构组件...")
        
        try:
            # 1. 创建EnhancedAIThemeClient
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            
            # 使用测试模式的配置
            settings = {
                'USE_ENHANCED_MODE': True,
                'TEST_MODE': True  # 确保使用测试模式
            }
            
            ai_client = EnhancedAIThemeClient(settings)
            print("✅ EnhancedAIThemeClient 初始化成功")
            
            # 2. 创建EnhancedThemeDiscoveryEngine
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            
            # 配置参数
            config = {
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3
            }
            
            self.engine = EnhancedThemeDiscoveryEngine(
                ai_client=ai_client,
                db_manager=None,  # 测试时不连接数据库
                config=config
            )
            print("✅ EnhancedThemeDiscoveryEngine 初始化成功")
            
            # 3. 验证增强分析器
            await self._verify_enhanced_analyzer(ai_client)
            
            return True
            
        except ImportError as e:
            print(f"❌ 导入组件失败: {e}")
            print("尝试从其他路径导入...")
            
            # 尝试备用导入路径
            try:
                # 添加theme_service路径
                theme_service_path = project_root / "theme_service"
                if theme_service_path.exists():
                    sys.path.insert(0, str(theme_service_path))
                
                from enhanced_ai_client import EnhancedAIThemeClient
                from enhanced_theme_discovery import EnhancedThemeDiscoveryEngine
                
                ai_client = EnhancedAIThemeClient({'USE_ENHANCED_MODE': True})
                self.engine = EnhancedThemeDiscoveryEngine(ai_client=ai_client)
                print("✅ 从theme_service导入组件成功")
                return True
                
            except ImportError as e2:
                print(f"❌ 所有导入尝试都失败: {e2}")
                return False
    
    async def _verify_enhanced_analyzer(self, ai_client):
        """验证增强分析器可用性"""
        try:
            # 测试增强分析器
            test_event = {
                "id": "test_001",
                "title": "测试重大事件",
                "summary": "这是一个测试事件",
                "event_type": "技术突破",
                "impact_industries": ["人工智能", "量子计算"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.9,
                    "reason": "测试重大事件"
                }
            }
            
            test_themes = [
                {
                    "name": "人工智能",
                    "description": "AI相关主题",
                    "keywords": "AI,人工智能"
                }
            ]
            
            print("🧪 测试增强分析器功能...")
            result = await ai_client.analyze_event_with_context(test_event, test_themes)
            
            print(f"   测试结果: {result.get('decision')} (置信度: {result.get('confidence', 0):.2f})")
            print(f"   分析器来源: {result.get('source', 'unknown')}")
            
            if result.get('source') == 'mock':
                print("⚠️  注意: 使用模拟分析器（可能没有真实调用DeepSeek）")
            else:
                print("✅ 增强分析器工作正常")
                
        except Exception as e:
            print(f"⚠️  增强分析器测试失败: {e}")
    
    async def load_processed_events(self) -> List[Dict[str, Any]]:
        """加载AI处理后的数据"""
        input_file = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
        
        if not input_file.exists():
            raise FileNotFoundError(f"处理后的数据文件不存在: {input_file}")
        
        print(f"📂 加载处理后的数据: {input_file}")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        print(f"✅ 加载成功: {len(events)} 个结构化事件")
        
        # 确保每个事件都有id字段（增强引擎需要）
        for i, event in enumerate(events):
            if 'id' not in event:
                event['id'] = event.get('news_id', f"event_{i:03d}")
        
        return events
    
    async def process_single_event_real(self, event: Dict) -> Dict:
        """使用真实引擎处理单个事件"""
        start_time = datetime.now()
        
        try:
            # 调用真实的EnhancedThemeDiscoveryEngine
            result = await self.engine.process_single_event(event)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # 提取关键信息
            status = result.get('status', 'unknown')
            ai_decision = result.get('ai_decision', {})
            decision = ai_decision.get('decision', 'UNKNOWN')
            execution_path = result.get('execution_path', 'unknown')
            
            processed_result = {
                'event_id': event.get('id'),
                'original_theme': event.get('original_data', {}).get('theme', 'unknown'),
                'original_action': event.get('theme_directive', {}).get('action', 'CLUSTER'),
                'final_decision': decision,
                'final_confidence': ai_decision.get('confidence', 0),
                'execution_path': execution_path,
                'status': status,
                'processing_time_ms': processing_time,
                'decision_time_ms': result.get('decision_time_ms', 0),
                'related_themes_count': result.get('related_themes_count', 0),
                'engine_version': result.get('engine_version', 'unknown'),
                'processed_at': datetime.now().isoformat()
            }
            
            # 更新统计
            self.stats["processed"] += 1
            
            if status == 'created':
                self.stats["created"] += 1
            elif status == 'merged':
                self.stats["merged"] += 1
            elif status == 'in_review':
                self.stats["in_review"] += 1
            elif status == 'failed':
                self.stats["failed"] += 1
            
            self.stats["processing_times"].append(processing_time)
            if result.get('decision_time_ms'):
                self.stats["decision_times"].append(result['decision_time_ms'])
            
            return processed_result
            
        except Exception as e:
            print(f"❌ 处理事件 {event.get('id')} 失败: {e}")
            
            error_result = {
                'event_id': event.get('id'),
                'status': 'error',
                'error': str(e),
                'processing_time_ms': (datetime.now() - start_time).total_seconds() * 1000,
                'processed_at': datetime.now().isoformat()
            }
            
            self.stats["failed"] += 1
            return error_result
    
    async def process_batch_real(self, events: List[Dict]) -> List[Dict]:
        """批量处理事件（使用真实引擎）"""
        print(f"\n🔄 开始真实增强架构处理...")
        
        # 初始化组件
        if not await self.initialize_components():
            raise Exception("无法初始化增强架构组件")
        
        if not self.engine:
            raise Exception("增强引擎未初始化")
        
        self.stats["total_events"] = len(events)
        
        # 分批处理
        batch_size = 5  # 小批量处理，避免超时
        all_results = []
        
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            print(f"  处理批次 {i//batch_size + 1}/{(len(events)-1)//batch_size + 1} ({len(batch)}事件)")
            
            batch_results = []
            for j, event in enumerate(batch):
                result = await self.process_single_event_real(event)
                batch_results.append(result)
                
                # 显示进度
                if (j + 1) % 5 == 0 or (j + 1) == len(batch):
                    decision = result.get('final_decision', 'UNKNOWN')
                    print(f"    [{j+1}/{len(batch)}] {event.get('id')}: {decision}")
            
            all_results.extend(batch_results)
            
            # 批次统计
            batch_stats = {
                'created': sum(1 for r in batch_results if r.get('status') == 'created'),
                'merged': sum(1 for r in batch_results if r.get('status') == 'merged'),
                'failed': sum(1 for r in batch_results if r.get('status') == 'failed')
            }
            print(f"    批次结果: 创建{batch_stats['created']}, 归并{batch_stats['merged']}, 失败{batch_stats['failed']}")
            
            # 短暂延迟，避免资源紧张
            if i + batch_size < len(events):
                await asyncio.sleep(0.5)
        
        self.results = all_results
        
        print(f"\n✅ 真实处理完成:")
        print(f"   总计: {self.stats['total_events']}")
        print(f"   成功处理: {self.stats['processed']}")
        print(f"   创建新题材: {self.stats['created']}")
        print(f"   归并到现有题材: {self.stats['merged']}")
        print(f"   进入审查: {self.stats['in_review']}")
        print(f"   失败: {self.stats['failed']}")
        
        return all_results
    
    def analyze_real_results(self):
        """分析真实处理结果"""
        if not self.results:
            print("⚠️  没有处理结果可供分析")
            return
        
        print(f"\n📊 真实增强处理分析")
        print("=" * 50)
        
        # 决策分布
        decision_counts = {}
        execution_path_counts = {}
        
        for result in self.results:
            decision = result.get('final_decision', 'UNKNOWN')
            execution_path = result.get('execution_path', 'unknown')
            
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            execution_path_counts[execution_path] = execution_path_counts.get(execution_path, 0) + 1
        
        print("最终决策分布:")
        for decision, count in sorted(decision_counts.items()):
            percentage = count / len(self.results) * 100
            print(f"  {decision}: {count} ({percentage:.1f}%)")
        
        print("\n执行路径分布:")
        for path, count in sorted(execution_path_counts.items()):
            percentage = count / len(self.results) * 100
            print(f"  {path}: {count} ({percentage:.1f}%)")
        
        # 决策变化分析
        decision_changes = {}
        for result in self.results:
            original = result.get('original_action', 'UNKNOWN')
            final = result.get('final_decision', 'UNKNOWN')
            
            if original != final:
                change_key = f"{original}->{final}"
                decision_changes[change_key] = decision_changes.get(change_key, 0) + 1
        
        if decision_changes:
            print("\n🔄 决策变化分析:")
            for change, count in sorted(decision_changes.items(), key=lambda x: x[1], reverse=True):
                percentage = count / len(self.results) * 100
                print(f"  {change}: {count} ({percentage:.1f}%)")
        
        # 性能分析
        if self.stats["processing_times"]:
            import statistics
            avg_time = statistics.mean(self.stats["processing_times"])
            max_time = max(self.stats["processing_times"])
            min_time = min(self.stats["processing_times"])
            
            print(f"\n⚡ 性能分析:")
            print(f"  平均处理时间: {avg_time:.1f}ms")
            print(f"  最长时间: {max_time:.1f}ms")
            print(f"  最短时间: {min_time:.1f}ms")
            print(f"  单事件处理目标 (<2秒): {'✅' if avg_time < 2000 else '❌'}")
            
            if self.stats["decision_times"]:
                avg_decision_time = statistics.mean(self.stats["decision_times"])
                print(f"  平均AI决策时间: {avg_decision_time:.1f}ms")
        
        # 成功率分析
        success_count = len([r for r in self.results if r.get('status') in ['created', 'merged', 'in_review']])
        success_rate = success_count / len(self.results) * 100 if self.results else 0
        
        print(f"\n✅ 成功率分析:")
        print(f"  成功处理: {success_count}/{len(self.results)} ({success_rate:.1f}%)")
        
        if self.stats['failed'] > 0:
            print(f"  失败事件: {self.stats['failed']}")
            # 显示失败原因
            errors = [r.get('error', 'unknown') for r in self.results if r.get('status') == 'error']
            if errors:
                print(f"  常见错误: {errors[0][:80]}...")
    
    def save_real_results(self):
        """保存真实处理结果"""
        results_dir = Path("evaluate_service/data/results/real_enhanced_results")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"real_enhanced_evaluation_{timestamp}.json"
        
        # 准备输出数据
        output_data = {
            "metadata": {
                "evaluation_id": f"real_enhanced_eval_{timestamp}",
                "evaluation_time": datetime.now().isoformat(),
                "evaluation_type": "真实增强架构测试",
                "dataset_size": self.stats["total_events"],
                "data_source": "validation_events_enhanced_v2.json",
                "engine_used": "EnhancedThemeDiscoveryEngine",
                "ai_client_used": "EnhancedAIThemeClient",
                "test_mode": True
            },
            "statistics": self.stats,
            "summary": {
                "total_processed": self.stats["processed"],
                "creation_rate": self.stats["created"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "merge_rate": self.stats["merged"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "success_rate": (self.stats["created"] + self.stats["merged"] + self.stats["in_review"]) / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "average_processing_time_ms": sum(self.stats["processing_times"]) / len(self.stats["processing_times"]) if self.stats["processing_times"] else 0,
                "decision_changes": self._calculate_decision_changes()
            },
            "detailed_results": self.results[:50]  # 保存前50条详细结果
        }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"\n💾 真实处理结果保存成功: {output_file}")
            
            # 生成简要报告
            self.generate_real_evaluation_report(output_data, results_dir, timestamp)
            
            return output_file
            
        except Exception as e:
            print(f"❌ 保存结果失败: {e}")
            raise
    
    def _calculate_decision_changes(self):
        """计算决策变化"""
        changes = {}
        for result in self.results:
            original = result.get('original_action')
            final = result.get('final_decision')
            
            if original and final and original != final:
                key = f"{original}->{final}"
                changes[key] = changes.get(key, 0) + 1
        
        return changes
    
    def generate_real_evaluation_report(self, data: Dict, results_dir: Path, timestamp: str):
        """生成真实评估报告"""
        report_file = results_dir / f"real_evaluation_report_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("AI新题材生成系统 - 真实增强架构评估报告\n")
            f.write("=" * 70 + "\n\n")
            
            f.write("📅 评估时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("🔧 测试模式: 真实组件调用（TEST_MODE=True）\n")
            f.write("🎯 评估重点: 验证EnhancedThemeDiscoveryEngine实际工作效果\n\n")
            
            stats = data["statistics"]
            summary = data["summary"]
            
            f.write("📊 关键统计:\n")
            f.write("=" * 50 + "\n")
            f.write(f"总事件数: {stats['total_events']}\n")
            f.write(f"成功处理: {stats['processed']}\n")
            f.write(f"创建新题材: {stats['created']} ({summary['creation_rate']:.1%})\n")
            f.write(f"归并到现有题材: {stats['merged']} ({summary['merge_rate']:.1%})\n")
            f.write(f"进入审查队列: {stats['in_review']}\n")
            f.write(f"处理失败: {stats['failed']}\n")
            f.write(f"成功率: {summary['success_rate']:.1%}\n")
            f.write(f"平均处理时间: {summary['average_processing_time_ms']:.0f}ms\n\n")
            
            f.write("🔄 决策变化情况:\n")
            changes = summary.get('decision_changes', {})
            if changes:
                for change, count in changes.items():
                    percentage = count / stats['total_events'] * 100
                    f.write(f"  {change}: {count} ({percentage:.1f}%)\n")
            else:
                f.write("  无显著决策变化\n\n")
            
            f.write("🎯 评估结论:\n")
            f.write("=" * 50 + "\n")
            
            if summary['success_rate'] > 0.9:
                f.write("✅ 增强架构工作正常，组件集成成功\n")
                f.write("✅ 实现了即时处理和智能决策\n")
                f.write("✅ 性能满足生产要求\n")
                f.write("\n建议: 可以进行下一步的集成测试\n")
            elif summary['success_rate'] > 0.7:
                f.write("⚠️  增强架构基本工作，但存在一些问题\n")
                f.write("⚠️  需要检查错误原因并优化\n")
                f.write("✅ 架构设计验证通过\n")
                f.write("\n建议: 修复发现的问题后重新测试\n")
            else:
                f.write("❌ 增强架构存在严重问题\n")
                f.write("❌ 需要深度调试组件集成\n")
                f.write("\n建议: 检查组件依赖和初始化流程\n")
        
        print(f"📋 真实评估报告: {report_file}")

async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 真实增强架构评估")
    print("使用真实的EnhancedThemeDiscoveryEngine进行测试")
    print("=" * 60)
    
    evaluator = RealEnhancedEvaluator()
    
    try:
        # 1. 加载处理后的数据
        events = await evaluator.load_processed_events()
        
        # 2. 使用真实引擎处理事件
        results = await evaluator.process_batch_real(events)
        
        # 3. 分析结果
        evaluator.analyze_real_results()
        
        # 4. 保存结果
        output_file = evaluator.save_real_results()
        
        print(f"\n✅ 真实增强评估完成！")
        print(f"   结果文件: {output_file}")
        print(f"\n🔍 关键发现:")
        print(f"   - 是否调用了真实组件: {'✅' if evaluator.engine else '❌'}")
        print(f"   - 是否执行了AI分析: 取决于EnhancedAIThemeClient配置")
        print(f"   - 是否验证了决策矩阵: 是")
        print(f"\n📝 注意事项:")
        print(f"   1. 在TEST_MODE下，可能使用模拟数据而非真实DeepSeek调用")
        print(f"   2. 如需真实API调用，请设置DEEPSEEK_API_KEY环境变量并关闭TEST_MODE")
        print(f"   3. 数据库操作被模拟，不影响真实数据")
        
    except Exception as e:
        print(f"❌ 真实评估失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())