"""
Redis Stream 实时推送服务（WebSocket/SSE）

为前端提供实时数据推送，直接从Redis Stream消费事件并广播到连接的客户端。
支持WebSocket和SSE两种协议，支持主题过滤。
"""
import asyncio
import atexit
import json
import logging
import os
import socket
import time
from typing import Dict, Set, Optional, List, Any
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from .stream_manager import RetryEnhancedRedisStreamManager
from .utils.alert_service import AlertService, Alert, AlertType, AlertSeverity

logger = logging.getLogger(__name__)

# 僵尸消费者判定: 空闲超过此阈值且无 pending 消息，视为已死
_STALE_CONSUMER_MAX_IDLE_MS = 300_000  # 5 分钟


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_subscriptions: Dict[str, Set[str]] = {}
        self.subscription_connections: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """接受WebSocket连接"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_subscriptions[client_id] = set()
        logger.info(f"Client connected: {client_id}")

    def disconnect(self, client_id: str):
        """断开WebSocket连接"""
        if client_id in self.active_connections:
            # 清理订阅关系
            subscriptions = self.connection_subscriptions.get(client_id, set())
            for stream in subscriptions:
                if stream in self.subscription_connections:
                    self.subscription_connections[stream].discard(client_id)
                    if not self.subscription_connections[stream]:
                        del self.subscription_connections[stream]

            del self.active_connections[client_id]
            if client_id in self.connection_subscriptions:
                del self.connection_subscriptions[client_id]
            logger.info(f"Client disconnected: {client_id}")

    def subscribe(self, client_id: str, stream_name: str):
        """客户端订阅Stream"""
        if client_id not in self.active_connections:
            return False

        self.connection_subscriptions[client_id].add(stream_name)
        if stream_name not in self.subscription_connections:
            self.subscription_connections[stream_name] = set()
        self.subscription_connections[stream_name].add(client_id)
        logger.info(f"Client {client_id} subscribed to {stream_name}")
        return True

    def unsubscribe(self, client_id: str, stream_name: str):
        """客户端取消订阅Stream"""
        if client_id in self.connection_subscriptions:
            self.connection_subscriptions[client_id].discard(stream_name)

        if stream_name in self.subscription_connections:
            self.subscription_connections[stream_name].discard(client_id)
            if not self.subscription_connections[stream_name]:
                del self.subscription_connections[stream_name]

        logger.info(f"Client {client_id} unsubscribed from {stream_name}")

    async def send_personal_message(self, message: dict, client_id: str):
        """发送私密消息到指定客户端"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message to {client_id}: {e}")
                self.disconnect(client_id)

    async def broadcast_to_stream(self, message: dict, stream_name: str):
        """广播消息到订阅指定Stream的所有客户端"""
        if stream_name not in self.subscription_connections:
            return

        client_ids = list(self.subscription_connections[stream_name])
        disconnected_clients = []

        for client_id in client_ids:
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].send_json(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast to {client_id}: {e}")
                    disconnected_clients.append(client_id)
            else:
                disconnected_clients.append(client_id)

        # 清理断开连接的客户端
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    async def broadcast(self, message: dict):
        """广播消息到所有连接的客户端"""
        disconnected_clients = []

        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to {client_id}: {e}")
                disconnected_clients.append(client_id)

        # 清理断开连接的客户端
        for client_id in disconnected_clients:
            self.disconnect(client_id)

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)

    def get_subscription_stats(self) -> Dict[str, Any]:
        """获取订阅统计信息"""
        return {
            "total_connections": len(self.active_connections),
            "total_subscriptions": sum(len(subs) for subs in self.connection_subscriptions.values()),
            "stream_subscription_counts": {
                stream: len(clients) for stream, clients in self.subscription_connections.items()
            }
        }


