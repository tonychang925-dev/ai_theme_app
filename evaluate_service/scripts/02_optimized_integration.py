#!/usr/bin/env python3
"""
第二阶段：性能优化与判重整合测试
优化API调用，整合判重引擎，提高系统效率
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple
import logging
import statistics
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizedIntegrationTest:
    """优化后的集成测试（整合判重引擎）"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_events": 0,
            "processed": 0,
            "processing_times": [],
            "duplication_checks": 0,
            "duplicates_prevented": 0,
            "themes_created": defaultdict(int),
            "errors": []
        }
        
        # 模拟的题材数据库
        self.theme_database = []
        
    async def initialize_components(self) -> bool:
        """初始化所有组件（包含判重引擎）"""
        logger.info("🔧 开始初始化优化版组件...")
        
        try:
            # 1. 初始化判重引擎
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            self.deduplication_engine = ThemeDeduplicationEngine()
            logger.info("✅ ThemeDeduplicationEngine 初始化成功")
            
            # 2. 初始化EnhancedAIThemeClient（模拟模式，减少API调用）
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            
            # 使用模拟模式配置
            sim_config = {
                'USE_ENHANCED_MODE': True,
                'USE_MOCK_MODE': True,  # 新增：模拟模式
                'MOCK_RESPONSE_DELAY': 0.1,  # 模拟延迟100ms
                'BATCH_SIZE': 5  # 批量处理大小
            }
            
            self.ai_client = EnhancedAIThemeClient(settings=sim_config)
            logger.info("✅ EnhancedAIThemeClient（模拟模式）初始化成功")
            
            # 3. 初始化EnhancedThemeDiscoveryEngine（优化版）
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            
            # 集成判重引擎的配置
            engine_config = {
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3,
                'deduplication_enabled': True,  # 启用判重
                'deduplication_engine': self.deduplication_engine,
                'cache_enabled': True,  # 启用缓存
                'batch_processing': True  # 启用批量处理
            }
            
            self.engine = EnhancedThemeDiscoveryEngine(
                ai_client=self.ai_client,
                db_manager=None,
                config=engine_config
            )
            logger.info("✅ EnhancedThemeDiscoveryEngine（优化版）初始化成功")
            
            # 4. 测试连通性
            test_result = await self._test_component_connectivity()
            if not test_result:
                raise Exception("组件连通性测试失败")
                
            logger.info("✅ 所有组件初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化组件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _test_component_connectivity(self) -> bool:
        """测试组件连通性（包含判重）"""
        try:
            # 创建测试事件
            test_event = {
                "id": "optimized_test_001",
                "title": "测试优化版组件连通性",
                "summary": "测试包含判重引擎的组件协同工作",
                "event_type": "政策发布",
                "impact_industries": ["人工智能", "信息技术"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.9,
                    "reason": "测试事件"
                }
            }
            
            # 先创建一个测试题材
            test_theme = {
                "id": "test_theme_001",
                "name": "人工智能",
                "keywords": "AI,人工智能,机器学习",
                "event_count": 1
            }
            self.theme_database.append(test_theme)
            
            # 测试判重引擎
            dedup_result = await self.deduplication_engine.check_duplication(
                new_theme_name="人工智能发展规划",
                event_data=test_event,
                existing_themes=self.theme_database
            )
            
            if dedup_result.should_merge:
                logger.info(f"✅ 判重引擎测试成功: 检测到重复题材")
            else:
                logger.info(f"✅ 判重引擎测试成功: 未检测到重复")
                
            # 测试EnhancedThemeDiscoveryEngine
            result = await self.engine.process_single_event(test_event)
            
            logger.info(f"✅ 组件连通性测试成功: {result.get('status')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 组件连通性测试失败: {e}")
            return False
    
    async def load_test_data(self) -> List[Dict[str, Any]]:
        """加载测试数据（带判重测试用例）"""
        data_path = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
        
        if not data_path.exists():
            logger.error(f"❌ 测试数据文件不存在: {data_path}")
            raise FileNotFoundError(f"测试数据文件不存在: {data_path}")
        
        logger.info(f"📂 加载测试数据: {data_path}")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        
        # 添加一些重复测试用例
        enhanced_events = self._add_duplicate_test_cases(events)
        
        # 取前40条用于测试
        sample_size = min(40, len(enhanced_events))
        sampled_events = enhanced_events[:sample_size]
        
        logger.info(f"✅ 加载成功: {len(sampled_events)} 个事件（包含重复测试用例）")
        
        self.stats["total_events"] = len(sampled_events)
        return sampled_events
    
    def _add_duplicate_test_cases(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """添加重复测试用例"""
        enhanced_events = events.copy()
        
        # 添加一些语义重复的事件
        duplicate_tests = [
            {
                "id": "dup_test_001",
                "title": "AI技术新突破：深度学习算法优化",
                "summary": "AI技术新突破：深度学习算法优化，提升效率",
                "event_type": "技术突破",
                "impact_industries": ["人工智能", "软件"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.85,
                    "reason": "AI技术新突破"
                }
            },
            {
                "id": "dup_test_002",
                "title": "人工智能发展规划出台",
                "summary": "人工智能发展规划出台，推动产业发展",
                "event_type": "政策发布",
                "impact_industries": ["人工智能", "信息技术"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.88,
                    "reason": "人工智能政策"
                }
            },
            {
                "id": "dup_test_003",
                "title": "新能源车销量再创新高",
                "summary": "新能源车销量再创新高，市场需求旺盛",
                "event_type": "市场数据",
                "impact_industries": ["新能源汽车", "汽车制造"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.82,
                    "reason": "新能源汽车销量"
                }
            }
        ]
        
        enhanced_events.extend(duplicate_tests)
        logger.info(f"📝 添加了 {len(duplicate_tests)} 个重复测试用例")
        return enhanced_events
    
    async def process_with_duplication_check(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """带判重检查的事件处理"""
        start_time = datetime.now()
        
        try:
            # 1. 首先检查是否是重复事件（基于标题和摘要）
            if await self._is_duplicate_event(event):
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                return {
                    'event_id': event.get('id'),
                    'status': 'duplicate_ignored',
                    'reason': '事件内容重复',
                    'processing_time_ms': processing_time
                }
            
            # 2. 使用引擎处理事件
            result = await self.engine.process_single_event(event)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.stats["processing_times"].append(processing_time)
            
            # 3. 提取关键信息
            status = result.get('status', 'unknown')
            final_theme = result.get('execution_result', {}).get('target_theme_name', '') 
                         or result.get('execution_result', {}).get('new_theme_name', '未知')
            
            # 4. 判重统计
            dedup_info = result.get('deduplication_check', {})
            if dedup_info:
                self.stats["duplication_checks"] += 1
                if dedup_info.get('duplicate_prevented', False):
                    self.stats["duplicates_prevented"] += 1
            
            # 5. 题材统计
            if status == 'created' and final_theme != '未知':
                self.stats["themes_created"][final_theme] += 1
            
            simplified_result = {
                'event_id': event.get('id'),
                'title': event.get('title', '')[:30],
                'final_decision': result.get('ai_decision', {}).get('decision', 'UNKNOWN'),
                'final_theme': final_theme,
                'status': status,
                'processing_time_ms': processing_time,
                'duplication_checked': bool(dedup_info),
                'duplicate_prevented': dedup_info.get('duplicate_prevented', False)
            }
            
            self.stats["processed"] += 1
            
            # 进度显示
            if self.stats["processed"] % 10 == 0:
                avg_time = statistics.mean(self.stats["processing_times"][-10:]) if len(self.stats["processing_times"]) >= 10 else 0
                logger.info(f"  已处理 {self.stats['processed']}/{self.stats['total_events']} | 平均耗时: {avg_time:.1f}ms")
            
            return simplified_result
            
        except Exception as e:
            logger.error(f"❌ 处理事件 {event.get('id')} 失败: {e}")
            
            error_result = {
                'event_id': event.get('id'),
                'status': 'error',
                'error': str(e),
                'processing_time_ms': (datetime.now() - start_time).total_seconds() * 1000
            }
            
            self.stats["errors"].append(f"事件 {event.get('id')}: {str(e)}")
            return error_result
    
    async def _is_duplicate_event(self, event: Dict[str, Any]) -> bool:
        """简单的事件重复检查"""
        # 这里可以实现更复杂的事件去重逻辑
        # 现在只检查标题是否完全相同
        title = event.get('title', '')
        event_id = event.get('id', '')
        
        # 检查是否已经处理过相同ID或标题的事件
        for result in self.results:
            if result.get('event_id') == event_id:
                return True
            if result.get('title') == title:
                return True
        
        return False
    
    async def process_batch_optimized(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化版批量处理（带并发和判重）"""
        logger.info(f"🔄 开始优化版批量处理 {len(events)} 个事件...")
        
        results = []
        batch_size = 3  # 更小的批次，便于控制
        
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            batch_results = []
            
            # 并发处理批次内的事件
            tasks = [self.process_with_duplication_check(event) for event in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ 批次处理异常: {result}")
                    error_result = {
                        'event_id': batch[idx].get('id'),
                        'status': 'batch_error',
                        'error': str(result)
                    }
                    results.append(error_result)
                else:
                    results.append(result)
            
            # 批次统计
            created = sum(1 for r in results[-len(batch):] if r.get('status') == 'created')
            merged = sum(1 for r in results[-len(batch):] if r.get('status') == 'merged')
            duplicates = sum(1 for r in results[-len(batch):] if r.get('status') == 'duplicate_ignored')
            
            logger.info(f"  批次 {i//batch_size + 1}: 创建{created}, 归并{merged}, 重复{duplicates}, 失败{len(batch)-created-merged-duplicates}")
            
            # 短暂延迟，避免API限制
            if i + batch_size < len(events):
                await asyncio.sleep(0.05)
        
        logger.info(f"✅ 批量处理完成: {len(results)} 个结果")
        return results
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析处理结果"""
        logger.info(f"📊 分析 {len(results)} 个处理结果...")
        
        # 1. 状态分布
        status_counts = defaultdict(int)
        for result in results:
            status = result.get('status', 'unknown')
            status_counts[status] += 1
        
        logger.info("处理状态分布:")
        for status, count in sorted(status_counts.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {status}: {count} ({percentage:.1f}%)")
        
        # 2. 判重统计
        duplication_checked = sum(1 for r in results if r.get('duplication_checked', False))
        duplicates_prevented = sum(1 for r in results if r.get('duplicate_prevented', False))
        
        logger.info(f"判重统计:")
        logger.info(f"  判重检查: {duplication_checked}/{len(results)} ({duplication_checked/len(results)*100:.1f}%)")
        logger.info(f"  阻止重复: {duplicates_prevented}")
        if duplication_checked > 0:
            logger.info(f"  判重有效率: {duplicates_prevented/duplication_checked*100:.1f}%")
        
        # 3. 题材统计
        logger.info(f"题材统计:")
        logger.info(f"  创建的不同题材数: {len(self.stats['themes_created'])}")
        
        if self.stats["themes_created"]:
            # 按事件数量排序
            sorted_themes = sorted(self.stats["themes_created"].items(), 
                                 key=lambda x: x[1], reverse=True)
            
            logger.info("题材分布 (前10):")
            for theme, count in sorted_themes[:10]:
                logger.info(f"  {theme}: {count}个事件")
            
            # 分析题材重复问题
            self._analyze_theme_duplicates(sorted_themes)
        
        # 4. 性能统计
        if self.stats["processing_times"]:
            avg_time = statistics.mean(self.stats["processing_times"])
            median_time = statistics.median(self.stats["processing_times"])
            max_time = max(self.stats["processing_times"])
            min_time = min(self.stats["processing_times"])
            
            logger.info("性能统计:")
            logger.info(f"  平均处理时间: {avg_time:.1f}ms")
            logger.info(f"  中位数时间: {median_time:.1f}ms")
            logger.info(f"  最快: {min_time:.1f}ms, 最慢: {max_time:.1f}ms")
            logger.info(f"  单事件处理目标 (<2秒): {'✅' if avg_time < 2000 else '❌'}")
            
            # 性能分布
            fast = sum(1 for t in self.stats["processing_times"] if t < 1000)
            medium = sum(1 for t in self.stats["processing_times"] if 1000 <= t < 3000)
            slow = sum(1 for t in self.stats["processing_times"] if t >= 3000)
            
            logger.info("性能分布:")
            logger.info(f"  <1秒: {fast} ({fast/len(self.stats['processing_times'])*100:.1f}%)")
            logger.info(f"  1-3秒: {medium} ({medium/len(self.stats['processing_times'])*100:.1f}%)")
            logger.info(f"  >=3秒: {slow} ({slow/len(self.stats['processing_times'])*100:.1f}%)")
        
        # 5. 错误分析
        if self.stats["errors"]:
            logger.warning(f"⚠️ 发现 {len(self.stats['errors'])} 个错误")
            for error in self.stats["errors"][:5]:
                logger.warning(f"  错误: {error}")
    
    def _analyze_theme_duplicates(self, themes: List[Tuple[str, int]]):
        """分析题材重复问题"""
        logger.info("🔍 题材重复分析:")
        
        # 简单的重复检测（基于名称包含关系）
        potential_duplicates = []
        theme_names = [name for name, _ in themes]
        
        for i, name1 in enumerate(theme_names):
            for j, name2 in enumerate(theme_names[i+1:], i+1):
                # 检查包含关系
                if name1 in name2 or name2 in name1:
                    # 计算相似度
                    similarity = len(set(name1) & set(name2)) / len(set(name1) | set(name2))
                    if similarity > 0.6:  # 相似度阈值
                        potential_duplicates.append((name1, name2, similarity))
        
        if potential_duplicates:
            logger.info(f"  发现 {len(potential_duplicates)} 对潜在重复题材:")
            for name1, name2, similarity in potential_duplicates[:5]:  # 只显示前5个
                logger.info(f"    {name1} ↔ {name2} (相似度: {similarity:.2f})")
        else:
            logger.info("  未发现明显重复题材")
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存处理结果"""
        results_dir = Path("evaluate_service/data/results/optimized_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"optimized_results_{timestamp}.json"
        
        output_data = {
            "metadata": {
                "test_type": "优化版集成测试（带判重）",
                "test_time": datetime.now().isoformat(),
                "dataset_size": self.stats["total_events"],
                "components": [
                    "ThemeDeduplicationEngine",
                    "EnhancedAIThemeClient（模拟模式）",
                    "EnhancedThemeDiscoveryEngine（优化版）"
                ]
            },
            "statistics": self.stats,
            "detailed_results": results,
            "summary": {
                "total_processed": self.stats["processed"],
                "success_rate": self.stats["processed"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "duplication_checks": self.stats["duplication_checks"],
                "duplicates_prevented": self.stats["duplicates_prevented"],
                "unique_themes_created": len(self.stats["themes_created"]),
                "avg_processing_time_ms": statistics.mean(self.stats["processing_times"]) if self.stats["processing_times"] else 0
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file
    
    def generate_report(self, results_file: Path):
        """生成测试报告"""
        report_dir = Path("evaluate_service/data/results/optimized_test/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"optimized_report_{timestamp}.txt"
        
        with open(results_file, 'r', encoding='utf-8') as f:
            results_data = json.load(f)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("优化版集成测试报告（带判重引擎）\n")
            f.write("=" * 70 + "\n\n")
            
            metadata = results_data["metadata"]
            stats = results_data["statistics"]
            summary = results_data["summary"]
            
            f.write(f"📅 测试时间: {metadata['test_time'][:19]}\n")
            f.write(f"📊 数据集: {metadata['dataset_size']} 个事件\n")
            f.write(f"🔧 使用组件: {', '.join(metadata['components'])}\n\n")
            
            f.write("📈 处理统计:\n")
            f.write("-" * 50 + "\n")
            f.write(f"总事件数: {stats['total_events']}\n")
            f.write(f"成功处理: {stats['processed']}\n")
            f.write(f"成功率: {summary['success_rate']:.1%}\n")
            f.write(f"判重检查: {stats['duplication_checks']}\n")
            f.write(f"阻止重复: {stats['duplicates_prevented']}\n")
            f.write(f"创建题材数: {summary['unique_themes_created']}\n")
            f.write(f"平均处理时间: {summary['avg_processing_time_ms']:.1f}ms\n\n")
            
            f.write("🎯 性能评估:\n")
            f.write("-" * 50 + "\n")
            if summary['avg_processing_time_ms'] < 2000:
                f.write("✅ 性能达标: 平均处理时间 < 2秒\n")
            else:
                f.write("⚠️ 性能需优化: 平均处理时间 > 2秒\n")
            
            if stats['duplicates_prevented'] > 0:
                f.write("✅ 判重机制有效: 成功阻止了重复题材创建\n")
            else:
                f.write("⚠️ 判重效果: 未检测到重复题材\n\n")
            
            # 题材统计
            if stats['themes_created']:
                f.write("🏷️ 题材创建统计:\n")
                f.write("-" * 30 + "\n")
                for theme, count in sorted(stats['themes_created'].items(), 
                                         key=lambda x: x[1], reverse=True)[:10]:
                    f.write(f"{theme}: {count}个事件\n")
        
        logger.info(f"📋 测试报告生成: {report_file}")
        return report_file

async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 第二阶段：优化版集成测试")
    print("整合判重引擎，优化性能，防止题材重复")
    print("=" * 70)
    
    tester = OptimizedIntegrationTest()
    
    try:
        # 1. 初始化组件
        init_success = await tester.initialize_components()
        if not init_success:
            print("❌ 组件初始化失败，无法继续测试")
            return 1
        
        # 2. 加载测试数据
        events = await tester.load_test_data()
        if not events:
            print("❌ 没有测试数据，无法继续")
            return 1
        
        # 3. 处理事件（优化版）
        results = await tester.process_batch_optimized(events)
        
        # 4. 分析结果
        tester.analyze_results(results)
        
        # 5. 保存结果
        results_file = tester.save_results(results)
        
        # 6. 生成报告
        tester.generate_report(results_file)
        
        print("\n" + "=" * 70)
        print("✅ 第二阶段优化测试完成！")
        print("=" * 70)
        print(f"📊 关键结果:")
        print(f"  总事件数: {tester.stats['total_events']}")
        print(f"  成功处理: {tester.stats['processed']}")
        print(f"  判重检查: {tester.stats['duplication_checks']}")
        print(f"  阻止重复: {tester.stats['duplicates_prevented']}")
        print(f"  创建题材: {len(tester.stats['themes_created'])} 个")
        
        if tester.stats["processing_times"]:
            avg_time = statistics.mean(tester.stats["processing_times"])
            print(f"  平均耗时: {avg_time:.1f}ms")
            print(f"  性能状态: {'✅ 达标' if avg_time < 2000 else '❌ 需优化'}")
        
        if tester.stats["errors"]:
            print(f"⚠️  发现 {len(tester.stats['errors'])} 个错误")
        else:
            print("✅ 无错误发生")
        
        return 0
        
    except Exception as e:
        print(f"❌ 优化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())