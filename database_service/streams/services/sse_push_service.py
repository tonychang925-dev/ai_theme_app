"""
SSE推送服务 (SSEPushService)

基于全链路打通方案，监听Redis Stream `stream:event:feed`，
将事件转换为SSE格式推送到前端客户端。
实现Stream→SSE断点的打通。

功能：
- 监听事件feed Stream
- 将Stream事件转换为SSE格式
- 支持多客户端SSE连接管理
- 保持与现有SSE API的兼容性
- 异常处理和连接恢复
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator, Set
import time

logger = logging.getLogger(__name__)

# 尝试导入Redis Stream管理器
try:
    from database_service.streams.stream_manager import RetryEnhancedRedisStreamManager
    STREAM_MANAGER_AVAILABLE = True
except ImportError as e:
    STREAM_MANAGER_AVAILABLE = False
    logger.warning(f"无法导入RetryEnhancedRedisStreamManager: {e}")


class SSEConnectionManager:
    """SSE连接管理器

    管理所有活跃的SSE连接，支持消息广播和连接状态跟踪。
    """

    def __init__(self):
        # client_id -> 连接信息字典
        self.active_connections: Dict[str, Dict] = {}
        # 连接创建时间跟踪
        self.connection_times: Dict[str, float] = {}
        # 连接统计
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_failed": 0,
            "connection_errors": 0
        }

    def register_connection(self, client_id: str, connection_info: Dict) -> None:
        """注册新的SSE连接"""
        self.active_connections[client_id] = connection_info
        self.connection_times[client_id] = time.time()
        self.stats["total_connections"] += 1
        self.stats["active_connections"] += 1
        logger.debug(f"SSE连接注册: {client_id}")

    def unregister_connection(self, client_id: str) -> None:
        """注销SSE连接"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.connection_times:
            del self.connection_times[client_id]
        self.stats["active_connections"] = max(0, self.stats["active_connections"] - 1)
        logger.debug(f"SSE连接注销: {client_id}")

    def update_connection_info(self, client_id: str, info_updates: Dict) -> None:
        """更新连接信息"""
        if client_id in self.active_connections:
            self.active_connections[client_id].update(info_updates)

    async def send_sse_event(self, client_id: str, event_type: str, data: Any) -> bool:
        """发送SSE事件到指定客户端

        注意：SSE连接是单向的，我们通过队列发送事件。
        实际发送由SSE事件生成器处理。
        """
        if client_id not in self.active_connections:
            return False

        try:
            # 将事件放入客户端的消息队列
            if "message_queue" in self.active_connections[client_id]:
                event = {
                    "event_type": event_type,
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                }
                await self.active_connections[client_id]["message_queue"].put(event)
                self.stats["messages_sent"] += 1
                return True
        except Exception as e:
            logger.error(f"发送SSE事件到 {client_id} 失败: {e}")
            self.stats["messages_failed"] += 1
            self.stats["connection_errors"] += 1

        return False

    async def broadcast_sse_event(self, event_type: str, data: Any) -> int:
        """广播SSE事件到所有活跃客户端

        Returns:
            成功发送的客户端数量
        """
        if not self.active_connections:
            return 0

        sent_count = 0
        disconnected_clients = []

        for client_id in list(self.active_connections.keys()):
            success = await self.send_sse_event(client_id, event_type, data)
            if success:
                sent_count += 1
            else:
                disconnected_clients.append(client_id)

        # 清理断开连接的客户端
        for client_id in disconnected_clients:
            self.unregister_connection(client_id)

        return sent_count

    def get_connection_info(self, client_id: str) -> Optional[Dict]:
        """获取连接信息"""
        return self.active_connections.get(client_id)

    def get_all_connections(self) -> Dict[str, Dict]:
        """获取所有连接信息"""
        return self.active_connections.copy()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = self.stats.copy()
        stats["connection_durations"] = {}

        # 计算连接持续时间
        current_time = time.time()
        for client_id, connect_time in self.connection_times.items():
            duration = current_time - connect_time
            stats["connection_durations"][client_id] = round(duration, 2)

        return stats

    def cleanup_inactive_connections(self, timeout_seconds: int = 300) -> List[str]:
        """清理不活跃的连接

        Args:
            timeout_seconds: 超时时间（秒）

        Returns:
            被清理的客户端ID列表
        """
        if not self.connection_times:
            return []

        current_time = time.time()
        inactive_clients = []

        for client_id, connect_time in self.connection_times.items():
            if current_time - connect_time > timeout_seconds:
                inactive_clients.append(client_id)

        for client_id in inactive_clients:
            self.unregister_connection(client_id)
            logger.info(f"清理不活跃SSE连接: {client_id}")

        return inactive_clients