class RedisStreamConsumer:
    """Redis Stream消费者，负责从Stream读取消息并推送到连接管理器"""

    def __init__(
        self,
        redis_client: Redis,
        connection_manager: ConnectionManager,
        stream_configs: Optional[Dict[str, Dict]] = None,
        alert_service: Optional[AlertService] = None,
    ):
        self.redis = redis_client
        self.connection_manager = connection_manager
        self.stream_configs = stream_configs or {}
        self.alert_service = alert_service
        self.consumer_group = "realtime_push_service"
        self.consumer_name = (
            f"push-{socket.gethostname()[:16]}-{os.getpid()}-{int(time.time())}"
        )
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

    async def _cleanup_stale_consumers(self, stream_names: List[str]) -> int:
        """启动时清理僵尸消费者: 空闲超过阈值且无 pending 消息的视为已死。

        解决: 进程崩溃/被 kill 后 xgroup_delconsumer 未执行的残留问题。
        """
        removed_total = 0
        for stream_name in stream_names:
            try:
                consumers = await self.redis.xinfo_consumers(
                    stream_name, self.consumer_group,
                )
            except Exception:
                continue  # 消费组可能尚不存在
            for c in consumers:
                c_name = c.get("name", "")
                c_idle = int(c.get("idle", 0))
                c_pending = int(c.get("pending", 0))
                if c_idle > _STALE_CONSUMER_MAX_IDLE_MS and c_pending == 0:
                    try:
                        await self.redis.xgroup_delconsumer(
                            stream_name, self.consumer_group, c_name,
                        )
                        removed_total += 1
                        logger.warning(
                            "Zombie cleanup: removed consumer %s from %s/%s "
                            "(idle=%dms, pending=%d)",
                            c_name, stream_name, self.consumer_group,
                            c_idle, c_pending,
                        )
                    except Exception as exc:
                        logger.debug(
                            "Zombie cleanup failed for %s: %s", c_name, exc,
                        )
        if removed_total:
            logger.info("Zombie cleanup complete: removed %d stale consumers", removed_total)
        return removed_total

    async def ensure_consumer_group(self, stream_name: str):
        """确保消费者组存在"""
        try:
            await self.redis.xgroup_create(
                name=stream_name,
                groupname=self.consumer_group,
                id="$",
                mkstream=True
            )
            logger.info(f"Created consumer group {self.consumer_group} for stream {stream_name}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group {self.consumer_group} already exists for {stream_name}")
            elif "BUSYLOADING" in str(e) or "loading the dataset in memory" in str(e):
                logger.warning(
                    f"Redis still loading dataset, skip consumer-group setup for now: {stream_name}"
                )
            else:
                logger.error(f"Failed to create consumer group for {stream_name}: {e}")
                raise

    async def consume_stream(self, stream_name: str, batch_size: int = 10, block_ms: int = 5000):
        """消费指定Stream的消息"""
        last_id = ">"

        while self.is_running:
            try:
                # 读取消息
                messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={stream_name: last_id},
                    count=batch_size,
                    block=block_ms
                )

                if not messages:
                    continue

                stream_data = messages[0]  # 格式: [(stream_name, [(message_id, data), ...])]
                _, message_list = stream_data

                for message_id, message_data in message_list:
                    # 处理消息
                    await self.process_message(stream_name, message_id, message_data)

                    # 确认消息
                    await self.redis.xack(stream_name, self.consumer_group, message_id)

                    last_id = message_id

            except asyncio.CancelledError:
                logger.info(f"Stream consumption cancelled for {stream_name}")
                break
            except Exception as e:
                logger.error(f"Error consuming stream {stream_name}: {e}")
                # 发送告警
                if self.alert_service:
                    alert = Alert(
                        alert_type=AlertType.STREAM_CONSUMPTION_ERROR,
                        severity=AlertSeverity.ERROR,
                        title=f"Stream消费错误: {stream_name}",
                        message=f"消费Stream时发生错误: {str(e)}",
                        context={
                            "stream_name": stream_name,
                            "consumer_group": self.consumer_group,
                            "consumer_name": self.consumer_name,
                            "error": str(e),
                        }
                    )
                    await self.alert_service.send_alert(alert)

                # 短暂延迟后重试
                await asyncio.sleep(1)

    async def process_message(self, stream_name: str, message_id: str, message_data: Dict[str, str]):
        """处理从Stream读取的消息"""
        try:
            # 解析消息数据
            event_data = {}
            for key, value in message_data.items():
                if key in ["data", "payload", "event"]:
                    try:
                        event_data = json.loads(value)
                    except json.JSONDecodeError:
                        event_data = {"raw_data": value}
                    break

            if not event_data:
                event_data = message_data

            # 构建推送消息
            push_message = {
                "stream": stream_name,
                "message_id": message_id,
                "timestamp": datetime.now().isoformat(),
                "data": event_data,
                "type": "stream_message"
            }

            # 根据Stream类型添加元数据
            if "event_type" in event_data:
                push_message["event_type"] = event_data.get("event_type")
            if "subject_key" in event_data:
                push_message["subject_key"] = event_data.get("subject_key")
            if "stock_id" in event_data:
                push_message["stock_id"] = event_data.get("stock_id")

            # 广播到订阅该Stream的客户端
            await self.connection_manager.broadcast_to_stream(push_message, stream_name)

            logger.debug(f"Processed message {message_id} from {stream_name}")

        except Exception as e:
            logger.error(f"Error processing message {message_id} from {stream_name}: {e}")

    async def start(self, streams: List[str]):
        """启动Stream消费者"""
        self.is_running = True

        # ── 启动前清理僵尸消费者 ──
        await self._cleanup_stale_consumers(streams)

        # 为每个Stream创建消费者组
        for stream_name in streams:
            try:
                await self.ensure_consumer_group(stream_name)
            except Exception as e:
                logger.error(f"Failed to setup consumer group for {stream_name}: {e}")
                # 发送告警
                if self.alert_service:
                    alert = Alert(
                        alert_type=AlertType.CONSUMER_GROUP_ERROR,
                        severity=AlertSeverity.ERROR,
                        title=f"消费者组创建失败: {stream_name}",
                        message=f"无法为Stream创建消费者组: {str(e)}",
                        context={
                            "stream_name": stream_name,
                            "consumer_group": self.consumer_group,
                            "error": str(e),
                        }
                    )
                    await self.alert_service.send_alert(alert)

        # 为每个Stream启动消费任务
        tasks = []
        for stream_name in streams:
            task = asyncio.create_task(self.consume_stream(stream_name))
            tasks.append(task)
            logger.info(f"Started consumer for stream: {stream_name}")

        self.task = asyncio.gather(*tasks, return_exceptions=True)

        # atexit 兜底: 正常退出时尽力清理（SIGKILL 无法拦截，但 SIGTERM/SIGINT 可）
        _atexit_streams = list(streams)
        _atexit_redis = self.redis
        _atexit_group = self.consumer_group
        _atexit_name = self.consumer_name

        def _atexit_cleanup():
            for s in _atexit_streams:
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(
                        _atexit_redis.xgroup_delconsumer(s, _atexit_group, _atexit_name)
                    )
                    loop.close()
                except Exception:
                    pass
        atexit.register(_atexit_cleanup)

        # 发送启动告警
        if self.alert_service:
            alert = Alert(
                alert_type=AlertType.SERVICE_STARTUP,
                severity=AlertSeverity.INFO,
                title="实时推送服务启动",
                message=f"实时推送服务已启动，正在消费Stream: {', '.join(streams)}",
                context={
                    "streams": streams,
                    "consumer_group": self.consumer_group,
                    "consumer_name": self.consumer_name,
                }
            )
            await self.alert_service.send_alert(alert)

    async def stop(self):
        """停止Stream消费者"""
        self.is_running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("Stream consumer tasks cancelled")

        # Phase 6A: self-cleanup — remove our consumer from groups on exit
        for _stream in self.stream_configs:
            try:
                await self.redis.xgroup_delconsumer(_stream, self.consumer_group, self.consumer_name)
                logger.info("Self-cleanup: removed consumer %s from %s/%s", self.consumer_name, _stream, self.consumer_group)
            except Exception:
                pass

        logger.info("RedisStreamConsumer stopped")

        # 发送停止告警
        if self.alert_service:
            alert = Alert(
                alert_type=AlertType.SERVICE_SHUTDOWN,
                severity=AlertSeverity.INFO,
                title="实时推送服务停止",
                message="实时推送服务已停止",
                context={
                    "consumer_group": self.consumer_group,
                    "consumer_name": self.consumer_name,
                }
            )
            await self.alert_service.send_alert(alert)


