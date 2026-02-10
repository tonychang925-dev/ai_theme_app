"""
Redis Stream管理器 - 重试增强版
在原有基础上添加完整的重试机制
"""
import json
import logging
import asyncio
from datetime import datetime
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
                stop_on_exception=["ResponseError"]  # 不重试 ResponseError
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
            self._retry_manager = RetryManager(**self.retry_config)
        
        logger.info(f"初始化重试增强的RedisStreamManager: {redis_url}")
        logger.info(f"重试功能: {'启用' if self.enable_retry else '禁用'}")
    
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
                    logger.error(f"❌ 检查Stream失败: {stream_name} - {e}")
                    return False
            except Exception as e:
                logger.error(f"❌ 检查Stream异常: {stream_name} - {e}")
                return False
                
        except Exception as e:
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
        
        async def _publish():
            try:
                if max_len:
                    message_id = await self.redis.xadd(stream, message_data, maxlen=max_len, approximate=True)
                else:
                    message_id = await self.redis.xadd(stream, message_data)
                
                logger.info(f"发布消息成功: {stream} -> {message_id}")
                self.stats['publish_success'] += 1
                return message_id
            except Exception as e:
                logger.error(f"发布消息失败: {e}")
                self.stats['publish_failed'] += 1
                raise
        
        if enable_retry and self._retry_manager:
            try:
                message_id = await self._retry_manager.execute_with_retry(
                    _publish,
                    context={
                        "operation": "publish_message",
                        "stream": stream,
                        "data_keys": list(data.keys()) if data else []
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
                    
                    if max_len:
                        pipe.xadd(stream, message_data, maxlen=max_len, approximate=True)
                    else:
                        pipe.xadd(stream, message_data)
                
                # 执行批量发布
                batch_ids = await pipe.execute()
                message_ids.extend(batch_ids)
                
                logger.info(f"批量发布成功: {len(batch)} 条消息到 {stream}")
                
            except Exception as e:
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
                            # 修复：确保正确处理消息数据
                            if isinstance(msg_data.get("payload"), bytes):
                                # 如果是字节串，先解码
                                payload = msg_data["payload"].decode('utf-8')
                            else:
                                payload = msg_data.get("payload", "{}")
                            
                            data = json.loads(payload)
                            
                            # 处理时间戳
                            published_at = msg_data.get("published_at")
                            if isinstance(published_at, bytes):
                                published_at = published_at.decode('utf-8')
                            
                            timestamp = datetime.fromisoformat(published_at) if published_at else datetime.now()
                            
                            # 提取元数据
                            metadata = {
                                "group": group,
                                "consumer": consumer,
                                "attempts": int(msg_data.get("attempts", 0)) if isinstance(msg_data.get("attempts"), (int, str)) else 0,
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
                            logger.error(f"解析消息失败: {e}")
                            continue
                
                logger.info(f"消费消息成功: {len(messages)} 条 from {stream}/{group}")
                self.stats['consume_success'] += 1
                return messages
                
            except Exception as e:
                logger.error(f"消费消息失败: {e}")
                self.stats['consume_failed'] += 1
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
                logger.error(f"确认消息失败: {e}")
                self.stats['ack_failed'] += 1
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
            logger.error(f"批量确认失败: {e}")
            
            # 尝试单个确认
            results = []
            for msg_id in message_ids:
                try:
                    result = await self.ack(stream, group, msg_id, enable_retry=False)
                    results.append(result)
                except:
                    results.append(0)
            return results
    
    async def create_consumer_group(self, stream: str, group: str, 
                                   mkstream: bool = True) -> bool:
        """创建消费者组（带重试）"""
        await self.connect()
        
        async def _create_group():
            try:
                result = await self.redis.xgroup_create(stream, group, id="0", mkstream=mkstream)
                logger.info(f"创建消费者组成功: {stream}/{group}")
                return True
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"消费者组已存在: {stream}/{group}")
                    return True
                logger.error(f"创建消费者组失败: {e}")
                raise
        
        if self.enable_retry and self._retry_manager:
            try:
                result = await self._retry_manager.execute_with_retry(
                    _create_group,
                    context={
                        "operation": "create_consumer_group",
                        "stream": stream,
                        "group": group
                    }
                )
                return result
            except Exception as e:
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
            streams = await self.redis._client.keys(pattern)
            
            result = {}
            for stream in streams:
                if isinstance(stream, bytes):
                    stream = stream.decode('utf-8')
                
                info = await self.get_stream_info(stream)
                result[stream] = info
            
            return result
        except Exception as e:
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
                logger.error(f"关闭连接失败: {e}")
    
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
                        if isinstance(msg_data.get("payload"), bytes):
                            payload = msg_data["payload"].decode('utf-8')
                        else:
                            payload = msg_data.get("payload", "{}")
                        
                        data = json.loads(payload)
                        
                        published_at = msg_data.get("published_at")
                        if isinstance(published_at, bytes):
                            published_at = published_at.decode('utf-8')
                        
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