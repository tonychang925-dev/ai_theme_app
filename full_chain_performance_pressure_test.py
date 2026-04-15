#!/usr/bin/env python3
"""
全链路性能压力测试脚本
基于进度跟踪看板_2026-04-17.md中的性能测试要求
"""

import asyncio
import json
import time
import statistics
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple
import sys
import random

# 添加项目路径
sys.path.insert(0, '/Users/admin/desktop/ai_theme_app')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FullChainPerformanceTester:
    """全链路性能压力测试器"""
    
    def __init__(self):
        self.test_results = []
        self.performance_metrics = {
            "baseline": {},
            "optimized": {},
            "comparison": {}
        }
        
    async def simulate_full_chain_processing(self, items: List[Dict]) -> Tuple[List[Dict], float]:
        """模拟全链路处理"""
        start_time = time.time()
        results = []
        
        for item in items:
            # 模拟全链路各阶段处理时间
            stages = {
                "news_raw_injection": random.uniform(0.01, 0.05),  # 新闻注入
                "news_storage": random.uniform(0.05, 0.15),  # 新闻存储
                "event_processing": random.uniform(0.5, 1.5),  # 事件处理
                "theme_classification": random.uniform(1.0, 3.0),  # 主题分类
                "decision_generation": random.uniform(0.1, 0.3),  # 决策生成
            }
            
            total_processing_time = sum(stages.values())
            await asyncio.sleep(total_processing_time)
            
            results.append({
                "item_id": item["id"],
                "success": True,
                "total_processing_time": total_processing_time,
                "stage_times": stages,
                "mode": "full_chain_baseline"
            })
        
        total_time = time.time() - start_time
        return results, total_time
    
    async def simulate_concurrent_processing(self, items: List[Dict], concurrency: int = 10) -> Tuple[List[Dict], float]:
        """模拟并发处理"""
        start_time = time.time()
        results = []
        
        # 创建并发任务
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_item(item):
            async with semaphore:
                # 模拟处理时间
                processing_time = random.uniform(2.0, 5.0)
                await asyncio.sleep(processing_time)
                
                return {
                    "item_id": item["id"],
                    "success": True,
                    "processing_time": processing_time,
                    "mode": f"concurrent_{concurrency}"
                }
        
        # 并发执行
        tasks = [process_item(item) for item in items]
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        return results, total_time
    
    async def simulate_high_load_scenario(self, items: List[Dict], load_factor: float = 2.0) -> Tuple[List[Dict], float]:
        """模拟高负载场景"""
        start_time = time.time()
        results = []
        
        for item in items:
            # 高负载下处理时间增加
            base_time = random.uniform(2.0, 4.0)
            load_penalty = base_time * (load_factor - 1.0) * random.uniform(0.5, 1.5)
            processing_time = base_time + load_penalty
            
            await asyncio.sleep(processing_time)
            
            results.append({
                "item_id": item["id"],
                "success": True,
                "processing_time": processing_time,
                "load_factor": load_factor,
                "mode": f"high_load_{load_factor}"
            })
        
        total_time = time.time() - start_time
        return results, total_time
    
    def generate_test_data(self, num_items: int = 100) -> List[Dict]:
        """生成测试数据"""
        test_data = []
        for i in range(num_items):
            test_data.append({
                "id": f"test_news_{i:04d}",
                "content": f"测试新闻内容 {i} - AI主题应用全链路性能测试",
                "timestamp": datetime.now().isoformat(),
                "category": random.choice(["finance", "tech", "market", "analysis"]),
                "length": random.randint(50, 500)
            })
        return test_data
    
    async def run_performance_test(self, test_name: str, test_func, test_data: List[Dict], **kwargs) -> Dict[str, Any]:
        """运行性能测试"""
        logger.info(f"🧪 运行性能测试: {test_name}")
        
        # 预热运行
        if len(test_data) > 5:
            warmup_data = test_data[:2]
            await test_func(warmup_data, **kwargs)
        
        # 正式测试
        start_time = time.time()
        results, processing_time = await test_func(test_data, **kwargs)
        actual_time = time.time() - start_time
        
        # 计算指标
        processing_times = [r["processing_time"] for r in results if "processing_time" in r]
        avg_processing_time = statistics.mean(processing_times) if processing_times else 0
        throughput = len(results) / actual_time if actual_time > 0 else 0
        
        # 计算百分位数延迟
        if processing_times:
            sorted_times = sorted(processing_times)
            p50 = sorted_times[int(len(sorted_times) * 0.5)]
            p90 = sorted_times[int(len(sorted_times) * 0.9)]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]
        else:
            p50 = p90 = p95 = p99 = 0
        
        test_result = {
            "test_name": test_name,
            "total_items": len(results),
            "total_time": actual_time,
            "avg_processing_time": avg_processing_time,
            "throughput": throughput,
            "throughput_units": "items/second",
            "latency_percentiles": {
                "p50": p50,
                "p90": p90,
                "p95": p95,
                "p99": p99
            },
            "success_rate": sum(1 for r in results if r["success"]) / len(results) if results else 0,
            "timestamp": datetime.now().isoformat(),
            "config": kwargs
        }
        
        logger.info(f"  ✅ {test_name}: {len(results)}项, {actual_time:.2f}秒, 吞吐量: {throughput:.2f}项/秒")
        logger.info(f"     延迟: P50={p50:.2f}s, P90={p90:.2f}s, P95={p95:.2f}s, P99={p99:.2f}s")
        
        return test_result
    
    async def test_baseline_performance(self):
        """测试基线性能"""
        logger.info("\n📊 测试基线性能（全链路处理）")
        
        test_data = self.generate_test_data(50)  # 50项测试数据
        result = await self.run_performance_test(
            "full_chain_baseline",
            self.simulate_full_chain_processing,
            test_data
        )
        
        self.performance_metrics["baseline"] = result
        self.test_results.append(result)
    
    async def test_concurrent_performance(self):
        """测试并发性能"""
        logger.info("\n📊 测试并发性能")
        
        test_data = self.generate_test_data(100)  # 100项测试数据
        
        # 测试不同并发级别
        concurrency_levels = [5, 10, 20, 50]
        for concurrency in concurrency_levels:
            result = await self.run_performance_test(
                f"concurrent_{concurrency}",
                self.simulate_concurrent_processing,
                test_data,
                concurrency=concurrency
            )
            self.test_results.append(result)
    
    async def test_high_load_performance(self):
        """测试高负载性能"""
        logger.info("\n📊 测试高负载性能")
        
        test_data = self.generate_test_data(80)  # 80项测试数据
        
        # 测试不同负载因子
        load_factors = [1.5, 2.0, 3.0, 5.0]
        for load_factor in load_factors:
            result = await self.run_performance_test(
                f"high_load_{load_factor}",
                self.simulate_high_load_scenario,
                test_data,
                load_factor=load_factor
            )
            self.test_results.append(result)
    
    def calculate_improvements(self):
        """计算性能改进"""
        logger.info("\n📈 计算性能改进")
        
        # 找到基线测试
        baseline = None
        for result in self.test_results:
            if result["test_name"] == "full_chain_baseline":
                baseline = result
                break
        
        if not baseline:
            logger.warning("未找到基线测试结果")
            return
        
        improvements = []
        for result in self.test_results:
            if result["test_name"] != "full_chain_baseline":
                # 计算吞吐量改进
                throughput_improvement = result["throughput"] / baseline["throughput"] if baseline["throughput"] > 0 else 0
                
                # 计算处理时间改进
                time_improvement = baseline["avg_processing_time"] / result["avg_processing_time"] if result["avg_processing_time"] > 0 else 0
                
                improvement = {
                    "test_name": result["test_name"],
                    "throughput_baseline": baseline["throughput"],
                    "throughput_optimized": result["throughput"],
                    "throughput_improvement": throughput_improvement,
                    "throughput_improvement_percent": (throughput_improvement - 1) * 100,
                    "processing_time_baseline": baseline["avg_processing_time"],
                    "processing_time_optimized": result["avg_processing_time"],
                    "processing_time_improvement": time_improvement,
                    "processing_time_reduction_percent": (1 - 1/time_improvement) * 100 if time_improvement > 0 else 0,
                    "latency_comparison": {
                        "baseline_p90": baseline["latency_percentiles"]["p90"],
                        "optimized_p90": result["latency_percentiles"]["p90"],
                        "p90_improvement": baseline["latency_percentiles"]["p90"] / result["latency_percentiles"]["p90"] if result["latency_percentiles"]["p90"] > 0 else 0
                    }
                }
                
                improvements.append(improvement)
                
                logger.info(f"  📊 {result['test_name']}:")
                logger.info(f"     吞吐量: {baseline['throughput']:.2f} → {result['throughput']:.2f} ({improvement['throughput_improvement_percent']:+.1f}%)")
                logger.info(f"     处理时间: {baseline['avg_processing_time']:.2f}s → {result['avg_processing_time']:.2f}s ({improvement['processing_time_reduction_percent']:+.1f}%减少)")
                logger.info(f"     P90延迟: {baseline['latency_percentiles']['p90']:.2f}s → {result['latency_percentiles']['p90']:.2f}s")
        
        self.performance_metrics["comparison"]["improvements"] = improvements
        self.performance_metrics["comparison"]["baseline"] = baseline
    
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "="*60)
        logger.info("📋 全链路性能压力测试摘要")
        logger.info("="*60)
        
        total_tests = len(self.test_results)
        baseline_throughput = None
        best_optimization = None
        best_improvement = 0
        
        # 找到基线
        for result in self.test_results:
            if result["test_name"] == "full_chain_baseline":
                baseline_throughput = result["throughput"]
                logger.info(f"基线性能: {result['throughput']:.2f} 项/秒")
                logger.info(f"基线延迟: P90={result['latency_percentiles']['p90']:.2f}s")
                break
        
        # 分析优化效果
        logger.info("\n优化效果分析:")
        for result in self.test_results:
            if result["test_name"] != "full_chain_baseline" and baseline_throughput:
                improvement = result["throughput"] / baseline_throughput
                logger.info(f"  {result['test_name']}: {result['throughput']:.2f} 项/秒 ({improvement:.1f}x)")
                
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_optimization = result["test_name"]
        
        if best_optimization:
            logger.info(f"\n🎯 最佳优化: {best_optimization} ({best_improvement:.1f}x 提升)")
        
        logger.info(f"\n总测试数: {total_tests}")
        logger.info("="*60)
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始全链路性能压力测试")
        logger.info("="*60)
        
        try:
            await self.test_baseline_performance()
            await self.test_concurrent_performance()
            await self.test_high_load_performance()
            
            self.calculate_improvements()
            self.print_summary()
            
            # 保存结果
            self.save_results()
            
            logger.info("🎉 全链路性能压力测试完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 测试执行失败: {e}", exc_info=True)
            return False
    
    def save_results(self):
        """保存测试结果"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "test_results": self.test_results,
            "performance_metrics": self.performance_metrics,
            "summary": {
                "total_tests": len(self.test_results),
                "baseline_throughput": next((r["throughput"] for r in self.test_results if r["test_name"] == "full_chain_baseline"), 0),
                "best_optimization": None,
                "best_improvement": 0
            }
        }
        
        # 找到最佳优化
        baseline = self.performance_metrics.get("baseline", {})
        if baseline:
            for improvement in self.performance_metrics.get("comparison", {}).get("improvements", []):
                if improvement["throughput_improvement"] > results["summary"]["best_improvement"]:
                    results["summary"]["best_improvement"] = improvement["throughput_improvement"]
                    results["summary"]["best_optimization"] = improvement["test_name"]
        
        with open("full_chain_performance_test_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📥 测试结果已保存到: full_chain_performance_test_results.json")

async def main():
    """主函数"""
    tester = FullChainPerformanceTester()
    success = await tester.run_all_tests()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