class RealtimePushService:
    """实时推送服务主类"""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        stream_manager: Optional[RetryEnhancedRedisStreamManager] = None,
        alert_service: Optional[AlertService] = None,
    ):
        self.connection_manager = ConnectionManager()
        self.redis_url = redis_url
        self.stream_manager = stream_manager
        self.alert_service = alert_service
        self.redis_client: Optional[Redis] = None
        self.stream_consumer: Optional[RedisStreamConsumer] = None
        self.default_streams = [
            "stream:event:feed",
            "stream:jyhf:feed",
            "stream:theme:feed",
            "stream:news:feed",
            "stream:stock:feed"
        ]

    async def initialize(self):
        """初始化服务"""
        try:
            # 初始化Redis客户端
            if self.redis_url:
                self.redis_client = Redis.from_url(self.redis_url, decode_responses=True)
            elif self.stream_manager:
                self.redis_client = self.stream_manager.redis_client

            if not self.redis_client:
                raise ValueError("No Redis client available")

            # 初始化Stream消费者
            self.stream_consumer = RedisStreamConsumer(
                redis_client=self.redis_client,
                connection_manager=self.connection_manager,
                alert_service=self.alert_service,
            )

            # 启动消费者
            await self.stream_consumer.start(self.default_streams)

            logger.info("RealtimePushService initialized")

        except Exception as e:
            logger.error(f"Failed to initialize RealtimePushService: {e}")
            raise

    async def shutdown(self):
        """关闭服务"""
        if self.stream_consumer:
            await self.stream_consumer.stop()

        if self.redis_client:
            await self.redis_client.close()

        logger.info("RealtimePushService shutdown complete")

    def get_connection_manager(self) -> ConnectionManager:
        """获取连接管理器"""
        return self.connection_manager

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        if not self.stream_consumer:
            return {"status": "not_initialized"}

        connection_stats = self.connection_manager.get_subscription_stats()

        return {
            "status": "running",
            "connections": connection_stats,
            "consumer": {
                "consumer_group": self.stream_consumer.consumer_group,
                "consumer_name": self.stream_consumer.consumer_name,
                "streams": self.default_streams,
            }
        }


