#!/usr/bin/env python3
"""
全链路压力测试框架 - 基于run_full_chain_100_to_decision_with_progress.py
增强性能监测功能，支持系统资源监控和压力测试

功能特性：
1. 全链路性能测试（吞吐量、延迟、成功率）
2. 系统资源监控（CPU、内存、磁盘、网络）
3. Redis深度监控（内存、连接、命令统计）
4. PostgreSQL监控（连接、查询性能）
5. 压力测试场景（恒定负载、递增负载、峰值负载）
6. 实时指标收集和报告生成
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid
import statistics
import math
import threading
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable, Set
from enum import Enum

import asyncpg
import redis.asyncio as redis
import psutil

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.streams.stream_config import EnhancedDatabaseConfig, RedisStreamConfig, StreamDefinition, StreamPriority
from database_service.gateway import DatabaseGateway
from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor


class TestScenario(Enum):
    """压力测试场景类型"""
    CONSTANT_LOAD = "constant_load"      # 恒定负载
    RAMP_UP = "ramp_up"                  # 递增负载
    SPIKE = "spike"                      # 峰值负载
    ENDURANCE = "endurance"              # 耐力测试
    SOAK = "soak"                        # 浸泡测试


@dataclass
class StressTestConfig:
    """压力测试配置"""
    total_messages: int = 100            # 总消息数
    concurrent_users: int = 10           # 并发用户数
    batch_size: int = 10                 # 批量大小
    scenario: TestScenario = TestScenario.CONSTANT_LOAD  # 测试场景
    duration_seconds: Optional[int] = None  # 测试持续时间（秒）
    ramp_up_steps: int = 5               # 递增负载步数
    spike_multiplier: float = 3.0        # 峰值乘数

    # 监控配置
    monitor_interval: float = 1.0        # 监控采集间隔（秒）
    enable_system_monitoring: bool = True  # 启用系统监控
    enable_redis_monitoring: bool = True  # 启用Redis监控
    enable_postgres_monitoring: bool = True  # 启用PostgreSQL监控

    # 报告配置
    report_dir: Path = PROJECT_ROOT / "tmp/stress_test_reports"
    detailed_report: bool = True         # 生成详细报告


class ResourceMonitor:
    """系统资源监控器"""

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.metrics = {
            "cpu_percent": [],
            "memory_percent": [],
            "memory_used_mb": [],
            "disk_io_read_mb": [],
            "disk_io_write_mb": [],
            "network_sent_mb": [],
            "network_recv_mb": [],
            "timestamp": []
        }
        self._stop_event = threading.Event()
        self._thread = None

        # 初始基准值
        self._prev_disk_io = psutil.disk_io_counters()
        self._prev_net_io = psutil.net_io_counters()

    def start(self):
        """启动资源监控"""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止资源监控"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _monitor_loop(self):
        """监控循环"""
        while not self._stop_event.is_set():
            try:
                self._collect_metrics()
            except Exception as e:
                print(f"资源监控收集失败: {e}")

            time.sleep(self.interval)

    def _collect_metrics(self):
        """收集系统指标"""
        timestamp = time.time()

        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # 内存使用率
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / (1024 * 1024)

        # 磁盘IO
        disk_io = psutil.disk_io_counters()
        if self._prev_disk_io:
            read_mb = (disk_io.read_bytes - self._prev_disk_io.read_bytes) / (1024 * 1024)
            write_mb = (disk_io.write_bytes - self._prev_disk_io.write_bytes) / (1024 * 1024)
        else:
            read_mb = write_mb = 0
        self._prev_disk_io = disk_io

        # 网络IO
        net_io = psutil.net_io_counters()
        if self._prev_net_io:
            sent_mb = (net_io.bytes_sent - self._prev_net_io.bytes_sent) / (1024 * 1024)
            recv_mb = (net_io.bytes_recv - self._prev_net_io.bytes_recv) / (1024 * 1024)
        else:
            sent_mb = recv_mb = 0
        self._prev_net_io = net_io

        # 存储指标
        self.metrics["cpu_percent"].append(cpu_percent)
        self.metrics["memory_percent"].append(memory_percent)
        self.metrics["memory_used_mb"].append(memory_used_mb)
        self.metrics["disk_io_read_mb"].append(read_mb)
        self.metrics["disk_io_write_mb"].append(write_mb)
        self.metrics["network_sent_mb"].append(sent_mb)
        self.metrics["network_recv_mb"].append(recv_mb)
        self.metrics["timestamp"].append(timestamp)

    def get_summary(self) -> Dict[str, Any]:
        """获取资源使用摘要"""
        if not self.metrics["cpu_percent"]:
            return {}

        summary = {
            "cpu_avg": statistics.mean(self.metrics["cpu_percent"]) if self.metrics["cpu_percent"] else 0,
            "cpu_max": max(self.metrics["cpu_percent"]) if self.metrics["cpu_percent"] else 0,
            "memory_avg": statistics.mean(self.metrics["memory_percent"]) if self.metrics["memory_percent"] else 0,
            "memory_max": max(self.metrics["memory_percent"]) if self.metrics["memory_percent"] else 0,
            "memory_used_avg_mb": statistics.mean(self.metrics["memory_used_mb"]) if self.metrics["memory_used_mb"] else 0,
            "disk_read_total_mb": sum(self.metrics["disk_io_read_mb"]) if self.metrics["disk_io_read_mb"] else 0,
            "disk_write_total_mb": sum(self.metrics["disk_io_write_mb"]) if self.metrics["disk_io_write_mb"] else 0,
            "network_sent_total_mb": sum(self.metrics["network_sent_mb"]) if self.metrics["network_sent_mb"] else 0,
            "network_recv_total_mb": sum(self.metrics["network_recv_mb"]) if self.metrics["network_recv_mb"] else 0,
        }

        return summary


class RedisMonitor:
    """Redis监控器"""

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.metrics = {
            "memory_used": [],
            "connected_clients": [],
            "blocked_clients": [],
            "total_commands_processed": [],
            "instantaneous_ops_per_sec": [],
            "keyspace_hits": [],
            "keyspace_misses": [],
            "timestamp": []
        }

    async def collect_metrics(self):
        """收集Redis指标"""
        try:
            info = await self.redis_client.info()
            timestamp = time.time()

            self.metrics["memory_used"].append(info.get("used_memory", 0))
            self.metrics["connected_clients"].append(info.get("connected_clients", 0))
            self.metrics["blocked_clients"].append(info.get("blocked_clients", 0))
            self.metrics["total_commands_processed"].append(info.get("total_commands_processed", 0))
            self.metrics["instantaneous_ops_per_sec"].append(info.get("instantaneous_ops_per_sec", 0))
            self.metrics["keyspace_hits"].append(info.get("keyspace_hits", 0))
            self.metrics["keyspace_misses"].append(info.get("keyspace_misses", 0))
            self.metrics["timestamp"].append(timestamp)

        except Exception as e:
            print(f"Redis监控收集失败: {e}")

    async def get_summary(self) -> Dict[str, Any]:
        """获取Redis监控摘要"""
        if not self.metrics["memory_used"]:
            return {}

        summary = {
            "memory_used_avg": statistics.mean(self.metrics["memory_used"]) if self.metrics["memory_used"] else 0,
            "memory_used_max": max(self.metrics["memory_used"]) if self.metrics["memory_used"] else 0,
            "connected_clients_avg": statistics.mean(self.metrics["connected_clients"]) if self.metrics["connected_clients"] else 0,
            "connected_clients_max": max(self.metrics["connected_clients"]) if self.metrics["connected_clients"] else 0,
            "instantaneous_ops_per_sec_avg": statistics.mean(self.metrics["instantaneous_ops_per_sec"]) if self.metrics["instantaneous_ops_per_sec"] else 0,
            "instantaneous_ops_per_sec_max": max(self.metrics["instantaneous_ops_per_sec"]) if self.metrics["instantaneous_ops_per_sec"] else 0,
            "hit_rate": 0
        }

        total_hits = sum(self.metrics["keyspace_hits"]) if self.metrics["keyspace_hits"] else 0
        total_misses = sum(self.metrics["keyspace_misses"]) if self.metrics["keyspace_misses"] else 0
        if total_hits + total_misses > 0:
            summary["hit_rate"] = total_hits / (total_hits + total_misses)

        return summary


class PostgresMonitor:
    """PostgreSQL监控器"""

    def __init__(self, connection_params: Dict[str, Any]):
        self.connection_params = connection_params
        self.metrics = {
            "active_connections": [],
            "idle_connections": [],
            "total_transactions": [],
            "timestamp": []
        }

    async def collect_metrics(self):
        """收集PostgreSQL指标"""
        try:
            conn = await asyncpg.connect(**self.connection_params)
            try:
                timestamp = time.time()

                # 获取连接数
                row = await conn.fetchrow("""
                    SELECT
                        count(*) as total,
                        count(*) filter (where state = 'active') as active,
                        count(*) filter (where state = 'idle') as idle
                    FROM pg_stat_activity
                    WHERE datname = $1
                """, self.connection_params.get("database", "stock_data_test"))

                if row:
                    self.metrics["active_connections"].append(row["active"])
                    self.metrics["idle_connections"].append(row["idle"])
                    self.metrics["total_transactions"].append(row["total"])
                    self.metrics["timestamp"].append(timestamp)

            finally:
                await conn.close()

        except Exception as e:
            print(f"PostgreSQL监控收集失败: {e}")

    async def get_summary(self) -> Dict[str, Any]:
        """获取PostgreSQL监控摘要"""
        if not self.metrics["active_connections"]:
            return {}

        summary = {
            "active_connections_avg": statistics.mean(self.metrics["active_connections"]) if self.metrics["active_connections"] else 0,
            "active_connections_max": max(self.metrics["active_connections"]) if self.metrics["active_connections"] else 0,
            "idle_connections_avg": statistics.mean(self.metrics["idle_connections"]) if self.metrics["idle_connections"] else 0,
            "idle_connections_max": max(self.metrics["idle_connections"]) if self.metrics["idle_connections"] else 0,
        }

        return summary


class EnhancedPerformanceMetrics:
    """增强性能指标收集器"""

    def __init__(self):
        self.metrics = {
            "test_start_time": None,
            "test_end_time": None,
            "total_messages": 0,
            "successful_messages": 0,
            "failed_messages": 0,
            "throughput": 0.0,

            # 各阶段延迟
            "stage_latencies": {
                "news_raw_publish": [],
                "news_raw_to_db": [],
                "db_to_news_event": [],
                "news_event_to_structured": [],
                "structured_to_decision": [],
                "total_processing": []
            },

            # 各阶段成功率
            "stage_success_counts": {
                "news_raw_storage": 0,
                "news_event_creation": 0,
                "structured_publishing": 0,
                "decision_generation": 0
            },

            # 资源使用
            "resource_metrics": {
                "cpu": [],
                "memory": [],
                "redis_memory": [],
                "redis_connections": [],
                "postgres_connections": []
            },

            # 测试配置
            "test_config": {},

            # 详细结果
            "detailed_results": []
        }

        # 实时统计
        self._real_time_stats = {
            "messages_per_second": deque(maxlen=60),
            "current_concurrent": 0,
            "peak_concurrent": 0
        }

    def start_test(self, test_config: Dict[str, Any]):
        """开始测试"""
        self.metrics["test_start_time"] = time.time()
        self.metrics["test_config"] = test_config
        self.metrics["total_messages"] = test_config.get("total_messages", 0)

    def end_test(self):
        """结束测试"""
        self.metrics["test_end_time"] = time.time()
        duration = self.metrics["test_end_time"] - self.metrics["test_start_time"]
        if duration > 0:
            self.metrics["throughput"] = self.metrics["successful_messages"] / duration

    def record_latency(self, stage: str, latency: float):
        """记录阶段延迟"""
        if stage in self.metrics["stage_latencies"]:
            self.metrics["stage_latencies"][stage].append(latency)

    def record_success(self, stage: str):
        """记录阶段成功"""
        if stage in self.metrics["stage_success_counts"]:
            self.metrics["stage_success_counts"][stage] += 1

    def record_failure(self):
        """记录失败"""
        self.metrics["failed_messages"] += 1

    def record_successful_message(self):
        """记录成功消息"""
        self.metrics["successful_messages"] += 1

    def record_detailed_result(self, result: Dict[str, Any]):
        """记录详细结果"""
        self.metrics["detailed_results"].append(result)

    def record_resource_metric(self, metric_type: str, value: float):
        """记录资源指标"""
        if metric_type in self.metrics["resource_metrics"]:
            self.metrics["resource_metrics"][metric_type].append(value)

    def update_real_time_stats(self, current_concurrent: int):
        """更新实时统计"""
        self._real_time_stats["current_concurrent"] = current_concurrent
        if current_concurrent > self._real_time_stats["peak_concurrent"]:
            self._real_time_stats["peak_concurrent"] = current_concurrent

    def _calculate_percentile(self, values: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = (len(sorted_values) - 1) * percentile / 100
        lower = math.floor(index)
        upper = math.ceil(index)

        if lower == upper:
            return sorted_values[int(index)]

        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    def generate_report(self) -> Dict[str, Any]:
        """生成完整测试报告"""
        # 计算统计信息
        stats = {}

        # 基本统计
        total = self.metrics["total_messages"]
        if total > 0:
            stats["overall_success_rate"] = self.metrics["successful_messages"] / total
            stats["overall_failure_rate"] = self.metrics["failed_messages"] / total

        stats["throughput"] = self.metrics["throughput"]
        stats["test_duration"] = self.metrics["test_end_time"] - self.metrics["test_start_time"]

        # 各阶段延迟统计
        for stage, latencies in self.metrics["stage_latencies"].items():
            if latencies:
                stats[f"{stage}_latency"] = {
                    "count": len(latencies),
                    "mean": statistics.mean(latencies),
                    "median": statistics.median(latencies),
                    "p50": self._calculate_percentile(latencies, 50),
                    "p90": self._calculate_percentile(latencies, 90),
                    "p95": self._calculate_percentile(latencies, 95),
                    "p99": self._calculate_percentile(latencies, 99),
                    "min": min(latencies),
                    "max": max(latencies),
                    "stddev": statistics.stdev(latencies) if len(latencies) > 1 else 0
                }

        # 各阶段成功率
        for stage, count in self.metrics["stage_success_counts"].items():
            if total > 0:
                stats[f"{stage}_success_rate"] = count / total

        # 资源使用统计
        resource_stats = {}
        for metric_type, values in self.metrics["resource_metrics"].items():
            if values:
                resource_stats[metric_type] = {
                    "avg": statistics.mean(values),
                    "max": max(values),
                    "min": min(values),
                    "samples": len(values)
                }
        stats["resource_usage"] = resource_stats

        # 构建完整报告
        report = {
            "test_configuration": {
                **self.metrics["test_config"],
                "test_start_time": datetime.fromtimestamp(self.metrics["test_start_time"]).isoformat() if self.metrics["test_start_time"] else None,
                "test_end_time": datetime.fromtimestamp(self.metrics["test_end_time"]).isoformat() if self.metrics["test_end_time"] else None
            },
            "performance_statistics": stats,
            "real_time_stats": {
                "peak_concurrent": self._real_time_stats["peak_concurrent"]
            },
            "summary": {
                "total_messages": self.metrics["total_messages"],
                "successful_messages": self.metrics["successful_messages"],
                "failed_messages": self.metrics["failed_messages"],
                "throughput_mps": round(self.metrics["throughput"], 2),
                "total_duration_seconds": round(stats["test_duration"], 2)
            }
        }

        if self.metrics["detailed_results"]:
            report["detailed_results"] = self.metrics["detailed_results"][:100]  # 限制数量

        return report


class FullChainStressTester:
    """全链路压力测试器"""

    def __init__(self, config: StressTestConfig):
        self.config = config
        self.metrics = EnhancedPerformanceMetrics()
        self.resource_monitor = None
        self.redis_monitor = None
        self.postgres_monitor = None

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

    async def _monitoring_task(self, duration: float):
        """监控任务"""
        start_time = time.time()
        while time.time() - start_time < duration:
            # 收集系统资源指标
            if self.config.enable_system_monitoring and self.resource_monitor:
                self.metrics.record_resource_metric("cpu", self.resource_monitor.metrics["cpu_percent"][-1] if self.resource_monitor.metrics["cpu_percent"] else 0)
                self.metrics.record_resource_metric("memory", self.resource_monitor.metrics["memory_percent"][-1] if self.resource_monitor.metrics["memory_percent"] else 0)

            # 收集Redis指标
            if self.config.enable_redis_monitoring and self.redis_monitor:
                await self.redis_monitor.collect_metrics()
                if self.redis_monitor.metrics["memory_used"]:
                    self.metrics.record_resource_metric("redis_memory", self.redis_monitor.metrics["memory_used"][-1])
                if self.redis_monitor.metrics["connected_clients"]:
                    self.metrics.record_resource_metric("redis_connections", self.redis_monitor.metrics["connected_clients"][-1])

            # 收集PostgreSQL指标
            if self.config.enable_postgres_monitoring and self.postgres_monitor:
                await self.postgres_monitor.collect_metrics()
                if self.postgres_monitor.metrics["active_connections"]:
                    self.metrics.record_resource_metric("postgres_connections", self.postgres_monitor.metrics["active_connections"][-1])

            await asyncio.sleep(self.config.monitor_interval)

    async def _test_single_message(self, sample: Dict[str, Any], index: int, batch_id: str,
                                  stream_bus, base_gateway, redis_client,
                                  news_handler, theme_processor, news_processor) -> Dict[str, Any]:
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

            # 直接查询数据库
            conn = await asyncpg.connect(**self._pg_kwargs())
            try:
                while time.time() - start_time < timeout:
                    row = await conn.fetchrow("""
                        SELECT id, news_id, title, content, source,
                               publish_date, publish_time, market, url,
                               created_at, updated_at
                        FROM news_raw
                        WHERE news_id = $1
                    """, external_news_id)

                    if row:
                        stored_news = dict(row)
                        stored_news['keywords'] = []
                        stored_news['metadata'] = {}
                        break
                    await asyncio.sleep(0.1)
            finally:
                await conn.close()

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
                        "source": stored_news.get("source") or "stress_test",
                        "publish_date": str(stored_news.get("publish_date") or "2026-03-01"),
                    }
                }
            }

            processor_result = await news_processor.process_stream_message(
                message_id=f"stress_{uuid.uuid4().hex[:8]}",
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

            result = {
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

            self.metrics.record_detailed_result(result)
            return result

        except Exception as e:
            self.metrics.record_failure()
            return {"status": "failed", "stage": "unknown", "reason": str(e)}

    def _pg_kwargs(self) -> Dict[str, Any]:
        """获取PostgreSQL连接参数"""
        return {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
            "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        }

    async def _initialize_services(self, run_id: str, batch_id: str):
        """初始化服务"""
        # 初始化增强配置
        cfg = EnhancedDatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
            postgres_username=os.getenv("POSTGRES_USER", "postgres"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        )
        cfg.redis.enabled = True
        # 禁用Stream监控以避免WRONGTYPE错误
        cfg.redis_stream.enable_monitoring = False
        init_config(cfg)
        DatabaseGateway._instance = None

        # 临时修改gateway_integration的get_gateway函数，使其返回包装后的gateway
        # 创建一个具有base_gateway属性的包装器，满足theme_processor的期望
        import database_service.streams.gateway_integration as gateway_integration
        from database_service.gateway import get_gateway as get_original_gateway
        original_get_gateway = gateway_integration.get_gateway

        # 首先获取原始gateway
        base_gateway = await get_original_gateway()

        # 创建一个包装类，具有base_gateway属性
        class WrappedGateway:
            def __init__(self, base_gateway):
                self.base_gateway = base_gateway

                # 将所有方法代理到base_gateway
                for attr_name in dir(base_gateway):
                    if not attr_name.startswith('_'):
                        attr = getattr(base_gateway, attr_name)
                        if callable(attr):
                            setattr(self, attr_name, self._create_proxy_method(attr_name, attr))
                        else:
                            setattr(self, attr_name, attr)

            def _create_proxy_method(self, method_name, original_method):
                async def proxy_method(*args, **kwargs):
                    return await original_method(*args, **kwargs)
                proxy_method.__name__ = method_name
                return proxy_method

            # 确保关键方法存在
            async def get_all_active_themes(self, limit: int = 1000):
                return await self.base_gateway.get_all_active_themes(limit)

            async def load_all_categories(self):
                if hasattr(self.base_gateway, 'load_all_categories'):
                    return await self.base_gateway.load_all_categories()
                return []

            async def health_check(self) -> bool:
                return await self.base_gateway.health_check()

        # 创建包装后的gateway
        wrapped_gateway = WrappedGateway(base_gateway)

        async def patched_get_gateway(enable_retry=True, retry_config=None):
            return wrapped_gateway

        gateway_integration.get_gateway = patched_get_gateway

        # 初始化Redis
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
                "batch_size": self.config.batch_size,
                "block_time": 500,
            },
        )

        consumer_group = f"theme_processors_stress_{run_id}"
        consumer_name = f"tp_stress_{run_id}"

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
                "structured_batch_size": self.config.batch_size,
                "structured_block_time": 500,
            },
            db_manager=base_gateway,
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

        # 调试：检查gateway_integration.get_gateway是否已修补
        print(f"调试: gateway_integration.get_gateway = {gateway_integration.get_gateway}")

        ok = await theme_processor.initialize()
        if not ok:
            raise RuntimeError("theme_processor 初始化失败")

        # 调试：检查theme_processor.gateway的类型和属性
        print(f"调试: theme_processor.gateway类型 = {type(theme_processor.gateway)}")
        print(f"调试: hasattr(gateway, 'base_gateway') = {hasattr(theme_processor.gateway, 'base_gateway')}")
        print(f"调试: hasattr(gateway, 'get_all_active_themes') = {hasattr(theme_processor.gateway, 'get_all_active_themes')}")
        print(f"调试: gateway.base_gateway类型 = {type(getattr(theme_processor.gateway, 'base_gateway', None))}")

        await theme_processor.start()

        return {
            "redis_client": redis_client,
            "stream_bus": stream_bus,
            "base_gateway": base_gateway,
            "news_handler": news_handler,
            "theme_processor": theme_processor,
            "news_processor": news_processor,
            "raw_stream": raw_stream,
            "structured_stream": structured_stream,
            "decision_stream": decision_stream,
            "dead_letter_stream": dead_letter_stream,
            "original_get_gateway": original_get_gateway,
            "gateway_integration": gateway_integration
        }

    async def _cleanup_services(self, services: Dict[str, Any]):
        """清理服务"""
        try:
            await services["news_handler"].stop_storage_service()
        except Exception:
            pass
        try:
            await services["theme_processor"].stop()
        except Exception:
            pass

        # 清理测试数据
        await services["redis_client"].delete(
            services["raw_stream"],
            services["structured_stream"],
            services["decision_stream"],
            services["dead_letter_stream"]
        )

        # 恢复原始get_gateway函数
        if "gateway_integration" in services and "original_get_gateway" in services:
            services["gateway_integration"].get_gateway = services["original_get_gateway"]
            print("已恢复原始get_gateway函数")

        if hasattr(services["base_gateway"], "close"):
            await services["base_gateway"].close()

    async def run_stress_test(self):
        """运行压力测试"""
        print("=" * 80)
        print("全链路压力测试框架")
        print("=" * 80)

        # 加载测试数据
        samples = self._parse_test_cases(self.config.total_messages)
        print(f"已加载 {len(samples)} 条测试数据")

        # 生成运行ID
        run_id = uuid.uuid4().hex[:8]
        batch_id = f"stress_test_{run_id}"

        # 初始化监控器
        if self.config.enable_system_monitoring:
            self.resource_monitor = ResourceMonitor(interval=self.config.monitor_interval)
            self.resource_monitor.start()
            print("系统资源监控已启动")

        # 初始化服务
        print("初始化服务...")
        services = await self._initialize_services(run_id, batch_id)

        # 初始化Redis监控
        if self.config.enable_redis_monitoring:
            self.redis_monitor = RedisMonitor(services["redis_client"])

        # 初始化PostgreSQL监控
        if self.config.enable_postgres_monitoring:
            self.postgres_monitor = PostgresMonitor(self._pg_kwargs())

        # 开始测试
        test_config = {
            "total_messages": self.config.total_messages,
            "concurrent_users": self.config.concurrent_users,
            "batch_size": self.config.batch_size,
            "scenario": self.config.scenario.value,
            "duration_seconds": self.config.duration_seconds,
            "run_id": run_id,
            "batch_id": batch_id
        }
        self.metrics.start_test(test_config)

        print(f"\n开始压力测试 (场景: {self.config.scenario.value})")
        print(f"并发用户: {self.config.concurrent_users}, 批量大小: {self.config.batch_size}")
        print(f"总消息数: {self.config.total_messages}")

        # 启动监控任务
        monitoring_task = None
        if self.config.duration_seconds:
            monitoring_task = asyncio.create_task(
                self._monitoring_task(self.config.duration_seconds)
            )

        try:
            # 根据测试场景执行不同的测试策略
            if self.config.scenario == TestScenario.CONSTANT_LOAD:
                await self._run_constant_load_test(samples, batch_id, services)
            elif self.config.scenario == TestScenario.RAMP_UP:
                await self._run_ramp_up_test(samples, batch_id, services)
            elif self.config.scenario == TestScenario.SPIKE:
                await self._run_spike_test(samples, batch_id, services)
            elif self.config.scenario == TestScenario.ENDURANCE:
                await self._run_endurance_test(samples, batch_id, services)
            elif self.config.scenario == TestScenario.SOAK:
                await self._run_soak_test(samples, batch_id, services)
            else:
                await self._run_constant_load_test(samples, batch_id, services)

        finally:
            # 停止监控任务
            if monitoring_task:
                monitoring_task.cancel()
                try:
                    await monitoring_task
                except asyncio.CancelledError:
                    pass

            # 停止资源监控
            if self.resource_monitor:
                self.resource_monitor.stop()

            # 清理服务
            print("\n清理服务...")
            await self._cleanup_services(services)

            # 结束测试
            self.metrics.end_test()

            # 生成报告
            report = self.metrics.generate_report()

            # 添加资源监控摘要
            if self.resource_monitor:
                report["resource_monitoring"] = {
                    "system": self.resource_monitor.get_summary()
                }

            if self.redis_monitor:
                redis_summary = await self.redis_monitor.get_summary()
                if redis_summary:
                    if "resource_monitoring" not in report:
                        report["resource_monitoring"] = {}
                    report["resource_monitoring"]["redis"] = redis_summary

            if self.postgres_monitor:
                postgres_summary = await self.postgres_monitor.get_summary()
                if postgres_summary:
                    if "resource_monitoring" not in report:
                        report["resource_monitoring"] = {}
                    report["resource_monitoring"]["postgres"] = postgres_summary

            # 保存报告
            self.config.report_dir.mkdir(parents=True, exist_ok=True)
            report_file = self.config.report_dir / f"stress_test_report_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

            print(f"\n压力测试完成!")
            print(f"报告已保存到: {report_file}")

            # 输出关键指标
            self._print_summary(report)

            return report

    async def _run_constant_load_test(self, samples: List[Dict[str, Any]], batch_id: str, services: Dict[str, Any]):
        """运行恒定负载测试"""
        print("\n执行恒定负载测试...")

        tasks = []
        for i, sample in enumerate(samples, 1):
            # 控制并发数
            if len(tasks) >= self.config.concurrent_users:
                # 等待一批任务完成
                results = await asyncio.gather(*tasks, return_exceptions=True)
                self._process_batch_results(results, i - self.config.concurrent_users)
                tasks = []

            # 创建新任务
            task = self._test_single_message(
                sample=sample,
                index=i,
                batch_id=batch_id,
                stream_bus=services["stream_bus"],
                base_gateway=services["base_gateway"],
                redis_client=services["redis_client"],
                news_handler=services["news_handler"],
                theme_processor=services["theme_processor"],
                news_processor=services["news_processor"]
            )
            tasks.append(task)

            # 更新实时统计
            self.metrics.update_real_time_stats(len(tasks))

            # 轻微延迟以避免瞬间过载
            await asyncio.sleep(0.05)

        # 处理剩余任务
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._process_batch_results(results, len(samples) - len(tasks))

    async def _run_ramp_up_test(self, samples: List[Dict[str, Any]], batch_id: str, services: Dict[str, Any]):
        """运行递增负载测试"""
        print(f"\n执行递增负载测试 (步数: {self.config.ramp_up_steps})...")

        step_size = len(samples) // self.config.ramp_up_steps
        if step_size == 0:
            step_size = 1

        for step in range(self.config.ramp_up_steps):
            start_idx = step * step_size
            end_idx = min((step + 1) * step_size, len(samples))

            if start_idx >= end_idx:
                break

            step_samples = samples[start_idx:end_idx]
            step_concurrent = min(self.config.concurrent_users, (step + 1) * (self.config.concurrent_users // self.config.ramp_up_steps))

            print(f"步骤 {step + 1}/{self.config.ramp_up_steps}: 并发数={step_concurrent}, 消息数={len(step_samples)}")

            tasks = []
            for i, sample in enumerate(step_samples, start_idx + 1):
                if len(tasks) >= step_concurrent:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    self._process_batch_results(results, i - step_concurrent)
                    tasks = []

                task = self._test_single_message(
                    sample=sample,
                    index=i,
                    batch_id=batch_id,
                    stream_bus=services["stream_bus"],
                    base_gateway=services["base_gateway"],
                    redis_client=services["redis_client"],
                    news_handler=services["news_handler"],
                    theme_processor=services["theme_processor"],
                    news_processor=services["news_processor"]
                )
                tasks.append(task)

                self.metrics.update_real_time_stats(len(tasks))
                await asyncio.sleep(0.05)

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                self._process_batch_results(results, end_idx - len(tasks))

            # 步骤间延迟
            if step < self.config.ramp_up_steps - 1:
                await asyncio.sleep(2.0)

    async def _run_spike_test(self, samples: List[Dict[str, Any]], batch_id: str, services: Dict[str, Any]):
        """运行峰值负载测试"""
        print(f"\n执行峰值负载测试 (峰值乘数: {self.config.spike_multiplier}x)...")

        # 计算峰值并发数
        spike_concurrent = int(self.config.concurrent_users * self.config.spike_multiplier)

        # 将样本分为三部分：平稳、峰值、平稳
        third = len(samples) // 3

        # 第一部分：平稳负载
        print("阶段1: 平稳负载")
        await self._run_subset_test(samples[:third], batch_id, services, self.config.concurrent_users, start_index=1)

        # 第二部分：峰值负载
        print(f"阶段2: 峰值负载 (并发={spike_concurrent})")
        await self._run_subset_test(samples[third:2*third], batch_id, services, spike_concurrent, start_index=third+1)

        # 第三部分：平稳负载
        print("阶段3: 平稳负载")
        await self._run_subset_test(samples[2*third:], batch_id, services, self.config.concurrent_users, start_index=2*third+1)

    async def _run_endurance_test(self, samples: List[Dict[str, Any]], batch_id: str, services: Dict[str, Any]):
        """运行耐力测试"""
        print("\n执行耐力测试...")

        if not self.config.duration_seconds:
            print("耐力测试需要设置duration_seconds参数")
            return

        start_time = time.time()
        message_count = 0

        while time.time() - start_time < self.config.duration_seconds:
            # 循环使用样本
            for i in range(0, len(samples), self.config.concurrent_users):
                if time.time() - start_time >= self.config.duration_seconds:
                    break

                batch_samples = samples[i:i + self.config.concurrent_users]
                tasks = []

                for j, sample in enumerate(batch_samples):
                    task = self._test_single_message(
                        sample=sample,
                        index=message_count + j + 1,
                        batch_id=batch_id,
                        stream_bus=services["stream_bus"],
                        base_gateway=services["base_gateway"],
                        redis_client=services["redis_client"],
                        news_handler=services["news_handler"],
                        theme_processor=services["theme_processor"],
                        news_processor=services["news_processor"]
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks, return_exceptions=True)
                self._process_batch_results(results, message_count + 1)
                message_count += len(batch_samples)

                self.metrics.update_real_time_stats(len(tasks))

                # 进度显示
                elapsed = time.time() - start_time
                print(f"耐力测试进度: {elapsed:.1f}/{self.config.duration_seconds}秒, 消息数: {message_count}")

                await asyncio.sleep(0.1)

    async def _run_soak_test(self, samples: List[Dict[str, Any]], batch_id: str, services: Dict[str, Any]):
        """运行浸泡测试（长时间低负载）"""
        print("\n执行浸泡测试...")

        if not self.config.duration_seconds:
            print("浸泡测试需要设置duration_seconds参数")
            return

        # 使用较低的并发数
        soak_concurrent = max(1, self.config.concurrent_users // 2)

        start_time = time.time()
        message_count = 0

        while time.time() - start_time < self.config.duration_seconds:
            # 每次发送少量消息
            batch_size = min(soak_concurrent, len(samples))
            batch_samples = samples[:batch_size]

            tasks = []
            for j, sample in enumerate(batch_samples):
                task = self._test_single_message(
                    sample=sample,
                    index=message_count + j + 1,
                    batch_id=batch_id,
                    stream_bus=services["stream_bus"],
                    base_gateway=services["base_gateway"],
                    redis_client=services["redis_client"],
                    news_handler=services["news_handler"],
                    theme_processor=services["theme_processor"],
                    news_processor=services["news_processor"]
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._process_batch_results(results, message_count + 1)
            message_count += len(batch_samples)

            self.metrics.update_real_time_stats(len(tasks))

            # 长时间间隔
            elapsed = time.time() - start_time
            print(f"浸泡测试进度: {elapsed:.1f}/{self.config.duration_seconds}秒, 消息数: {message_count}")

            await asyncio.sleep(5.0)  # 5秒间隔

    async def _run_subset_test(self, samples: List[Dict[str, Any]], batch_id: str, services: Dict[str, Any],
                              concurrent: int, start_index: int):
        """运行子集测试"""
        tasks = []
        for i, sample in enumerate(samples, start_index):
            if len(tasks) >= concurrent:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                self._process_batch_results(results, i - concurrent)
                tasks = []

            task = self._test_single_message(
                sample=sample,
                index=i,
                batch_id=batch_id,
                stream_bus=services["stream_bus"],
                base_gateway=services["base_gateway"],
                redis_client=services["redis_client"],
                news_handler=services["news_handler"],
                theme_processor=services["theme_processor"],
                news_processor=services["news_processor"]
            )
            tasks.append(task)

            self.metrics.update_real_time_stats(len(tasks))
            await asyncio.sleep(0.05)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._process_batch_results(results, start_index + len(samples) - len(tasks))

    def _process_batch_results(self, results: List[Any], start_index: int):
        """处理批次结果"""
        success_count = 0
        for result in results:
            if isinstance(result, Exception):
                print(f"任务异常 (索引{start_index}): {result}")
            elif isinstance(result, dict) and result.get("status") == "success":
                success_count += 1

        if success_count > 0:
            print(f"批次处理完成: {success_count}/{len(results)} 成功")

    def _print_summary(self, report: Dict[str, Any]):
        """输出测试摘要"""
        print("\n" + "=" * 80)
        print("压力测试摘要")
        print("=" * 80)

        summary = report.get("summary", {})
        stats = report.get("performance_statistics", {})

        print(f"总消息数: {summary.get('total_messages', 0)}")
        print(f"成功消息数: {summary.get('successful_messages', 0)}")
        print(f"失败消息数: {summary.get('failed_messages', 0)}")
        print(f"成功率: {summary.get('successful_messages', 0)/summary.get('total_messages', 1)*100:.2f}%")
        print(f"吞吐量: {summary.get('throughput_mps', 0):.2f} 消息/秒")
        print(f"总时长: {summary.get('total_duration_seconds', 0):.2f} 秒")

        if "total_processing_latency" in stats:
            latency = stats["total_processing_latency"]
            print(f"总处理延迟: {latency.get('mean', 0):.3f}s (P95: {latency.get('p95', 0):.3f}s)")

        # 资源使用摘要
        if "resource_monitoring" in report:
            print("\n资源使用:")
            if "system" in report["resource_monitoring"]:
                system = report["resource_monitoring"]["system"]
                print(f"  CPU平均使用率: {system.get('cpu_avg', 0):.1f}%")
                print(f"  内存平均使用率: {system.get('memory_avg', 0):.1f}%")

            if "redis" in report["resource_monitoring"]:
                redis = report["resource_monitoring"]["redis"]
                print(f"  Redis平均连接数: {redis.get('connected_clients_avg', 0):.1f}")
                print(f"  Redis命中率: {redis.get('hit_rate', 0)*100:.1f}%")

        print("=" * 80)


async def main():
    """主函数"""
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
            print("请设置: export DEEPSEEK_API_KEY=your_key")
            return None

    # 配置压力测试
    config = StressTestConfig(
        total_messages=5,                 # 总消息数（测试时减少数量）
        concurrent_users=2,               # 并发用户数
        batch_size=5,                     # 批量大小
        scenario=TestScenario.CONSTANT_LOAD,  # 测试场景
        duration_seconds=None,            # 测试持续时间（耐力测试使用）
        monitor_interval=2.0,             # 监控采集间隔
        enable_system_monitoring=True,
        enable_redis_monitoring=True,
        enable_postgres_monitoring=True
    )

    # 创建测试器
    tester = FullChainStressTester(config)

    try:
        print("启动全链路压力测试框架...")
        report = await tester.run_stress_test()
        return report

    except Exception as e:
        print(f"压力测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    report = asyncio.run(main())

    if report:
        print("\n压力测试执行完成")
        # 输出测试配置
        config = report.get("test_configuration", {})
        print(f"\n测试配置:")
        print(f"  总消息数: {config.get('total_messages', 0)}")
        print(f"  并发用户数: {config.get('concurrent_users', 0)}")
        print(f"  批量大小: {config.get('batch_size', 0)}")
        print(f"  测试场景: {config.get('scenario', 'unknown')}")
        print(f"  运行ID: {config.get('run_id', 'unknown')}")
    else:
        print("\n压力测试执行失败")
        sys.exit(1)