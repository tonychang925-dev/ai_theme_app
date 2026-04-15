#!/usr/bin/env python3
"""
AI主题分析应用 - 全链路性能统计测试脚本
使用数据库和Redis流直接交互，模拟完整业务流程并统计性能数据
参考: run_full_chain_100_to_decision_with_progress.py
"""

import json
import time
import asyncio
import asyncpg
import redis.asyncio as redis
import sys
import os
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import uuid

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 导入环境变量工具
from env_utils import get_database_url


class DirectFullChainTester:
    """直接全链路测试器（使用数据库和Redis流）"""

    def __init__(self, test_news_count: int = 50):
        self.test_news_count = test_news_count
        self.db_conn = None
        self.redis_client = None
        self.test_results = []
        self.batch_id = f"test_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 性能指标收集
        self.performance_metrics = {
            "write_times": [],  # 数据库写入时间
            "redis_publish_times": [],  # Redis发布时间
            "processing_times": [],  # 各阶段处理时间
            "stage_latencies": {  # 各阶段延迟
                "news_to_event": [],
                "event_to_classified": [],
                "classified_to_theme": [],
                "theme_to_decision": []
            },
            "throughput": 0,  # 吞吐量（条/秒）
            "success_count": 0,
            "error_count": 0,
            "start_times": {},  # 各新闻开始处理时间
            "stage_completion_times": {}  # 各阶段完成时间
        }

        # Redis流配置
        self.news_raw_stream = "stream:news:raw"
        self.events_structured_stream = "stream:events:structured"
        self.events_classified_stream = "stream:events:classified"
        self.theme_matched_stream = "stream:theme:matched"
        self.decision_stream = "stream:decision:executed"

        # 性能达标标准
        self.performance_standards = {
            "db_write_latency": 0.1,  # 100ms
            "redis_publish_latency": 0.05,  # 50ms
            "news_to_event_latency": 2.0,  # 2秒
            "event_to_classified_latency": 3.0,  # 3秒
            "classified_to_theme_latency": 2.0,  # 2秒
            "theme_to_decision_latency": 1.0,  # 1秒
            "total_processing_latency": 8.0,  # 8秒
            "throughput_min": 10.0,  # 10条/秒
            "success_rate": 90.0,  # 90%
            "conversion_rate": 70.0  # 70%
        }

    async def __aenter__(self):
        # 连接数据库
        db_url = get_database_url()
        if not db_url:
            raise ValueError("未找到数据库配置，请检查.env.theme文件")

        self.db_conn = await asyncpg.connect(db_url)

        # 连接Redis
        self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=False)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.db_conn:
            await self.db_conn.close()
        if self.redis_client:
            await self.redis_client.close()

    async def load_test_data(self) -> List[Dict[str, Any]]:
        """加载测试数据"""
        print("1. 加载测试数据集...")

        test_cases_path = "../../../evaluate_service/data/raw/test_cases.txt"
        try:
            with open(test_cases_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析测试数据
            test_cases = {}
            current_theme = None

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

            # 提取测试新闻
            news_items = []
            theme_names = list(test_cases.keys())

            for i in range(min(self.test_news_count, 100)):  # 最多100条
                theme_idx = i % len(theme_names)
                theme_name = theme_names[theme_idx]
                theme_news = test_cases[theme_name]

                if theme_news:
                    news_idx = (i // len(theme_names)) % len(theme_news)
                    news_content = theme_news[news_idx]

                    news_items.append({
                        "id": f"test_news_{i:04d}",
                        "content": news_content,
                        "theme_name": theme_name,
                        "sequence": i,
                        "batch_id": self.batch_id
                    })

            print(f"  加载了 {len(news_items)} 条测试新闻")
            return news_items

        except Exception as e:
            print(f"  加载测试数据失败: {str(e)}")
            return []

    async def write_news_to_database(self, news_items: List[Dict[str, Any]]) -> int:
        """将新闻写入数据库并收集性能数据"""
        print(f"2. 将新闻写入数据库 (批量ID: {self.batch_id})...")

        success_count = 0
        total_start_time = time.time()

        for news in news_items:
            try:
                # 记录开始时间
                self.performance_metrics["start_times"][news["id"]] = time.time()

                # 数据库写入性能监控
                db_start = time.time()
                await self.db_conn.execute("""
                    INSERT INTO news_raw (
                        news_id, title, content, source, publish_date, publish_time,
                        market, url, created_at, is_processed
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), FALSE)
                    ON CONFLICT (news_id) DO NOTHING
                """,
                news["id"],  # news_id
                f"测试新闻: {news['theme_name']}",  # title
                news["content"],  # content
                "test_dataset",  # source
                datetime.now().date(),  # publish_date
                datetime.now().time(),  # publish_time
                "A股",  # market
                f"http://test/{news['id']}",  # url
                )
                db_write_time = time.time() - db_start
                self.performance_metrics["write_times"].append(db_write_time)

                # Redis发布性能监控
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
                self.performance_metrics["redis_publish_times"].append(redis_publish_time)

                success_count += 1
                self.performance_metrics["success_count"] += 1

            except Exception as e:
                print(f"  写入新闻失败 {news['id']}: {str(e)}")
                self.performance_metrics["error_count"] += 1

        total_time = time.time() - total_start_time
        if total_time > 0:
            self.performance_metrics["throughput"] = success_count / total_time

        print(f"  成功写入 {success_count}/{len(news_items)} 条新闻")
        print(f"  性能数据: DB写入平均={statistics.mean(self.performance_metrics['write_times'])*1000:.1f}ms, "
              f"Redis发布平均={statistics.mean(self.performance_metrics['redis_publish_times'])*1000:.1f}ms, "
              f"吞吐量={self.performance_metrics['throughput']:.2f}条/秒")

        return success_count

    async def monitor_processing_progress(self, expected_count: int, timeout_minutes: int = 10) -> Dict[str, Any]:
        """监控处理进度并收集各阶段延迟数据"""
        print(f"3. 监控处理进度并统计性能数据 (超时: {timeout_minutes}分钟)...")

        start_time = time.time()
        timeout_seconds = timeout_minutes * 60

        # 监控各个阶段的处理结果
        results = {
            "news_raw": 0,
            "events_structured": 0,
            "events_classified": 0,
            "theme_matched": 0,
            "decisions": 0
        }

        # 记录已处理的消息ID
        seen_ids = {
            "news_raw": set(),
            "events_structured": set(),
            "events_classified": set(),
            "theme_matched": set(),
            "decisions": set()
        }

        # 记录各阶段完成时间
        stage_completion_times = {
            "news_raw": {},
            "events_structured": {},
            "events_classified": {},
            "theme_matched": {},
            "decisions": {}
        }

        last_print_time = start_time
        last_performance_print = start_time

        while time.time() - start_time < timeout_seconds:
            current_time = time.time()

            # 每10秒打印一次进度
            if current_time - last_print_time >= 10:
                print(f"  处理进度: 新闻={results['news_raw']}, 结构化={results['events_structured']}, "
                      f"分类={results['events_classified']}, 匹配={results['theme_matched']}, 决策={results['decisions']}")
                last_print_time = current_time

            # 检查数据库中的处理结果
            try:
                # 检查news_event表（结构化结果）- 通过news_raw.news_id找到相关事件
                event_count = await self.db_conn.fetchval("""
                    SELECT COUNT(*) FROM news_event ne
                    INNER JOIN news_raw nr ON ne.news_id = nr.id
                    WHERE nr.news_id LIKE $1
                """, f"test_news_%")
                results["events_structured"] = event_count or 0

                # 检查event_theme_map表（主题匹配结果）
                theme_count = await self.db_conn.fetchval("""
                    SELECT COUNT(DISTINCT etm.event_id) FROM event_theme_map etm
                    INNER JOIN news_event ne ON etm.event_id = ne.id
                    INNER JOIN news_raw nr ON ne.news_id = nr.id
                    WHERE nr.news_id LIKE $1
                """, f"test_news_%")
                results["theme_matched"] = theme_count or 0

            except Exception as e:
                print(f"  数据库查询失败: {str(e)}")

            # 检查Redis流并收集性能数据
            try:
                # 检查结构化事件流
                structured_messages = await self.redis_client.xread(
                    {self.events_structured_stream: "0-0"},
                    count=100,
                    block=1000
                )
                for stream, messages in structured_messages:
                    for msg_id, payload in messages:
                        if msg_id not in seen_ids["events_structured"]:
                            seen_ids["events_structured"].add(msg_id)
                            results["events_structured"] += 1

                            # 提取新闻ID并计算延迟
                            try:
                                payload_data = json.loads(payload[b"payload"])
                                news_id = payload_data.get("id")
                                if news_id and news_id in self.performance_metrics["start_times"]:
                                    latency = current_time - self.performance_metrics["start_times"][news_id]
                                    self.performance_metrics["stage_latencies"]["news_to_event"].append(latency)
                                    stage_completion_times["events_structured"][news_id] = current_time
                            except Exception as e:
                                print(f"  解析结构化事件失败: {str(e)}")

                # 检查分类事件流
                classified_messages = await self.redis_client.xread(
                    {self.events_classified_stream: "0-0"},
                    count=100,
                    block=1000
                )
                for stream, messages in classified_messages:
                    for msg_id, payload in messages:
                        if msg_id not in seen_ids["events_classified"]:
                            seen_ids["events_classified"].add(msg_id)
                            results["events_classified"] += 1

                            # 计算分类延迟
                            try:
                                payload_data = json.loads(payload[b"payload"])
                                event_id = payload_data.get("event_id")
                                # 这里需要从事件ID关联到新闻ID，简化处理
                                if "events_structured" in stage_completion_times:
                                    # 查找对应的新闻ID
                                    for nid, struct_time in stage_completion_times["events_structured"].items():
                                        if current_time - struct_time < 10:  # 假设10秒内的事件
                                            latency = current_time - struct_time
                                            self.performance_metrics["stage_latencies"]["event_to_classified"].append(latency)
                                            stage_completion_times["events_classified"][nid] = current_time
                                            break
                            except Exception as e:
                                print(f"  解析分类事件失败: {str(e)}")

                # 检查主题匹配流
                theme_messages = await self.redis_client.xread(
                    {self.theme_matched_stream: "0-0"},
                    count=100,
                    block=1000
                )
                for stream, messages in theme_messages:
                    for msg_id, payload in messages:
                        if msg_id not in seen_ids["theme_matched"]:
                            seen_ids["theme_matched"].add(msg_id)
                            results["theme_matched"] += 1

                # 检查决策流
                decision_messages = await self.redis_client.xread(
                    {self.decision_stream: "0-0"},
                    count=100,
                    block=1000
                )
                for stream, messages in decision_messages:
                    for msg_id, payload in messages:
                        if msg_id not in seen_ids["decisions"]:
                            seen_ids["decisions"].add(msg_id)
                            results["decisions"] += 1

                            # 计算总处理延迟
                            try:
                                payload_data = json.loads(payload[b"payload"])
                                news_id = payload_data.get("news_id")
                                if news_id and news_id in self.performance_metrics["start_times"]:
                                    total_latency = current_time - self.performance_metrics["start_times"][news_id]
                                    self.performance_metrics["processing_times"].append(total_latency)
                                    stage_completion_times["decisions"][news_id] = current_time
                            except Exception as e:
                                print(f"  解析决策事件失败: {str(e)}")

            except Exception as e:
                print(f"  Redis流检查失败: {str(e)}")

            # 检查是否完成
            if results["decisions"] >= expected_count * 0.8:  # 80%完成率
                print(f"  达到完成标准: {results['decisions']}/{expected_count} 条决策")
                break

            await asyncio.sleep(2)

        elapsed_time = time.time() - start_time
        print(f"  监控结束，耗时: {elapsed_time:.1f}秒")

        # 保存阶段完成时间
        self.performance_metrics["stage_completion_times"] = stage_completion_times

        # 每30秒打印一次性能数据
        if current_time - last_performance_print >= 30:
            self._print_performance_summary()
            last_performance_print = current_time

        return results

    def _print_performance_summary(self):
        """打印性能数据摘要"""
        print("\n" + "=" * 60)
        print("性能数据摘要:")
        print("=" * 60)

        if self.performance_metrics["write_times"]:
            avg_db_write = statistics.mean(self.performance_metrics["write_times"]) * 1000
            print(f"数据库写入延迟: {avg_db_write:.1f}ms (平均)")

        if self.performance_metrics["redis_publish_times"]:
            avg_redis_publish = statistics.mean(self.performance_metrics["redis_publish_times"]) * 1000
            print(f"Redis发布延迟: {avg_redis_publish:.1f}ms (平均)")

        if self.performance_metrics["stage_latencies"]["news_to_event"]:
            avg_news_to_event = statistics.mean(self.performance_metrics["stage_latencies"]["news_to_event"])
            print(f"新闻→事件延迟: {avg_news_to_event:.2f}秒 (平均)")

        if self.performance_metrics["stage_latencies"]["event_to_classified"]:
            avg_event_to_classified = statistics.mean(self.performance_metrics["stage_latencies"]["event_to_classified"])
            print(f"事件→分类延迟: {avg_event_to_classified:.2f}秒 (平均)")

        if self.performance_metrics["processing_times"]:
            avg_total = statistics.mean(self.performance_metrics["processing_times"])
            print(f"总处理延迟: {avg_total:.2f}秒 (平均)")

        print(f"吞吐量: {self.performance_metrics['throughput']:.2f}条/秒")

        total_ops = self.performance_metrics["success_count"] + self.performance_metrics["error_count"]
        if total_ops > 0:
            success_rate = (self.performance_metrics["success_count"] / total_ops) * 100
            print(f"成功率: {success_rate:.1f}% ({self.performance_metrics['success_count']}/{total_ops})")

        print("=" * 60)

    def _verify_performance_standards(self) -> Dict[str, Any]:
        """验证性能数据是否达标"""
        verification = {
            "standards": self.performance_standards.copy(),
            "actual_values": {},
            "passed": {},
            "overall_passed": True,
            "recommendations": []
        }

        # 检查数据库写入延迟
        if self.performance_metrics["write_times"]:
            avg_db_write = statistics.mean(self.performance_metrics["write_times"])
            verification["actual_values"]["db_write_latency"] = avg_db_write
            verification["passed"]["db_write_latency"] = avg_db_write <= self.performance_standards["db_write_latency"]
            if not verification["passed"]["db_write_latency"]:
                verification["overall_passed"] = False
                verification["recommendations"].append(f"数据库写入延迟过高: {avg_db_write*1000:.1f}ms > {self.performance_standards['db_write_latency']*1000:.0f}ms")

        # 检查Redis发布延迟
        if self.performance_metrics["redis_publish_times"]:
            avg_redis_publish = statistics.mean(self.performance_metrics["redis_publish_times"])
            verification["actual_values"]["redis_publish_latency"] = avg_redis_publish
            verification["passed"]["redis_publish_latency"] = avg_redis_publish <= self.performance_standards["redis_publish_latency"]
            if not verification["passed"]["redis_publish_latency"]:
                verification["overall_passed"] = False
                verification["recommendations"].append(f"Redis发布延迟过高: {avg_redis_publish*1000:.1f}ms > {self.performance_standards['redis_publish_latency']*1000:.0f}ms")

        # 检查各阶段延迟
        for stage in ["news_to_event", "event_to_classified", "classified_to_theme", "theme_to_decision"]:
            if self.performance_metrics["stage_latencies"][stage]:
                avg_latency = statistics.mean(self.performance_metrics["stage_latencies"][stage])
                verification["actual_values"][f"{stage}_latency"] = avg_latency
                standard_key = f"{stage}_latency"
                if standard_key in self.performance_standards:
                    verification["passed"][standard_key] = avg_latency <= self.performance_standards[standard_key]
                    if not verification["passed"][standard_key]:
                        verification["overall_passed"] = False
                        verification["recommendations"].append(f"{stage}延迟过高: {avg_latency:.2f}秒 > {self.performance_standards[standard_key]:.1f}秒")

        # 检查总处理延迟
        if self.performance_metrics["processing_times"]:
            avg_total = statistics.mean(self.performance_metrics["processing_times"])
            verification["actual_values"]["total_processing_latency"] = avg_total
            verification["passed"]["total_processing_latency"] = avg_total <= self.performance_standards["total_processing_latency"]
            if not verification["passed"]["total_processing_latency"]:
                verification["overall_passed"] = False
                verification["recommendations"].append(f"总处理延迟过高: {avg_total:.2f}秒 > {self.performance_standards['total_processing_latency']:.1f}秒")

        # 检查吞吐量
        verification["actual_values"]["throughput"] = self.performance_metrics["throughput"]
        verification["passed"]["throughput"] = self.performance_metrics["throughput"] >= self.performance_standards["throughput_min"]
        if not verification["passed"]["throughput"]:
            verification["overall_passed"] = False
            verification["recommendations"].append(f"吞吐量过低: {self.performance_metrics['throughput']:.2f}条/秒 < {self.performance_standards['throughput_min']:.0f}条/秒")

        # 检查成功率
        total_ops = self.performance_metrics["success_count"] + self.performance_metrics["error_count"]
        if total_ops > 0:
            success_rate = (self.performance_metrics["success_count"] / total_ops) * 100
            verification["actual_values"]["success_rate"] = success_rate
            verification["passed"]["success_rate"] = success_rate >= self.performance_standards["success_rate"]
            if not verification["passed"]["success_rate"]:
                verification["overall_passed"] = False
                verification["recommendations"].append(f"成功率过低: {success_rate:.1f}% < {self.performance_standards['success_rate']:.0f}%")

        return verification

    async def verify_final_results(self) -> Dict[str, Any]:
        """验证最终结果和性能数据"""
        print("4. 验证最终结果和性能数据...")

        verification = {
            "database_tables": {},
            "processing_stats": {},
            "performance_verification": {},
            "errors": []
        }

        try:
            # 检查各表数据量
            tables = ["news_raw", "news_event", "event_theme_map"]
            # theme_decision表可能不存在，先检查
            try:
                theme_decision_count = await self.db_conn.fetchval("SELECT COUNT(*) FROM theme_decision")
                verification["database_tables"]["theme_decision"] = theme_decision_count or 0
            except Exception:
                verification["database_tables"]["theme_decision"] = 0
                print("  注意: theme_decision表不存在")

            for table in tables:
                try:
                    count = await self.db_conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    verification["database_tables"][table] = count or 0
                except Exception as e:
                    verification["database_tables"][table] = 0
                    print(f"  注意: {table}表查询失败: {str(e)}")

            # 检查测试批次数据
            test_news_count = await self.db_conn.fetchval("""
                SELECT COUNT(*) FROM news_raw
                WHERE news_id LIKE $1
            """, "test_news_%")

            test_events_count = await self.db_conn.fetchval("""
                SELECT COUNT(*) FROM news_event ne
                INNER JOIN news_raw nr ON ne.news_id = nr.id
                WHERE nr.news_id LIKE $1
            """, "test_news_%")

            test_themes_count = await self.db_conn.fetchval("""
                SELECT COUNT(DISTINCT etm.event_id) FROM event_theme_map etm
                INNER JOIN news_event ne ON etm.event_id = ne.id
                INNER JOIN news_raw nr ON ne.news_id = nr.id
                WHERE nr.news_id LIKE $1
            """, "test_news_%")

            verification["processing_stats"] = {
                "test_news_count": test_news_count or 0,
                "test_events_count": test_events_count or 0,
                "test_themes_count": test_themes_count or 0,
                "conversion_rate": (test_themes_count / test_news_count * 100) if test_news_count > 0 else 0
            }

            print(f"  测试数据统计:")
            print(f"    - 原始新闻: {verification['processing_stats']['test_news_count']}")
            print(f"    - 结构化事件: {verification['processing_stats']['test_events_count']}")
            print(f"    - 主题匹配: {verification['processing_stats']['test_themes_count']}")
            print(f"    - 转换率: {verification['processing_stats']['conversion_rate']:.1f}%")

            # 验证性能数据是否达标
            performance_verification = self._verify_performance_standards()
            verification["performance_verification"] = performance_verification

            print("\n" + "=" * 60)
            print("性能达标验证结果:")
            print("=" * 60)

            passed_count = sum(1 for v in performance_verification["passed"].values() if v)
            total_count = len(performance_verification["passed"])
            print(f"通过率: {passed_count}/{total_count} ({passed_count/total_count*100:.1f}%)")

            for metric, passed in performance_verification["passed"].items():
                actual = performance_verification["actual_values"].get(metric, "N/A")
                standard = performance_verification["standards"].get(metric, "N/A")
                status = "✅ 通过" if passed else "❌ 失败"

                if isinstance(actual, float):
                    if "latency" in metric:
                        actual_str = f"{actual*1000:.1f}ms" if actual < 1 else f"{actual:.2f}秒"
                        standard_str = f"{standard*1000:.0f}ms" if standard < 1 else f"{standard:.1f}秒"
                    elif "rate" in metric:
                        actual_str = f"{actual:.1f}%"
                        standard_str = f"{standard:.0f}%"
                    elif "throughput" in metric:
                        actual_str = f"{actual:.2f}条/秒"
                        if isinstance(standard, (int, float)):
                            standard_str = f"{standard:.0f}条/秒"
                        else:
                            standard_str = str(standard)
                    else:
                        actual_str = f"{actual:.3f}"
                        standard_str = f"{standard:.3f}"
                else:
                    actual_str = str(actual)
                    standard_str = str(standard)

                print(f"  {metric}: {actual_str} (标准: {standard_str}) - {status}")

            if performance_verification["recommendations"]:
                print("\n优化建议:")
                for rec in performance_verification["recommendations"]:
                    print(f"  - {rec}")

            print(f"\n总体结果: {'✅ 所有性能指标达标' if performance_verification['overall_passed'] else '❌ 部分性能指标未达标'}")

        except Exception as e:
            verification["errors"].append(f"验证失败: {str(e)}")
            print(f"  验证异常: {str(e)}")

        return verification

    async def cleanup_test_data(self):
        """清理测试数据"""
        print("5. 清理测试数据...")

        try:
            # 删除测试批次数据
            deleted_count = await self.db_conn.execute("""
                WITH deleted_news AS (
                    DELETE FROM news_raw
                    WHERE news_id LIKE $1
                    RETURNING id
                ),
                deleted_events AS (
                    DELETE FROM news_event
                    WHERE news_id IN (SELECT id FROM deleted_news)
                    RETURNING id
                )
                DELETE FROM event_theme_map
                WHERE event_id IN (SELECT id FROM deleted_events)
            """, "test_news_%")

            print(f"  清理完成，删除测试数据")

        except Exception as e:
            print(f"  清理失败: {str(e)}")

    async def run_full_test(self) -> bool:
        """运行完整测试"""
        print("=" * 60)
        print("AI主题分析应用 - 全链路直接测试")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"测试新闻数量: {self.test_news_count}")
        print(f"测试批次ID: {self.batch_id}")
        print("=" * 60)

        start_time = time.time()

        try:
            # 1. 加载测试数据
            news_items = await self.load_test_data()
            if not news_items:
                print("错误: 没有加载到测试数据")
                return False

            # 2. 写入数据库并触发处理
            written_count = await self.write_news_to_database(news_items)
            if written_count == 0:
                print("错误: 没有成功写入新闻")
                return False

            # 3. 监控处理进度
            print("\n等待系统处理数据...")
            await asyncio.sleep(5)  # 给系统一些启动时间

            processing_results = await self.monitor_processing_progress(written_count)

            # 4. 验证最终结果
            verification = await self.verify_final_results()

            # 5. 清理测试数据
            await self.cleanup_test_data()

            # 生成测试报告
            end_time = time.time()
            duration = end_time - start_time

            report = {
                "test_name": "full_chain_direct",
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.fromtimestamp(end_time).isoformat(),
                "duration_seconds": duration,
                "test_config": {
                    "news_count": self.test_news_count,
                    "batch_id": self.batch_id,
                    "written_count": written_count
                },
                "performance_metrics": self.performance_metrics,
                "performance_standards": self.performance_standards,
                "processing_results": processing_results,
                "verification": verification,
                "success": processing_results.get("decisions", 0) >= written_count * 0.5  # 50%完成率
            }

            # 保存报告
            report_file = f"full_chain_direct_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            print("=" * 60)
            print("测试完成报告:")
            print(f"总耗时: {duration:.1f} 秒")
            print(f"写入新闻: {written_count} 条")
            print(f"生成决策: {processing_results.get('decisions', 0)} 条")
            print(f"转换率: {verification.get('processing_stats', {}).get('conversion_rate', 0):.1f}%")
            print(f"详细报告: {report_file}")
            print("=" * 60)

            return report["success"]

        except Exception as e:
            print(f"测试异常: {str(e)}")
            return False


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='AI主题分析应用全链路直接测试')
    parser.add_argument('--news-count', type=int, default=30, help='测试新闻数量')
    parser.add_argument('--timeout-minutes', type=int, default=10, help='处理超时时间（分钟）')
    parser.add_argument('--no-cleanup', action='store_true', help='不清理测试数据')

    args = parser.parse_args()

    async with DirectFullChainTester(args.news_count) as tester:
        success = await tester.run_full_test()

        if success:
            print("\n✅ 全链路直接测试通过！系统处理流程正常。")
            return 0
        else:
            print("\n❌ 全链路直接测试失败！请检查系统状态。")
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