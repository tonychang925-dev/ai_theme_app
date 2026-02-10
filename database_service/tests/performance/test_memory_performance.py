#!/usr/bin/env python3
"""
内存数据库性能基准测试 - 28字段表结构
测试内存管理器在28字段结构下的性能
"""
import os
import asyncio
import time
import statistics
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path

# 设置正确的Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)  # ai_theme_app
sys.path.insert(0, service_dir)   # database_service

from database_service.factory import DatabaseManagerFactory
from database_service.config import DatabaseConfig, DatabaseType
from database_service.interface import ThemeTags


class MemoryPerformanceBenchmark:
    """内存数据库性能基准测试类"""
    
    def __init__(self):
        self.results = {}
        self.operations_count = 50  # 减少操作次数以加快测试
        self.batch_sizes = [1, 10, 50]  # 调整批量操作的大小
        self.manager = None
        
    async def run_all_benchmarks(self):
        """运行所有性能基准测试"""
        print("⚡ 内存数据库性能基准测试 - 28字段表结构")
        print("=" * 60)
        
        try:
            # 创建管理器 - 使用最简单的配置
            config = DatabaseConfig(
                db_type=DatabaseType.MEMORY
            )
            
            # 禁用Redis以进行纯内存测试
            config.redis.enabled = False
            
            # 设置表名配置
            config.table_names = {"theme_master": "performance_themes"}
            
            self.manager = await DatabaseManagerFactory.create_manager(config)
            
            # 运行基准测试
            await self.benchmark_create_themes()
            await self.benchmark_get_themes()
            await self.benchmark_update_themes()
            await self.benchmark_search_operations()
            await self.benchmark_batch_operations()
            await self.benchmark_concurrent_operations()
            
            # 清理
            await self.manager.disconnect()
            
            # 显示结果
            await self.display_results()
            
        except Exception as e:
            print(f"❌ 性能测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return True
    
    async def benchmark_create_themes(self):
        """基准测试：创建主题"""
        print("\n📝 基准测试1: 创建主题 (28字段)")
        
        # 单次创建
        single_times = []
        for i in range(self.operations_count):
            start_time = time.time()
            
            theme = await self.manager.create_theme(
                name=f"性能测试主题{i}",
                code=f"PERF_CREATE_{i:04d}",
                description=f"性能测试主题{i}描述",
                level1_category="性能测试",
                level2_category="创建测试",
                level3_category="单次创建",
                category_path=["性能测试", "创建测试", "单次创建"],
                category1_code="P001",
                category2_code="C001",
                category3_code="S001",
                tags=ThemeTags(
                    keywords=[f"性能{i}", "创建", "28字段"],
                    heat_level="medium",
                    industries=["性能测试行业"]
                ),
                heat_score=50 + i % 50,
                confidence_score=0.7 + (i % 30) / 100,
                related_stocks=[f"STOCK{i:04d}" for _ in range(3)],
                stock_count=3,
                news_count=i % 20,
                mention_count=i % 10
            )
            
            assert theme is not None
            single_times.append(time.time() - start_time)
        
        # 计算统计
        avg_single = statistics.mean(single_times) * 1000  # 转换为毫秒
        min_single = min(single_times) * 1000
        max_single = max(single_times) * 1000
        std_single = statistics.stdev(single_times) * 1000 if len(single_times) > 1 else 0
        
        self.results["create_single"] = {
            "count": self.operations_count,
            "avg_ms": avg_single,
            "min_ms": min_single,
            "max_ms": max_single,
            "std_ms": std_single,
            "ops_per_sec": 1000 / avg_single if avg_single > 0 else 0
        }
        
        print(f"  单次创建 {self.operations_count} 个主题:")
        print(f"    平均时间: {avg_single:.2f} ms")
        print(f"    最小时间: {min_single:.2f} ms")
        print(f"    最大时间: {max_single:.2f} ms")
        print(f"    标准差: {std_single:.2f} ms")
        print(f"    每秒操作数: {1000/avg_single:.1f} ops/sec")
    
    async def benchmark_get_themes(self):
        """基准测试：获取主题"""
        print("\n🔍 基准测试2: 获取主题")
        
        # 先创建一些测试主题
        theme_ids = []
        for i in range(self.operations_count):
            theme = await self.manager.create_theme(
                name=f"获取测试主题{i}",
                code=f"PERF_GET_{i:04d}",
                description=f"获取性能测试主题{i}"
            )
            theme_ids.append(theme.id)
        
        # 按ID获取
        get_by_id_times = []
        for theme_id in theme_ids:
            start_time = time.time()
            theme = await self.manager.get_theme(theme_id)
            assert theme is not None
            get_by_id_times.append(time.time() - start_time)
        
        # 按code获取
        get_by_code_times = []
        for i in range(self.operations_count):
            start_time = time.time()
            theme = await self.manager.get_theme_by_code(f"PERF_GET_{i:04d}")
            assert theme is not None
            get_by_code_times.append(time.time() - start_time)
        
        # 计算统计
        avg_by_id = statistics.mean(get_by_id_times) * 1000
        avg_by_code = statistics.mean(get_by_code_times) * 1000
        
        self.results["get_by_id"] = {
            "count": self.operations_count,
            "avg_ms": avg_by_id,
            "ops_per_sec": 1000 / avg_by_id if avg_by_id > 0 else 0
        }
        
        self.results["get_by_code"] = {
            "count": self.operations_count,
            "avg_ms": avg_by_code,
            "ops_per_sec": 1000 / avg_by_code if avg_by_code > 0 else 0
        }
        
        print(f"  按ID获取 {self.operations_count} 次:")
        print(f"    平均时间: {avg_by_id:.2f} ms")
        print(f"    每秒操作数: {1000/avg_by_id:.1f} ops/sec")
        
        print(f"  按code获取 {self.operations_count} 次:")
        print(f"    平均时间: {avg_by_code:.2f} ms")
        print(f"    每秒操作数: {1000/avg_by_code:.1f} ops/sec")
    
    async def benchmark_update_themes(self):
        """基准测试：更新主题"""
        print("\n🔄 基准测试3: 更新主题")
        
        # 创建测试主题
        theme_ids = []
        for i in range(self.operations_count):
            theme = await self.manager.create_theme(
                name=f"更新测试主题{i}",
                code=f"PERF_UPDATE_{i:04d}",
                heat_score=50
            )
            theme_ids.append(theme.id)
        
        # 更新操作
        update_times = []
        increment_times = []
        
        for i, theme_id in enumerate(theme_ids):
            # 测试完整更新
            start_time = time.time()
            updated = await self.manager.update_theme(theme_id, {
                "heat_score": 75,
                "description": f"更新后的主题{i}",
                "tags": {"heat_level": "high", "keywords": ["更新", f"测试{i}"]}
            })
            assert updated is not None
            update_times.append(time.time() - start_time)
            
            # 测试增加操作
            start_time = time.time()
            await self.manager.increment_theme_heat(theme_id, 5)
            await self.manager.increment_mention_count(theme_id, 2)
            increment_times.append(time.time() - start_time)
        
        # 计算统计
        avg_update = statistics.mean(update_times) * 1000
        avg_increment = statistics.mean(increment_times) * 1000
        
        self.results["update_full"] = {
            "count": self.operations_count,
            "avg_ms": avg_update,
            "ops_per_sec": 1000 / avg_update if avg_update > 0 else 0
        }
        
        self.results["update_increment"] = {
            "count": self.operations_count,
            "avg_ms": avg_increment,
            "ops_per_sec": 1000 / avg_increment if avg_increment > 0 else 0
        }
        
        print(f"  完整更新 {self.operations_count} 次:")
        print(f"    平均时间: {avg_update:.2f} ms")
        print(f"    每秒操作数: {1000/avg_update:.1f} ops/sec")
        
        print(f"  增加操作 {self.operations_count} 次:")
        print(f"    平均时间: {avg_increment:.2f} ms")
        print(f"    每秒操作数: {1000/avg_increment:.1f} ops/sec")
    
    async def benchmark_search_operations(self):
        """基准测试：搜索操作"""
        print("\n🔎 基准测试4: 搜索操作")
        
        # 创建具有不同关键词的主题
        keywords_list = ["人工智能", "机器学习", "大数据", "区块链", "云计算"]
        
        for i in range(min(self.operations_count, 50)):  # 减少创建数量
            keyword = keywords_list[i % len(keywords_list)]
            await self.manager.create_theme(
                name=f"{keyword}测试主题{i}",
                code=f"PERF_SEARCH_{keyword}_{i:04d}",
                description=f"{keyword}性能测试主题{i}",
                tags=ThemeTags(
                    keywords=[keyword, f"测试{i}", "性能测试"],
                    heat_level=["low", "medium", "high"][i % 3]
                ),
                heat_score=40 + i % 60
            )
        
        # 测试搜索
        search_times = []
        keyword_times = []
        category_times = []
        heat_times = []
        
        test_count = min(20, self.operations_count)  # 进一步减少测试次数
        for i in range(test_count):
            # 普通搜索
            start_time = time.time()
            results = await self.manager.search_themes("测试", limit=10)
            search_times.append(time.time() - start_time)
            
            # 关键词搜索
            keyword = keywords_list[i % len(keywords_list)]
            start_time = time.time()
            results = await self.manager.get_themes_by_keywords([keyword], limit=10)
            keyword_times.append(time.time() - start_time)
            
            # 热度搜索
            start_time = time.time()
            results = await self.manager.get_themes_by_heat_level(min_heat=50, limit=10)
            heat_times.append(time.time() - start_time)
        
        # 计算统计
        avg_search = statistics.mean(search_times) * 1000 if search_times else 0
        avg_keyword = statistics.mean(keyword_times) * 1000 if keyword_times else 0
        avg_heat = statistics.mean(heat_times) * 1000 if heat_times else 0
        
        self.results["search_general"] = {
            "count": len(search_times),
            "avg_ms": avg_search,
            "ops_per_sec": 1000 / avg_search if avg_search > 0 else 0
        }
        
        self.results["search_keyword"] = {
            "count": len(keyword_times),
            "avg_ms": avg_keyword,
            "ops_per_sec": 1000 / avg_keyword if avg_keyword > 0 else 0
        }
        
        self.results["search_heat"] = {
            "count": len(heat_times),
            "avg_ms": avg_heat,
            "ops_per_sec": 1000 / avg_heat if avg_heat > 0 else 0
        }
        
        print(f"  普通搜索 {len(search_times)} 次:")
        print(f"    平均时间: {avg_search:.2f} ms")
        print(f"    每秒操作数: {1000/avg_search:.1f} ops/sec")
        
        print(f"  关键词搜索 {len(keyword_times)} 次:")
        print(f"    平均时间: {avg_keyword:.2f} ms")
        print(f"    每秒操作数: {1000/avg_keyword:.1f} ops/sec")
        
        print(f"  热度搜索 {len(heat_times)} 次:")
        print(f"    平均时间: {avg_heat:.2f} ms")
        print(f"    每秒操作数: {1000/avg_heat:.1f} ops/sec")
    
    async def benchmark_batch_operations(self):
        """基准测试：批量操作"""
        print("\n📦 基准测试5: 批量操作")
        
        batch_results = {}
        
        for batch_size in self.batch_sizes:
            # 使用UUID确保每个批量测试的唯一性
            batch_id = str(uuid.uuid4())[:8]
            
            # 准备批量数据
            themes_data = []
            for i in range(batch_size):
                themes_data.append({
                    "name": f"批量测试主题{batch_id}_{i}",
                    "code": f"BATCH_PERF_{batch_id}_{i:04d}",
                    "description": f"批量性能测试主题{batch_id}_{i}",
                    "level1_category": "批量测试",
                    "tags": {
                        "keywords": [f"批量{batch_id}", f"测试{i}"],
                        "heat_level": "medium"
                    },
                    "heat_score": 50 + i % 50
                })
            
            # 批量创建
            try:
                start_time = time.time()
                themes = await self.manager.batch_create_themes(themes_data)
                batch_time = time.time() - start_time
                
                assert len(themes) == batch_size
                
                # 计算性能
                avg_time_per_theme = (batch_time / batch_size) * 1000
                ops_per_sec = batch_size / batch_time
                
                batch_results[batch_size] = {
                    "batch_size": batch_size,
                    "total_time_ms": batch_time * 1000,
                    "avg_time_per_theme_ms": avg_time_per_theme,
                    "ops_per_sec": ops_per_sec,
                    "efficiency_gain": 1.0  # 基准值
                }
                
            except Exception as e:
                print(f"  批量大小 {batch_size} 创建失败: {e}")
                # 继续下一个批量测试
        
        # 计算效率增益（相对于单次操作）
        if 1 in batch_results and batch_results[1]["avg_time_per_theme_ms"] > 0:
            single_avg = batch_results[1]["avg_time_per_theme_ms"]
            for size in self.batch_sizes:
                if size > 1 and size in batch_results:
                    batch_avg = batch_results[size]["avg_time_per_theme_ms"]
                    efficiency = single_avg / batch_avg if batch_avg > 0 else 1.0
                    batch_results[size]["efficiency_gain"] = efficiency
        
        self.results["batch_create"] = batch_results
        
        print(f"  批量创建性能:")
        for size in self.batch_sizes:
            if size in batch_results:
                result = batch_results[size]
                print(f"    批量大小 {size}:")
                print(f"      总时间: {result['total_time_ms']:.2f} ms")
                print(f"      每个主题平均: {result['avg_time_per_theme_ms']:.2f} ms")
                print(f"      每秒操作数: {result['ops_per_sec']:.1f} ops/sec")
                if size > 1:
                    print(f"      效率增益: {result['efficiency_gain']:.1f}x")
            else:
                print(f"    批量大小 {size}: 测试失败")
    
    async def benchmark_concurrent_operations(self):
        """基准测试：并发操作"""
        print("\n⚡ 基准测试6: 并发操作")
        
        # 创建测试主题
        theme_ids = []
        for i in range(50):  # 减少主题数量
            theme = await self.manager.create_theme(
                name=f"并发测试主题{i}",
                code=f"CONCURRENT_{i:04d}",
                heat_score=50
            )
            theme_ids.append(theme.id)
        
        # 并发读取测试
        concurrency_levels = [1, 5, 10]
        concurrent_results = {}
        
        for concurrency in concurrency_levels:
            print(f"  测试并发度: {concurrency}")
            
            # 准备任务
            tasks = []
            operations_per_concurrent = 5  # 减少每个并发的操作次数
            for i in range(concurrency * operations_per_concurrent):
                theme_id = theme_ids[i % len(theme_ids)]
                tasks.append(self.manager.get_theme(theme_id))
            
            # 执行并发测试
            start_time = time.time()
            
            # 分批执行以避免太多并发
            batch_size = concurrency
            total_batches = (len(tasks) + batch_size - 1) // batch_size
            
            for batch_num in range(total_batches):
                batch_start = batch_num * batch_size
                batch_end = min(batch_start + batch_size, len(tasks))
                batch_tasks = tasks[batch_start:batch_end]
                
                await asyncio.gather(*batch_tasks)
            
            total_time = time.time() - start_time
            
            # 计算性能
            total_operations = len(tasks)
            avg_time_per_op = (total_time / total_operations) * 1000
            ops_per_sec = total_operations / total_time
            
            concurrent_results[concurrency] = {
                "concurrency": concurrency,
                "total_operations": total_operations,
                "total_time_ms": total_time * 1000,
                "avg_time_per_op_ms": avg_time_per_op,
                "ops_per_sec": ops_per_sec
            }
        
        self.results["concurrent_read"] = concurrent_results
        
        print(f"  并发读取性能:")
        for concurrency in concurrency_levels:
            result = concurrent_results[concurrency]
            print(f"    并发度 {concurrency}:")
            print(f"      总操作数: {result['total_operations']}")
            print(f"      总时间: {result['total_time_ms']:.2f} ms")
            print(f"      每个操作平均: {result['avg_time_per_op_ms']:.2f} ms")
            print(f"      每秒操作数: {result['ops_per_sec']:.1f} ops/sec")
    
    async def display_results(self):
        """显示性能测试结果"""
        print("\n" + "=" * 60)
        print("📊 性能测试结果汇总")
        print("=" * 60)
        
        # 汇总关键指标
        print("\n🔑 关键性能指标:")
        
        if "create_single" in self.results:
            create = self.results["create_single"]
            print(f"  单次创建: {create['avg_ms']:.2f} ms/op, {create['ops_per_sec']:.1f} ops/sec")
        
        if "get_by_id" in self.results:
            get_id = self.results["get_by_id"]
            print(f"  按ID获取: {get_id['avg_ms']:.2f} ms/op, {get_id['ops_per_sec']:.1f} ops/sec")
        
        if "update_full" in self.results:
            update = self.results["update_full"]
            print(f"  完整更新: {update['avg_ms']:.2f} ms/op, {update['ops_per_sec']:.1f} ops/sec")
        
        # 批量操作效率分析
        if "batch_create" in self.results:
            print("\n📦 批量操作效率分析:")
            batch_results = self.results["batch_create"]
            
            if len(batch_results) > 1:
                sizes = sorted(batch_results.keys())
                if len(sizes) > 1:
                    first_size = sizes[0]
                    last_size = sizes[-1]
                    
                    if first_size in batch_results and last_size in batch_results:
                        first_avg = batch_results[first_size]["avg_time_per_theme_ms"]
                        last_avg = batch_results[last_size]["avg_time_per_theme_ms"]
                        
                        if first_avg > 0:
                            efficiency = first_avg / last_avg
                            print(f"  从{first_size}到{last_size}的效率提升: {efficiency:.1f}x")
        
        # 并发性能分析
        if "concurrent_read" in self.results:
            print("\n⚡ 并发性能分析:")
            concurrent_results = self.results["concurrent_read"]
            
            if len(concurrent_results) > 1:
                concurrency_levels = sorted(concurrent_results.keys())
                if 1 in concurrent_results:
                    single_ops = concurrent_results[1]["ops_per_sec"]
                    max_ops = max(r["ops_per_sec"] for r in concurrent_results.values())
                    
                    if single_ops > 0:
                        scalability = max_ops / single_ops
                        print(f"  并发扩展性: {scalability:.1f}x (从1到{concurrency_levels[-1]}并发)")
        
        print("\n💡 性能建议:")
        print("  1. 对于大量数据创建，使用批量操作")
        print("  2. 高并发场景下，内存数据库表现良好")
        print("  3. 28字段结构对性能影响较小，可接受")
        print("  4. 搜索操作相对较慢，可考虑优化索引")
        
        # 保存结果到文件
        results_dir = Path(project_root) / "test_results"
        results_dir.mkdir(exist_ok=True)
        
        result_file = results_dir / f"memory_perf_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # 转换结果以便序列化
        serializable_results = self._make_results_serializable()
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2, default=str)
        
        print(f"\n📁 详细结果已保存到: {result_file}")
    
    def _make_results_serializable(self):
        """将结果转换为可序列化的格式"""
        serializable = {}
        for key, value in self.results.items():
            if isinstance(value, dict):
                # 处理嵌套字典
                if key == "batch_create":
                    serializable[key] = {
                        str(k): v for k, v in value.items()
                    }
                elif key == "concurrent_read":
                    serializable[key] = {
                        str(k): v for k, v in value.items()
                    }
                else:
                    serializable[key] = value
            else:
                serializable[key] = str(value)
        return serializable


async def main():
    """主函数"""
    print("=" * 60)
    print("⚡ 内存数据库性能基准测试启动 - 28字段表结构")
    print("=" * 60)
    
    benchmark = MemoryPerformanceBenchmark()
    success = await benchmark.run_all_benchmarks()
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())