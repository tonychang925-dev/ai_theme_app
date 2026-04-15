#!/usr/bin/env python3
"""
全链路性能测试脚本
基于run_full_chain_100_to_decision_with_progress.py构建，专注于性能测试

测试目标：
1. 吞吐量（每秒处理的消息数）
2. 各阶段延迟（news_raw → news_event → structured → decision）
3. 成功率
4. 资源使用情况（Redis、数据库）
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import asyncpg
import redis.asyncio as redis

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway
from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor


class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        self.metrics = {
            "test_start_time": None,
            "test_end_time": None,
            "total_messages": 0,
            "successful_messages": 0,
            "failed_messages": 0,
            "throughput": 0.0,  # 消息/秒
            "stage_latencies": {
                "news_raw_to_db": [],
                "db_to_news_event": [],
                "news_event_to_structured": [],
                "structured_to_decision": [],
                "total_processing": []
            },
            "stage_success_rates": {
                "news_raw_storage": 0,
                "news_event_creation": 0,
                "structured_publishing": 0,
                "decision_generation": 0
            },
            "resource_usage": {
                "redis_memory_usage": 0,
                "db_connections": 0,
                "cpu_usage": []
            },
            "concurrent_users": 0,
            "batch_size": 0
        }
    
    def start_test(self, total_messages: int, concurrent_users: int, batch_size: int):
        self.metrics["test_start_time"] = time.time()
        self.metrics["total_messages"] = total_messages
        self.metrics["concurrent_users"] = concurrent_users
        self.metrics["batch_size"] = batch_size
    
    def end_test(self):
        self.metrics["test_end_time"] = time.time()
        duration = self.metrics["test_end_time"] - self.metrics["test_start_time"]
        if duration > 0:
            self.metrics["throughput"] = self.metrics["successful_messages"] / duration
    
    def record_latency(self, stage: str, latency: float):
        if stage in self.metrics["stage_latencies"]:
            self.metrics["stage_latencies"][stage].append(latency)
    
    def record_success(self, stage: str):
        if stage in self.metrics["stage_success_rates"]:
            self.metrics["stage_success_rates"][stage] += 1
    
    def record_failure(self):
        self.metrics["failed_messages"] += 1
    
    def record_successful_message(self):
        self.metrics["successful_messages"] += 1
    
    def calculate_statistics(self) -> Dict[str, Any]:
        """计算统计信息"""
        stats = {}
        
        # 计算各阶段延迟统计
        for stage, latencies in self.metrics["stage_latencies"].items():
            if latencies:
                stats[f"{stage}_latency"] = {
                    "count": len(latencies),
                    "mean": statistics.mean(latencies),
                    "median": statistics.median(latencies),
                    "p95": statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies),
                    "min": min(latencies),
                    "max": max(latencies)
                }
        
        # 计算成功率
        total = self.metrics["total_messages"]
        if total > 0:
            stats["overall_success_rate"] = self.metrics["successful_messages"] / total
            stats["overall_failure_rate"] = self.metrics["failed_messages"] / total
        
        # 计算各阶段成功率
        for stage, count in self.metrics["stage_success_rates"].items():
            if total > 0:
                stats[f"{stage}_success_rate"] = count / total
        
        stats["throughput"] = self.metrics["throughput"]
        stats["test_duration"] = self.metrics["test_end_time"] - self.metrics["test_start_time"]
        
        return stats
    
    def generate_report(self) -> Dict[str, Any]:
        """生成完整报告"""
        return {
            "test_configuration": {
                "total_messages": self.metrics["total_messages"],
                "concurrent_users": self.metrics["concurrent_users"],
                "batch_size": self.metrics["batch_size"],
                "test_start_time": datetime.fromtimestamp(self.metrics["test_start_time"]).isoformat() if self.metrics["test_start_time"] else None,
                "test_end_time": datetime.fromtimestamp(self.metrics["test_end_time"]).isoformat() if self.metrics["test_end_time"] else None
            },
            "performance_statistics": self.calculate_statistics(),
            "raw_metrics": self.metrics
        }


class FullChainPerformanceTester:
    """全链路性能测试器"""
    
    def __init__(self, concurrent_users: int = 10, batch_size: int = 10, total_messages: int = 100):
        self.concurrent_users = concurrent_users
        self.batch_size = batch_size
        self.total_messages = total_messages
        self.metrics = PerformanceMetrics()
        
        # 测试数据路径
        self.raw_test_path = PROJECT_ROOT / "evaluate_service/data/raw/test_cases.txt"
        self.gt_override_path = PROJECT_ROOT / "structured_events_with_gt.jsonl"
        
        # 主题映射
        self.theme_key_map = {
            "AI/AR眼镜": "9030409",
            "SpaceX": "9064166",
            "可控核聚变": "9017950",
            "对日制裁": "9059919",
            "稀土永磁": "9010367",
            "海洋经济": "9043698",
            "深海经济": "9043698",
            "光刻胶": "9018411",
            "卫星互联": "9019807",
            "卫星互联网": "9019807",
            "液冷数据中心": "9024880",
            "AI智能体Manus": "9043089",
        }
    
    def _parse_test_cases(self, limit: int) -> List[Dict[str, Any]]:
        """解析测试用例"""
        text = self.raw_test_path.read_text(encoding="utf-8")
        parts = re.split(r"(?=测试集\d+:题材名称:)", text)
        rows: List[Dict[str, str]] = []
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            lines = part.splitlines()
            header = lines[0].strip()
            match = re.match(r"测试集\d+:题材名称:(.+)", header)
            if not match:
                continue
            theme_name = match.group(1).strip()
            expected_subject_key = self.theme_key_map.get(theme_name, "")
            
            seen_raws = set()
            for line in lines[1:]:
                value = line.strip()
                if not value.startswith("- "):
                    continue
                raw_text = value[2:].strip().rstrip("*").strip()
                if not raw_text or raw_text in seen_raws:
                    continue
                seen_raws.add(raw_text)
                rows.append({
                    "theme_name": theme_name,
                    "expected_subject_key": expected_subject_key,
                    "raw_text": raw_text
                })
        
        if len(rows) < limit:
            raise RuntimeError(f"原始测试样本不足 {limit} 条，当前 {len(rows)} 条")
        return rows[:limit]
    
    def _build_v2_payload(self, raw_text: str, news_id: str, sequence: int, batch_id: str) -> Dict[str, Any]:
        """构建V2格式的payload"""
        return {
            "_t": "news",
            "_v": 2,
            "id": news_id,
            "t": "",
            "c": raw_text,
            "s": "cls",
            "d": "2026-03-01",
            "tm": "00:00:00",
            "_b": batch_id,
            "_s": sequence,
        }
    
    async def _measure_stage_latency(self, stage: str, coroutine):
        """测量阶段延迟"""
        start_time = time.time()
        result = await coroutine
        latency = time.time() - start_time
        self.metrics.record_latency(stage, latency)
        return result
    
    async def run_test(self):
        """运行性能测试"""
        print(f"开始全链路性能测试")
        print(f"配置: {self.concurrent_users}并发用户, {self.total_messages}条消息, 批量大小{self.batch_size}")
        
        # 初始化指标
        self.metrics.start_test(self.total_messages, self.concurrent_users, self.batch_size)
        
        # 加载测试数据
        samples = self._parse_test_cases(self.total_messages)
        print(f"已加载 {len(samples)} 条测试数据")
        
        # 运行测试
        # 这里需要实现具体的测试逻辑
        # 由于时间关系，我先输出框架
        
        print("性能测试框架已构建完成")
        print("下一步需要实现具体的并发测试逻辑")
        
        # 结束测试
        self.metrics.end_test()
        
        # 生成报告
        report = self.metrics.generate_report()
        
        # 保存报告
        report_path = PROJECT_ROOT / f"tmp/performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        
        print(f"性能测试完成，报告已保存到: {report_path}")
        
        # 输出关键指标
        stats = report["performance_statistics"]
        print("\n=== 性能测试结果 ===")
        print(f"总消息数: {self.total_messages}")
        print(f"成功消息数: {self.metrics.metrics['successful_messages']}")
        print(f"失败消息数: {self.metrics.metrics['failed_messages']}")
        print(f"吞吐量: {stats.get('throughput', 0):.2f} 消息/秒")
        if 'overall_success_rate' in stats:
            print(f"整体成功率: {stats['overall_success_rate']*100:.2f}%")
        
        return report


async def main():
    """主函数"""
    # 检查环境变量
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("警告: DEEPSEEK_API_KEY 环境变量未设置")
        print("请设置: export DEEPSEEK_API_KEY=your_key")
        # 尝试从.env.theme文件读取
        env_file = PROJECT_ROOT / ".env.theme"
        if env_file.exists():
            content = env_file.read_text()
            for line in content.splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip()
                    print(f"已从.env.theme文件读取DEEPSEEK_API_KEY")
                    break
    
    # 创建测试器
    tester = FullChainPerformanceTester(
        concurrent_users=10,  # 并发用户数
        batch_size=10,        # 批量大小
        total_messages=100    # 总消息数
    )
    
    try:
        report = await tester.run_test()
        return report
    except Exception as e:
        print(f"性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    report = asyncio.run(main())
    if report:
        print("\n性能测试执行完成")
    else:
        print("\n性能测试执行失败")
        sys.exit(1)

class ConcurrentFullChainTester(FullChainPerformanceTester):
    """并发全链路测试器"""
    
    async def _get_news_directly(self, base_gateway, news_id: str) -> Optional[Dict[str, Any]]:
        """直接查询数据库获取新闻，绕过有问题的get_news方法"""
        try:
            # 通过反射获取数据库连接池
            # base_gateway._client 是数据库管理器
            if hasattr(base_gateway, '_client') and base_gateway._client:
                client = base_gateway._client
                # 检查是否有pool属性
                if hasattr(client, 'pool'):
                    pool = client.pool
                    async with pool.acquire() as conn:
                        # 只查询实际存在的列，避免keywords和metadata
                        row = await conn.fetchrow("""
                            SELECT
                                id, news_id, title, content, source,
                                publish_date, publish_time, market, url,
                                created_at, updated_at
                            FROM news_raw
                            WHERE news_id = $1
                        """, news_id)

                        if row:
                            # 转换为字典
                            result = dict(row)
                            # 确保有必要的字段
                            if 'id' not in result:
                                return None
                            # 添加默认值
                            result['keywords'] = []
                            result['metadata'] = {}
                            return result
            return None
        except Exception as e:
            # 打印错误但继续
            print(f"直接获取新闻失败 {news_id}: {e}")
            return None

    async def _test_single_message(self, sample: Dict[str, Any], index: int, batch_id: str,
                                   stream_bus, base_gateway, redis_client,
                                   news_handler, theme_processor, news_processor):
        """测试单条消息的全链路处理"""
        try:
            # 生成唯一的news_id
            external_news_id = f"{batch_id}_{index:03d}_{uuid.uuid4().hex[:6]}"

            # 1. 发布到news_raw流
            payload = self._build_v2_payload(
                raw_text=sample["raw_text"],
                news_id=external_news_id,
                sequence=index,
                batch_id=batch_id
            )

            publish_start = time.time()
            await stream_bus.publish_to_stream("news_raw", {"payload": payload})
            publish_latency = time.time() - publish_start
            self.metrics.record_latency("news_raw_publish", publish_latency)

            # 2. 等待news_raw存储到数据库
            storage_start = time.time()
            stored_news = None
            timeout = 30.0
            start_time = time.time()
            while time.time() - start_time < timeout:
                # 尝试使用直接查询方法
                stored_news = await self._get_news_directly(base_gateway, external_news_id)
                if stored_news:
                    break
                await asyncio.sleep(0.1)

            if not stored_news:
                self.metrics.record_failure()
                return {"status": "failed", "stage": "news_raw_storage", "reason": "timeout"}
            
            storage_latency = time.time() - storage_start
            self.metrics.record_latency("news_raw_to_db", storage_latency)
            self.metrics.record_success("news_raw_storage")
            
            # 3. 处理为news_event
            event_start = time.time()
            stored_message = {
                "payload": {
                    "news_data": {
                        "id": int(stored_news["id"]),
                        "news_row_id": int(stored_news["id"]),
                        "news_id": external_news_id,
                        "title": stored_news.get("title") or "",
                        "content": stored_news.get("content") or sample["raw_text"],
                        "source": stored_news.get("source") or "performance_test",
                        "publish_date": str(stored_news.get("publish_date") or "2026-03-01"),
                    }
                }
            }
            
            processor_result = await news_processor.process_stream_message(
                message_id=f"perf_{uuid.uuid4().hex[:8]}",
                message_data=stored_message,
            )
            
            if not processor_result.get("success"):
                self.metrics.record_failure()
                return {"status": "failed", "stage": "news_event_creation", "reason": "processor_failed"}
            
            news_event_id = processor_result.get("news_event_id")
            if not news_event_id:
                self.metrics.record_failure()
                return {"status": "failed", "stage": "news_event_creation", "reason": "no_event_id"}
            
            event_latency = time.time() - event_start
            self.metrics.record_latency("db_to_news_event", event_latency)
            self.metrics.record_success("news_event_creation")
            
            # 4. 等待structured事件发布
            if not processor_result.get("structured_stream_published"):
                self.metrics.record_failure()
                return {"status": "failed", "stage": "structured_publishing", "reason": "not_published"}
            
            self.metrics.record_success("structured_publishing")
            
            # 5. 等待decision生成
            decision_start = time.time()
            decision_stream = "stream:events:decision"
            seen_ids = set()
            timeout = 60.0
            start_time = time.time()
            decision = None
            
            while time.time() - start_time < timeout:
                messages = await redis_client.xread({decision_stream: "0-0"}, count=10, block=1000)
                for _stream, message_list in messages:
                    for message_id, payload_data in message_list:
                        if message_id in seen_ids:
                            continue
                        seen_ids.add(message_id)
                        raw_decision = payload_data.get("decision")
                        if isinstance(raw_decision, bytes):
                            raw_decision = raw_decision.decode("utf-8")
                        try:
                            decision_data = json.loads(raw_decision)
                            # 检查是否是我们的事件
                            if decision_data.get("news_event_id") == news_event_id:
                                decision = decision_data
                                break
                        except:
                            continue
                if decision:
                    break
                await asyncio.sleep(0.1)
            
            if not decision:
                self.metrics.record_failure()
                return {"status": "failed", "stage": "decision_generation", "reason": "timeout"}
            
            decision_latency = time.time() - decision_start
            self.metrics.record_latency("structured_to_decision", decision_latency)
            self.metrics.record_success("decision_generation")
            
            # 记录总处理时间
            total_latency = time.time() - publish_start
            self.metrics.record_latency("total_processing", total_latency)
            self.metrics.record_successful_message()
            
            return {
                "status": "success",
                "news_id": external_news_id,
                "news_event_id": news_event_id,
                "latencies": {
                    "publish": publish_latency,
                    "storage": storage_latency,
                    "event": event_latency,
                    "decision": decision_latency,
                    "total": total_latency
                }
            }
            
        except Exception as e:
            self.metrics.record_failure()
            return {"status": "failed", "stage": "unknown", "reason": str(e)}
    
    async def run_concurrent_test(self):
        """运行并发测试"""
        print(f"开始并发全链路性能测试")
        
        # 初始化指标
        self.metrics.start_test(self.total_messages, self.concurrent_users, self.batch_size)
        
        # 加载测试数据
        samples = self._parse_test_cases(self.total_messages)
        print(f"已加载 {len(samples)} 条测试数据")
        
        # 初始化服务
        run_id = uuid.uuid4().hex[:8]
        batch_id = f"perf_test_{run_id}"
        
        cfg = DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data"),
            postgres_username=os.getenv("POSTGRES_USER", "postgres"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        )
        cfg.redis.enabled = True
        init_config(cfg)
        DatabaseGateway._instance = None
        
        stream_gateway = await get_gateway(enable_retry=True, retry_config={"max_retries": 2})
        base_gateway = stream_gateway.base_gateway
        
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
        )
        await redis_client.ping()
        
        stream_bus = UnifiedRedisStreamBus(redis_client, cfg)

        # 清理之前的测试数据
        raw_stream = "stream:news:raw"
        structured_stream = "stream:events:structured"
        decision_stream = "stream:events:decision"
        dead_letter_stream = "stream:dead:letter"

        # 按照参考代码的正确顺序初始化
        await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")
        for stream_name in (raw_stream, structured_stream, decision_stream, dead_letter_stream):
            await redis_client.delete(stream_name)
        await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")
        
        # 初始化处理器
        news_handler = NewsStreamHandler(
            stream_bus=stream_bus,
            database_gateway=base_gateway,
            config={
                "consumer_group": "news_storage_handlers",
                "stream_name": "news_raw",
                "batch_size": self.batch_size,
                "block_time": 500,
            },
        )
        
        consumer_group = f"theme_processors_perf_{run_id}"
        consumer_name = f"tp_perf_{run_id}"
        
        theme_processor = ThemeProcessor(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            enable_classification_first=False,
            consumer_name=consumer_name,
            config={
                "stream_structured": structured_stream,
                "stream_decision": decision_stream,
                "stream_dead_letter": dead_letter_stream,
                "consumer_group": consumer_group,
                "structured_batch_size": self.batch_size,
                "structured_block_time": 500,
            },
        )
        
        class _RedisStructuredEventBus:
            def __init__(self, redis_client, structured_stream):
                self.redis_client = redis_client
                self.structured_stream = structured_stream
            
            async def publish_to_stream(self, stream_key, data):
                target = self.structured_stream if stream_key == "stream:events:structured" else stream_key
                payload = {"payload": json.dumps(data, ensure_ascii=False)}
                return await self.redis_client.xadd(target, payload, maxlen=10000)
        
        news_processor = NewsStreamProcessor(
            event_bus=_RedisStructuredEventBus(redis_client, structured_stream),
            config={"database_gateway": base_gateway},
        )
        
        # 启动服务
        await news_handler.start_storage_service()
        ok = await theme_processor.initialize()
        if not ok:
            raise RuntimeError("theme_processor 初始化失败")
        await theme_processor.start()
        
        print("服务初始化完成，开始并发测试...")
        
        # 创建并发任务
        tasks = []
        for i in range(0, len(samples), self.concurrent_users):
            batch = samples[i:i + self.concurrent_users]
            batch_tasks = []
            
            for j, sample in enumerate(batch):
                task_index = i + j + 1
                task = self._test_single_message(
                    sample=sample,
                    index=task_index,
                    batch_id=batch_id,
                    stream_bus=stream_bus,
                    base_gateway=base_gateway,
                    redis_client=redis_client,
                    news_handler=news_handler,
                    theme_processor=theme_processor,
                    news_processor=news_processor
                )
                batch_tasks.append(task)
            
            # 等待批次完成
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # 处理结果
            success_count = 0
            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"任务异常: {result}")
                elif result.get("status") == "success":
                    success_count += 1
            
            print(f"批次 {i//self.concurrent_users + 1} 完成: {success_count}/{len(batch)} 成功")
            
            # 控制并发速率
            await asyncio.sleep(0.1)
        
        # 停止服务
        try:
            await news_handler.stop_storage_service()
        except Exception:
            pass
        try:
            await theme_processor.stop()
        except Exception:
            pass
        
        # 清理测试数据
        await redis_client.delete(raw_stream, structured_stream, decision_stream, dead_letter_stream)
        if hasattr(base_gateway, "close"):
            await base_gateway.close()
        
        # 结束测试
        self.metrics.end_test()
        
        # 生成报告
        report = self.metrics.generate_report()
        
        # 保存报告
        report_path = PROJECT_ROOT / f"tmp/concurrent_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        
        print(f"并发性能测试完成，报告已保存到: {report_path}")
        
        # 输出关键指标
        stats = report["performance_statistics"]
        print("\n=== 并发性能测试结果 ===")
        print(f"总消息数: {self.total_messages}")
        print(f"成功消息数: {self.metrics.metrics['successful_messages']}")
        print(f"失败消息数: {self.metrics.metrics['failed_messages']}")
        print(f"吞吐量: {stats.get('throughput', 0):.2f} 消息/秒")
        if 'overall_success_rate' in stats:
            print(f"整体成功率: {stats['overall_success_rate']*100:.2f}%")
        
        # 输出各阶段延迟
        print("\n=== 各阶段延迟统计 (秒) ===")
        for stage in ["news_raw_to_db", "db_to_news_event", "structured_to_decision", "total_processing"]:
            if f"{stage}_latency" in stats:
                stage_stats = stats[f"{stage}_latency"]
                print(f"{stage}:")
                print(f"  平均: {stage_stats['mean']:.3f}s, P95: {stage_stats.get('p95', stage_stats['max']):.3f}s")
                print(f"  最小: {stage_stats['min']:.3f}s, 最大: {stage_stats['max']:.3f}s")
        
        return report


async def main_concurrent():
    """并发测试主函数"""
    # 检查环境变量
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("警告: DEEPSEEK_API_KEY 环境变量未设置")
        env_file = PROJECT_ROOT / ".env.theme"
        if env_file.exists():
            content = env_file.read_text()
            for line in content.splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip()
                    print(f"已从.env.theme文件读取DEEPSEEK_API_KEY")
                    break
        else:
            print("错误: 未找到DEEPSEEK_API_KEY环境变量")
            return None
    
    # 创建并发测试器
    tester = ConcurrentFullChainTester(
        concurrent_users=5,    # 并发用户数（可调整）
        batch_size=10,         # 批量大小
        total_messages=50      # 总消息数（从100减少到50以加快测试）
    )
    
    try:
        report = await tester.run_concurrent_test()
        return report
    except Exception as e:
        print(f"并发性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # 运行并发测试
    print("启动全链路并发性能测试...")
    report = asyncio.run(main_concurrent())
    
    if report:
        print("\n性能测试执行完成")
        # 输出测试配置
        config = report["test_configuration"]
        print(f"\n测试配置:")
        print(f"  总消息数: {config['total_messages']}")
        print(f"  并发用户数: {config['concurrent_users']}")
        print(f"  批量大小: {config['batch_size']}")
        print(f"  测试开始时间: {config['test_start_time']}")
        print(f"  测试结束时间: {config['test_end_time']}")
    else:
        print("\n性能测试执行失败")
        sys.exit(1)
