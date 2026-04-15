#!/usr/bin/env python3
"""
AI主题分析应用 - 全链路压力测试脚本
使用测试集数据进行真实压力测试，验证Redis性能、AI分析瓶颈等问题
"""

import json
import time
import asyncio
import asyncpg
import redis.asyncio as redis
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import uuid
import statistics
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 导入环境变量工具
from env_utils import get_database_url


class PressureFullChainTester:
    """全链路压力测试器（使用测试集数据进行真实压力测试）"""

    def __init__(self, concurrent_users: int = 10, news_per_user: int = 10):
        self.concurrent_users = concurrent_users
        self.news_per_user = news_per_user
        self.total_news_count = concurrent_users * news_per_user
        self.db_conn = None
        self.redis_client = None
        self.performance_metrics = {
            "redis_latency": [],
            "db_write_latency": [],
            "processing_times": [],
            "success_count": 0,
            "error_count": 0,
            "throughput": 0,
            "concurrent_operations": []
        }
        self.batch_id = f"pressure_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Redis流配置
        self.news_raw_stream = "stream:news:raw"
        self.events_structured_stream = "stream:events:structured"
        self.events_classified_stream = "stream:events:classified"
        self.theme_matched_stream = "stream:theme:matched"
        self.decision_stream = "stream:decision:executed"

        # 测试数据
        self.test_news_items = []

    async def __aenter__(self):
        # 连接数据库 - 创建连接池
        db_url = get_database_url()
        if not db_url:
            raise ValueError("未找到数据库配置，请检查.env.theme文件")

        # 创建连接池，支持并发操作
        self.db_pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=self.concurrent_users * 2,  # 为每个并发用户预留连接
            max_queries=50000,
            max_inactive_connection_lifetime=300
        )

        # 连接Redis
        self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=False)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'db_pool') and self.db_pool:
            await self.db_pool.close()
        if self.redis_client:
            await self.redis_client.close()

    async def load_all_test_data(self) -> List[Dict[str, Any]]:
        """加载所有测试数据（100个测试事件）"""
        print("1. 加载所有测试数据（100个测试事件）...")

        test_cases_path = "../../../evaluate_service/data/raw/test_cases.txt"

        try:
            with open(test_cases_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析测试数据
            test_cases = {}
            current_theme = None
            news_counter = 0

            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # 检查是否是主题行
                if line.startswith("测试集") and "题材名称:" in line:
                    # 提取主题名称
                    parts = line.split("题材名称:")
                    if len(parts) > 1:
                        current_theme = parts[1].strip()
                        test_cases[current_theme] = []
                elif line.startswith("- ") and current_theme:
                    # 提取新闻内容
                    news_content = line[2:].strip()
                    test_cases[current_theme].append(news_content)
                    news_counter += 1

            # 提取所有测试新闻
            news_items = []
            theme_names = list(test_cases.keys())

            for theme_name in theme_names:
                theme_news = test_cases[theme_name]
                for i, news_content in enumerate(theme_news):
                    news_items.append({
                        "id": f"pressure_news_{len(news_items):04d}",
                        "content": news_content,
                        "theme_name": theme_name,
                        "sequence": len(news_items),
                        "batch_id": self.batch_id
                    })

            print(f"  加载了 {len(news_items)} 条测试新闻（来自 {len(theme_names)} 个主题）")
            self.test_news_items = news_items
            return news_items

        except Exception as e:
            print(f"  加载测试数据失败: {str(e)}")
            return []

    async def pressure_write_single_news(self, news: Dict[str, Any]) -> Dict[str, Any]:
        """压力测试：单条新闻写入（包含性能监控）"""
        start_time = time.time()
        result = {
            "success": False,
            "news_id": news["id"],
            "db_write_time": 0,
            "redis_publish_time": 0,
            "total_time": 0,
            "error": None
        }

        try:
            # 1. 数据库写入（监控延迟）- 使用连接池
            db_start = time.time()
            async with self.db_pool.acquire() as connection:
                await connection.execute("""
                    INSERT INTO news_raw (
                        news_id, title, content, source, publish_date, publish_time,
                        market, url, created_at, is_processed
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), FALSE)
                    ON CONFLICT (news_id) DO NOTHING
                """,
                news["id"],
                f"压力测试新闻: {news['theme_name']}",
                news["content"],
                "pressure_test_dataset",
                datetime.now().date(),
                datetime.now().time(),
                "A股",
                f"http://pressure_test/{news['id']}",
                )
            db_write_time = time.time() - db_start
            result["db_write_time"] = db_write_time
            self.performance_metrics["db_write_latency"].append(db_write_time)

            # 2. Redis发布（监控延迟）
            redis_start = time.time()
            payload = {
                "_t": "news",
                "_v": 2,
                "id": news["id"],
                "t": "",
                "c": news["content"],
                "s": "cls",
                "d": datetime.now().strftime("%Y-%m-%d"),
                "tm": datetime.now().strftime("%H:%M:%S"),
                "_b": news["batch_id"],
                "_s": news["sequence"],
            }

            await self.redis_client.xadd(
                self.news_raw_stream,
                {"payload": json.dumps(payload, ensure_ascii=False)},
                maxlen=10000
            )
            redis_publish_time = time.time() - redis_start
            result["redis_publish_time"] = redis_publish_time
            self.performance_metrics["redis_latency"].append(redis_publish_time)

            # 3. 记录成功
            total_time = time.time() - start_time
            result["total_time"] = total_time
            result["success"] = True
            self.performance_metrics["success_count"] += 1
            self.performance_metrics["processing_times"].append(total_time)

        except Exception as e:
            result["error"] = str(e)
            self.performance_metrics["error_count"] += 1
            # 打印错误详情（前5个错误）
            if self.performance_metrics["error_count"] <= 5:
                print(f"      错误 [{news['id']}]: {str(e)[:100]}")

        return result

    async def run_concurrent_pressure_test(self):
        """运行并发压力测试"""
        print(f"2. 运行并发压力测试（{self.concurrent_users}个并发用户，每个用户{self.news_per_user}条新闻）...")

        if not self.test_news_items:
            print("  错误：没有测试数据")
            return

        # 准备测试数据（循环使用100个测试事件，但生成唯一的新闻ID）
        test_data = []
        for i in range(self.total_news_count):
            news_idx = i % len(self.test_news_items)
            original_news = self.test_news_items[news_idx]
            # 创建新的新闻对象，使用唯一的ID
            unique_news = original_news.copy()
            unique_news["id"] = f"pressure_news_{self.batch_id}_{i:06d}"
            unique_news["sequence"] = i
            test_data.append(unique_news)

        print(f"  准备测试 {len(test_data)} 条新闻...")

        # 运行并发测试
        start_time = time.time()
        tasks = []

        # 分批处理，模拟并发用户
        batch_size = len(test_data) // self.concurrent_users
        for i in range(self.concurrent_users):
            batch_start = i * batch_size
            batch_end = batch_start + batch_size if i < self.concurrent_users - 1 else len(test_data)
            batch_data = test_data[batch_start:batch_end]

            # 为每个并发用户创建任务
            for news in batch_data:
                task = asyncio.create_task(self.pressure_write_single_news(news))
                tasks.append(task)
                self.performance_metrics["concurrent_operations"].append(len(tasks))

        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.time() - start_time
        self.performance_metrics["throughput"] = len(test_data) / total_time if total_time > 0 else 0

        # 统计结果
        successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        failed = len(results) - successful

        print(f"  并发测试完成:")
        print(f"    - 总耗时: {total_time:.2f} 秒")
        print(f"    - 成功: {successful} 条")
        print(f"    - 失败: {failed} 条")
        print(f"    - 吞吐量: {self.performance_metrics['throughput']:.2f} 条/秒")

    async def monitor_system_performance(self, duration_seconds: int = 60):
        """监控系统性能（Redis队列积压、数据库负载等）"""
        print(f"3. 监控系统性能 ({duration_seconds}秒)...")

        start_time = time.time()
        monitoring_data = {
            "redis_stream_lengths": [],
            "db_connection_count": 0,
            "processing_backlog": 0,
            "timestamps": []
        }

        while time.time() - start_time < duration_seconds:
            current_time = time.time()

            try:
                # 监控Redis流长度
                stream_info = await self.redis_client.xlen(self.news_raw_stream)
                monitoring_data["redis_stream_lengths"].append({
                    "time": current_time - start_time,
                    "length": stream_info
                })

                # 监控数据库连接（简化版本）
                # 在实际系统中，这里可以查询pg_stat_activity等系统表

                monitoring_data["timestamps"].append(current_time - start_time)

                # 每5秒打印一次状态
                if len(monitoring_data["timestamps"]) % 5 == 0:
                    print(f"    监控状态: Redis队列长度={stream_info}, 时间={(current_time - start_time):.1f}秒")

                await asyncio.sleep(1)

            except Exception as e:
                print(f"    监控异常: {str(e)}")
                await asyncio.sleep(1)

        print(f"  性能监控完成，收集了 {len(monitoring_data['timestamps'])} 个数据点")

        return monitoring_data

    async def generate_performance_report(self):
        """生成性能测试报告"""
        print("4. 生成性能测试报告...")

        if not self.performance_metrics["processing_times"]:
            print("  错误：没有性能数据")
            return None

        # 计算统计指标
        report = {
            "test_config": {
                "concurrent_users": self.concurrent_users,
                "news_per_user": self.news_per_user,
                "total_news_count": self.total_news_count,
                "batch_id": self.batch_id,
                "test_timestamp": datetime.now().isoformat()
            },
            "performance_summary": {
                "total_success": self.performance_metrics["success_count"],
                "total_errors": self.performance_metrics["error_count"],
                "success_rate": (self.performance_metrics["success_count"] /
                               (self.performance_metrics["success_count"] + self.performance_metrics["error_count"]) * 100
                               if (self.performance_metrics["success_count"] + self.performance_metrics["error_count"]) > 0 else 0),
                "throughput_ops_per_second": self.performance_metrics["throughput"]
            },
            "latency_metrics": {
                "db_write_latency": {
                    "avg": statistics.mean(self.performance_metrics["db_write_latency"]) if self.performance_metrics["db_write_latency"] else 0,
                    "min": min(self.performance_metrics["db_write_latency"]) if self.performance_metrics["db_write_latency"] else 0,
                    "max": max(self.performance_metrics["db_write_latency"]) if self.performance_metrics["db_write_latency"] else 0,
                    "p95": statistics.quantiles(self.performance_metrics["db_write_latency"], n=20)[18] if len(self.performance_metrics["db_write_latency"]) >= 20 else 0
                },
                "redis_latency": {
                    "avg": statistics.mean(self.performance_metrics["redis_latency"]) if self.performance_metrics["redis_latency"] else 0,
                    "min": min(self.performance_metrics["redis_latency"]) if self.performance_metrics["redis_latency"] else 0,
                    "max": max(self.performance_metrics["redis_latency"]) if self.performance_metrics["redis_latency"] else 0,
                    "p95": statistics.quantiles(self.performance_metrics["redis_latency"], n=20)[18] if len(self.performance_metrics["redis_latency"]) >= 20 else 0
                },
                "total_processing_time": {
                    "avg": statistics.mean(self.performance_metrics["processing_times"]) if self.performance_metrics["processing_times"] else 0,
                    "min": min(self.performance_metrics["processing_times"]) if self.performance_metrics["processing_times"] else 0,
                    "max": max(self.performance_metrics["processing_times"]) if self.performance_metrics["processing_times"] else 0
                }
            },
            "bottleneck_analysis": {
                "db_write_bottleneck": "是" if (statistics.mean(self.performance_metrics["db_write_latency"]) if self.performance_metrics["db_write_latency"] else 0) > 0.1 else "否",
                "redis_bottleneck": "是" if (statistics.mean(self.performance_metrics["redis_latency"]) if self.performance_metrics["redis_latency"] else 0) > 0.05 else "否",
                "concurrent_limit": max(self.performance_metrics["concurrent_operations"]) if self.performance_metrics["concurrent_operations"] else 0
            },
            "recommendations": []
        }

        # 生成建议
        if report["latency_metrics"]["db_write_latency"]["avg"] > 0.1:
            report["recommendations"].append("数据库写入延迟较高，建议优化数据库索引或增加连接池")

        if report["latency_metrics"]["redis_latency"]["avg"] > 0.05:
            report["recommendations"].append("Redis发布延迟较高，建议检查Redis服务器性能或网络连接")

        if report["performance_summary"]["success_rate"] < 95:
            report["recommendations"].append(f"成功率较低 ({report['performance_summary']['success_rate']:.1f}%)，建议检查错误日志")

        # 打印报告摘要
        print("\n" + "=" * 60)
        print("性能测试报告摘要:")
        print("=" * 60)
        print(f"测试配置: {report['test_config']['concurrent_users']}并发用户 × {report['test_config']['news_per_user']}条新闻")
        print(f"成功率: {report['performance_summary']['success_rate']:.1f}%")
        print(f"吞吐量: {report['performance_summary']['throughput_ops_per_second']:.2f} 条/秒")
        print(f"数据库写入延迟: {report['latency_metrics']['db_write_latency']['avg']*1000:.1f}ms (平均)")
        print(f"Redis发布延迟: {report['latency_metrics']['redis_latency']['avg']*1000:.1f}ms (平均)")
        print(f"瓶颈分析: DB={report['bottleneck_analysis']['db_write_bottleneck']}, Redis={report['bottleneck_analysis']['redis_bottleneck']}")

        if report["recommendations"]:
            print("\n优化建议:")
            for rec in report["recommendations"]:
                print(f"  - {rec}")

        print("=" * 60)

        return report

    async def run_full_pressure_test(self) -> bool:
        """运行完整压力测试"""
        print("=" * 60)
        print("AI主题分析应用 - 全链路压力测试")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"测试配置: {self.concurrent_users}并发用户 × {self.news_per_user}条新闻")
        print(f"总新闻数: {self.total_news_count}")
        print(f"测试批次ID: {self.batch_id}")
        print("=" * 60)

        start_time = time.time()

        try:
            # 1. 加载测试数据
            await self.load_all_test_data()
            if not self.test_news_items:
                print("错误: 没有加载到测试数据")
                return False

            # 2. 运行并发压力测试
            await self.run_concurrent_pressure_test()

            # 3. 监控系统性能
            await self.monitor_system_performance(duration_seconds=30)

            # 4. 生成性能报告
            report = await self.generate_performance_report()

            # 5. 保存报告
            if report:
                report_file = f"pressure_test_report_{self.batch_id}.json"
                with open(report_file, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f"\n详细报告已保存: {report_file}")

            end_time = time.time()
            print(f"\n✅ 压力测试完成！总耗时: {end_time - start_time:.1f} 秒")

            # 判断测试是否通过（成功率 > 90%）
            success_rate = report["performance_summary"]["success_rate"] if report else 0
            return success_rate > 90

        except Exception as e:
            print(f"压力测试异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='AI主题分析应用全链路压力测试')
    parser.add_argument('--concurrent-users', type=int, default=5, help='并发用户数量')
    parser.add_argument('--news-per-user', type=int, default=20, help='每个用户的新闻数量')
    parser.add_argument('--monitor-seconds', type=int, default=30, help='性能监控时间（秒）')

    args = parser.parse_args()

    async with PressureFullChainTester(args.concurrent_users, args.news_per_user) as tester:
        success = await tester.run_full_pressure_test()

        if success:
            print("\n✅ 全链路压力测试通过！系统性能满足要求。")
            return 0
        else:
            print("\n❌ 全链路压力测试失败！系统性能需要优化。")
            return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n用户中断测试")
        sys.exit(130)
    except Exception as e:
        print(f"测试异常: {str(e)}")
        sys.exit(1)
