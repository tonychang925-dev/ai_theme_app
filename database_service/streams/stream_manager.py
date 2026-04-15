"""
Redis Stream管理器 - 重试增强版
在原有基础上添加完整的重试机制
"""
import json
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import redis.asyncio as redis
import redis.exceptions

# 尝试导入重试管理器
try:
    from database_service.streams.utils.retry_manager import RetryManager, with_retry, RetryStrategy
    RETRY_MANAGER_AVAILABLE = True
except ImportError as e:
    RETRY_MANAGER_AVAILABLE = False
    logging.getLogger(__name__).warning(f"重试管理器未找到: {e}")

# 正确设置日志
logger = logging.getLogger(__name__)

# 尝试导入redis.asyncio作为aioredis的替代
try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis

    logger.info("✅ 使用 redis.asyncio 作为 aioredis 替代")
except ImportError as e:
    logger.error(f"❌ 无法导入redis.asyncio: {e}")
    raise

# 尝试导入错误处理器
try:
    from .utils.error_handler import StreamErrorHandler, ErrorCategory
    ERROR_HANDLER_AVAILABLE = True
except ImportError as e:
    ERROR_HANDLER_AVAILABLE = False
    logger.warning(f"错误处理器未找到: {e}")

# 尝试导入消费者组管理器
try:
    from .utils.consumer_group_manager import ConsumerGroupManager, create_consumer_group_manager
    CONSUMER_GROUP_MANAGER_AVAILABLE = True
except ImportError as e:
    CONSUMER_GROUP_MANAGER_AVAILABLE = False
    logger.warning(f"消费者组管理器未找到: {e}")

# 尝试导入告警服务
try:
    from .utils.alert_service import (AlertService, ConsoleAlertService, AlertManager,
                                     AlertType, AlertSeverity, AlertContext, Alert)
    ALERT_SERVICE_AVAILABLE = True
except ImportError as e:
    ALERT_SERVICE_AVAILABLE = False
    AlertService = ConsoleAlertService = AlertManager = None
    AlertType = AlertSeverity = AlertContext = Alert = None
    logger.warning(f"告警服务未找到: {e}")

# 尝试导入Stream配置
try:
    from .stream_config import StreamDefinition, RedisStreamConfig, get_stream_config
    STREAM_CONFIG_AVAILABLE = True
except ImportError as e:
    STREAM_CONFIG_AVAILABLE = False
    logger.warning(f"Stream配置未找到: {e}")

@dataclass
class StreamMessage:
    """Stream消息数据类"""
    id: str
    stream: str
    data: Dict[str, Any]
    timestamp: datetime
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {
                "attempts": 0,
                "status": "pending",
                "created_at": datetime.now().isoformat()
            }


