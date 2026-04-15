# database_service/streams/utils/error_handler.py
"""
Stream错误处理器 - 统一错误处理模式
提供错误分类、处理和监控功能
"""

import logging
import traceback
import json
from typing import Dict, Any, Optional, List, Type, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误分类"""
    REDIS_CONNECTION = "redis_connection"
    STREAM_NOT_FOUND = "stream_not_found"
    CONSUMER_GROUP = "consumer_group"
    MESSAGE_FORMAT = "message_format"
    VALIDATION = "validation"
    PROCESSING = "processing"
    UNKNOWN = "unknown"


class StreamErrorHandler:
    """Stream错误处理器 - 统一错误处理模式"""

    def __init__(self, redis_client=None, config: Optional[Dict] = None):
        """
        初始化错误处理器

        Args:
            redis_client: Redis客户端（可选）
            config: 配置字典
        """
        self.redis = redis_client
        self.config = config or {}

        # 错误分类映射
        self.error_patterns = {
            ErrorCategory.REDIS_CONNECTION: [
                "ConnectionError", "TimeoutError", "Connection refused",
                "redis.exceptions.ConnectionError", "redis.exceptions.TimeoutError",
                "BusyLoadingError", "BUSYLOADING", "loading the dataset in memory"
            ],
            ErrorCategory.STREAM_NOT_FOUND: [
                "no such key", "NOGROUP", "ERR no such key"
            ],
            ErrorCategory.CONSUMER_GROUP: [
                "BUSYGROUP", "NOGROUP", "consumer group"
            ],
            ErrorCategory.MESSAGE_FORMAT: [
                "JSONDecodeError", "KeyError", "AttributeError",
                "'dict' object has no attribute", "bytes",
                "string indices must be integers"
            ],
            ErrorCategory.VALIDATION: [
                "validation", "required", "missing", "invalid"
            ],
            ErrorCategory.PROCESSING: [
                "processing", "extract", "analysis", "match"
            ]
        }

        # 错误处理策略
        self.handling_strategies = {
            ErrorCategory.REDIS_CONNECTION: self._handle_connection_error,
            ErrorCategory.STREAM_NOT_FOUND: self._handle_stream_not_found,
            ErrorCategory.CONSUMER_GROUP: self._handle_consumer_group_error,
            ErrorCategory.MESSAGE_FORMAT: self._handle_message_format_error,
            ErrorCategory.VALIDATION: self._handle_validation_error,
            ErrorCategory.PROCESSING: self._handle_processing_error,
            ErrorCategory.UNKNOWN: self._handle_unknown_error
        }

        # 统计信息
        self.stats = {
            "total_errors": 0,
            "by_category": {cat.value: 0 for cat in ErrorCategory},
            "by_strategy": {cat.value: 0 for cat in ErrorCategory},
            "recovered_errors": 0,
            "unrecovered_errors": 0,
            "dead_letter_messages": 0,
            "last_error": None,
            "error_history": []  # 最近错误记录
        }

        logger.info("✅ 初始化Stream错误处理器")

    def categorize_error(self, error: Exception) -> ErrorCategory:
        """
        分类错误

        Args:
            error: 异常对象

        Returns:
            错误分类
        """
        error_str = str(error)
        error_type = type(error).__name__

        for category, patterns in self.error_patterns.items():
            for pattern in patterns:
                if (pattern in error_str or pattern in error_type or
                    pattern in str(error.__class__.__name__)):
                    return category

        # 检查特定异常类型
        if hasattr(error, '__class__'):
            error_class_name = error.__class__.__name__
            if "Connection" in error_class_name or "Timeout" in error_class_name:
                return ErrorCategory.REDIS_CONNECTION
            elif "JSON" in error_class_name or "KeyError" in error_class_name:
                return ErrorCategory.MESSAGE_FORMAT

        return ErrorCategory.UNKNOWN

    async def handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一错误处理入口

        Args:
            error: 异常对象
            context: 错误上下文信息

        Returns:
            处理结果
        """
        self.stats["total_errors"] += 1

        # 分类错误
        category = self.categorize_error(error)
        self.stats["by_category"][category.value] += 1

        # 构建错误记录
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "category": category.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "stack_trace": traceback.format_exc(),
            "recovered": False,
            "handling_strategy": category.value
        }

        try:
            # 根据分类选择处理策略
            handler = self.handling_strategies.get(category, self._handle_unknown_error)
            result = await handler(error, context)

            if result.get("recovered", False):
                self.stats["recovered_errors"] += 1
                error_record["recovered"] = True
                error_record["recovery_action"] = result.get("action")
            else:
                self.stats["unrecovered_errors"] += 1

            self.stats["by_strategy"][category.value] += 1

            # 记录错误
            error_record.update(result)
            self._record_error_history(error_record)

            # 更新最后错误
            self.stats["last_error"] = {
                "timestamp": error_record["timestamp"],
                "category": category.value,
                "message": str(error)[:200]
            }

            return error_record

        except Exception as handling_error:
            logger.error(f"错误处理失败: {handling_error}", exc_info=True)

            # 记录原始错误
            error_record["handling_error"] = str(handling_error)
            self._record_error_history(error_record)

            return error_record

    async def _handle_connection_error(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理连接错误"""
        error_str = str(error).lower()
        if "busyloading" in error_str or "loading the dataset in memory" in error_str:
            logger.warning(f"Redis正在加载数据，稍后重试: {error}")
            return {
                "recovered": True,
                "action": "redis_loading_wait",
                "message": "Redis正在加载数据，等待后续重试"
            }

        logger.error(f"Redis连接错误: {error}", exc_info=True)

        # 尝试重新连接
        if self.redis and hasattr(self.redis, 'ping'):
            try:
                await self.redis.ping()
                logger.info("✅ Redis连接已恢复")
                return {
                    "recovered": True,
                    "action": "reconnect_success",
                    "message": "Redis连接已恢复"
                }
            except Exception as e:
                logger.error(f"Redis重连失败: {e}")

        return {
            "recovered": False,
            "action": "reconnect_failed",
            "message": "Redis连接错误，需要人工干预",
            "suggestion": "检查Redis服务状态和网络连接"
        }

    async def _handle_stream_not_found(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理Stream不存在错误"""
        stream = context.get("stream", "未知")

        logger.warning(f"Stream不存在: {stream} - {error}")

        # 尝试创建Stream（如果配置允许）
        if context.get("create_if_missing", False) and self.redis:
            try:
                # 通过发布空消息创建Stream
                await self.redis.xadd(stream, {"_init": "true"}, maxlen=1)
                logger.info(f"✅ 创建Stream: {stream}")
                return {
                    "recovered": True,
                    "action": "stream_created",
                    "message": f"Stream {stream} 已创建"
                }
            except Exception as e:
                logger.error(f"创建Stream失败: {e}")

        return {
            "recovered": False,
            "action": "stream_not_found",
            "message": f"Stream {stream} 不存在",
            "suggestion": "检查Stream名称或启用自动创建"
        }

    async def _handle_consumer_group_error(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理消费者组错误"""
        stream = context.get("stream", "未知")
        group = context.get("group", "未知")

        error_str = str(error)

        if "BUSYGROUP" in error_str:
            logger.debug(f"消费者组已存在: {stream}/{group}")
            return {
                "recovered": True,
                "action": "group_exists",
                "message": "消费者组已存在（正常情况）"
            }
        elif "NOGROUP" in error_str:
            logger.warning(f"消费者组不存在: {stream}/{group}")

            # 尝试创建消费者组
            if context.get("create_group_if_missing", True) and self.redis:
                try:
                    await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
                    logger.info(f"✅ 创建消费者组: {stream}/{group}")
                    return {
                        "recovered": True,
                        "action": "group_created",
                        "message": f"消费者组 {group} 已创建"
                    }
                except Exception as e:
                    logger.error(f"创建消费者组失败: {e}")

        return {
            "recovered": False,
            "action": "consumer_group_error",
            "message": f"消费者组错误: {stream}/{group}",
            "suggestion": "检查消费者组配置或权限"
        }

    async def _handle_message_format_error(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理消息格式错误"""
        message_id = context.get("message_id", "未知")
        stream = context.get("stream", "未知")

        logger.error(f"消息格式错误: {stream}/{message_id} - {error}")

        # 尝试修复或发送到死信队列
        if context.get("send_to_dead_letter", True) and self.redis:
            try:
                dead_letter_stream = context.get("dead_letter_stream", "stream:dead:letter")

                error_message = {
                    "original_stream": stream,
                    "message_id": message_id,
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "context": context,
                    "timestamp": datetime.now().isoformat(),
                    "attempted_recovery": False
                }

                await self.redis.xadd(dead_letter_stream, error_message)
                self.stats["dead_letter_messages"] += 1

                logger.info(f"📭 发送到死信队列: {stream}/{message_id}")

                return {
                    "recovered": True,
                    "action": "sent_to_dead_letter",
                    "message": "消息已发送到死信队列",
                    "dead_letter_stream": dead_letter_stream
                }

            except Exception as e:
                logger.error(f"发送到死信队列失败: {e}")

        return {
            "recovered": False,
            "action": "message_format_error",
            "message": f"消息格式错误: {stream}/{message_id}",
            "suggestion": "检查消息序列化格式或编码"
        }

    async def _handle_validation_error(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理验证错误"""
        logger.warning(f"数据验证错误: {error}")

        # 验证错误通常无法自动恢复，但可以记录
        return {
            "recovered": False,
            "action": "validation_error",
            "message": "数据验证失败",
            "suggestion": "检查输入数据格式和必填字段"
        }

    async def _handle_processing_error(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理处理错误"""
        processor = context.get("processor", "未知")
        logger.error(f"处理错误 [{processor}]: {error}", exc_info=True)

        # 可以尝试重试或降级处理
        retry_count = context.get("retry_count", 0)
        max_retries = context.get("max_retries", 3)

        if retry_count < max_retries:
            logger.info(f"准备重试 ({retry_count + 1}/{max_retries})")
            return {
                "recovered": True,  # 标记为可恢复，因为会重试
                "action": "will_retry",
                "message": f"将在重试中处理错误",
                "retry_info": {
                    "current": retry_count + 1,
                    "max": max_retries
                }
            }

        return {
            "recovered": False,
            "action": "processing_error",
            "message": f"处理失败: {processor}",
            "suggestion": "检查处理器逻辑或依赖服务"
        }

    async def _handle_unknown_error(self, error: Exception, context: Dict) -> Dict[str, Any]:
        """处理未知错误"""
        logger.error(f"未知错误: {error}", exc_info=True)

        # 对于未知错误，保守处理
        return {
            "recovered": False,
            "action": "unknown_error",
            "message": "未知错误类型",
            "suggestion": "检查日志和系统状态"
        }

    async def send_to_dead_letter(self, stream: str, message_id: str,
                                error: Exception, context: Dict) -> bool:
        """
        发送消息到死信队列

        Args:
            stream: 原始Stream
            message_id: 消息ID
            error: 错误对象
            context: 上下文信息

        Returns:
            是否成功
        """
        if not self.redis:
            logger.warning("无Redis客户端，无法发送到死信队列")
            return False

        try:
            dead_letter_stream = context.get("dead_letter_stream", "stream:dead:letter")

            # 尝试获取原始消息
            original_message = None
            try:
                messages = await self.redis.xrange(stream, min=message_id, max=message_id)
                if messages:
                    original_message = dict(messages[0][1])
            except Exception as e:
                logger.debug(f"获取原始消息失败: {e}")

            # 构建死信消息
            dead_letter_message = {
                "original_stream": stream,
                "original_message_id": message_id,
                "error": str(error),
                "error_type": type(error).__name__,
                "error_category": self.categorize_error(error).value,
                "context": json.dumps(context, default=str),
                "original_message": json.dumps(original_message, default=str) if original_message else None,
                "timestamp": datetime.now().isoformat(),
                "handler": "StreamErrorHandler"
            }

            await self.redis.xadd(dead_letter_stream, dead_letter_message)
            self.stats["dead_letter_messages"] += 1

            logger.info(f"📭 发送到死信队列: {stream}/{message_id} -> {dead_letter_stream}")

            return True

        except Exception as e:
            logger.error(f"发送到死信队列失败: {e}")
            return False

    def _record_error_history(self, error_record: Dict[str, Any]):
        """记录错误历史（保留最近100条）"""
        self.stats["error_history"].append(error_record)

        # 限制历史记录大小
        if len(self.stats["error_history"]) > 100:
            self.stats["error_history"] = self.stats["error_history"][-100:]

    def get_stats(self) -> Dict[str, Any]:
        """获取错误处理统计"""
        stats = self.stats.copy()

        # 计算恢复率
        total = max(1, stats["total_errors"])
        stats["recovery_rate"] = stats["recovered_errors"] / total

        # 按类别统计百分比
        stats["category_percentages"] = {
            category: (count / total) if total > 0 else 0
            for category, count in stats["by_category"].items()
        }

        return stats

    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()

        print("\n📊 Stream错误处理器统计")
        print("=" * 60)
        print(f"总错误数: {stats['total_errors']}")
        print(f"恢复错误: {stats['recovered_errors']}")
        print(f"未恢复错误: {stats['unrecovered_errors']}")
        print(f"恢复率: {stats['recovery_rate']:.1%}")
        print(f"死信队列消息: {stats['dead_letter_messages']}")

        print(f"\n错误分类:")
        for category, count in stats["by_category"].items():
            if count > 0:
                percentage = stats["category_percentages"][category]
                print(f"  {category}: {count} ({percentage:.1%})")

        if stats["last_error"]:
            print(f"\n最后错误:")
            print(f"  时间: {stats['last_error']['timestamp']}")
            print(f"  分类: {stats['last_error']['category']}")
            print(f"  消息: {stats['last_error']['message']}")

        print("=" * 60)


# 装饰器：自动错误处理
def with_error_handler(error_handler: StreamErrorHandler = None,
                      context: Optional[Dict] = None):
    """
    错误处理装饰器

    Args:
        error_handler: 错误处理器实例
        context: 基础上下文信息

    Returns:
        装饰器函数
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 创建默认错误处理器（如果需要）
            handler = error_handler
            if not handler:
                handler = StreamErrorHandler()

            # 构建上下文
            ctx = context or {}
            ctx.update({
                "function": func.__name__,
                "module": func.__module__,
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys())
            })

            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # 处理错误
                result = await handler.handle_error(e, ctx)

                # 如果未恢复，重新抛出
                if not result.get("recovered", False):
                    raise

                # 返回错误处理结果
                return result

        return wrapper

    return decorator


# 便捷函数
async def create_error_handler(redis_client=None, config: Optional[Dict] = None) -> StreamErrorHandler:
    """创建错误处理器的便捷函数"""
    return StreamErrorHandler(redis_client, config)


# 测试函数
async def test_error_handler():
    """测试错误处理器"""
    import redis.asyncio as redis

    print("🧪 测试Stream错误处理器...")

    try:
        # 创建Redis客户端
        redis_client = await redis.from_url("redis://localhost:6379/0", decode_responses=True)

        # 创建错误处理器
        handler = await create_error_handler(redis_client)

        # 测试各种错误
        test_errors = [
            {
                "error": Exception("模拟连接错误"),
                "context": {"operation": "test_connection", "stream": "stream:test"},
                "expected_category": ErrorCategory.REDIS_CONNECTION.value
            },
            {
                "error": Exception("no such key 'stream:not:exists'"),
                "context": {"operation": "test_stream", "stream": "stream:not:exists"},
                "expected_category": ErrorCategory.STREAM_NOT_FOUND.value
            },
            {
                "error": Exception("BUSYGROUP Consumer Group name already exists"),
                "context": {"operation": "test_group", "stream": "stream:test", "group": "test_group"},
                "expected_category": ErrorCategory.CONSUMER_GROUP.value
            },
            {
                "error": json.JSONDecodeError("Expecting value", "invalid json", 0),
                "context": {"operation": "test_message", "stream": "stream:test", "message_id": "test_id"},
                "expected_category": ErrorCategory.MESSAGE_FORMAT.value
            }
        ]

        for test in test_errors:
            result = await handler.handle_error(test["error"], test["context"])
            print(f"测试 {test['context']['operation']}: "
                  f"分类={result['category']}, "
                  f"恢复={result.get('recovered', False)}")

        # 打印统计
        handler.print_stats()

        await redis_client.close()

        print("✅ Stream错误处理器测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_error_handler())