class SSEPushService:
    """SSE推送服务主类"""

    def __init__(
        self,
        stream_manager=None,
        redis_client=None,
        redis_url: Optional[str] = None,
        config: Optional[Dict] = None
    ):
        """
        初始化SSE推送服务

        Args:
            stream_manager: Redis Stream管理器（可选）
            redis_client: Redis客户端（可选）
            redis_url: Redis连接URL（可选，如果没有提供stream_manager和redis_client）
            config: 配置字典
        """
        self.config = config or {}

        # 初始化stream_manager
        if stream_manager:
            self.stream_manager = stream_manager
        elif redis_url and STREAM_MANAGER_AVAILABLE:
            # 使用redis_url创建stream_manager
            self.stream_manager = RetryEnhancedRedisStreamManager(redis_url=redis_url)
        elif redis_client and STREAM_MANAGER_AVAILABLE:
            # 兼容调用方仅传redis_client的场景（stream_manager当前不支持redis_client参数）
            logger.warning("SSEPushService收到redis_client但stream_manager不支持该构造参数，回退使用默认redis_url")
            self.stream_manager = RetryEnhancedRedisStreamManager(
                redis_url=self.config.get("redis_url", "redis://localhost:6379/0")
            )
        else:
            if not STREAM_MANAGER_AVAILABLE:
                raise ImportError("RetryEnhancedRedisStreamManager不可用，无法初始化SSEPushService")
            # 使用默认配置创建stream_manager
            self.stream_manager = RetryEnhancedRedisStreamManager()

        self.redis_client = redis_client or getattr(self.stream_manager, 'redis_client', None)

        # 配置参数
        self.input_stream = self.config.get("input_stream", "stream:event:feed")
        self.consumer_group = self.config.get("consumer_group", "sse_pushers")
        self.consumer_name = self.config.get("consumer_name", f"sse_pusher_{int(time.time())}")
        self.batch_size = self.config.get("batch_size", 10)
        self.polling_interval = self.config.get("polling_interval", 1)  # 秒
        self.heartbeat_interval = self.config.get("heartbeat_interval", 15)  # 秒

        # 连接管理器
        self.connection_manager = SSEConnectionManager()

        # 运行状态
        self.is_running = False
        self.consumer_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self.stats = {
            "started_at": None,
            "total_messages_consumed": 0,
            "sse_events_sent": 0,
            "sse_events_failed": 0,
            "clients_served": 0,
            "errors": []
        }

        logger.info(f"SSEPushService 初始化完成")
        logger.info(f"  输入Stream: {self.input_stream}")
        logger.info(f"  消费者组: {self.consumer_group}")
        logger.info(f"  批量大小: {self.batch_size}")

    async def start(self) -> None:
        """启动SSE推送服务"""
        if self.is_running:
            logger.warning("SSE推送服务已经在运行中")
            return

        self.is_running = True
        self.stats["started_at"] = datetime.now().isoformat()

        # 确保消费者组存在
        await self._ensure_consumer_group()

        # 启动Stream消费任务
        self.consumer_task = asyncio.create_task(self._stream_consumption_loop())

        # 启动连接清理任务
        self.cleanup_task = asyncio.create_task(self._connection_cleanup_loop())

        logger.info("SSE推送服务已启动")

    async def stop(self) -> None:
        """停止SSE推送服务"""
        if not self.is_running:
            logger.warning("SSE推送服务未在运行")
            return

        self.is_running = False

        # 停止任务
        if self.consumer_task:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                logger.info("Stream消费任务已取消")

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                logger.info("连接清理任务已取消")

        # Phase 6A: self-cleanup — remove our consumer from group on exit
        if self.consumer_name and self.consumer_group and self.input_stream:
            try:
                redis = self.redis_client or getattr(self.stream_manager, "redis", None) or getattr(self.stream_manager, "redis_client", None)
                if redis:
                    await redis.xgroup_delconsumer(self.input_stream, self.consumer_group, self.consumer_name)
                    logger.info("Self-cleanup: removed consumer %s from %s/%s", self.consumer_name, self.input_stream, self.consumer_group)
            except Exception as e:
                logger.debug("Self-cleanup skipped: %s", e)

        logger.info("SSE推送服务已停止")

    async def _ensure_consumer_group(self) -> None:
        """确保消费者组存在"""
        try:
            await self.stream_manager.create_consumer_group(
                self.input_stream,
                self.consumer_group
            )
            logger.info(f"消费者组 '{self.consumer_group}' 已创建或已存在")
        except Exception as e:
            # 消费者组可能已存在
            logger.debug(f"消费者组创建/检查: {e}")

    async def _stream_consumption_loop(self):
        """Stream消费循环"""
        while self.is_running:
            try:
                # 从Stream读取消息
                messages = await self.stream_manager.read_group(
                    stream=self.input_stream,
                    group=self.consumer_group,
                    consumer=self.consumer_name,
                    count=self.batch_size,
                    block_ms=int(self.polling_interval * 1000)
                )

                if messages:
                    # 处理消息批次
                    await self._process_message_batch(messages)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream消费循环发生错误: {e}")
                self.stats["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": str(e)
                })

                # 短暂等待后继续
                await asyncio.sleep(5)

    async def _process_message_batch(self, messages: List[Dict]) -> None:
        """处理消息批次"""
        for message in messages:
            message_id = message.get("id")
            message_data = message.get("data", {})

            try:
                # 处理单条消息
                success = await self._process_single_message(message_id, message_data)

                if success:
                    # 确认消息
                    await self.stream_manager.ack(
                        self.input_stream,
                        self.consumer_group,
                        message_id
                    )
                    self.stats["total_messages_consumed"] += 1
                else:
                    logger.warning(f"消息 {message_id}: 处理失败，跳过确认")

            except Exception as e:
                logger.error(f"处理消息 {message_id} 失败: {e}")
                self.stats["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": f"消息 {message_id}: {str(e)}"
                })

    async def _process_single_message(self, message_id: str, message_data: Dict) -> bool:
        """处理单条消息"""
        try:
            # 提取事件数据
            event_data = self._extract_event_data(message_data)
            if not event_data:
                logger.warning(f"消息 {message_id}: 无法提取事件数据")
                return False

            # 转换为SSE事件
            sse_event = self._create_sse_event(event_data)
            if not sse_event:
                logger.warning(f"消息 {message_id}: 无法创建SSE事件")
                return False

            # 广播到所有SSE客户端
            sent_count = await self.connection_manager.broadcast_sse_event(
                sse_event["event_type"],
                sse_event["data"]
            )

            if sent_count > 0:
                self.stats["sse_events_sent"] += sent_count
                logger.debug(f"消息 {message_id}: 已发送到 {sent_count} 个SSE客户端")
            else:
                logger.debug(f"消息 {message_id}: 没有活跃的SSE客户端")

            return True

        except Exception as e:
            logger.error(f"处理消息 {message_id} 时发生错误: {e}")
            return False

    def _extract_event_data(self, message_data: Dict) -> Optional[Dict]:
        """从Stream消息中提取事件数据"""
        # 支持多种消息格式
        if isinstance(message_data, dict):
            # 直接是事件数据
            if "item_id" in message_data or "event_type" in message_data:
                return message_data

            # 嵌套在payload/data中
            for key in ["payload", "data", "event_data"]:
                if key in message_data:
                    value = message_data[key]
                    if isinstance(value, dict):
                        return value
                    elif isinstance(value, str):
                        # 尝试解析JSON字符串
                        try:
                            data = json.loads(value)
                            return self._extract_event_data(data)
                        except json.JSONDecodeError:
                            pass

        # 尝试解析JSON字符串
        if isinstance(message_data, str):
            try:
                data = json.loads(message_data)
                return self._extract_event_data(data)
            except json.JSONDecodeError:
                pass

        return None

    def _create_sse_event(self, event_data: Dict) -> Optional[Dict]:
        """创建SSE事件"""
        try:
            # 确定事件类型
            event_type = event_data.get("event_type", "theme_move")

            # 构建SSE数据
            sse_data = {
                "event_id": event_data.get("item_id", f"event_{int(time.time())}"),
                "occurred_at": event_data.get("occurred_at", datetime.now().isoformat()),
                "event_type": event_type,
                "item": event_data
            }

            # 确保事件类型与前端兼容
            if event_type not in ["theme_move", "new_theme", "stock_move", "event"]:
                # 如果是不认识的事件类型，转换为通用事件
                sse_data["event_type"] = "event"
                sse_data["item"]["original_event_type"] = event_type

            return {
                "event_type": "intel_item",  # SSE事件类型
                "data": sse_data
            }

        except Exception as e:
            logger.error(f"创建SSE事件失败: {e}")
            return None

    async def _connection_cleanup_loop(self):
        """连接清理循环"""
        cleanup_interval = 60  # 每60秒清理一次

        while self.is_running:
            try:
                await asyncio.sleep(cleanup_interval)

                # 清理不活跃连接
                cleaned = self.connection_manager.cleanup_inactive_connections()
                if cleaned:
                    logger.info(f"清理了 {len(cleaned)} 个不活跃SSE连接")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"连接清理循环发生错误: {e}")

    async def create_sse_event_generator(self, client_info: Optional[Dict] = None) -> AsyncGenerator[str, None]:
        """创建SSE事件生成器

        每个SSE客户端调用此方法获取事件流。

        Args:
            client_info: 客户端信息字典

        Yields:
            SSE格式的事件字符串
        """
        client_id = f"sse_client_{uuid.uuid4().hex[:8]}"
        client_info = client_info or {}
        client_info.update({
            "client_id": client_id,
            "connected_at": datetime.now().isoformat(),
            "message_queue": asyncio.Queue(maxsize=100)
        })

        # 注册连接
        self.connection_manager.register_connection(client_id, client_info)
        self.stats["clients_served"] += 1

        logger.info(f"SSE客户端连接: {client_id}")

        try:
            # 发送连接确认
            connect_event = {
                "event_type": "connected",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat()
            }
            await client_info["message_queue"].put({
                "event_type": "heartbeat",
                "data": connect_event
            })

            # 心跳计数器
            heartbeat_counter = 0
            heartbeat_interval = self.heartbeat_interval

            while True:
                try:
                    # 等待消息或心跳超时
                    try:
                        event = await asyncio.wait_for(
                            client_info["message_queue"].get(),
                            timeout=heartbeat_interval
                        )
                    except asyncio.TimeoutError:
                        # 发送心跳
                        heartbeat_counter += 1
                        heartbeat_event = {
                            "event_type": "heartbeat",
                            "data": {
                                "status": "ok",
                                "counter": heartbeat_counter,
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        yield self._format_sse_event(heartbeat_event)
                        continue

                    # 发送事件
                    yield self._format_sse_event(event)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"SSE生成器错误 (client: {client_id}): {e}")
                    # 发送错误事件
                    error_event = {
                        "event_type": "error",
                        "data": {
                            "message": f"内部错误: {str(e)}",
                            "timestamp": datetime.now().isoformat()
                        }
                    }
                    yield self._format_sse_event(error_event)
                    # 短暂延迟后继续
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"SSE客户端断开连接: {client_id}")
        except Exception as e:
            logger.error(f"SSE生成器异常 (client: {client_id}): {e}")
        finally:
            # 注销连接
            self.connection_manager.unregister_connection(client_id)
            logger.info(f"SSE客户端断开: {client_id}")

    def _format_sse_event(self, event: Dict) -> str:
        """格式化SSE事件"""
        event_type = event.get("event_type", "message")
        data = event.get("data", {})

        # 转换为JSON字符串
        data_str = json.dumps(data, ensure_ascii=False)

        # SSE格式: event: <type>\ndata: <json>\n\n
        return f"event: {event_type}\ndata: {data_str}\n\n"

    async def get_service_stats(self) -> Dict:
        """获取服务统计信息"""
        stats = self.stats.copy()

        # 连接统计
        connection_stats = self.connection_manager.get_stats()
        stats.update(connection_stats)

        # 运行状态
        stats["is_running"] = self.is_running
        stats["input_stream"] = self.input_stream
        stats["consumer_group"] = self.consumer_group

        return stats

    def get_config(self) -> Dict:
        """获取当前配置"""
        return {
            "input_stream": self.input_stream,
            "consumer_group": self.consumer_group,
            "batch_size": self.batch_size,
            "polling_interval": self.polling_interval,
            "heartbeat_interval": self.heartbeat_interval,
            "is_running": self.is_running
        }


# FastAPI集成函数
async def create_sse_push_service(
    stream_manager=None,
    redis_client=None,
    redis_url: Optional[str] = None,
    config: Optional[Dict] = None
) -> SSEPushService:
    """创建并初始化SSE推送服务"""
    service = SSEPushService(
        stream_manager=stream_manager,
        redis_client=redis_client,
        redis_url=redis_url,
        config=config
    )
    await service.start()
    return service