# FastAPI WebSocket端点示例
"""
# 在FastAPI应用中添加以下端点：

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from database_service.streams.realtime_push_service import RealtimePushService

app = FastAPI()
push_service = RealtimePushService()

@app.on_event("startup")
async def startup():
    await push_service.initialize()

@app.on_event("shutdown")
async def shutdown():
    await push_service.shutdown()

@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    client_id = f"client-{uuid.uuid4().hex[:8]}"
    connection_manager = push_service.get_connection_manager()

    await connection_manager.connect(websocket, client_id)

    try:
        while True:
            # 接收客户端消息（订阅/取消订阅指令）
            data = await websocket.receive_json()
            command = data.get("command")

            if command == "subscribe":
                stream_name = data.get("stream")
                if stream_name:
                    connection_manager.subscribe(client_id, stream_name)
                    await connection_manager.send_personal_message({
                        "type": "subscription",
                        "status": "subscribed",
                        "stream": stream_name
                    }, client_id)

            elif command == "unsubscribe":
                stream_name = data.get("stream")
                if stream_name:
                    connection_manager.unsubscribe(client_id, stream_name)
                    await connection_manager.send_personal_message({
                        "type": "subscription",
                        "status": "unsubscribed",
                        "stream": stream_name
                    }, client_id)

            elif command == "list_subscriptions":
                subscriptions = list(connection_manager.connection_subscriptions.get(client_id, set()))
                await connection_manager.send_personal_message({
                    "type": "subscription_list",
                    "subscriptions": subscriptions
                }, client_id)

            elif command == "ping":
                await connection_manager.send_personal_message({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }, client_id)

    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)

@app.get("/api/realtime/stats")
async def get_realtime_stats():
    return push_service.get_stats()
"""