class RedisWrapper:
    """Redis包装器，提供统一的接口和重试支持"""
    
    def __init__(self, redis_client, enable_retry: bool = True):
        self._client = redis_client
        self.enable_retry = enable_retry and RETRY_MANAGER_AVAILABLE
        self._retry_manager = None
        self._operation_stats = {
            "total_operations": 0,
            "operations_with_retries": 0,
            "successful_retries": 0,
            "failed_retries": 0
        }
        
        if self.enable_retry:
            self._retry_manager = RetryManager(
                max_retries=3,
                base_delay=0.5,
                strategy=RetryStrategy.EXPONENTIAL,
                jitter=True,
                stop_on_exception=[redis.exceptions.ResponseError]  # 不重试 ResponseError
            )
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """带重试执行Redis操作"""
        self._operation_stats["total_operations"] += 1
        
        if not self.enable_retry or not self._retry_manager:
            return await func(*args, **kwargs)
        
        try:
            result = await self._retry_manager.execute_with_retry(
                func, *args, **kwargs,
                context={"operation": func.__name__}
            )
            
            if self._retry_manager.stats["total_retries"] > 0:
                self._operation_stats["operations_with_retries"] += 1
                self._operation_stats["successful_retries"] += 1
            
            return result
            
        except Exception as e:
            logger.debug(f"Redis操作重试失败: {e}")
            raise
    
    async def xadd(self, stream, mapping, **kwargs):
        return await self.execute_with_retry(
            self._client.xadd, stream, mapping, **kwargs
        )
    
    async def xreadgroup(self, groupname, consumername, streams, count=None, block=None, **kwargs):
        return await self.execute_with_retry(
            self._client.xreadgroup,
            groupname=groupname,
            consumername=consumername,
            streams=streams,
            count=count,
            block=block,
            **kwargs
        )
    
    async def xack(self, stream, group, message_id, **kwargs):
        return await self.execute_with_retry(
            self._client.xack, stream, group, message_id, **kwargs
        )
    
    async def xgroup_create(self, stream, group, id="0", mkstream=True, **kwargs):
        return await self.execute_with_retry(
            self._client.xgroup_create,
            stream, group, id=id, mkstream=mkstream, **kwargs
        )
    
    async def xinfo_stream(self, stream):
        return await self.execute_with_retry(
            self._client.xinfo_stream, stream
        )
    
    async def xlen(self, stream):
        return await self.execute_with_retry(
            self._client.xlen, stream
        )

    async def keys(self, pattern="*"):
        return await self.execute_with_retry(
            self._client.keys, pattern
        )

    async def type(self, key):
        return await self.execute_with_retry(
            self._client.type, key
        )

    async def xinfo_groups(self, stream):
        return await self.execute_with_retry(
            self._client.xinfo_groups, stream
        )

    async def xtrim(self, stream, **kwargs):
        return await self.execute_with_retry(
            self._client.xtrim, stream, **kwargs
        )

    async def xautoclaim(self, stream, groupname, consumername, min_idle_time, start_id, count=None, **kwargs):
        return await self.execute_with_retry(
            self._client.xautoclaim,
            stream,
            groupname,
            consumername,
            min_idle_time,
            start_id,
            count=count,
            **kwargs
        )

    async def xrange(self, *args, **kwargs):
        return await self.execute_with_retry(
            self._client.xrange, *args, **kwargs
        )

    async def xrevrange(self, *args, **kwargs):
        return await self.execute_with_retry(
            self._client.xrevrange, *args, **kwargs
        )

    async def xdel(self, stream, *ids):
        return await self.execute_with_retry(
            self._client.xdel, stream, *ids
        )

    async def delete(self, *keys):
        return await self.execute_with_retry(
            self._client.delete, *keys
        )

    async def close(self):
        await self._client.aclose()
    
    def pipeline(self):
        return self._client.pipeline()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取操作统计"""
        stats = self._operation_stats.copy()
        
        if self._retry_manager:
            retry_stats = self._retry_manager.get_stats()
            stats.update({
                "retry_stats": retry_stats,
                "retry_enabled": True,
                "retry_manager_available": True
            })
        else:
            stats.update({
                "retry_enabled": False,
                "retry_manager_available": RETRY_MANAGER_AVAILABLE
            })
        
        return stats
    
    @classmethod
    async def from_url(cls, url, enable_retry: bool = True, **kwargs):
        # 确保使用decode_responses=True
        if 'decode_responses' not in kwargs:
            kwargs['decode_responses'] = True
        client = await Redis.from_url(url, **kwargs)
        return cls(client, enable_retry)


class RetryEnhancedRedisStreamManager:
    """重试增强的Redis Stream管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 enable_retry: bool = True,
                 retry_config: Optional[Dict[str, Any]] = None):
        self.redis_url = redis_url
        self.redis = None
        self.connected = False
        self.enable_retry = enable_retry
        self.retry_config = retry_config or {}
        # 全局默认发布截断长度（0/None表示不启用全局默认）
        self.default_publish_max_len = int(self.retry_config.get("default_publish_max_len", 0) or 0)
        
        # 操作统计
        self.stats = {
            'publish_operations': 0,
            'publish_success': 0,
            'publish_failed': 0,
            'consume_operations': 0,
            'consume_success': 0,
            'consume_failed': 0,
            'ack_operations': 0,
            'ack_success': 0,
            'ack_failed': 0
        }
        
        # 重试管理器
        self._retry_manager = None
        if self.enable_retry and RETRY_MANAGER_AVAILABLE:
            # 过滤掉RetryManager不支持的参数
            valid_retry_params = {
                'max_retries', 'base_delay', 'strategy', 'max_delay',
                'jitter', 'retry_on_exception', 'stop_on_exception'
            }
            filtered_retry_config = {
                k: v for k, v in self.retry_config.items()
                if k in valid_retry_params
            }
            self._retry_manager = RetryManager(**filtered_retry_config)
        
        logger.info(f"初始化重试增强的RedisStreamManager: {redis_url}")
        logger.info(f"重试功能: {'启用' if self.enable_retry else '禁用'}")

        # 错误处理器
        self.error_handler = None
        if ERROR_HANDLER_AVAILABLE:
            try:
                # 初始化错误处理器
                self.error_handler = StreamErrorHandler(
                    redis_client=None,  # 连接后再设置
                    config=self.retry_config.get("error_handler", {})
                )
                logger.info("✅ 错误处理器初始化完成")
            except Exception as e:
                logger.warning(f"错误处理器初始化失败: {e}")
        else:
            logger.info("ℹ️ 错误处理器不可用")

        # 消费者组管理器
        self.consumer_group_manager = None
        if CONSUMER_GROUP_MANAGER_AVAILABLE:
            try:
                # 初始化消费者组管理器
                self.consumer_group_manager = ConsumerGroupManager(
                    redis_client=None,  # 连接后再设置
                    config=self.retry_config.get("consumer_group_manager", {})
                )
                logger.info("✅ 消费者组管理器初始化完成")
            except Exception as e:
                logger.warning(f"消费者组管理器初始化失败: {e}")
        else:
            logger.info("ℹ️ 消费者组管理器不可用")

        # 告警管理器
        self.alert_manager = None
        if ALERT_SERVICE_AVAILABLE:
            try:
                # 初始化默认告警管理器（控制台告警）
                console_service = ConsoleAlertService(name="console", enabled=True)
                self.alert_manager = AlertManager([console_service])
                logger.info("✅ 告警管理器初始化完成")
            except Exception as e:
                logger.warning(f"告警管理器初始化失败: {e}")
        else:
            logger.info("ℹ️ 告警服务不可用")

    def _resolve_publish_max_len(self, stream: str, max_len: Optional[int]) -> Optional[int]:
        """解析发布时使用的MAXLEN策略（显式参数优先，其次按Stream配置，最后全局默认）。"""
        if max_len is not None:
            return max_len

        stream_def = self._get_stream_definition(stream)
        if stream_def and getattr(stream_def, "auto_trim", True):
            stream_max_len = getattr(stream_def, "max_length", None)
            if isinstance(stream_max_len, int) and stream_max_len > 0:
                return stream_max_len

        if self.default_publish_max_len > 0:
            return self.default_publish_max_len

        return None

    async def connect(self) -> bool:
        """连接Redis（带重试）"""
        if self.connected:
            return True
        
        async def _connect():
            try:
                self.redis = await RedisWrapper.from_url(
                    self.redis_url,
                    enable_retry=self.enable_retry,
                    decode_responses=True,
                    max_connections=10
                )
                self.connected = True
                logger.info(f"✅ Redis连接成功: {self.redis_url}")

                # 设置错误处理器的Redis客户端
                if self.error_handler:
                    self.error_handler.redis = self.redis.redis if hasattr(self.redis, 'redis') else self.redis
                    logger.debug("✅ 错误处理器Redis客户端已设置")

                # 设置消费者组管理器的Redis客户端
                if self.consumer_group_manager:
                    self.consumer_group_manager.redis = self.redis.redis if hasattr(self.redis, 'redis') else self.redis
                    logger.debug("✅ 消费者组管理器Redis客户端已设置")

                return True
            except Exception as e:
                logger.error(f"❌ Redis连接失败: {e}")
                self.connected = False
                raise
        
        if self.enable_retry and self._retry_manager:
            try:
                result = await self._retry_manager.execute_with_retry(
                    _connect,
                    context={"operation": "connect_redis", "url": self.redis_url}
                )
                return result
            except Exception as e:
                logger.error(f"带重试的Redis连接失败: {e}")
                return False
        else:
            return await _connect()
    
    async def ensure_stream(self, stream_name: str, max_len: Optional[int] = None) -> bool:
        """确保 Stream 存在（简单有效版）"""
        try:
            # 尝试获取Stream信息
            try:
                info = await self.redis.xinfo_stream(stream_name)
                logger.debug(f"✅ Stream已存在: {stream_name} (长度: {info.get('length', 0)})")
                return True
            except redis.exceptions.ResponseError as e:
                if "no such key" in str(e).lower():
                    # Stream不存在，但这是OK的
                    # Redis Stream 会在第一次 xadd 时自动创建
                    logger.info(f"📋 Stream不存在: {stream_name}，将在首次发布时创建")
                    return True  # 返回True，让调用方继续
                else:
                    # 使用错误处理器处理异常
                    if self.error_handler:
                        error_context = {
                            "operation": "ensure_stream_response_error",
                            "stream_name": stream_name,
                            "error_type": "ResponseError",
                            "error_message": str(e)
                        }

                        try:
                            error_result = await self.error_handler.handle_error(e, error_context)
                            logger.error(f"❌ 检查Stream失败（已通过错误处理器处理）: {stream_name} - {e}")
                        except Exception as handling_error:
                            logger.error(f"错误处理失败: {handling_error}")

                    logger.error(f"❌ 检查Stream失败: {stream_name} - {e}")
                    return False
            except Exception as e:
                # 使用错误处理器处理异常
                if self.error_handler:
                    error_context = {
                        "operation": "ensure_stream_inner_error",
                        "stream_name": stream_name,
                        "error_type": type(e).__name__
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"❌ 检查Stream异常（已通过错误处理器处理）: {stream_name} - {e}")
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                logger.error(f"❌ 检查Stream异常: {stream_name} - {e}")
                return False
                
        except Exception as e:
            # 使用错误处理器处理异常
            if self.error_handler:
                error_context = {
                    "operation": "ensure_stream",
                    "stream_name": stream_name,
                    "max_len": max_len
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"❌ 确保Stream存在失败（已通过错误处理器处理）: {stream_name} - {e}")
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"❌ 确保Stream存在失败: {stream_name} - {e}")
            return False
    
    async def publish(self, stream: str, data: Dict, 
                     max_len: Optional[int] = None,
                     enable_retry: Optional[bool] = None) -> str:
        """发布消息到Stream（带重试）"""
        self.stats['publish_operations'] += 1
        
        if enable_retry is None:
            enable_retry = self.enable_retry
        
        await self.connect()
        
        message_data = {
            "payload": json.dumps(data, ensure_ascii=False),
            "published_at": datetime.now().isoformat(),
            "source": "database_service",
            "stream": stream
        }
        
        effective_max_len = self._resolve_publish_max_len(stream, max_len)

        async def _publish():
            try:
                if effective_max_len:
                    message_id = await self.redis.xadd(stream, message_data, maxlen=effective_max_len, approximate=True)
                else:
                    message_id = await self.redis.xadd(stream, message_data)
                
                logger.info(f"发布消息成功: {stream} -> {message_id}")
                self.stats['publish_success'] += 1
                return message_id
            except Exception as e:
                self.stats['publish_failed'] += 1

                # 使用错误处理器处理异常
                if self.error_handler:
                    error_context = {
                        "operation": "publish_message",
                        "stream": stream,
                        "data_keys": list(data.keys()) if data else [],
                        "enable_retry": enable_retry,
                        "max_len": effective_max_len
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"发布消息失败（已通过错误处理器处理）: {e}")

                        # 如果错误处理器标记为已恢复，可以返回特殊标识
                        if error_result.get("recovered", False):
                            logger.info(f"错误已恢复，恢复动作: {error_result.get('action')}")
                            # 这里可以返回一个特殊标识，表示错误已处理但消息未发送
                            return f"error_handled:{error_result.get('action')}:{datetime.now().timestamp()}"
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                # 记录原始错误日志
                logger.error(f"发布消息失败: {e}")
                raise
        
        if enable_retry and self._retry_manager:
            try:
                message_id = await self._retry_manager.execute_with_retry(
                    _publish,
                    context={
                        "operation": "publish_message",
                        "stream": stream,
                        "data_keys": list(data.keys()) if data else [],
                        "max_len": effective_max_len
                    }
                )
                return message_id
            except Exception as e:
                logger.error(f"带重试的发布失败: {e}")
                raise
        else:
            return await _publish()
    
    async def publish_batch(self, stream: str, messages: List[Dict],
                          max_len: Optional[int] = None,
                          batch_size: int = 10) -> List[str]:
        """批量发布消息（带重试）"""
        await self.connect()
        effective_max_len = self._resolve_publish_max_len(stream, max_len)
        
        message_ids = []
        
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            
            try:
                # 为每个批次创建管道
                pipe = self.redis.pipeline()
                
                for message in batch:
                    message_data = {
                        "payload": json.dumps(message, ensure_ascii=False),
                        "published_at": datetime.now().isoformat(),
                        "source": "database_service",
                        "batch_index": i
                    }
                    
                    if effective_max_len:
                        pipe.xadd(stream, message_data, maxlen=effective_max_len, approximate=True)
                    else:
                        pipe.xadd(stream, message_data)
                
                # 执行批量发布
                batch_ids = await pipe.execute()
                message_ids.extend(batch_ids)
                
                logger.info(f"批量发布成功: {len(batch)} 条消息到 {stream}")
                
            except Exception as e:
                # 使用错误处理器处理批量发布异常
                if self.error_handler:
                    error_context = {
                        "operation": "publish_batch_messages",
                        "stream": stream,
                        "batch_index": i,
                        "batch_size": len(batch),
                        "total_messages": len(messages),
                        "max_len": effective_max_len
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"批量发布失败（已通过错误处理器处理）: {e}")

                        # 如果错误处理器标记为已恢复，可以继续处理下一个批次
                        if error_result.get("recovered", False):
                            logger.info(f"错误已恢复，恢复动作: {error_result.get('action')}")
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                logger.error(f"批量发布失败: {e}")
                # 继续处理下一个批次
        
        return message_ids
    
    async def consume(self, group: str, consumer: str, stream: str,
                     count: int = 10, block_ms: int = 5000,
                     enable_retry: Optional[bool] = None) -> List[StreamMessage]:
        """消费消息（带重试）"""
        self.stats['consume_operations'] += 1
        
        if enable_retry is None:
            enable_retry = self.enable_retry
        
        await self.connect()
        
        async def _consume():
            try:
                result = await self.redis.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream: ">"},
                    count=count,
                    block=block_ms
                )
                
                if not result:
                    logger.debug(f"没有消息可消费: {stream}/{group}")
                    self.stats['consume_success'] += 1
                    return []
                
                messages = []
                for stream_name, stream_messages in result:
                    for msg_id, msg_data in stream_messages:
                        try:
                            # 简化版：由于Redis配置了decode_responses=True，直接获取字符串
                            payload = msg_data.get("payload", "{}")
                            data = json.loads(payload)

                            # 处理时间戳
                            published_at = msg_data.get("published_at")
                            timestamp = datetime.fromisoformat(published_at) if published_at else datetime.now()
                            
                            # 提取元数据（简化版）
                            attempts_value = msg_data.get("attempts", 0)
                            attempts = int(attempts_value) if attempts_value and str(attempts_value).isdigit() else 0
                            metadata = {
                                "group": group,
                                "consumer": consumer,
                                "attempts": attempts,
                                "status": msg_data.get("status", "pending")
                            }
                            
                            messages.append(StreamMessage(
                                id=msg_id,
                                stream=stream_name,
                                data=data,
                                timestamp=timestamp,
                                metadata=metadata
                            ))
                        except Exception as e:
                            # 使用错误处理器处理消息解析异常
                            if self.error_handler:
                                error_context = {
                                    "operation": "parse_message",
                                    "stream": stream_name,
                                    "group": group,
                                    "consumer": consumer,
                                    "message_id": msg_id,
                                    "message_data_keys": list(msg_data.keys()) if msg_data else []
                                }

                                try:
                                    error_result = await self.error_handler.handle_error(e, error_context)
                                    logger.error(f"解析消息失败（已通过错误处理器处理）: {e}")

                                    # 如果启用了死信队列，可以发送消息到死信队列
                                    if error_result.get("action") == "sent_to_dead_letter":
                                        try:
                                            await self.error_handler.send_to_dead_letter(
                                                stream=stream_name,
                                                message_id=msg_id,
                                                error=e,
                                                context=error_context
                                            )
                                        except Exception as dl_error:
                                            logger.error(f"发送到死信队列失败: {dl_error}")
                                except Exception as handling_error:
                                    logger.error(f"错误处理失败: {handling_error}")
                            else:
                                logger.error(f"解析消息失败: {e}")
                            continue
                
                logger.info(f"消费消息成功: {len(messages)} 条 from {stream}/{group}")
                self.stats['consume_success'] += 1
                return messages
                
            except Exception as e:
                self.stats['consume_failed'] += 1

                # 使用错误处理器处理异常
                if self.error_handler:
                    error_context = {
                        "operation": "consume_messages",
                        "stream": stream,
                        "group": group,
                        "consumer": consumer,
                        "count": count,
                        "block_ms": block_ms,
                        "enable_retry": enable_retry
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"消费消息失败（已通过错误处理器处理）: {e}")

                        # 如果错误处理器标记为已恢复，可以返回空列表
                        if error_result.get("recovered", False):
                            logger.info(f"错误已恢复，恢复动作: {error_result.get('action')}")
                            return []
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                # 记录原始错误日志
                logger.error(f"消费消息失败: {e}")
                raise
        
        if enable_retry and self._retry_manager:
            try:
                messages = await self._retry_manager.execute_with_retry(
                    _consume,
                    context={
                        "operation": "consume_messages",
                        "stream": stream,
                        "group": group,
                        "consumer": consumer
                    }
                )
                return messages
            except Exception as e:
                logger.error(f"带重试的消费失败: {e}")
                return []
        else:
            return await _consume()
    
    async def ack(self, stream: str, group: str, message_id: str,
                 enable_retry: Optional[bool] = None) -> int:
        """确认消息处理完成（带重试）"""
        self.stats['ack_operations'] += 1
        
        if enable_retry is None:
            enable_retry = self.enable_retry
        
        await self.connect()
        
        async def _ack():
            try:
                result = await self.redis.xack(stream, group, message_id)
                logger.debug(f"确认消息成功: {stream}/{group}/{message_id}")
                self.stats['ack_success'] += 1
                return result
            except Exception as e:
                self.stats['ack_failed'] += 1

                # 使用错误处理器处理异常
                if self.error_handler:
                    error_context = {
                        "operation": "ack_message",
                        "stream": stream,
                        "group": group,
                        "message_id": message_id
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"确认消息失败（已通过错误处理器处理）: {e}")

                        # 如果错误处理器标记为已恢复，可以返回0（表示确认失败）
                        if error_result.get("recovered", False):
                            logger.info(f"错误已恢复，恢复动作: {error_result.get('action')}")
                            return 0
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                # 记录原始错误日志并重新抛出
                logger.error(f"确认消息失败: {e}")
                raise
        
        if enable_retry and self._retry_manager:
            try:
                result = await self._retry_manager.execute_with_retry(
                    _ack,
                    context={
                        "operation": "ack_message",
                        "stream": stream,
                        "group": group,
                        "message_id": message_id
                    }
                )
                return result
            except Exception as e:
                # 使用错误处理器处理重试失败
                if self.error_handler:
                    error_context = {
                        "operation": "ack_message_with_retry",
                        "stream": stream,
                        "group": group,
                        "message_id": message_id,
                        "retry_enabled": True
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"带重试的确认失败（已通过错误处理器处理）: {e}")
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                logger.error(f"带重试的确认失败: {e}")
                return 0
        else:
            return await _ack()
    
    async def batch_ack(self, stream: str, group: str, message_ids: List[str]) -> List[int]:
        """批量确认消息（带重试）"""
        await self.connect()
        
        try:
            pipe = self.redis.pipeline()
            for msg_id in message_ids:
                pipe.xack(stream, group, msg_id)
            results = await pipe.execute()
            logger.info(f"批量确认成功: {len(message_ids)} 条")
            return results
        except Exception as e:
            # 使用错误处理器处理批量确认异常
            if self.error_handler:
                error_context = {
                    "operation": "batch_ack_messages",
                    "stream": stream,
                    "group": group,
                    "message_ids_count": len(message_ids),
                    "message_ids_sample": message_ids[:5] if message_ids else []
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"批量确认失败（已通过错误处理器处理）: {e}")

                    # 如果错误处理器标记为已恢复，可以继续尝试单个确认
                    if error_result.get("recovered", False):
                        logger.info(f"错误已恢复，恢复动作: {error_result.get('action')}")
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"批量确认失败: {e}")

            # 尝试单个确认
            results = []
            for msg_id in message_ids:
                try:
                    result = await self.ack(stream, group, msg_id, enable_retry=False)
                    results.append(result)
                except Exception as ack_error:
                    # 记录单个确认失败
                    if self.error_handler:
                        ack_context = {
                            "operation": "single_ack_in_batch",
                            "stream": stream,
                            "group": group,
                            "message_id": msg_id,
                            "batch_size": len(message_ids)
                        }
                        try:
                            await self.error_handler.handle_error(ack_error, ack_context)
                        except:
                            pass
                    results.append(0)
            return results

    async def read_group(self, stream: str, group: str, consumer: str, count: int = 10, block_ms: int = 5000):
        """
        从消费者组读取消息

        Args:
            stream: Stream名称
            group: 消费者组名称
            consumer: 消费者名称
            count: 读取数量
            block_ms: 阻塞时间（毫秒）

        Returns:
            消息列表
        """
        await self.connect()

        # 使用redis.xreadgroup读取消息
        result = await self.redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms
        )

        if not result:
            return []

        # 转换结果为标准格式
        messages = []
        for stream_name, stream_messages in result:
            for msg_id, msg_data in stream_messages:
                messages.append({
                    "id": msg_id,
                    "stream": stream_name,
                    "data": msg_data
                })

        return messages

    async def create_consumer_group(self, stream: str, group: str,
                                   mkstream: bool = True,
                                   is_test_group: bool = False) -> bool:
        """创建消费者组（带重试）- 优先使用消费者组管理器"""
        await self.connect()

        # 🔥 优先使用消费者组管理器（如果可用）
        if self.consumer_group_manager and CONSUMER_GROUP_MANAGER_AVAILABLE:
            try:
                result = await self.consumer_group_manager.ensure_consumer_group(
                    stream, group, mkstream=mkstream, is_test_group=is_test_group
                )
                if result:
                    logger.info(f"✅ 通过消费者组管理器创建成功: {stream}/{group}")
                return result
            except Exception as e:
                logger.warning(f"消费者组管理器创建失败，回退到标准方法: {e}")
                # 回退到标准方法

        # 标准创建方法（保留原有重试和错误处理）
        async def _create_group():
            try:
                result = await self.redis.xgroup_create(stream, group, id="0", mkstream=mkstream)
                logger.info(f"创建消费者组成功: {stream}/{group}")
                return True
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"消费者组已存在: {stream}/{group}")
                    return True

                # 使用错误处理器处理异常
                if self.error_handler:
                    error_context = {
                        "operation": "create_consumer_group",
                        "stream": stream,
                        "group": group,
                        "mkstream": mkstream,
                        "is_test_group": is_test_group
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"创建消费者组失败（已通过错误处理器处理）: {e}")

                        # 如果错误处理器标记为已恢复，可以返回False
                        if error_result.get("recovered", False):
                            logger.info(f"错误已恢复，恢复动作: {error_result.get('action')}")
                            return False
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                logger.error(f"创建消费者组失败: {e}")
                raise

        if self.enable_retry and self._retry_manager:
            try:
                result = await self._retry_manager.execute_with_retry(
                    _create_group,
                    context={
                        "operation": "create_consumer_group",
                        "stream": stream,
                        "group": group,
                        "is_test_group": is_test_group
                    }
                )
                return result
            except Exception as e:
                # 使用错误处理器处理重试失败
                if self.error_handler:
                    error_context = {
                        "operation": "create_consumer_group_with_retry",
                        "stream": stream,
                        "group": group,
                        "mkstream": mkstream,
                        "is_test_group": is_test_group,
                        "retry_enabled": True
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"带重试的创建消费者组失败（已通过错误处理器处理）: {e}")
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                logger.error(f"带重试的创建消费者组失败: {e}")
                return False
        else:
            return await _create_group()
    
    async def get_stream_info(self, stream: str) -> Dict[str, Any]:
        """获取Stream信息"""
        await self.connect()
        
        try:
            info = await self.redis.xinfo_stream(stream)
            length = await self.redis.xlen(stream)
            
            return {
                "stream": stream,
                "length": length,
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "groups": info.get("groups", 0)
            }
        except Exception as e:
            # 使用错误处理器处理异常
            if self.error_handler:
                error_context = {
                    "operation": "get_stream_info",
                    "stream": stream
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"获取Stream信息失败（已通过错误处理器处理）: {e}")
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            if "no such key" in str(e).lower():
                return {
                    "stream": stream,
                    "length": 0,
                    "error": "Stream does not exist"
                }
            else:
                return {
                    "stream": stream,
                    "length": 0,
                    "error": str(e)
                }
    
    async def get_all_streams_info(self, pattern: str = "*") -> Dict[str, Any]:
        """获取所有Stream信息"""
        await self.connect()
        
        try:
            # 使用redis-py的keys命令获取所有stream
            keys = await self.redis._client.keys(pattern)
            streams = []
            for key in keys:
                try:
                    key_type = await self.redis.type(key)
                    if isinstance(key_type, bytes):
                        key_type = key_type.decode("utf-8", errors="ignore")
                    if str(key_type).lower() == "stream":
                        streams.append(key)
                except Exception as type_err:
                    logger.debug(f"获取key类型失败，已跳过 {key}: {type_err}")

            result = {}
            for stream in streams:
                # stream应为字符串（decode_responses=True）
                info = await self.get_stream_info(stream)
                result[stream] = info
            
            return result
        except Exception as e:
            # 使用错误处理器处理异常
            if self.error_handler:
                error_context = {
                    "operation": "get_all_streams_info",
                    "pattern": pattern
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"获取所有Stream信息失败（已通过错误处理器处理）: {e}")
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"获取所有Stream信息失败: {e}")
            return {}
    
    async def close(self):
        """关闭连接"""
        if self.redis and self.connected:
            try:
                await self.redis.close()
                self.connected = False
                logger.info("Redis连接已关闭")
            except Exception as e:
                # 使用错误处理器处理异常
                if self.error_handler:
                    error_context = {
                        "operation": "close_connection"
                    }

                    try:
                        error_result = await self.error_handler.handle_error(e, error_context)
                        logger.error(f"关闭连接失败（已通过错误处理器处理）: {e}")
                    except Exception as handling_error:
                        logger.error(f"错误处理失败: {handling_error}")

                logger.error(f"关闭连接失败: {e}")

    async def cleanup_consumer_groups(self, pattern: Optional[str] = None,
                                    max_age_hours: Optional[int] = None) -> Dict[str, Any]:
        """
        清理旧的消费者组（特别是测试创建的组）

        Args:
            pattern: 匹配模式，如 "theme_processors_real_*"
            max_age_hours: 最大年龄（小时）

        Returns:
            清理结果统计
        """
        await self.connect()

        if not self.consumer_group_manager:
            logger.warning("消费者组管理器不可用，无法清理消费者组")
            return {
                "success": False,
                "error": "consumer_group_manager_not_available",
                "message": "消费者组管理器未初始化"
            }

        try:
            result = await self.consumer_group_manager.cleanup_old_groups(
                pattern=pattern,
                max_age_hours=max_age_hours
            )
            logger.info(f"消费者组清理完成: {result}")
            cleanup_result = result if isinstance(result, dict) else {}
            return {
                "success": True,
                "cleanup_result": cleanup_result,
                "cleaned_groups": cleanup_result.get("groups_cleaned", 0),
                "protected_groups": cleanup_result.get("groups_protected", 0),
                "failed_groups": cleanup_result.get("errors", 0),
                "total_groups_found": cleanup_result.get("total_groups_found", 0),
            }
        except Exception as e:
            # 使用错误处理器处理异常
            if self.error_handler:
                error_context = {
                    "operation": "cleanup_consumer_groups",
                    "pattern": pattern,
                    "max_age_hours": max_age_hours
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"清理消费者组失败（已通过错误处理器处理）: {e}")

                    return {
                        "success": False,
                        "error": str(e),
                        "error_handled": True,
                        "error_handler_result": error_result
                    }
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"清理消费者组失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def reclaim_stale_pending(
        self,
        stream_pattern: str = "stream:*",
        min_idle_ms: int = 300000,
        count: int = 50,
        max_messages_per_group: int = 200,
        maintenance_consumer: str = "pending_reclaimer",
        requeue: bool = True,
    ) -> Dict[str, Any]:
        """
        回收长期pending消息（XAUTOCLAIM），可选重投递回主Stream以恢复处理链路。

        注意:
        - requeue=True 会为同一消息生成新的Stream ID。
        - 下游消费者需要保持幂等处理能力。
        """
        await self.connect()

        result = {
            "success": True,
            "streams_scanned": 0,
            "groups_scanned": 0,
            "groups_with_pending": 0,
            "claimed_messages": 0,
            "requeued_messages": 0,
            "acked_messages": 0,
            "errors": [],
        }

        try:
            streams = await self.redis.keys(stream_pattern)
            result["streams_scanned"] = len(streams)

            for stream in streams:
                try:
                    groups_info = await self.redis.xinfo_groups(stream)
                except Exception as e:
                    result["errors"].append(f"{stream}: xinfo_groups_failed: {e}")
                    continue

                for group_info in groups_info:
                    result["groups_scanned"] += 1
                    group_name = group_info.get("name")
                    pending = int(group_info.get("pending", 0) or 0)
                    if pending <= 0:
                        continue

                    result["groups_with_pending"] += 1
                    group_claimed = 0
                    start_id = "0-0"

                    while group_claimed < max_messages_per_group:
                        batch_count = min(count, max_messages_per_group - group_claimed)
                        if batch_count <= 0:
                            break

                        try:
                            claim_res = await self.redis.xautoclaim(
                                stream,
                                group_name,
                                maintenance_consumer,
                                min_idle_ms,
                                start_id,
                                count=batch_count,
                            )
                        except Exception as e:
                            result["errors"].append(f"{stream}/{group_name}: xautoclaim_failed: {e}")
                            break

                        next_start = start_id
                        claimed_entries = []
                        if isinstance(claim_res, (list, tuple)):
                            if len(claim_res) >= 1:
                                next_start = claim_res[0] or start_id
                            if len(claim_res) >= 2 and claim_res[1]:
                                claimed_entries = claim_res[1]

                        if not claimed_entries:
                            break

                        for entry in claimed_entries:
                            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                                continue
                            msg_id, msg_data = entry[0], entry[1]
                            result["claimed_messages"] += 1
                            group_claimed += 1

                            if requeue and isinstance(msg_data, dict):
                                try:
                                    requeue_data = dict(msg_data)
                                    requeue_data["reclaimed_from_pending"] = "1"
                                    requeue_data["reclaimed_group"] = str(group_name)
                                    requeue_data["reclaimed_at"] = datetime.now().isoformat()
                                    stream_max_len = self._resolve_publish_max_len(stream, None)
                                    if stream_max_len:
                                        await self.redis.xadd(
                                            stream,
                                            requeue_data,
                                            maxlen=stream_max_len,
                                            approximate=True,
                                        )
                                    else:
                                        await self.redis.xadd(stream, requeue_data)
                                    result["requeued_messages"] += 1
                                except Exception as e:
                                    result["errors"].append(
                                        f"{stream}/{group_name}/{msg_id}: requeue_failed: {e}"
                                    )
                                    continue

                            try:
                                acked = await self.redis.xack(stream, group_name, msg_id)
                                if acked:
                                    result["acked_messages"] += int(acked)
                            except Exception as e:
                                result["errors"].append(f"{stream}/{group_name}/{msg_id}: ack_failed: {e}")

                        if not next_start or next_start == start_id:
                            break
                        start_id = next_start

            return result
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                **result,
            }

    async def trim_stream_by_age(self, stream: str, max_age_days: int, dry_run: bool = False) -> Dict[str, Any]:
        """
        按时间清理Stream中的旧消息（基于时间戳）

        Args:
            stream: Stream名称
            max_age_days: 最大保留天数
            dry_run: 是否仅模拟运行（预览模式）

        Returns:
            清理结果统计
        """
        await self.connect()

        try:
            # 计算截止时间戳（毫秒）
            cutoff_timestamp_ms = int((time.time() - max_age_days * 86400) * 1000)
            cutoff_id = f"{cutoff_timestamp_ms}-0"

            # 获取清理前的Stream信息
            stream_info = await self.redis.xinfo_stream(stream)
            before_length = stream_info.get("length", 0)

            if before_length == 0:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": 0,
                    "after_length": 0,
                    "trimmed_count": 0,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "cutoff_id": cutoff_id,
                    "message": "Stream为空，无需清理"
                }

            # 获取第一条消息的时间戳
            first_entry = stream_info.get("first-entry", {})
            if not first_entry:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": before_length,
                    "trimmed_count": 0,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "cutoff_id": cutoff_id,
                    "message": "无法获取第一条消息，跳过清理"
                }

            # 解析第一条消息的ID获取时间戳
            # 支持两种格式：元组 (id, data) 或字典 {id: data}
            if isinstance(first_entry, tuple) and len(first_entry) >= 1:
                first_id = first_entry[0]
            elif isinstance(first_entry, dict) and first_entry:
                first_id = list(first_entry.keys())[0]
            else:
                first_id = None
            if not first_id:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": before_length,
                    "trimmed_count": 0,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "cutoff_id": cutoff_id,
                    "message": "无法解析第一条消息ID，跳过清理"
                }

            first_timestamp_ms = int(first_id.split("-")[0])

            # 检查是否需要清理（第一条消息是否早于截止时间）
            if first_timestamp_ms >= cutoff_timestamp_ms:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": before_length,
                    "trimmed_count": 0,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "cutoff_id": cutoff_id,
                    "first_message_age_days": (time.time() - first_timestamp_ms/1000) / 86400,
                    "message": "所有消息都新于截止时间，无需清理"
                }

            # 执行清理
            if dry_run:
                trimmed_count = "模拟运行 - 实际将清理"
                after_length = before_length  # 模拟运行不实际清理
            else:
                try:
                    # Redis 6.2+ 支持 MINID 参数
                    trimmed_count = await self.redis.xtrim(
                        stream,
                        approximate=True,
                        minid=cutoff_id
                    )

                    # 获取清理后的Stream信息
                    stream_info_after = await self.redis.xinfo_stream(stream)
                    after_length = stream_info_after.get("length", 0)

                    # 检查是否实际清理了消息（如果应该有旧消息但未清理，使用备用方案）
                    if trimmed_count == 0 and first_timestamp_ms < cutoff_timestamp_ms:
                        logger.warning(f"xtrim返回0条清理消息，但应有旧消息，使用备用方案")
                        return await self._trim_stream_by_age_fallback(
                            stream, max_age_days, cutoff_timestamp_ms, before_length, dry_run
                        )

                except (redis.exceptions.ResponseError, redis.exceptions.DataError) as e:
                    if ("syntax" in str(e).lower() and "MINID" in str(e)) or "Only one of" in str(e):
                        # Redis版本可能不支持MINID，或者参数冲突，使用替代方案
                        return await self._trim_stream_by_age_fallback(
                            stream, max_age_days, cutoff_timestamp_ms, before_length, dry_run
                        )
                    else:
                        raise

            # 计算实际清理的消息数
            actual_trimmed = before_length - after_length if isinstance(after_length, int) else 0

            result = {
                "success": True,
                "stream": stream,
                "max_age_days": max_age_days,
                "dry_run": dry_run,
                "before_length": before_length,
                "after_length": after_length,
                "trimmed_count": trimmed_count if dry_run else actual_trimmed,
                "cutoff_timestamp": cutoff_timestamp_ms,
                "cutoff_id": cutoff_id,
                "first_message_age_days": (time.time() - first_timestamp_ms/1000) / 86400,
                "message": f"清理完成: {actual_trimmed if not dry_run else '模拟运行'} 条消息"
            }

            logger.info(f"{'🧹 [模拟]' if dry_run else '🧹'} Stream时间清理: {stream}, "
                       f"保留{dry_run}天, 清理前: {before_length}, 清理后: {after_length}, "
                       f"清理: {actual_trimmed if not dry_run else trimmed_count} 条")

            return result

        except Exception as e:
            # 使用错误处理器处理异常
            if self.error_handler:
                error_context = {
                    "operation": "trim_stream_by_age",
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"Stream时间清理失败（已通过错误处理器处理）: {e}")

                    return {
                        "success": False,
                        "error": str(e),
                        "error_handled": True,
                        "error_handler_result": error_result,
                        "stream": stream,
                        "max_age_days": max_age_days,
                        "dry_run": dry_run
                    }
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"Stream时间清理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "stream": stream,
                "max_age_days": max_age_days,
                "dry_run": dry_run
            }

    async def _trim_stream_by_age_fallback(self, stream: str, max_age_days: int,
                                         cutoff_timestamp_ms: int, before_length: int,
                                         dry_run: bool) -> Dict[str, Any]:
        """Redis不支持MINID时的备用清理方案"""
        try:
            # 获取所有消息ID
            messages = await self.redis.xrange(stream, "-", "+", count=1000)

            if not messages:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": before_length,
                    "trimmed_count": 0,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "message": "备用方案: Stream为空",
                    "method": "fallback_range_scan"
                }

            # 找到需要删除的消息ID
            to_delete = []
            for msg_id, msg_data in messages:
                msg_timestamp_ms = int(msg_id.split("-")[0])
                if msg_timestamp_ms < cutoff_timestamp_ms:
                    to_delete.append(msg_id)
                else:
                    break  # 消息按时间排序，后续消息都更新

            if not to_delete:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": before_length,
                    "trimmed_count": 0,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "message": "备用方案: 所有消息都新于截止时间",
                    "method": "fallback_range_scan"
                }

            # 执行删除
            if dry_run:
                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": before_length,
                    "trimmed_count": len(to_delete),
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "to_delete_count": len(to_delete),
                    "message": f"备用方案[模拟]: 将删除 {len(to_delete)} 条旧消息",
                    "method": "fallback_range_scan"
                }
            else:
                # 批量删除消息
                for msg_id in to_delete:
                    await self.redis.xdel(stream, msg_id)

                # 获取清理后的Stream信息
                stream_info_after = await self.redis.xinfo_stream(stream)
                after_length = stream_info_after.get("length", 0)
                actual_trimmed = before_length - after_length

                return {
                    "success": True,
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                    "before_length": before_length,
                    "after_length": after_length,
                    "trimmed_count": actual_trimmed,
                    "cutoff_timestamp": cutoff_timestamp_ms,
                    "to_delete_count": len(to_delete),
                    "message": f"备用方案: 删除 {actual_trimmed} 条旧消息",
                    "method": "fallback_range_scan"
                }

        except Exception as e:
            logger.error(f"备用清理方案失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "stream": stream,
                "max_age_days": max_age_days,
                "dry_run": dry_run,
                "method": "fallback_range_scan"
            }

    async def analyze_stream_health(self, stream: str) -> Dict[str, Any]:
        """
        分析Stream健康状况：长度、年龄分布、清理建议等

        Args:
            stream: Stream名称

        Returns:
            Stream健康分析报告
        """
        await self.connect()

        try:
            # 获取Stream信息
            stream_info = await self.redis.xinfo_stream(stream)
            length = stream_info.get("length", 0)

            if length == 0:
                return {
                    "success": True,
                    "stream": stream,
                    "length": 0,
                    "health_status": "healthy",
                    "message": "Stream为空，状态健康",
                    "recommendations": [],
                    "metrics": {
                        "length": 0,
                        "first_message_age_days": None,
                        "last_message_age_days": None,
                        "average_age_days": None,
                        "consumer_groups_count": 0,
                        "total_pending_messages": 0,
                        "oldest_pending_age_days": 0
                    }
                }

            # 获取第一条和最后一条消息
            first_entry = stream_info.get("first-entry", {})
            last_entry = stream_info.get("last-entry", {})

            # 解析消息时间戳
            first_id = None
            if first_entry and isinstance(first_entry, dict) and first_entry:
                keys = list(first_entry.keys())
                if keys:
                    first_id = keys[0]

            last_id = None
            if last_entry and isinstance(last_entry, dict) and last_entry:
                keys = list(last_entry.keys())
                if keys:
                    last_id = keys[0]

            first_timestamp_ms = int(first_id.split("-")[0]) if first_id else None
            last_timestamp_ms = int(last_id.split("-")[0]) if last_id else None

            current_time_ms = int(time.time() * 1000)

            # 计算年龄
            first_age_days = (current_time_ms - first_timestamp_ms) / (1000 * 86400) if first_timestamp_ms else None
            last_age_days = (current_time_ms - last_timestamp_ms) / (1000 * 86400) if last_timestamp_ms else None
            avg_age_days = (first_age_days + last_age_days) / 2 if first_age_days and last_age_days else None

            # 获取消费者组信息
            try:
                groups_info = await self.redis.xinfo_groups(stream)
                groups_count = len(groups_info)

                # 计算pending消息总数
                total_pending = sum(group.get("pending", 0) for group in groups_info)

                # 计算最老的pending消息
                oldest_pending_days = 0
                for group in groups_info:
                    last_delivered = group.get("last-delivered-id", "0-0")
                    if last_delivered != "0-0":
                        try:
                            last_timestamp = int(last_delivered.split("-")[0])
                            age_days = (current_time_ms - last_timestamp) / (1000 * 86400)
                            if age_days > oldest_pending_days:
                                oldest_pending_days = age_days
                        except:
                            pass

            except Exception as e:
                groups_count = 0
                total_pending = 0
                oldest_pending_days = 0
                logger.debug(f"获取消费者组信息失败: {e}")

            # 健康评估
            health_status = "healthy"
            recommendations = []

            # 评估标准
            if length > 10000:
                health_status = "warning"
                recommendations.append(f"Stream长度较大 ({length})，建议启用MAXLEN或定期清理")

            if first_age_days and first_age_days > 30:
                health_status = "warning"
                recommendations.append(f"最老消息已存在 {first_age_days:.1f} 天，建议基于时间清理")

            if total_pending > 1000:
                health_status = "warning"
                recommendations.append(f"有 {total_pending} 条pending消息，消费者处理可能延迟")

            if oldest_pending_days > 7:
                health_status = "warning"
                recommendations.append(f"最老pending消息已存在 {oldest_pending_days:.1f} 天，可能需要人工干预")

            if groups_count == 0 and length > 100:
                health_status = "info"
                recommendations.append("无消费者组，但Stream中有消息，可能未被消费")

            # 生成清理建议
            if first_age_days and first_age_days > 30:
                cleanup_days = min(30, int(first_age_days * 0.7))  # 建议保留30天或70%的当前年龄
                recommendations.append(f"建议执行 trim_stream_by_age({stream}, max_age_days={cleanup_days})")

            if length > 5000:
                recommendations.append(f"建议在发布时启用MAXLEN限制: publish(..., max_len=5000)")

            report = {
                "success": True,
                "stream": stream,
                "health_status": health_status,
                "timestamp": datetime.now().isoformat(),
                "metrics": {
                    "length": length,
                    "first_message_age_days": round(first_age_days, 2) if first_age_days else None,
                    "last_message_age_days": round(last_age_days, 2) if last_age_days else None,
                    "average_age_days": round(avg_age_days, 2) if avg_age_days else None,
                    "consumer_groups_count": groups_count,
                    "total_pending_messages": total_pending,
                    "oldest_pending_age_days": round(oldest_pending_days, 2)
                },
                "recommendations": recommendations,
                "estimated_memory_bytes": length * 1024  # 简单估算：每条消息约1KB
            }

            first_age_str = f"{first_age_days:.1f}天" if first_age_days is not None else "未知"
            logger.info(f"📊 Stream健康分析: {stream}, 状态: {health_status}, 长度: {length}, "
                       f"最老消息: {first_age_str}")

            return report

        except Exception as e:
            if self.error_handler:
                error_context = {
                    "operation": "analyze_stream_health",
                    "stream": stream
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"Stream健康分析失败（已通过错误处理器处理）: {e}")

                    return {
                        "success": False,
                        "error": str(e),
                        "error_handled": True,
                        "error_handler_result": error_result,
                        "stream": stream
                    }
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"Stream健康分析失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "stream": stream
            }

    async def safe_stream_cleanup(self, stream: str,
                                max_age_days: Optional[int] = 30,
                                max_length: Optional[int] = None,
                                dry_run: bool = True) -> Dict[str, Any]:
        """
        安全的Stream清理：先分析再清理，避免误删

        Args:
            stream: Stream名称
            max_age_days: 最大保留天数（None表示不按时间清理）
            max_length: 最大长度（None表示不按长度清理）
            dry_run: 是否仅模拟运行

        Returns:
            清理结果
        """
        await self.connect()

        try:
            # 步骤1：分析Stream健康状况
            health_report = await self.analyze_stream_health(stream)

            if not health_report.get("success", False):
                return {
                    "success": False,
                    "error": "健康分析失败",
                    "health_report": health_report,
                    "cleanup_performed": False,
                    "dry_run": dry_run
                }

            # 检查是否包含metrics数据
            if "metrics" not in health_report:
                return {
                    "success": False,
                    "error": "健康报告缺少metrics数据",
                    "health_report": health_report,
                    "cleanup_performed": False,
                    "dry_run": dry_run
                }

            # 步骤2：根据健康报告决定清理策略
            actions_taken = []
            cleanup_results = {}

            # 按时间清理
            first_message_age_days = health_report["metrics"].get("first_message_age_days")
            if max_age_days and first_message_age_days is not None and first_message_age_days > max_age_days:
                age_result = await self.trim_stream_by_age(stream, max_age_days, dry_run)
                cleanup_results["age_based_cleanup"] = age_result

                if age_result.get("success", False):
                    trimmed = age_result.get("trimmed_count", 0)
                    if trimmed > 0 or dry_run:
                        actions_taken.append(f"基于时间清理: 保留{max_age_days}天，{'模拟清理' if dry_run else '实际清理'} {trimmed} 条消息")

            # 按长度清理（如果需要）
            current_length = health_report["metrics"]["length"]
            if max_length and current_length > max_length:
                # 简单的MAXLEN清理（通过XADD带MAXLEN参数）
                # 注意：这需要重新发布消息或使用XTRIM
                if not dry_run:
                    # 使用XTRIM进行长度清理
                    try:
                        trimmed = await self.redis.xtrim(
                            stream,
                            maxlen=max_length,
                            approximate=True
                        )
                        cleanup_results["length_based_cleanup"] = {
                            "success": True,
                            "max_length": max_length,
                            "trimmed_count": trimmed,
                            "before_length": current_length
                        }
                        actions_taken.append(f"基于长度清理: 限制为{max_length}条，清理 {trimmed} 条消息")
                    except Exception as e:
                        cleanup_results["length_based_cleanup"] = {
                            "success": False,
                            "error": str(e)
                        }
                else:
                    cleanup_results["length_based_cleanup"] = {
                        "success": True,
                        "max_length": max_length,
                        "trimmed_count": f"模拟: 将清理 {current_length - max_length} 条",
                        "before_length": current_length,
                        "dry_run": True
                    }
                    actions_taken.append(f"基于长度清理[模拟]: 限制为{max_length}条，将清理 {current_length - max_length} 条消息")

            # 步骤3：生成最终报告
            final_report = {
                "success": True,
                "stream": stream,
                "dry_run": dry_run,
                "timestamp": datetime.now().isoformat(),
                "health_analysis": {
                    "status": health_report["health_status"],
                    "metrics": health_report["metrics"]
                },
                "cleanup_strategy": {
                    "max_age_days": max_age_days,
                    "max_length": max_length
                },
                "actions_taken": actions_taken,
                "cleanup_results": cleanup_results,
                "recommendations": health_report.get("recommendations", [])
            }

            if dry_run:
                final_report["message"] = "模拟运行完成，未执行实际清理"
            elif actions_taken:
                final_report["message"] = f"清理完成: {len(actions_taken)} 项操作"
            else:
                final_report["message"] = "无需清理，Stream状态健康"

            logger.info(f"{'🔍 [模拟]' if dry_run else '🧹'} 安全清理完成: {stream}, "
                       f"操作: {len(actions_taken)}, 策略: 保留{max_age_days}天{'/' if max_length else ''}{f'限制{max_length}条' if max_length else ''}")

            return final_report

        except Exception as e:
            if self.error_handler:
                error_context = {
                    "operation": "safe_stream_cleanup",
                    "stream": stream,
                    "max_age_days": max_age_days,
                    "max_length": max_length,
                    "dry_run": dry_run
                }

                try:
                    error_result = await self.error_handler.handle_error(e, error_context)
                    logger.error(f"安全清理失败（已通过错误处理器处理）: {e}")

                    return {
                        "success": False,
                        "error": str(e),
                        "error_handled": True,
                        "error_handler_result": error_result,
                        "stream": stream,
                        "dry_run": dry_run
                    }
                except Exception as handling_error:
                    logger.error(f"错误处理失败: {handling_error}")

            logger.error(f"安全清理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "stream": stream,
                "dry_run": dry_run
            }

    async def get_stream_metrics(self, stream_pattern: str = "stream:*") -> Dict[str, Any]:
        """获取Stream指标：长度、消费者组、延迟等

        Args:
            stream_pattern: Stream模式，默认"stream:*"

        Returns:
            Stream指标字典
        """
        await self.connect()

        try:
            # 获取匹配的Stream列表
            keys = await self.redis.keys(stream_pattern)
            streams = []
            for key in keys:
                try:
                    key_type = await self.redis.type(key)
                    if isinstance(key_type, bytes):
                        key_type = key_type.decode("utf-8", errors="ignore")
                    if str(key_type).lower() == "stream":
                        streams.append(key)
                except Exception as type_err:
                    logger.debug(f"获取key类型失败，已跳过 {key}: {type_err}")

            metrics = {
                "timestamp": datetime.now().isoformat(),
                "streams_found": len(streams),
                "streams": {},
                "summary": {
                    "total_messages": 0,
                    "total_groups": 0,
                    "total_pending": 0,
                    "total_consumers": 0
                }
            }

            for stream in streams:
                try:
                    stream_info = await self.redis.xinfo_stream(stream)
                    stream_length = stream_info.get("length", 0)

                    # 获取消费者组信息
                    groups_info = []
                    try:
                        groups = await self.redis.xinfo_groups(stream)
                        for group in groups:
                            group_name = group.get("name", "")
                            consumers = group.get("consumers", 0)
                            pending = group.get("pending", 0)
                            last_delivered = group.get("last-delivered-id", "0-0")

                            groups_info.append({
                                "name": group_name,
                                "consumers": consumers,
                                "pending": pending,
                                "last_delivered": last_delivered
                            })

                            metrics["summary"]["total_groups"] += 1
                            metrics["summary"]["total_pending"] += pending
                            metrics["summary"]["total_consumers"] += consumers
                    except Exception as e:
                        # 可能没有消费者组
                        groups_info = []

                    metrics["streams"][stream] = {
                        "length": stream_length,
                        "first_id": stream_info.get("first-entry", {}),
                        "last_id": stream_info.get("last-entry", {}),
                        "groups": groups_info,
                        "groups_count": len(groups_info)
                    }

                    metrics["summary"]["total_messages"] += stream_length

                except Exception as e:
                    logger.error(f"获取Stream指标失败 {stream}: {e}")
                    metrics["streams"][stream] = {"error": str(e)}

            return metrics

        except Exception as e:
            logger.error(f"获取Stream指标失败: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "streams_found": 0
            }

    async def get_consumer_group_metrics(self, stream: Optional[str] = None) -> Dict[str, Any]:
        """获取消费者组指标：pending数量、延迟、消费者状态等

        Args:
            stream: 可选的Stream名称，为None时获取所有Stream

        Returns:
            消费者组指标字典
        """
        await self.connect()

        try:
            if stream:
                streams = [stream]
            else:
                keys = await self.redis.keys("stream:*")
                streams = []
                for key in keys:
                    try:
                        key_type = await self.redis.type(key)
                        if isinstance(key_type, bytes):
                            key_type = key_type.decode("utf-8", errors="ignore")
                        if str(key_type).lower() == "stream":
                            streams.append(key)
                    except Exception as type_err:
                        logger.debug(f"获取key类型失败，已跳过 {key}: {type_err}")

            metrics = {
                "timestamp": datetime.now().isoformat(),
                "streams": {},
                "summary": {
                    "total_groups": 0,
                    "total_pending": 0,
                    "total_consumers": 0,
                    "inactive_groups": 0,
                    "high_pending_groups": 0  # pending > 100
                }
            }

            for s in streams:
                try:
                    groups = await self.redis.xinfo_groups(s)
                    stream_metrics = {
                        "stream": s,
                        "groups_count": len(groups),
                        "groups": []
                    }

                    for group in groups:
                        group_name = group.get("name", "")
                        consumers = group.get("consumers", 0)
                        pending = group.get("pending", 0)
                        last_delivered = group.get("last-delivered-id", "0-0")

                        group_metric = {
                            "name": group_name,
                            "consumers": consumers,
                            "pending": pending,
                            "last_delivered": last_delivered,
                            "status": "active" if consumers > 0 else "inactive",
                            "high_pending": pending > 100
                        }

                        stream_metrics["groups"].append(group_metric)

                        # 更新摘要
                        metrics["summary"]["total_groups"] += 1
                        metrics["summary"]["total_pending"] += pending
                        metrics["summary"]["total_consumers"] += consumers
                        if consumers == 0:
                            metrics["summary"]["inactive_groups"] += 1
                        if pending > 100:
                            metrics["summary"]["high_pending_groups"] += 1

                    metrics["streams"][s] = stream_metrics

                except Exception as e:
                    logger.error(f"获取消费者组指标失败 {s}: {e}")
                    metrics["streams"][s] = {"error": str(e)}

            return metrics

        except Exception as e:
            logger.error(f"获取消费者组指标失败: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }

    async def get_processing_metrics(self) -> Dict[str, Any]:
        """获取处理指标：成功率、延迟、重试率等"""
        stats = self.get_stats()

        processing_metrics = {
            "timestamp": datetime.now().isoformat(),
            "success_rates": stats.get("success_rates", {}),
            "operation_stats": stats.get("operation_stats", {}),
            "retry_metrics": {}
        }

        # 添加重试指标
        if "retry_manager_stats" in stats:
            retry_stats = stats["retry_manager_stats"]
            processing_metrics["retry_metrics"] = {
                "total_retries": retry_stats.get("total_retries", 0),
                "successful_retries": retry_stats.get("successful_retries", 0),
                "failed_retries": retry_stats.get("failed_retries", 0),
                "success_rate": retry_stats.get("success_rate", 0),
                "avg_retries_per_failure": retry_stats.get("avg_retries_per_failure", 0)
            }

        # 添加错误处理器指标
        if "error_handler_stats" in stats:
            error_stats = stats["error_handler_stats"]
            processing_metrics["error_metrics"] = {
                "total_errors": error_stats.get("total_errors", 0),
                "recovered_errors": error_stats.get("recovered_errors", 0),
                "recovery_rate": error_stats.get("recovery_rate", 0),
                "dead_letter_messages": error_stats.get("dead_letter_messages", 0)
            }

        # 计算平均处理延迟（简化版）
        # 这里可以扩展为实际测量延迟
        processing_metrics["latency_metrics"] = {
            "estimated_avg_latency_ms": 0,  # 需要实际测量
            "note": "需要实现实际延迟测量"
        }

        return processing_metrics

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        stats = {
            'connected': self.connected,
            'redis_url': self.redis_url,
            'enable_retry': self.enable_retry,
            'retry_manager_available': RETRY_MANAGER_AVAILABLE,
            'operation_stats': self.stats.copy(),
            'redis_stats': {}
        }
        
        # 添加Redis包装器统计
        if self.redis and hasattr(self.redis, 'get_stats'):
            stats['redis_stats'] = self.redis.get_stats()
        
        # 添加重试管理器统计
        if self._retry_manager:
            stats['retry_manager_stats'] = self._retry_manager.get_stats()

        # 添加错误处理器统计
        if self.error_handler and hasattr(self.error_handler, 'get_stats'):
            try:
                stats['error_handler_stats'] = self.error_handler.get_stats()
            except Exception as e:
                stats['error_handler_stats_error'] = str(e)

        # 添加消费者组管理器统计
        if self.consumer_group_manager and hasattr(self.consumer_group_manager, 'stats'):
            stats['consumer_group_manager_stats'] = self.consumer_group_manager.stats.copy()
            stats['consumer_group_manager_available'] = True
        else:
            stats['consumer_group_manager_available'] = False

        # 计算成功率
        total_publish = max(1, self.stats['publish_success'] + self.stats['publish_failed'])
        total_consume = max(1, self.stats['consume_success'] + self.stats['consume_failed'])
        total_ack = max(1, self.stats['ack_success'] + self.stats['ack_failed'])

        stats['success_rates'] = {
            'publish': self.stats['publish_success'] / total_publish,
            'consume': self.stats['consume_success'] / total_consume,
            'ack': self.stats['ack_success'] / total_ack
        }

        return stats
    
    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()
        
        print("\n📊 Redis Stream 管理器统计")
        print("=" * 60)
        print(f"连接状态: {'✅ 已连接' if stats['connected'] else '❌ 未连接'}")
        print(f"Redis URL: {stats['redis_url']}")
        print(f"重试功能: {'✅ 启用' if stats['enable_retry'] else '⏸️ 禁用'}")
        
        print(f"\n操作统计:")
        print(f"  发布操作: {stats['operation_stats']['publish_operations']}")
        print(f"  发布成功: {stats['operation_stats']['publish_success']}")
        print(f"  发布失败: {stats['operation_stats']['publish_failed']}")
        print(f"  发布成功率: {stats['success_rates']['publish']:.1%}")
        
        print(f"\n  消费操作: {stats['operation_stats']['consume_operations']}")
        print(f"  消费成功: {stats['operation_stats']['consume_success']}")
        print(f"  消费失败: {stats['operation_stats']['consume_failed']}")
        print(f"  消费成功率: {stats['success_rates']['consume']:.1%}")
        
        print(f"\n  确认操作: {stats['operation_stats']['ack_operations']}")
        print(f"  确认成功: {stats['operation_stats']['ack_success']}")
        print(f"  确认失败: {stats['operation_stats']['ack_failed']}")
        print(f"  确认成功率: {stats['success_rates']['ack']:.1%}")
        
        # 显示重试统计
        if 'retry_manager_stats' in stats:
            retry_stats = stats['retry_manager_stats']
            print(f"\n重试统计:")
            print(f"  总重试次数: {retry_stats.get('total_retries', 0)}")
            print(f"  成功重试: {retry_stats.get('successful_retries', 0)}")
            print(f"  失败重试: {retry_stats.get('failed_retries', 0)}")
            print(f"  重试成功率: {retry_stats.get('success_rate', 0):.1%}")

        # 显示错误处理器统计
        if 'error_handler_stats' in stats:
            error_stats = stats['error_handler_stats']
            print(f"\n错误处理器统计:")
            print(f"  总错误数: {error_stats.get('total_errors', 0)}")
            print(f"  恢复错误: {error_stats.get('recovered_errors', 0)}")
            print(f"  恢复率: {error_stats.get('recovery_rate', 0):.1%}")
            print(f"  死信队列消息: {error_stats.get('dead_letter_messages', 0)}")

        # 显示消费者组管理器统计
        if 'consumer_group_manager_stats' in stats:
            cg_stats = stats['consumer_group_manager_stats']
            print(f"\n消费者组管理器统计:")
            print(f"  创建组数: {cg_stats.get('created_groups', 0)}")
            print(f"  清理组数: {cg_stats.get('cleaned_groups', 0)}")
            print(f"  保护组数: {cg_stats.get('protected_groups', 0)}")
            print(f"  总操作数: {cg_stats.get('total_operations', 0)}")
            if cg_stats.get('last_cleanup'):
                print(f"  最后清理: {cg_stats.get('last_cleanup')}")

        print("=" * 60)

    def _get_stream_definition(self, stream_name: str):
        """获取Stream定义配置"""
        if not STREAM_CONFIG_AVAILABLE:
            return None

        try:
            # 从全局配置获取Stream配置
            from .stream_config import get_stream_config
            stream_config = get_stream_config()

            # 尝试匹配Stream名称
            # Stream名称可能是完整格式"stream:news:raw"或"news:raw"
            # 配置中的键是"news_raw"
            # 先尝试直接匹配
            for key, definition in stream_config.streams.items():
                if definition.name == stream_name:
                    return definition

            # 尝试去除"stream:"前缀
            if stream_name.startswith("stream:"):
                short_name = stream_name[7:]  # 移除"stream:"
                for key, definition in stream_config.streams.items():
                    if definition.name == short_name:
                        return definition

            # 尝试添加前缀
            if not stream_name.startswith("stream:"):
                prefixed_name = f"stream:{stream_name}"
                for key, definition in stream_config.streams.items():
                    if definition.name == prefixed_name:
                        return definition

            return None
        except Exception as e:
            logger.debug(f"获取Stream定义失败 {stream_name}: {e}")
            return None

    def _generate_fallback_alerts(self, summary, aging_streams, large_streams, success_rates):
        """生成回退告警（当告警服务不可用时）"""
        alerts = []

        # 检查高pending
        if summary.get('high_pending_groups', 0) > 0:
            alerts.append(f"有 {summary['high_pending_groups']} 个消费者组pending消息超过100条")

        # 检查非活跃组
        if summary.get('inactive_groups', 0) > 5:
            alerts.append(f"有 {summary['inactive_groups']} 个非活跃消费者组，可能需要清理")

        # 检查老化的Stream
        if aging_streams:
            aging_count = len(aging_streams)
            oldest_age = max(s['age_days'] for s in aging_streams)
            alerts.append(f"有 {aging_count} 个Stream老化超过30天，最老的 {oldest_age:.1f} 天")

        # 检查大型Stream
        if large_streams:
            large_count = len(large_streams)
            largest = max(s['length'] for s in large_streams)
            alerts.append(f"有 {large_count} 个Stream超过5000条消息，最大的 {largest} 条")

        # 检查成功率
        if success_rates.get('publish', 1) < 0.9:
            alerts.append(f"发布成功率较低: {success_rates['publish']:.1%}")

        if success_rates.get('consume', 1) < 0.9:
            alerts.append(f"消费成功率较低: {success_rates['consume']:.1%}")

        return alerts

    async def print_monitoring_report(self, stream_pattern: str = "stream:*"):
        """打印监控报告，包含Stream指标、消费者组指标和处理指标"""
        await self.connect()

        print("\n📈 Redis Stream 监控报告")
        print("=" * 60)
        print(f"时间: {datetime.now().isoformat()}")
        print(f"Stream模式: {stream_pattern}")
        print("=" * 60)

        try:
            # 获取Stream指标
            print("\n📊 Stream指标:")
            stream_metrics = await self.get_stream_metrics(stream_pattern)
            print(f"  找到Stream数量: {stream_metrics.get('streams_found', 0)}")
            print(f"  总消息数: {stream_metrics.get('summary', {}).get('total_messages', 0)}")
            print(f"  总消费者组数: {stream_metrics.get('summary', {}).get('total_groups', 0)}")
            print(f"  总Pending消息: {stream_metrics.get('summary', {}).get('total_pending', 0)}")
            print(f"  总消费者数: {stream_metrics.get('summary', {}).get('total_consumers', 0)}")

            # 列出每个Stream的摘要
            if stream_metrics.get('streams'):
                print(f"\n  Stream详情:")
                for stream_name, stream_info in stream_metrics['streams'].items():
                    if isinstance(stream_info, dict) and 'error' not in stream_info:
                        print(f"    {stream_name}:")
                        print(f"      消息数: {stream_info.get('length', 0)}")
                        print(f"      消费者组数: {stream_info.get('groups_count', 0)}")

            # Stream健康分析（重点关注年龄和清理需求）
            print("\n🔍 Stream健康分析:")
            aging_streams = []
            large_streams = []
            stream_health_data = {}  # 存储Stream健康数据，用于告警
            health_analysis_count = 0

            if stream_metrics.get('streams'):
                for stream_name, stream_info in stream_metrics['streams'].items():
                    if isinstance(stream_info, dict) and 'error' not in stream_info:
                        length = stream_info.get('length', 0)

                        # 只分析较大的Stream以提高性能
                        if length > 100 or length > 0 and health_analysis_count < 5:
                            health_analysis_count += 1
                            try:
                                # 获取Stream健康报告来分析年龄
                                health_report = await self.analyze_stream_health(stream_name)
                                if health_report.get('success', False):
                                    metrics = health_report.get('metrics', {})
                                    first_age_days = metrics.get('first_message_age_days')
                                    health_status = health_report.get('health_status', 'unknown')

                                    # 存储健康数据用于告警
                                    stream_health_data[stream_name] = {
                                        'metrics': metrics,
                                        'first_age_days': first_age_days,
                                        'health_status': health_status,
                                        'length': length
                                    }

                                    if first_age_days is not None:
                                        print(f"    {stream_name}:")
                                        print(f"      状态: {health_status}")
                                        print(f"      最老消息: {first_age_days:.1f}天")
                                        print(f"      估计内存: {metrics.get('estimated_memory_bytes', 0) / 1024:.1f}KB")

                                        # 检查是否需要清理
                                        if first_age_days > 30:
                                            aging_streams.append({
                                                'stream': stream_name,
                                                'age_days': first_age_days,
                                                'length': length
                                            })

                                    if length > 5000:
                                        large_streams.append({
                                            'stream': stream_name,
                                            'length': length,
                                            'age_days': first_age_days
                                        })
                            except Exception as e:
                                logger.debug(f"Stream健康分析失败 {stream_name}: {e}")
                                # 健康分析失败，仅检查长度
                                if length > 10000:
                                    large_streams.append({
                                        'stream': stream_name,
                                        'length': length,
                                        'age_days': None
                                    })
                        else:
                            # 小型Stream仅检查长度
                            if length > 10000:
                                large_streams.append({
                                    'stream': stream_name,
                                    'length': length,
                                    'age_days': None
                                })

            # 显示清理建议
            if aging_streams:
                print(f"\n  ⚠️  老化的Stream（建议清理）:")
                for stream_info in aging_streams:
                    print(f"    {stream_info['stream']}: {stream_info['age_days']:.1f}天, {stream_info['length']}条消息")
                    print(f"      建议: await manager.trim_stream_by_age('{stream_info['stream']}', max_age_days=30, dry_run=False)")

            if large_streams:
                print(f"\n  📊 大型Stream（考虑启用MAXLEN）:")
                for stream_info in large_streams:
                    age_info = f", {stream_info['age_days']:.1f}天" if stream_info['age_days'] is not None else ""
                    print(f"    {stream_info['stream']}: {stream_info['length']}条消息{age_info}")
                    print(f"      建议: 发布时添加 max_len=5000 参数")

            # 获取消费者组指标
            print("\n👥 消费者组指标:")
            consumer_metrics = await self.get_consumer_group_metrics()
            summary = consumer_metrics.get('summary', {})
            print(f"  总消费者组数: {summary.get('total_groups', 0)}")
            print(f"  活跃组数: {summary.get('total_groups', 0) - summary.get('inactive_groups', 0)}")
            print(f"  非活跃组数: {summary.get('inactive_groups', 0)}")
            print(f"  高Pending组数: {summary.get('high_pending_groups', 0)}")
            print(f"  总Pending消息: {summary.get('total_pending', 0)}")
            print(f"  总消费者数: {summary.get('total_consumers', 0)}")

            # 获取处理指标
            print("\n⚙️ 处理指标:")
            processing_metrics = await self.get_processing_metrics()
            success_rates = processing_metrics.get('success_rates', {})
            print(f"  发布成功率: {success_rates.get('publish', 0):.1%}")
            print(f"  消费成功率: {success_rates.get('consume', 0):.1%}")
            print(f"  确认成功率: {success_rates.get('ack', 0):.1%}")

            # 重试指标
            retry_metrics = processing_metrics.get('retry_metrics', {})
            if retry_metrics:
                print(f"  总重试次数: {retry_metrics.get('total_retries', 0)}")
                print(f"  重试成功率: {retry_metrics.get('success_rate', 0):.1%}")

            # 错误处理指标
            error_metrics = processing_metrics.get('error_metrics', {})
            if error_metrics:
                print(f"  总错误数: {error_metrics.get('total_errors', 0)}")
                print(f"  恢复错误数: {error_metrics.get('recovered_errors', 0)}")
                print(f"  恢复率: {error_metrics.get('recovery_rate', 0):.1%}")

            print("\n⚠️  警报:")
            alerts = []
            alert_objects = []

            # 如果有告警管理器，使用告警服务生成告警
            if self.alert_manager and ALERT_SERVICE_AVAILABLE:
                try:
                    # 1. 积压告警（检查每个Stream的消息数是否超过阈值）
                    if stream_metrics.get('streams'):
                        for stream_name, stream_info in stream_metrics['streams'].items():
                            if isinstance(stream_info, dict) and 'error' not in stream_info:
                                backlog_count = stream_info.get('length', 0)
                                # 获取Stream配置
                                stream_config = None
                                if STREAM_CONFIG_AVAILABLE:
                                    stream_config = self._get_stream_definition(stream_name)

                                # 检查积压告警
                                alert_service = self.alert_manager.alert_services[0] if self.alert_manager.alert_services else None
                                if alert_service and stream_config:
                                    alert = alert_service.check_backlog_alert(stream_name, stream_config, backlog_count)
                                    if alert:
                                        alert_objects.append(alert)
                                        alerts.append(alert.message)

                    # 2. 卡住消息告警（检查最旧消息是否超过阈值）
                    for stream_name, health_data in stream_health_data.items():
                        metrics = health_data.get('metrics', {})
                        first_age_days = health_data.get('first_age_days')
                        if first_age_days is not None:
                            # 转换为毫秒
                            oldest_message_age_ms = int(first_age_days * 24 * 60 * 60 * 1000)
                            # 获取Stream配置
                            stream_config = None
                            if STREAM_CONFIG_AVAILABLE:
                                stream_config = self._get_stream_definition(stream_name)

                            # 检查卡住消息告警
                            alert_service = self.alert_manager.alert_services[0] if self.alert_manager.alert_services else None
                            if alert_service and stream_config:
                                alert = alert_service.check_stuck_message_alert(stream_name, stream_config, oldest_message_age_ms)
                                if alert:
                                    alert_objects.append(alert)
                                    alerts.append(alert.message)

                    # 3. 为每个老化Stream生成告警（使用配置中的阈值，如果可用）
                    for aging_info in aging_streams:
                        stream_name = aging_info['stream']
                        age_days = aging_info['age_days']
                        # 获取Stream配置（如果可用）
                        stream_config = None
                        if STREAM_CONFIG_AVAILABLE:
                            # 尝试从配置中获取StreamDefinition
                            stream_config = self._get_stream_definition(stream_name)

                        # 使用AlertService检查老化告警
                        alert_service = self.alert_manager.alert_services[0] if self.alert_manager.alert_services else None
                        if alert_service:
                            alert = alert_service.check_aging_stream_alert(stream_name, age_days)
                            if alert:
                                alert_objects.append(alert)
                                alerts.append(alert.message)

                    # 4. 为每个大型Stream生成告警
                    for large_info in large_streams:
                        stream_name = large_info['stream']
                        message_count = large_info['length']
                        stream_config = None
                        if STREAM_CONFIG_AVAILABLE:
                            stream_config = self._get_stream_definition(stream_name)

                        alert_service = self.alert_manager.alert_services[0] if self.alert_manager.alert_services else None
                        if alert_service:
                            alert = alert_service.check_large_stream_alert(stream_name, message_count)
                            if alert:
                                alert_objects.append(alert)
                                alerts.append(alert.message)

                    # 5. 高pending消费者组告警
                    if summary.get('high_pending_groups', 0) > 0:
                        # 通用告警，因为没有具体组信息
                        alerts.append(f"有 {summary['high_pending_groups']} 个消费者组pending消息超过100条")
                        # 可以创建一个通用告警对象
                        if self.alert_manager.alert_services:
                            alert_service = self.alert_manager.alert_services[0]
                            # 使用通用告警类型
                            context = AlertContext(
                                additional_info={"high_pending_groups": summary['high_pending_groups']}
                            )
                            alert = Alert(
                                type=AlertType.HIGH_PENDING,
                                severity=AlertSeverity.WARNING,
                                message=f"有 {summary['high_pending_groups']} 个消费者组pending消息超过100条",
                                context=context
                            )
                            alert_objects.append(alert)

                    # 6. 非活跃消费者组告警
                    if summary.get('inactive_groups', 0) > 5:
                        alerts.append(f"有 {summary['inactive_groups']} 个非活跃消费者组，可能需要清理")
                        if self.alert_manager.alert_services:
                            alert_service = self.alert_manager.alert_services[0]
                            context = AlertContext(
                                additional_info={"inactive_groups": summary['inactive_groups']}
                            )
                            alert = Alert(
                                type=AlertType.INACTIVE_GROUP,
                                severity=AlertSeverity.WARNING,
                                message=f"有 {summary['inactive_groups']} 个非活跃消费者组，可能需要清理",
                                context=context
                            )
                            alert_objects.append(alert)

                    # 7. 低成功率告警
                    if success_rates.get('publish', 1) < 0.9:
                        publish_rate = success_rates['publish']
                        alerts.append(f"发布成功率较低: {publish_rate:.1%}")
                        if self.alert_manager.alert_services:
                            alert_service = self.alert_manager.alert_services[0]
                            alert = alert_service.check_success_rate_alert("publish", publish_rate, threshold=0.9)
                            if alert:
                                alert_objects.append(alert)

                    if success_rates.get('consume', 1) < 0.9:
                        consume_rate = success_rates['consume']
                        alerts.append(f"消费成功率较低: {consume_rate:.1%}")
                        if self.alert_manager.alert_services:
                            alert_service = self.alert_manager.alert_services[0]
                            alert = alert_service.check_success_rate_alert("consume", consume_rate, threshold=0.9)
                            if alert:
                                alert_objects.append(alert)

                    # 发送所有告警
                    for alert in alert_objects:
                        await self.alert_manager.send_alert(alert)

                except Exception as e:
                    logger.warning(f"告警生成失败，使用回退逻辑: {e}")
                    # 回退到原有逻辑
                    alerts = self._generate_fallback_alerts(summary, aging_streams, large_streams, success_rates)
            else:
                # 告警服务不可用，使用原有逻辑
                alerts = self._generate_fallback_alerts(summary, aging_streams, large_streams, success_rates)

            # 打印告警
            if alerts:
                for alert in alerts:
                    print(f"  ⚠️  {alert}")
            else:
                print("  ✅ 无异常警报")

            print("\n" + "=" * 60)

        except Exception as e:
            print(f"❌ 生成监控报告失败: {e}")
            print("=" * 60)


# 向后兼容的别名
RedisStreamManager = RetryEnhancedRedisStreamManager


# 示例：使用装饰器的重试版本
if RETRY_MANAGER_AVAILABLE:
    from database_service.streams.utils.retry_manager import with_retry
    
    class DecoratedRedisStreamManager(RetryEnhancedRedisStreamManager):
        """使用装饰器的重试增强管理器"""
        
        @with_retry(max_retries=3, base_delay=1.0, strategy="exponential")
        async def publish_with_decorator(self, stream: str, data: Dict, 
                                        max_len: Optional[int] = None) -> str:
            """使用装饰器的发布方法"""
            await self.connect()
            
            message_data = {
                "payload": json.dumps(data, ensure_ascii=False),
                "published_at": datetime.now().isoformat(),
                "source": "database_service"
            }
            
            if max_len:
                return await self.redis.xadd(stream, message_data, maxlen=max_len, approximate=True)
            else:
                return await self.redis.xadd(stream, message_data)
        
        @with_retry(max_retries=2, base_delay=0.5, strategy="fixed")
        async def consume_with_decorator(self, group: str, consumer: str, stream: str,
                                        count: int = 10, block_ms: int = 5000) -> List[StreamMessage]:
            """使用装饰器的消费方法"""
            await self.connect()
            
            result = await self.redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=count,
                block=block_ms
            )
            
            if not result:
                return []
            
            messages = []
            for stream_name, stream_messages in result:
                for msg_id, msg_data in stream_messages:
                    try:
                        # 简化版：由于Redis配置了decode_responses=True，直接获取字符串
                        payload = msg_data.get("payload", "{}")
                        data = json.loads(payload)

                        published_at = msg_data.get("published_at")
                        timestamp = datetime.fromisoformat(published_at) if published_at else datetime.now()
                        
                        messages.append(StreamMessage(
                            id=msg_id,
                            stream=stream_name,
                            data=data,
                            timestamp=timestamp
                        ))
                    except Exception as e:
                        logger.error(f"解析消息失败: {e}")
                        continue
            
            return messages


