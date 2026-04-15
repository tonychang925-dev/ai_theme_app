#!/usr/bin/env python3
"""
AI批量处理实验脚本
测试不同batch size对性能的影响
"""

import asyncio
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AIBatchExperiment:
    """AI批量处理实验"""
    
    def __init__(self):
        self.results = []
        
    async def simulate_ai_processing(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """模拟AI处理 - 单条处理"""
        # 模拟10-12秒的处理时间（当前瓶颈）
        processing_time = random.uniform(10.0, 12.0)
        await asyncio.sleep(processing_time)
        
        return {
            "success": True,
            "classification": random.choice(["normal", "important", "urgent"]),
            "confidence": random.uniform(0.7, 0.95),
            "processing_time": processing_time
        }
    
    async def simulate_batch_processing(self, batch_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """模拟批量处理 - 假设批量处理有优化"""
        batch_size = len(batch_data)
        
        # 模拟批量处理的优化效果
        # 基础时间 + 每条额外时间（比单条处理快）
        base_time = 2.0  # 批量处理的基础开销
        per_item_time = random.uniform(1.5, 2.5)  # 每条处理时间
        
        total_time = base_time + (per_item_time * batch_size)
        await asyncio.sleep(total_time)
        
        results = []
        for i, item in enumerate(batch_data):
            results.append({
                "success": True,
                "classification": random.choice(["normal", "important", "urgent"]),
                "confidence": random.uniform(0.7, 0.95),
                "processing_time": total_time / batch_size,  # 平均处理时间
                "item_index": i
            })
        
        return results
    
    def generate_test_data(self, count: int) -> List[Dict[str, Any]]:
        """生成测试数据"""
        test_data = []
        for i in range(count):
            test_data.append({
                "id": f"news_{i}",
                "title": f"测试新闻标题 {i} - AI性能优化实验",
                "content": f"这是测试新闻内容 {i}，用于测试AI批量处理性能。内容包含一些关键词和事件描述。",
                "keywords": ["AI", "性能", "优化", "实验", "测试"],
                "timestamp": datetime.now().isoformat()
            })
        return test_data
    
    async def run_single_processing_experiment(self, test_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """运行单条处理实验"""
        logger.info(f"🧪 开始单条处理实验: {len(test_data)} 条数据")
        
        start_time = time.time()
        results = []
        
        for i, news_item in enumerate(test_data):
            item_start = time.time()
            result = await self.simulate_ai_processing(news_item)
            item_time = time.time() - item_start
            
            results.append({
                "item_id": news_item["id"],
                "result": result,
                "processing_time": item_time
            })
            
            if (i + 1) % 5 == 0:
                logger.info(f"  处理进度: {i + 1}/{len(test_data)}")
        
        total_time = time.time() - start_time
        avg_time = total_time / len(test_data)
        
        experiment_result = {
            "experiment_type": "single_processing",
            "data_count": len(test_data),
            "total_time": total_time,
            "avg_time_per_item": avg_time,
            "throughput": len(test_data) / total_time,
            "results": results
        }
        
        logger.info(f"✅ 单条处理实验完成")
        logger.info(f"   总时间: {total_time:.2f}秒")
        logger.info(f"   平均每条: {avg_time:.2f}秒")
        logger.info(f"   吞吐量: {experiment_result['throughput']:.3f}条/秒")
        
        return experiment_result
    
    async def run_batch_processing_experiment(self, test_data: List[Dict[str, Any]], batch_size: int) -> Dict[str, Any]:
        """运行批量处理实验"""
        logger.info(f"🧪 开始批量处理实验: {len(test_data)} 条数据, batch_size={batch_size}")
        
        # 将数据分成批次
        batches = [test_data[i:i + batch_size] for i in range(0, len(test_data), batch_size)]
        
        start_time = time.time()
        all_results = []
        
        for i, batch in enumerate(batches):
            batch_start = time.time()
            batch_results = await self.simulate_batch_processing(batch)
            batch_time = time.time() - batch_start
            
            for j, result in enumerate(batch_results):
                all_results.append({
                    "item_id": batch[j]["id"],
                    "result": result,
                    "batch_index": i,
                    "batch_size": len(batch),
                    "batch_processing_time": batch_time
                })
            
            logger.info(f"  批次进度: {i + 1}/{len(batches)} (每批{batch_size}条)")
        
        total_time = time.time() - start_time
        avg_time = total_time / len(test_data)
        
        experiment_result = {
            "experiment_type": "batch_processing",
            "data_count": len(test_data),
            "batch_size": batch_size,
            "total_time": total_time,
            "avg_time_per_item": avg_time,
            "throughput": len(test_data) / total_time,
            "batch_count": len(batches),
            "results": all_results
        }
        
        logger.info(f"✅ 批量处理实验完成 (batch_size={batch_size})")
        logger.info(f"   总时间: {total_time:.2f}秒")
        logger.info(f"   平均每条: {avg_time:.2f}秒")
        logger.info(f"   吞吐量: {experiment_result['throughput']:.3f}条/秒")
        
        return experiment_result
    
    async def run_parallel_processing_experiment(self, test_data: List[Dict[str, Any]], concurrency: int) -> Dict[str, Any]:
        """运行并行处理实验"""
        logger.info(f"🧪 开始并行处理实验: {len(test_data)} 条数据, 并发数={concurrency}")
        
        start_time = time.time()
        
        # 使用信号量控制并发数
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_with_limit(news_item):
            async with semaphore:
                return await self.simulate_ai_processing(news_item)
        
        # 创建所有任务
        tasks = [process_with_limit(item) for item in test_data]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        avg_time = total_time / len(test_data)
        
        # 统计成功和失败
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        experiment_result = {
            "experiment_type": "parallel_processing",
            "data_count": len(test_data),
            "concurrency": concurrency,
            "total_time": total_time,
            "avg_time_per_item": avg_time,
            "throughput": len(test_data) / total_time,
            "success_count": success_count,
            "error_count": error_count
        }
        
        logger.info(f"✅ 并行处理实验完成 (concurrency={concurrency})")
        logger.info(f"   总时间: {total_time:.2f}秒")
        logger.info(f"   平均每条: {avg_time:.2f}秒")
        logger.info(f"   吞吐量: {experiment_result['throughput']:.3f}条/秒")
        logger.info(f"   成功: {success_count}, 失败: {error_count}")
        
        return experiment_result
    
    async def run_comprehensive_experiment(self):
        """运行综合实验"""
        logger.info("🚀 开始AI批量处理综合实验")
        print("=" * 70)
        
        # 生成测试数据
        test_data = self.generate_test_data(20)  # 20条测试数据
        
        # 1. 单条处理基准测试
        print("1️⃣ 单条处理基准测试")
        single_result = await self.run_single_processing_experiment(test_data[:5])  # 先用5条测试
        
        # 2. 批量处理实验（不同batch size）
        print("\n2️⃣ 批量处理实验")
        batch_sizes = [2, 3, 5, 10]
        batch_results = []
        
        for batch_size in batch_sizes:
            result = await self.run_batch_processing_experiment(test_data, batch_size)
            batch_results.append(result)
        
        # 3. 并行处理实验
        print("\n3️⃣ 并行处理实验")
        concurrency_levels = [2, 3, 5]
        parallel_results = []
        
        for concurrency in concurrency_levels:
            result = await self.run_parallel_processing_experiment(test_data[:10], concurrency)  # 用10条测试
            parallel_results.append(result)
        
        # 汇总结果
        summary = {
            "experiment_time": datetime.now().isoformat(),
            "test_data_count": len(test_data),
            "single_processing": single_result,
            "batch_processing": batch_results,
            "parallel_processing": parallel_results,
            "recommendations": []
        }
        
        # 生成建议
        best_batch = min(batch_results, key=lambda x: x["avg_time_per_item"])
        best_parallel = min(parallel_results, key=lambda x: x["avg_time_per_item"])
        
        summary["recommendations"].append({
            "type": "performance",
            "message": f"最佳批量大小: {best_batch['batch_size']} (平均 {best_batch['avg_time_per_item']:.2f}秒/条)",
            "improvement": f"相比单条处理提升 {(single_result['avg_time_per_item'] - best_batch['avg_time_per_item']) / single_result['avg_time_per_item'] * 100:.1f}%"
        })
        
        summary["recommendations"].append({
            "type": "performance",
            "message": f"最佳并发数: {best_parallel['concurrency']} (平均 {best_parallel['avg_time_per_item']:.2f}秒/条)",
            "improvement": f"相比单条处理提升 {(single_result['avg_time_per_item'] - best_parallel['avg_time_per_item']) / single_result['avg_time_per_item'] * 100:.1f}%"
        })
        
        # 保存结果
        report_file = f"ai_batch_experiment_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 实验报告已保存: {report_file}")
        
        # 打印摘要
        print("\n" + "=" * 70)
        print("📊 AI批量处理实验摘要")
        print("=" * 70)
        print(f"单条处理基准: {single_result['avg_time_per_item']:.2f}秒/条")
        print(f"最佳批量处理: {best_batch['avg_time_per_item']:.2f}秒/条 (batch_size={best_batch['batch_size']})")
        print(f"最佳并行处理: {best_parallel['avg_time_per_item']:.2f}秒/条 (concurrency={best_parallel['concurrency']})")
        print()
        print("💡 建议:")
        for rec in summary["recommendations"]:
            print(f"  • {rec['message']}")
            print(f"    {rec['improvement']}")
        
        return summary

async def main():
    """主函数"""
    print("🚀 AI批量处理性能优化实验")
    print("=" * 70)
    print("目标: 测试不同处理策略对AI性能的影响")
    print("当前瓶颈: 单条处理10-12秒")
    print("=" * 70)
    
    experiment = AIBatchExperiment()
    await experiment.run_comprehensive_experiment()

if __name__ == "__main__":
    asyncio.run(main())
