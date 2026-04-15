#!/usr/bin/env python3
"""
实时推送服务监控脚本

监控Redis Stream实时推送服务的健康状态，包括：
- Redis连接状态
- WebSocket端点可用性
- Stream长度和消费者组状态
- 服务统计信息
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RealtimeServiceMonitor:
    """实时推送服务监控器"""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        api_base_url: str = "http://localhost:8000",
        websocket_url: str = "ws://localhost:8000/ws/realtime",
        check_interval: int = 60,  # 检查间隔（秒）
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.api_base_url = api_base_url
        self.websocket_url = websocket_url
        self.check_interval = check_interval
        self.metrics_history = []
        self.alert_thresholds = {
            "redis_connection_failures": 3,
            "api_failures": 3,
            "stream_backlog_threshold": 1000,
            "consumer_lag_threshold": 100,
            "memory_usage_threshold_mb": 500,
        }

    async def check_redis_connection(self) -> Dict[str, Any]:
        """检查Redis连接状态"""
        try:
            from redis.asyncio import Redis

            start_time = time.time()
            redis_client = Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=5)

            # 测试连接
            pong = await redis_client.ping()
            latency = time.time() - start_time

            if pong:
                # 获取Redis信息
                info = await redis_client.info()

                # 检查关键Stream
                streams = ["stream:event:feed", "stream:theme:feed", "stream:news:feed", "stream:stock:feed"]
                stream_info = {}
                for stream in streams:
                    try:
                        length = await redis_client.xlen(stream)
                        stream_info[stream] = {"length": length}

                        # 检查消费者组
                        try:
                            groups = await redis_client.xinfo_groups(stream)
                            if groups:
                                stream_info[stream]["groups"] = groups
                        except Exception as e:
                            if "NOGROUP" not in str(e):
                                stream_info[stream]["group_error"] = str(e)
                    except Exception as e:
                        stream_info[stream] = {"error": str(e)}

                await redis_client.close()

                return {
                    "status": "healthy",
                    "latency_ms": round(latency * 1000, 2),
                    "version": info.get("redis_version"),
                    "used_memory_mb": round(int(info.get("used_memory", 0)) / 1024 / 1024, 2),
                    "connected_clients": info.get("connected_clients"),
                    "streams": stream_info,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                await redis_client.close()
                return {"status": "unhealthy", "error": "Redis ping failed", "timestamp": datetime.now().isoformat()}

        except ImportError as e:
            return {"status": "error", "error": f"Redis client not available: {e}", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": f"Redis connection failed: {e}", "timestamp": datetime.now().isoformat()}

    async def check_api_endpoints(self) -> Dict[str, Any]:
        """检查API端点可用性"""
        endpoints = {
            "health": f"{self.api_base_url}/health",
            "realtime_stats": f"{self.api_base_url}/api/realtime/stats",
            "realtime_streams": f"{self.api_base_url}/api/realtime/streams",
        }

        results = {}
        async with aiohttp.ClientSession() as session:
            for name, url in endpoints.items():
                try:
                    start_time = time.time()
                    async with session.get(url, timeout=10) as response:
                        latency = time.time() - start_time
                        status = response.status

                        if status == 200:
                            try:
                                data = await response.json()
                                results[name] = {
                                    "status": "healthy",
                                    "latency_ms": round(latency * 1000, 2),
                                    "http_status": status,
                                    "data": data
                                }
                            except:
                                results[name] = {
                                    "status": "healthy",
                                    "latency_ms": round(latency * 1000, 2),
                                    "http_status": status,
                                    "data": "non-json response"
                                }
                        else:
                            results[name] = {
                                "status": "unhealthy",
                                "latency_ms": round(latency * 1000, 2),
                                "http_status": status,
                                "error": f"HTTP {status}"
                            }
                except asyncio.TimeoutError:
                    results[name] = {"status": "timeout", "error": "Request timeout"}
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}

        # 总体状态
        all_healthy = all(r.get("status") == "healthy" for r in results.values())
        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "endpoints": results,
            "timestamp": datetime.now().isoformat()
        }

    async def check_websocket_connection(self) -> Dict[str, Any]:
        """检查WebSocket连接"""
        try:
            import websockets

            start_time = time.time()
            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 尝试WebSocket连接
                try:
                    # 注意：aiohttp不支持websocket检查，我们使用简单的HTTP升级检查
                    # 实际部署中可以使用websockets库
                    ws_url = self.websocket_url.replace("ws://", "http://").replace("wss://", "https://")
                    async with session.get(ws_url) as response:
                        latency = time.time() - start_time

                        # WebSocket端点应该返回426 Upgrade Required或类似
                        if response.status in [426, 101, 400, 404]:
                            return {
                                "status": "available",
                                "latency_ms": round(latency * 1000, 2),
                                "http_status": response.status,
                                "timestamp": datetime.now().isoformat()
                            }
                        else:
                            return {
                                "status": "unexpected_response",
                                "latency_ms": round(latency * 1000, 2),
                                "http_status": response.status,
                                "timestamp": datetime.now().isoformat()
                            }
                except Exception as e:
                    return {
                        "status": "error",
                        "error": f"WebSocket check failed: {e}",
                        "timestamp": datetime.now().isoformat()
                    }

        except ImportError:
            return {
                "status": "error",
                "error": "websockets library not available",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"WebSocket connection failed: {e}",
                "timestamp": datetime.now().isoformat()
            }

    async def collect_metrics(self) -> Dict[str, Any]:
        """收集所有监控指标"""
        logger.info("开始收集监控指标...")

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "redis": await self.check_redis_connection(),
            "api": await self.check_api_endpoints(),
            "websocket": await self.check_websocket_connection(),
        }

        # 计算总体状态
        statuses = [metrics["redis"]["status"], metrics["api"]["status"], metrics["websocket"]["status"]]
        if all(s == "healthy" or s == "available" for s in statuses):
            metrics["overall_status"] = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            metrics["overall_status"] = "unhealthy"
        else:
            metrics["overall_status"] = "degraded"

        # 添加性能指标
        redis_latency = metrics["redis"].get("latency_ms", 0)
        api_latency = 0
        api_count = 0
        for endpoint in metrics["api"].get("endpoints", {}).values():
            if "latency_ms" in endpoint:
                api_latency += endpoint["latency_ms"]
                api_count += 1

        metrics["performance"] = {
            "redis_latency_ms": redis_latency,
            "api_avg_latency_ms": round(api_latency / api_count, 2) if api_count > 0 else 0,
            "websocket_latency_ms": metrics["websocket"].get("latency_ms", 0),
        }

        self.metrics_history.append(metrics)
        # 保留最近100条记录
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]

        return metrics

    def check_alerts(self, metrics: Dict[str, Any]) -> list:
        """检查告警条件"""
        alerts = []

        # Redis内存使用检查
        redis_info = metrics.get("redis", {})
        if redis_info.get("status") == "healthy":
            memory_mb = redis_info.get("used_memory_mb", 0)
            if memory_mb > self.alert_thresholds["memory_usage_threshold_mb"]:
                alerts.append({
                    "severity": "warning",
                    "component": "redis",
                    "message": f"Redis内存使用过高: {memory_mb} MB",
                    "threshold": self.alert_thresholds["memory_usage_threshold_mb"],
                    "timestamp": metrics["timestamp"]
                })

            # Stream积压检查
            streams = redis_info.get("streams", {})
            for stream_name, stream_data in streams.items():
                if "length" in stream_data:
                    length = stream_data["length"]
                    if length > self.alert_thresholds["stream_backlog_threshold"]:
                        alerts.append({
                            "severity": "warning",
                            "component": "redis",
                            "message": f"Stream积压过高: {stream_name} ({length} 条消息)",
                            "threshold": self.alert_thresholds["stream_backlog_threshold"],
                            "timestamp": metrics["timestamp"]
                        })

        # API健康检查
        api_info = metrics.get("api", {})
        if api_info.get("status") != "healthy":
            alerts.append({
                "severity": "critical",
                "component": "api",
                "message": f"API服务不健康: {api_info.get('status')}",
                "timestamp": metrics["timestamp"]
            })

        # WebSocket检查
        ws_info = metrics.get("websocket", {})
        if ws_info.get("status") not in ["available", "healthy"]:
            alerts.append({
                "severity": "critical",
                "component": "websocket",
                "message": f"WebSocket服务不可用: {ws_info.get('status')}",
                "timestamp": metrics["timestamp"]
            })

        return alerts

    def format_metrics_report(self, metrics: Dict[str, Any], alerts: list) -> str:
        """格式化监控报告"""
        report = []

        report.append("="*80)
        report.append(f"实时推送服务监控报告 - {metrics['timestamp']}")
        report.append("="*80)

        # 总体状态
        status_emoji = "✅" if metrics["overall_status"] == "healthy" else "⚠️" if metrics["overall_status"] == "degraded" else "❌"
        report.append(f"\n📊 总体状态: {status_emoji} {metrics['overall_status'].upper()}")

        # Redis状态
        redis = metrics["redis"]
        redis_emoji = "✅" if redis["status"] == "healthy" else "❌"
        report.append(f"\n🔴 Redis状态: {redis_emoji} {redis['status']}")
        if redis["status"] == "healthy":
            report.append(f"   版本: {redis.get('version', 'N/A')}")
            report.append(f"   延迟: {redis.get('latency_ms', 0)}ms")
            report.append(f"   内存: {redis.get('used_memory_mb', 0)} MB")
            report.append(f"   连接数: {redis.get('connected_clients', 0)}")

            # Stream信息
            streams = redis.get("streams", {})
            if streams:
                report.append(f"   Streams:")
                for stream_name, stream_data in streams.items():
                    if "length" in stream_data:
                        report.append(f"    - {stream_name}: {stream_data['length']} 条消息")

        # API状态
        api = metrics["api"]
        api_emoji = "✅" if api["status"] == "healthy" else "❌"
        report.append(f"\n🌐 API状态: {api_emoji} {api['status']}")
        for endpoint_name, endpoint_data in api.get("endpoints", {}).items():
            endpoint_emoji = "✅" if endpoint_data.get("status") == "healthy" else "❌"
            report.append(f"    {endpoint_name}: {endpoint_emoji} {endpoint_data.get('latency_ms', 0)}ms")

        # WebSocket状态
        websocket = metrics["websocket"]
        ws_emoji = "✅" if websocket["status"] == "available" else "❌"
        report.append(f"\n🔌 WebSocket状态: {ws_emoji} {websocket['status']}")
        if "latency_ms" in websocket:
            report.append(f"   延迟: {websocket['latency_ms']}ms")

        # 性能指标
        perf = metrics.get("performance", {})
        report.append(f"\n⚡ 性能指标:")
        report.append(f"   Redis延迟: {perf.get('redis_latency_ms', 0)}ms")
        report.append(f"   API平均延迟: {perf.get('api_avg_latency_ms', 0)}ms")
        report.append(f"   WebSocket延迟: {perf.get('websocket_latency_ms', 0)}ms")

        # 告警
        if alerts:
            report.append(f"\n🚨 告警 ({len(alerts)} 个):")
            for alert in alerts:
                severity_emoji = "🔴" if alert["severity"] == "critical" else "🟡"
                report.append(f"   {severity_emoji} [{alert['component']}] {alert['message']}")
        else:
            report.append(f"\n✅ 无告警")

        # 历史趋势
        if len(self.metrics_history) > 1:
            healthy_count = sum(1 for m in self.metrics_history if m.get("overall_status") == "healthy")
            health_percentage = (healthy_count / len(self.metrics_history)) * 100
            report.append(f"\n📈 历史趋势: {len(self.metrics_history)} 次检查，{health_percentage:.1f}% 健康")

        report.append("\n" + "="*80)
        return "\n".join(report)

    async def run_monitoring_loop(self):
        """运行监控循环"""
        logger.info(f"启动实时推送服务监控，检查间隔: {self.check_interval}秒")
        logger.info(f"API地址: {self.api_base_url}")
        logger.info(f"Redis地址: {self.redis_url}")

        try:
            while True:
                logger.info(f"\n开始监控检查...")

                # 收集指标
                metrics = await self.collect_metrics()

                # 检查告警
                alerts = self.check_alerts(metrics)

                # 生成报告
                report = self.format_metrics_report(metrics, alerts)
                print(report)

                # 如果有严重告警，记录错误日志
                critical_alerts = [a for a in alerts if a["severity"] == "critical"]
                if critical_alerts:
                    logger.error(f"发现 {len(critical_alerts)} 个严重告警")

                # 等待下一次检查
                logger.info(f"等待 {self.check_interval} 秒后进行下一次检查...")
                await asyncio.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("监控循环被用户中断")
        except Exception as e:
            logger.error(f"监控循环出错: {e}")
            import traceback
            traceback.print_exc()

    async def run_single_check(self):
        """运行单次检查"""
        logger.info("运行单次监控检查...")

        # 收集指标
        metrics = await self.collect_metrics()

        # 检查告警
        alerts = self.check_alerts(metrics)

        # 生成报告
        report = self.format_metrics_report(metrics, alerts)
        print(report)

        # 返回退出码
        if metrics["overall_status"] == "healthy":
            logger.info("✅ 服务健康")
            return 0
        elif metrics["overall_status"] == "degraded":
            logger.warning("⚠️  服务降级")
            return 1
        else:
            logger.error("❌ 服务不健康")
            return 2


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="实时推送服务监控")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API基础URL")
    parser.add_argument("--redis-url", help="Redis URL（默认从环境变量REDIS_URL获取）")
    parser.add_argument("--interval", type=int, default=60, help="监控检查间隔（秒）")
    parser.add_argument("--single", action="store_true", help="运行单次检查")
    parser.add_argument("--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 初始化监控器
    monitor = RealtimeServiceMonitor(
        redis_url=args.redis_url,
        api_base_url=args.api_url,
        check_interval=args.interval,
    )

    if args.single:
        # 单次检查
        return await monitor.run_single_check()
    else:
        # 持续监控
        await monitor.run_monitoring_loop()
        return 0


if __name__ == "__main__":
    # 切换到项目根目录
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    exit_code = asyncio.run(main())
    sys.exit(exit_code)