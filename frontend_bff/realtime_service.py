"""
Frontend BFF 实时推送服务集成

在现有frontend_bff中集成WebSocket实时推送功能。
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import WebSocket, WebSocketDisconnect

# 尝试导入Redis Stream实时推送服务
try:
    from database_service.streams.realtime_push_service import (
        RealtimePushService,
        ConnectionManager
    )
    REALTIME_SERVICE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"无法导入RealtimePushService: {e}")
    REALTIME_SERVICE_AVAILABLE = False
    # 创建存根类
    class RealtimePushService:
        def __init__(self, *args, **kwargs):
            pass
        async def initialize(self):
            pass
        async def shutdown(self):
            pass
        def get_connection_manager(self):
            return None
        def get_stats(self):
            return {"status": "not_available"}

    class ConnectionManager:
        def __init__(self):
            self.active_connections = {}
        async def connect(self, websocket, client_id):
            await websocket.accept()
        def disconnect(self, client_id):
            pass
        def subscribe(self, client_id, stream_name):
            return False
        def unsubscribe(self, client_id, stream_name):
            pass


logger = logging.getLogger(__name__)


class FrontendRealtimeService:
    """Frontend BFF 实时服务包装器"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or "redis://localhost:6379/0"
        self.push_service: Optional[RealtimePushService] = None
        self.initialized = False

    async def initialize(self):
        """初始化实时推送服务"""
        if not REALTIME_SERVICE_AVAILABLE:
            logger.warning("RealtimePushService不可用，实时推送功能将被禁用")
            return

        try:
            self.push_service = RealtimePushService(redis_url=self.redis_url)
            await self.push_service.initialize()
            self.initialized = True
            logger.info("FrontendRealtimeService初始化成功")
        except Exception as e:
            logger.error(f"FrontendRealtimeService初始化失败: {e}")
            self.push_service = None

    async def shutdown(self):
        """关闭实时推送服务"""
        if self.push_service and self.initialized:
            await self.push_service.shutdown()
            logger.info("FrontendRealtimeService已关闭")

    def is_available(self) -> bool:
        """检查实时推送服务是否可用"""
        return REALTIME_SERVICE_AVAILABLE and self.initialized and self.push_service is not None

    def get_connection_manager(self) -> Optional[ConnectionManager]:
        """获取连接管理器"""
        if self.push_service:
            return self.push_service.get_connection_manager()
        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        if self.push_service:
            return self.push_service.get_stats()
        return {"status": "not_initialized", "reason": "service_unavailable"}

    async def handle_websocket_connection(self, websocket: WebSocket):
        """处理WebSocket连接"""
        if not self.is_available():
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": "实时推送服务不可用",
                "timestamp": datetime.now().isoformat()
            })
            await websocket.close()
            return

        connection_manager = self.get_connection_manager()
        if not connection_manager:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "message": "连接管理器不可用",
                "timestamp": datetime.now().isoformat()
            })
            await websocket.close()
            return

        client_id = f"frontend-client-{uuid.uuid4().hex[:8]}"

        try:
            # 连接WebSocket
            await connection_manager.connect(websocket, client_id)

            # 发送连接成功消息
            await connection_manager.send_personal_message({
                "type": "connected",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat(),
                "available_streams": [
                    "stream:event:feed",
                    "stream:theme:feed",
                    "stream:news:feed",
                    "stream:stock:feed"
                ]
            }, client_id)

            logger.info(f"WebSocket客户端已连接: {client_id}")

            # 处理客户端消息
            while True:
                try:
                    data = await websocket.receive_json(timeout=30.0)
                    await self._handle_client_message(client_id, connection_manager, data)
                except asyncio.TimeoutError:
                    # 发送心跳
                    await connection_manager.send_personal_message({
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    }, client_id)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"处理客户端消息时出错: {e}")
                    await connection_manager.send_personal_message({
                        "type": "error",
                        "message": f"处理消息时出错: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }, client_id)

        except WebSocketDisconnect:
            logger.info(f"WebSocket客户端断开连接: {client_id}")
        except Exception as e:
            logger.error(f"WebSocket连接处理出错: {e}")
        finally:
            connection_manager.disconnect(client_id)

    async def _handle_client_message(self, client_id: str, connection_manager: ConnectionManager, data: Dict[str, Any]):
        """处理客户端消息"""
        command = data.get("command")

        if command == "subscribe":
            stream_name = data.get("stream")
            if not stream_name:
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": "订阅命令需要stream参数",
                    "timestamp": datetime.now().isoformat()
                }, client_id)
                return

            # 检查Stream是否支持
            supported_streams = ["stream:event:feed", "stream:theme:feed", "stream:news:feed", "stream:stock:feed"]
            if stream_name not in supported_streams:
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": f"不支持的Stream: {stream_name}",
                    "supported_streams": supported_streams,
                    "timestamp": datetime.now().isoformat()
                }, client_id)
                return

            success = connection_manager.subscribe(client_id, stream_name)
            if success:
                await connection_manager.send_personal_message({
                    "type": "subscription",
                    "status": "subscribed",
                    "stream": stream_name,
                    "timestamp": datetime.now().isoformat()
                }, client_id)
            else:
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": f"订阅失败: {stream_name}",
                    "timestamp": datetime.now().isoformat()
                }, client_id)

        elif command == "unsubscribe":
            stream_name = data.get("stream")
            if stream_name:
                connection_manager.unsubscribe(client_id, stream_name)
                await connection_manager.send_personal_message({
                    "type": "subscription",
                    "status": "unsubscribed",
                    "stream": stream_name,
                    "timestamp": datetime.now().isoformat()
                }, client_id)

        elif command == "list_subscriptions":
            subscriptions = []
            if hasattr(connection_manager, 'connection_subscriptions'):
                subs = connection_manager.connection_subscriptions.get(client_id, set())
                subscriptions = list(subs)

            await connection_manager.send_personal_message({
                "type": "subscription_list",
                "subscriptions": subscriptions,
                "timestamp": datetime.now().isoformat()
            }, client_id)

        elif command == "ping":
            await connection_manager.send_personal_message({
                "type": "pong",
                "timestamp": datetime.now().isoformat()
            }, client_id)

        elif command == "get_stats":
            stats = self.get_stats()
            await connection_manager.send_personal_message({
                "type": "service_stats",
                "stats": stats,
                "timestamp": datetime.now().isoformat()
            }, client_id)

        else:
            await connection_manager.send_personal_message({
                "type": "error",
                "message": f"未知命令: {command}",
                "timestamp": datetime.now().isoformat()
            }, client_id)


# 全局实例
realtime_service = FrontendRealtimeService()