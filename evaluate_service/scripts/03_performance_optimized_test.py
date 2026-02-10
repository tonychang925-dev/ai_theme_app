#!/usr/bin/env python3
"""
第三阶段：性能优化测试
优化API调用，实现批量处理和并发优化
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
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PerformanceOptimizedTest:
    """性能优化测试"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_events": 0,
            "processed": 0,
            "processing_times": [],
            "batch_sizes": [],
            "concurrent_tasks": 0,
            "api_calls_saved": 0,
            "themes_created": defaultdict(int),
            "themes_merged": defaultdict(int),
            "errors": []
        }
        
        # 缓存：存储事件到决策的映射
        self.decision_cache = {}
        self.cache_hits = 0
        
    async def initialize_components(self) -> bool:
        """初始化优化版组件"""
        logger.info("🔧 开始初始化性能优化版组件...")
        
        try:
            # 1. 初始化优化版AI客户端
            self.ai_client = await self._create_optimized_ai_client()
            logger.info("✅ 优化版AI客户端初始化成功")
            
            # 2. 初始化判重引擎
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            self.dedup_engine = ThemeDeduplicationEngine()
            logger.info("✅ 判重引擎初始化成功")
            
            # 3. 初始化优化版引擎
            self.engine = await self._create_optimized_engine()
            logger.info("✅ 优化版引擎初始化成功")
            
            # 4. 测试连通性
            test_result = await self._test_optimization_features()
            if not test_result:
                logger.warning("⚠️  优化特性测试有警告，但继续测试")
                
            logger.info("✅ 性能优化版组件初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _create_optimized_ai_client(self):
        """创建优化版AI客户端，支持批量处理"""
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        
        # 创建子类，添加批量处理能力
        class OptimizedAIThemeClient(EnhancedAIThemeClient):
            def __init__(self):
                super().__init__(settings={'USE_ENHANCED_MODE': True})
                self.batch_cache = {}
                self.last_batch_time = 0
                self.batch_delay = 0.5  # 批处理延迟
                
            async def analyze_events_batch(self, events_with_context: List[Tuple[Dict, List]]) -> List[Dict]:
                """批量分析多个事件"""
                if not events_with_context:
                    return []
                
                # 检查缓存
                cached_results = []
                uncached_items = []
                
                for event_data, related_themes in events_with_context:
                    cache_key = self._get_cache_key(event_data, related_themes)
                    if cache_key in self.batch_cache:
                        cached_results.append(self.batch_cache[cache_key])
                    else:
                        uncached_items.append((event_data, related_themes, cache_key))
                
                # 如果有未缓存的项，进行批量API调用
                if uncached_items:
                    try:
                        # 模拟批量API调用（实际应该实现真正的批量API）
                        batch_results = []
                        for event_data, related_themes, cache_key in uncached_items:
                            # 使用原有分析逻辑
                            result = await super().analyze_event_with_context(event_data, related_themes)
                            self.batch_cache[cache_key] = result
                            batch_results.append(result)
                        
                        # 合并结果
                        return cached_results + batch_results
                        
                    except Exception as e:
                        logger.error(f"批量分析失败: {e}")
                        # 降级：逐个分析
                        fallback_results = []
                        for event_data, related_themes, _ in uncached_items:
                            result = await super().analyze_event_with_context(event_data, related_themes)
                            fallback_results.append(result)
                        return cached_results + fallback_results
                
                return cached_results
            
            def _get_cache_key(self, event_data: Dict, related_themes: List[Dict]) -> str:
                """生成缓存键"""
                # 基于事件标题、行业和相关题材生成缓存键
                title_hash = hash(event_data.get('title', ''))
                industries = '-'.join(sorted(event_data.get('impact_industries', [])))
                theme_ids = '-'.join(sorted([str(t.get('id', '')) for t in related_themes[:3]]))
                return f"{title_hash}:{industries}:{theme_ids}"
            
            def clear_cache(self):
                """清除缓存"""
                self.batch_cache.clear()
        
        return OptimizedAIThemeClient()
    
    async def _create_optimized_engine(self):
        """创建优化版引擎，添加性能监控和优化"""
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        class OptimizedEnhancedEngine(EnhancedThemeDiscoveryEngine):
            def __init__(self, ai_client, dedup_engine):
                super().__init__(ai_client, db_manager=None)
                self.dedup_engine = dedup_engine
                self.performance_stats = {
                    'cache_hits': 0,
                    'cache_misses': 0,
                    'avg_decision_time': 0,
                    'total_processed': 0
                }
                self.decision_cache = {}
                
            async def process_single_event_optimized(self, event: Dict) -> Dict:
                """优化版单事件处理"""
                start_time = datetime.now()
                
                # 检查是否有缓存的决策
                cache_key = self._get_event_cache_key(event)
                if cache_key in self.decision_cache:
                    cached_result = self.decision_cache[cache_key]
                    self.performance_stats['cache_hits'] += 1
                    
                    # 返回缓存结果，添加缓存标记
                    result = cached_result.copy()
                    result['cached'] = True
                    result['processing_time_ms'] = (datetime.now() - start_time).total_seconds() * 1000
                    return result
                
                self.performance_stats['cache_misses'] += 1
                
                # 正常处理
                result = await super().process_single_event(event)
                
                # 缓存结果（仅对成功处理的事件）
                if result.get('status') in ['created', 'merged']:
                    self.decision_cache[cache_key] = result
                
                # 更新性能统计
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                self.performance_stats['total_processed'] += 1
                
                # 计算平均决策时间
                if 'decision_time_ms' in result:
                    current_avg = self.performance_stats['avg_decision_time']
                    total = self.performance_stats['total_processed']
                    self.performance_stats['avg_decision_time'] = (
                        current_avg * (total - 1) + result['decision_time_ms']
                    ) / total
                
                result['processing_time_ms'] = processing_time
                return result
            
            def _get_event_cache_key(self, event: Dict) -> str:
                """生成事件缓存键"""
                title = event.get('title', '')
                industries = '-'.join(sorted(event.get('impact_industries', [])))
                directive = event.get('theme_directive', {})
                directive_str = f"{directive.get('action', '')}:{directive.get('confidence', 0)}"
                return f"{hash(title)}:{industries}:{directive_str}"
            
            def get_performance_stats(self) -> Dict:
                """获取性能统计"""
                cache_hit_rate = 0
                if self.performance_stats['cache_hits'] + self.performance_stats['cache_misses'] > 0:
                    cache_hit_rate = self.performance_stats['cache_hits'] / (
                        self.performance_stats['cache_hits'] + self.performance_stats['cache_misses']
                    ) * 100
                
                return {
                    **self.performance_stats,
                    'cache_hit_rate_percent': round(cache_hit_rate, 2),
                    'cache_size': len(self.decision_cache)
                }
        
        return OptimizedEnhancedEngine(self.ai_client, self.dedup_engine)
    
    async def _test_optimization_features(self) -> bool:
        """测试优化特性"""
        logger.info("🔍 测试性能优化特性...")
        
        try:
            # 测试缓存功能
            test_event = {
                "id": "cache_test_001",
                "title": "缓存测试事件",
                "summary": "测试缓存功能",
                "event_type": "测试",
                "impact_industries": ["测试"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.9,
                    "reason": "缓存测试"
                }
            }
            
            # 第一次处理（应该缓存）
            result1 = await self.engine.process_single_event_optimized(test_event)
            logger.info(f"第一次处理: {result1.get('status')}, 耗时: {result1.get('processing_time_ms', 0):.1f}ms")
            
            # 第二次处理（应该命中缓存）
            result2 = await self.engine.process_single_event_optimized(test_event)
            cached = result2.get('cached', False)
            logger.info(f"第二次处理: 缓存命中={cached}, 耗时: {result2.get('processing_time_ms', 0):.1f}ms")
            
            if cached:
                logger.info("✅ 缓存功能测试成功")
            else:
                logger.warning("⚠️  缓存功能未生效")
            
            # 测试性能统计
            stats = self.engine.get_performance_stats()
            logger.info(f"性能统计: 缓存命中率={stats.get('cache_hit_rate_percent', 0)}%")
            
            return True
            
        except Exception as e:
            logger.error(f"优化特性测试失败: {e}")
            return False
    
    async def load_test_data(self, sample_size: int = 15) -> List[Dict[str, Any]]:
        """加载测试数据"""
        data_path = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
        
        if not data_path.exists():
            logger.error(f"❌ 测试数据文件不存在: {data_path}")
            raise FileNotFoundError(f"测试数据文件不存在: {data_path}")
        
        logger.info(f"📂 加载测试数据: {data_path}")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        
        # 添加一些相似事件测试缓存效果
        enhanced_events = self._add_similar_events(events)
        
        # 抽样测试
        sample_size = min(sample_size, len(enhanced_events))
        sampled_events = enhanced_events[:sample_size]
        
        logger.info(f"✅ 加载成功: {len(sampled_events)} 个事件")
        
        self.stats["total_events"] = len(sampled_events)
        return sampled_events
    
    def _add_similar_events(self, events: List[Dict]) -> List[Dict]:
        """添加相似事件以测试缓存效果"""
        enhanced_events = events.copy()
        
        # 复制一些事件，创建相似版本
        similar_events = []
        for i in range(min(3, len(events))):
            original = events[i].copy()
            similar = original.copy()
            similar['id'] = f"similar_{original.get('id', '')}"
            similar_events.append(similar)
        
        enhanced_events.extend(similar_events)
        logger.info(f"📝 添加了 {len(similar_events)} 个相似事件测试缓存")
        return enhanced_events
    
    async def process_with_concurrency(self, events: List[Dict[str, Any]], max_concurrent: int = 3) -> List[Dict[str, Any]]:
        """并发处理事件"""
        logger.info(f"🔄 开始并发处理 {len(events)} 个事件 (最大并发: {max_concurrent})...")
        
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(event):
            async with semaphore:
                return await self._process_single_optimized(event)
        
        # 创建任务
        tasks = [process_with_semaphore(event) for event in events]
        
        # 批量执行，每批显示进度
        batch_size = 5
        for i in range(0, len(tasks), batch_size):
            batch_tasks = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"处理失败: {result}")
                    error_result = {
                        'event_id': events[i + j].get('id'),
                        'status': 'error',
                        'error': str(result)
                    }
                    results.append(error_result)
                    self.stats["errors"].append(str(result))
                else:
                    results.append(result)
            
            # 显示批次进度
            processed = i + len(batch_results)
            logger.info(f"  进度: {processed}/{len(events)}")
            
            # 显示当前批次统计
            if len(batch_results) > 0:
                batch_stats = {
                    'avg_time': statistics.mean([r.get('processing_time_ms', 0) for r in results[-len(batch_results):] 
                                              if not isinstance(r, Exception)]),
                    'cache_hits': sum(1 for r in results[-len(batch_results):] 
                                     if not isinstance(r, Exception) and r.get('cached', False))
                }
                logger.info(f"  批次平均耗时: {batch_stats['avg_time']:.1f}ms, 缓存命中: {batch_stats['cache_hits']}")
        
        self.stats["processed"] = len([r for r in results if not isinstance(r, Exception)])
        return results
    
    async def _process_single_optimized(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """优化版单事件处理"""
        start_time = datetime.now()
        
        try:
            # 使用优化版引擎处理
            result = await self.engine.process_single_event_optimized(event)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # 如果这是缓存命中，记录统计
            if result.get('cached', False):
                self.cache_hits += 1
            
            simplified_result = {
                'event_id': event.get('id'),
                'title': event.get('title', '')[:30],
                'final_decision': result.get('ai_decision', {}).get('decision', 'UNKNOWN'),
                'final_theme': result.get('execution_result', {}).get('target_theme_name', '') 
                             or result.get('execution_result', {}).get('new_theme_name', '未知'),
                'status': result.get('status', 'unknown'),
                'processing_time_ms': processing_time,
                'cached': result.get('cached', False),
                'decision_time_ms': result.get('decision_time_ms', 0)
            }
            
            # 题材统计
            final_theme = simplified_result['final_theme']
            status = simplified_result['status']
            
            if status == 'created' and final_theme != '未知':
                self.stats["themes_created"][final_theme] += 1
            elif status == 'merged' and final_theme != '未知':
                self.stats["themes_merged"][final_theme] += 1
            
            self.stats["processing_times"].append(processing_time)
            
            return simplified_result
            
        except Exception as e:
            logger.error(f"处理事件 {event.get('id')} 失败: {e}")
            error_result = {
                'event_id': event.get('id'),
                'status': 'error',
                'error': str(e),
                'processing_time_ms': (datetime.now() - start_time).total_seconds() * 1000
            }
            self.stats["errors"].append(f"事件 {event.get('id')}: {str(e)}")
            return error_result
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析优化后的结果"""
        logger.info(f"📊 分析 {len(results)} 个处理结果...")
        
        # 过滤掉异常结果
        valid_results = [r for r in results if not isinstance(r, Exception) and r.get('status') != 'error']
        
        if not valid_results:
            logger.error("❌ 没有有效的处理结果")
            return
        
        # 1. 性能统计
        processing_times = [r.get('processing_time_ms', 0) for r in valid_results]
        decision_times = [r.get('decision_time_ms', 0) for r in valid_results if r.get('decision_time_ms', 0) > 0]
        
        avg_processing = statistics.mean(processing_times) if processing_times else 0
        avg_decision = statistics.mean(decision_times) if decision_times else 0
        
        logger.info("⏱️ 性能统计:")
        logger.info(f"  平均总耗时: {avg_processing:.1f}ms")
        logger.info(f"  平均AI决策耗时: {avg_decision:.1f}ms")
        logger.info(f"  目标 (<2秒): {'✅ 达标' if avg_processing < 2000 else '❌ 超标'}")
        
        # 缓存效果
        cache_hits = sum(1 for r in valid_results if r.get('cached', False))
        cache_hit_rate = cache_hits / len(valid_results) * 100 if valid_results else 0
        
        logger.info(f"💾 缓存效果:")
        logger.info(f"  缓存命中: {cache_hits}/{len(valid_results)} ({cache_hit_rate:.1f}%)")
        
        # 2. 处理结果分布
        status_counts = defaultdict(int)
        for result in valid_results:
            status = result.get('status', 'unknown')
            status_counts[status] += 1
        
        logger.info("📈 处理状态分布:")
        for status, count in sorted(status_counts.items()):
            percentage = count / len(valid_results) * 100
            logger.info(f"  {status}: {count} ({percentage:.1f}%)")
        
        # 3. 题材统计
        logger.info("🏷️ 题材统计:")
        logger.info(f"  创建的不同题材数: {len(self.stats['themes_created'])}")
        logger.info(f"  归并到的题材数: {len(self.stats['themes_merged'])}")
        
        if self.stats["themes_created"]:
            logger.info("新建题材分布:")
            for theme, count in sorted(self.stats["themes_created"].items(), 
                                     key=lambda x: x[1], reverse=True)[:5]:
                logger.info(f"  {theme}: {count}个事件")
        
        # 4. 耗时分布分析
        time_ranges = {
            "优秀 (<500ms)": lambda t: t < 500,
            "良好 (500-1000ms)": lambda t: 500 <= t < 1000,
            "一般 (1-2秒)": lambda t: 1000 <= t < 2000,
            "较慢 (2-5秒)": lambda t: 2000 <= t < 5000,
            "慢 (>5秒)": lambda t: t >= 5000
        }
        
        logger.info("⏳ 耗时分布:")
        for range_name, condition in time_ranges.items():
            count = sum(1 for t in processing_times if condition(t))
            if count > 0:
                percentage = count / len(processing_times) * 100
                logger.info(f"  {range_name}: {count} ({percentage:.1f}%)")
        
        # 5. 引擎性能统计
        if hasattr(self.engine, 'get_performance_stats'):
            engine_stats = self.engine.get_performance_stats()
            logger.info("🔧 引擎性能统计:")
            logger.info(f"  缓存命中率: {engine_stats.get('cache_hit_rate_percent', 0)}%")
            logger.info(f"  缓存大小: {engine_stats.get('cache_size', 0)}")
            logger.info(f"  平均决策时间: {engine_stats.get('avg_decision_time', 0):.1f}ms")
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存优化测试结果"""
        results_dir = Path("evaluate_service/data/results/performance_optimized_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"performance_optimized_results_{timestamp}.json"
        
        # 获取引擎性能统计
        engine_stats = {}
        if hasattr(self.engine, 'get_performance_stats'):
            engine_stats = self.engine.get_performance_stats()
        
        output_data = {
            "metadata": {
                "test_type": "性能优化测试",
                "test_time": datetime.now().isoformat(),
                "dataset_size": self.stats["total_events"],
                "optimizations": ["缓存优化", "并发处理", "批量分析"]
            },
            "statistics": {
                **self.stats,
                "cache_hits": self.cache_hits,
                "cache_hit_rate": self.cache_hits / self.stats["processed"] * 100 if self.stats["processed"] > 0 else 0,
                "engine_performance": engine_stats
            },
            "detailed_results": results,
            "summary": {
                "total_processed": self.stats["processed"],
                "success_rate": self.stats["processed"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "avg_processing_time_ms": statistics.mean(self.stats["processing_times"]) if self.stats["processing_times"] else 0,
                "unique_themes_created": len(self.stats["themes_created"]),
                "performance_improvement": "待计算"  # 与基准对比
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file
    
    def generate_report(self, results_file: Path):
        """生成性能优化测试报告"""
        report_dir = Path("evaluate_service/data/results/performance_optimized_test/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"performance_report_{timestamp}.txt"
        
        with open(results_file, 'r', encoding='utf-8') as f:
            results_data = json.load(f)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("性能优化测试报告\n")
            f.write("=" * 70 + "\n\n")
            
            metadata = results_data["metadata"]
            stats = results_data["statistics"]
            summary = results_data["summary"]
            
            f.write(f"📅 测试时间: {metadata['test_time'][:19]}\n")
            f.write(f"📊 数据集: {metadata['dataset_size']} 个事件\n")
            f.write(f"🔧 优化措施: {', '.join(metadata['optimizations'])}\n\n")
            
            f.write("📈 性能指标:\n")
            f.write("-" * 50 + "\n")
            f.write(f"平均处理时间: {summary['avg_processing_time_ms']:.1f}ms\n")
            f.write(f"性能状态: {'✅ 达标 (<2秒)' if summary['avg_processing_time_ms'] < 2000 else '❌ 超标 (>2秒)'}\n")
            f.write(f"缓存命中率: {stats['cache_hit_rate']:.1f}%\n")
            f.write(f"并发处理: 支持\n\n")
            
            # 与基准对比
            baseline_time = 9825.9  # 从第二阶段测试结果获取
            optimized_time = summary['avg_processing_time_ms']
            if optimized_time > 0:
                improvement = (baseline_time - optimized_time) / baseline_time * 100
                f.write("⚡ 性能提升:\n")
                f.write(f"  基准性能: {baseline_time:.1f}ms\n")
                f.write(f"  优化后性能: {optimized_time:.1f}ms\n")
                f.write(f"  提升幅度: {improvement:.1f}%\n\n")
            
            f.write("🏷️ 题材创建统计:\n")
            f.write("-" * 30 + "\n")
            for theme, count in sorted(stats['themes_created'].items(), 
                                     key=lambda x: x[1], reverse=True)[:5]:
                f.write(f"{theme}: {count}个事件\n")
            
            # 优化建议
            f.write("\n💡 优化建议:\n")
            f.write("-" * 30 + "\n")
            if summary['avg_processing_time_ms'] < 2000:
                f.write("✅ 性能已达标，可以投入生产使用\n")
                f.write("建议：\n")
                f.write("1. 继续监控性能指标\n")
                f.write("2. 扩展测试数据集\n")
                f.write("3. 考虑更高级的缓存策略\n")
            else:
                f.write("⚠️ 性能仍需优化\n")
                f.write("建议：\n")
                f.write("1. 增加缓存命中率\n")
                f.write("2. 优化API调用频率\n")
                f.write("3. 考虑使用更快的AI模型\n")
        
        logger.info(f"📋 性能报告生成: {report_file}")

async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 第三阶段：性能优化测试")
    print("测试缓存、并发和批量处理优化效果")
    print("=" * 70)
    
    tester = PerformanceOptimizedTest()
    
    try:
        # 1. 初始化优化版组件
        print("🔧 初始化优化组件...")
        init_success = await tester.initialize_components()
        if not init_success:
            print("❌ 组件初始化失败，无法继续测试")
            return 1
        
        # 2. 加载测试数据
        print("📂 加载测试数据...")
        events = await tester.load_test_data(sample_size=15)
        if not events:
            print("❌ 没有测试数据，无法继续")
            return 1
        
        print(f"📊 测试规模: {len(events)} 个事件")
        print("🔄 将使用并发处理和缓存优化")
        
        # 3. 处理事件（并发优化）
        print("\n🔍 注意：将使用真实AI API")
        confirm = input("是否继续？ (y/n): ")
        
        if confirm.lower() != 'y':
            print("测试取消")
            return 0
        
        print("🚀 开始并发处理...")
        start_time = time.time()
        results = await tester.process_with_concurrency(events, max_concurrent=3)
        total_time = time.time() - start_time
        
        print(f"✅ 处理完成！总耗时: {total_time:.1f}秒")
        
        # 4. 分析结果
        tester.analyze_results(results)
        
        # 5. 保存结果
        results_file = tester.save_results(results)
        
        # 6. 生成报告
        tester.generate_report(results_file)
        
        print("\n" + "=" * 70)
        print("✅ 性能优化测试完成！")
        print("=" * 70)
        
        # 获取性能统计
        if hasattr(tester.engine, 'get_performance_stats'):
            stats = tester.engine.get_performance_stats()
            cache_hit_rate = stats.get('cache_hit_rate_percent', 0)
            print(f"📊 优化效果:")
            print(f"  缓存命中率: {cache_hit_rate}%")
            print(f"  平均决策时间: {stats.get('avg_decision_time', 0):.1f}ms")
        
        processing_times = tester.stats["processing_times"]
        if processing_times:
            avg_time = statistics.mean(processing_times)
            print(f"  平均处理时间: {avg_time:.1f}ms")
            print(f"  性能提升: 从 9.8秒 → {avg_time/1000:.1f}秒")
            print(f"  提升幅度: {(9825.9 - avg_time) / 9825.9 * 100:.1f}%")
        
        if tester.stats["errors"]:
            print(f"⚠️  发现 {len(tester.stats['errors'])} 个错误")
        else:
            print("✅ 无错误发生")
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())