# 便捷函数
async def create_redis_stream_manager(
    redis_url: str = "redis://localhost:6379/0",
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> RetryEnhancedRedisStreamManager:
    """创建Redis Stream管理器的便捷函数"""
    manager = RetryEnhancedRedisStreamManager(
        redis_url=redis_url,
        enable_retry=enable_retry,
        retry_config=retry_config
    )
    
    await manager.connect()
    return manager


async def test_retry_functionality():
    """测试重试功能"""
    print("🧪 测试Redis Stream管理器重试功能...")
    
    try:
        # 创建一个无效的URL来测试重试
        manager = await create_redis_stream_manager(
            redis_url="redis://invalid_host:6379/0",
            enable_retry=True,
            retry_config={"max_retries": 2, "base_delay": 0.1}
        )
        
        # 这会触发重试
        connected = await manager.connect()
        print(f"连接结果: {connected} (应该为False)")
        
        # 创建有效的管理器
        valid_manager = await create_redis_stream_manager(
            enable_retry=True
        )
        
        # 测试发布
        test_data = {"test": "retry", "timestamp": datetime.now().isoformat()}
        message_id = await valid_manager.publish("test:stream", test_data)
        print(f"✅ 发布成功: {message_id}")
        
        # 打印统计
        valid_manager.print_stats()
        
        await valid_manager.close()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_retry_functionality())
