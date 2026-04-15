# database_service/managers/redis_stream_bus.py

"""
统一的Redis Stream总线
合并原有的事件总线和新的Stream功能
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    import redis.asyncio as aioredis
except ImportError:
    # 模拟Redis客户端（用于测试）
    aioredis = None

logger = logging.getLogger(__name__)

# 导入优化的工具模块
try:
    from ..streams.utils.error_handler import StreamErrorHandler, ErrorCategory
    from ..streams.utils.consumer_group_manager import ConsumerGroupManager
    HAS_STREAM_UTILS = True
except ImportError:
    HAS_STREAM_UTILS = False
    logger.warning("Stream工具模块导入失败，使用降级模式")


class UnifiedRedisStreamBus:
    """
    统一的Redis Stream总线
    提供完整的事件总线和Stream管理功能
    """
    
    def __init__(self, redis_client, config):
        self.redis = redis_client
        self.config = config
        
        # 使用您的原有事件总线作为基础
        from .redis_event_bus import RedisEventBus
        self.event_bus = RedisEventBus(redis_client, config)
        
        # 添加新的Stream管理功能
        self._stream_definitions = self._load_stream_definitions()

        # 初始化优化工具模块
        self._init_stream_utils()

        logger.info(f"🚀 创建统一的Redis Stream总线，加载了 {len(self._stream_definitions)} 个Stream定义")
    
    def _init_stream_utils(self):
        """初始化Stream优化工具模块"""
        self.error_handler = None
        self.consumer_group_manager = None

        if HAS_STREAM_UTILS:
            try:
                # 初始化错误处理器
                self.error_handler = StreamErrorHandler(
                    redis_client=self.redis,
                    config=getattr(self.config, 'redis_stream', {})
                )

                # 初始化消费者组管理器
                cgm_config = {}
                if hasattr(self.config, 'redis_stream'):
                    stream_config = self.config.redis_stream
                    if hasattr(stream_config, 'consumer_group_cleanup'):
                        cgm_config = stream_config.consumer_group_cleanup

                self.consumer_group_manager = ConsumerGroupManager(
                    redis_client=self.redis,
                    config=cgm_config
                )

                logger.info("✅ Stream优化工具模块初始化完成")
            except Exception as e:
                logger.warning(f"Stream工具模块初始化失败: {e}")
        else:
            logger.info("ℹ️ Stream工具模块不可用，使用基础模式")

    def _decode_redis_dict(self, redis_dict):
        """将Redis返回的字节键值对解码为字符串"""
        decoded = {}
        for key, value in redis_dict.items():
            # 解码键
            if isinstance(key, bytes):
                key_str = key.decode('utf-8')
            else:
                key_str = str(key)
            # 解码值
            if isinstance(value, bytes):
                try:
                    value_str = value.decode('utf-8')
                except UnicodeDecodeError:
                    # 如果无法解码为UTF-8，保留原始字节
                    value_str = value
            else:
                value_str = value
            decoded[key_str] = value_str
        return decoded

    def _load_stream_definitions(self) -> Dict[str, Dict[str, Any]]:
        """加载Stream定义 - 修复版：支持EnhancedDatabaseConfig"""
        definitions = {}
        
        # 从配置加载（如果存在）
        if hasattr(self.config, 'redis_stream'):
            redis_stream_config = self.config.redis_stream
            # 检查是否是EnhancedDatabaseConfig格式
            if hasattr(redis_stream_config, 'streams'):
                for key, definition in redis_stream_config.streams.items():
                    # 🔧 修复：处理StreamDefinition对象
                    definitions[key] = self._process_stream_definition(key, definition)
        else:
            # 尝试从config.redis获取
            if hasattr(self.config, 'redis'):
                # 创建默认定义
                definitions = self._get_default_stream_definitions()
        
        return definitions
    
    def _process_stream_definition(self, key: str, definition) -> Dict[str, Any]:
        """处理Stream定义 - 支持对象和字典格式"""
        # 如果definition是StreamDefinition对象
        if hasattr(definition, 'name'):
            stream_name = definition.name
            if not stream_name.startswith('stream:'):
                stream_name = f'stream:{stream_name}'
            
            return {
                'key': stream_name,
                'group': f"{key}_group",
                'max_length': getattr(definition, 'max_length', 10000),
                'description': getattr(definition, 'description', ''),
                'priority': self._get_priority_value(definition)
            }
        # 如果definition是字典
        elif isinstance(definition, dict):
            stream_name = definition.get('name', key)
            if not stream_name.startswith('stream:'):
                stream_name = f'stream:{stream_name}'
            
            return {
                'key': stream_name,
                'group': definition.get('group', f"{key}_group"),
                'max_length': definition.get('max_length', 10000),
                'description': definition.get('description', ''),
                'priority': definition.get('priority', 'medium')
            }
        # 其他格式，使用默认值
        else:
            return {
                'key': f'stream:{key}',
                'group': f"{key}_group",
                'max_length': 10000,
                'description': '',
                'priority': 'medium'
            }
    
    def _get_priority_value(self, definition) -> str:
        """从StreamDefinition对象中获取priority值"""
        if hasattr(definition, 'priority'):
            priority = definition.priority
            if hasattr(priority, 'value'):
                return priority.value
            return str(priority)
        return 'medium'
    
    def _get_default_stream_definitions(self) -> Dict[str, Dict[str, Any]]:
        """获取默认的Stream定义"""
        return {
            'news_raw': {
                'key': 'stream:news:raw',
                'group': 'news_processors',
                'max_length': 10000,
                'description': '原始新闻流',
                'priority': 'high'
            },
            'events_major': {
                'key': 'stream:events:major',
                'group': 'major_workers',
                'max_length': 5000,
                'description': '重大事件流',
                'priority': 'high'
            },
            'events_normal': {
                'key': 'stream:events:normal',
                'group': 'theme_workers',
                'max_length': 20000,
                'description': '普通事件流',
                'priority': 'medium'
            },
            'events_structured': {
                'key': 'stream:events:structured',
                'group': 'event_matchers',
                'max_length': 10000,
                'description': '结构化事件流',
                'priority': 'high'
            },
            'themes_updates': {
                'key': 'stream:themes:updates',
                'group': 'data_updaters',
                'max_length': 2000,
                'description': '主题更新流',
                'priority': 'medium'
            },
            'dead_letter': {
                'key': 'stream:dead:letter',
                'group': 'monitoring',
                'max_length': 1000,
                'description': '死信队列',
                'priority': 'low'
            }
        }
    
    # ========== 事件总线兼容方法 ==========
    
    async def publish(self, event_type: str, data: Dict[str, Any], **kwargs):
        """兼容原有事件总线的publish方法"""
        return await self.event_bus.publish(event_type, data, **kwargs)
    
    async def publish_theme_event(self, *args, **kwargs):
        """兼容原有事件总线的publish_theme_event方法"""
        return await self.event_bus.publish_theme_event(*args, **kwargs)
    
    async def publish_relation_event(self, *args, **kwargs):
        """兼容原有事件总线的publish_relation_event方法"""
        return await self.event_bus.publish_relation_event(*args, **kwargs)
    
    async def publish_cache_event(self, *args, **kwargs):
        """兼容原有事件总线的publish_cache_event方法"""
        return await self.event_bus.publish_cache_event(*args, **kwargs)
    
    # ========== 新的Stream管理方法 ==========
    
    async def publish_to_stream(self, stream: str, data: Dict[str, Any], 
                               max_len: int = None) -> Optional[str]:
        """发布消息到指定Stream"""
        try:
            # 获取Stream定义
            definition = self._stream_definitions.get(stream)
            if not definition:
                logger.error(f"未知的Stream: {stream}")
                return None
            
            # 构建消息
            message = {
                'payload': json.dumps(data, ensure_ascii=False),
                'published_at': asyncio.get_event_loop().time(),
                'source': 'unified_bus',
                'stream': stream
            }
            
            # 发布到Stream
            message_id = await self.redis.xadd(
                definition['key'],
                message,
                maxlen=max_len or definition['max_length'],
                approximate=True
            )
            
            logger.debug(f"📤 发布到Stream: {stream} -> {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"发布到Stream失败 {stream}: {e}")
            return None
    
    async def consume_from_stream(self, stream: str, group: str, consumer: str,
                             count: int = 10, block_ms: int = 5000) -> List[Dict[str, Any]]:
        """从Stream消费消息 - 简化版"""
        try:
            definition = self._stream_definitions.get(stream)
            if not definition:
                logger.error(f"未知的Stream: {stream}")
                return []
            
            # 确保消费者组存在
            await self.ensure_consumer_group(stream, group)

            # 消费消息
            result = await self.redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={definition['key']: '>'},
                count=count,
                block=block_ms
            )
            
            messages = []
            if result:
                for stream_key, stream_messages in result:
                    for msg_id, msg_data in stream_messages:
                        # 🔧 简化的消息格式
                        messages.append({
                            'id': msg_id,
                            'stream': stream,
                            'data': self._decode_redis_dict(msg_data),  # 解码后的数据
                            'metadata': {
                                'stream_key': stream_key.decode('utf-8') if isinstance(stream_key, bytes) else stream_key,
                                'consumed_at': datetime.now().isoformat()
                            }
                        })
            
            return messages
            
        except Exception as e:
            logger.error(f"消费Stream失败 {stream}: {e}")
            return []
    
    async def ack_message(self, stream: str, group: str, message_id: str):
        """确认消息"""
        try:
            definition = self._stream_definitions.get(stream)
            if not definition:
                logger.error(f"未知的Stream: {stream}")
                return
            
            await self.redis.xack(definition['key'], group, message_id)
            
        except Exception as e:
            logger.error(f"确认消息失败: {e}")
    
    async def get_stream_info(self, stream: str = None) -> Dict[str, Any]:
        """获取Stream信息"""
        if stream:
            definition = self._stream_definitions.get(stream)
            if not definition:
                return {'error': f'未知的Stream: {stream}'}
            
            try:
                info = await self.redis.xinfo_stream(definition['key'])
                return {
                    'stream': stream,
                    'key': definition['key'],
                    'length': info['length'],
                    'max_length': definition['max_length'],
                    'description': definition['description'],
                    'priority': definition['priority']
                }
            except Exception as e:
                return {'error': str(e)}
        
        # 获取所有Stream信息
        result = {}
        for stream_name, definition in self._stream_definitions.items():
            try:
                info = await self.redis.xinfo_stream(definition['key'])
                result[stream_name] = {
                    'key': definition['key'],
                    'length': info['length'],
                    'max_length': definition['max_length'],
                    'description': definition['description'],
                    'priority': definition['priority']
                }
            except Exception as e:
                result[stream_name] = {'error': str(e)}
        
        return result
    
    # ========== 消费者组管理方法 ==========
    
    async def ensure_consumer_group(self, stream: str, group: str, is_test_group: bool = False) -> bool:
        """确保消费者组存在（使用优化的消费者组管理器）"""
        # 如果有消费者组管理器，优先使用
        if self.consumer_group_manager:
            try:
                definition = self._stream_definitions.get(stream)
                if not definition:
                    logger.error(f"未知的Stream: {stream}")
                    return False

                # 使用消费者组管理器确保组存在
                success = await self.consumer_group_manager.ensure_consumer_group(
                    stream=definition['key'],
                    group=group,
                    mkstream=True,
                    is_test_group=is_test_group
                )

                return success

            except Exception as e:
                # 如果消费者组管理器失败，使用降级处理
                logger.warning(f"消费者组管理器失败，使用降级处理: {e}")
                return await self._ensure_consumer_group_fallback(stream, group)
        else:
            # 使用降级处理
            return await self._ensure_consumer_group_fallback(stream, group)

    async def _ensure_consumer_group_fallback(self, stream: str, group: str) -> bool:
        """降级模式的消费者组确保方法"""
        try:
            definition = self._stream_definitions.get(stream)
            if not definition:
                logger.error(f"未知的Stream: {stream}")
                return False

            # 尝试创建消费者组
            try:
                await self.redis.xgroup_create(definition['key'], group, id="0", mkstream=True)
                logger.info(f"✅ 创建消费者组: {group} -> {definition['key']}")
                return True
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    # 消费者组已存在
                    return True
                logger.error(f"创建消费者组失败: {e}")
                return False

        except Exception as e:
            logger.error(f"确保消费者组失败: {e}")
            return False
    
    # ========== 监控和统计方法 ==========
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取总线统计（使用优化的错误处理）"""
        stats_context = {
            "operation": "get_stats",
            "component": "UnifiedRedisStreamBus",
            "total_streams": len(self._stream_definitions)
        }

        # 如果有错误处理器，使用统一错误处理
        if self.error_handler:
            try:
                result = await self._get_stats_with_error_handling(stats_context)
                return result
            except Exception as e:
                # 错误处理器本身失败，使用降级处理
                error_result = await self.error_handler.handle_error(e, stats_context)
                logger.error(f"获取统计失败（已通过错误处理器处理）: {e}")
                return {
                    'error': 'get_stats_failed',
                    'error_details': error_result,
                    'streams': {},
                    'total_streams': len(self._stream_definitions),
                    'timestamp': asyncio.get_event_loop().time()
                }
        else:
            # 降级处理：使用原有的try-catch逻辑
            return await self._get_stats_fallback(stats_context)

    async def _get_stats_with_error_handling(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """使用错误处理器的统计获取方法"""
        event_stats = {}
        stream_stats = {}
        errors = []

        # 获取事件总线统计（带错误处理）
        if hasattr(self.event_bus, 'get_event_stats'):
            try:
                event_stats = await self.event_bus.get_event_stats()
            except Exception as e:
                error_context = {**context, "sub_operation": "get_event_stats"}
                error_result = await self.error_handler.handle_error(e, error_context)
                errors.append({
                    "source": "event_bus",
                    "error_result": error_result
                })
                event_stats = {"error": "failed_to_get_stats"}

        # 获取Stream统计（使用优化的错误处理）
        for stream_name, definition in self._stream_definitions.items():
            stream_context = {
                **context,
                "stream": stream_name,
                "stream_key": definition['key'],
                "sub_operation": "xinfo_stream"
            }

            try:
                info = await self.redis.xinfo_stream(definition['key'])
                stream_stats[stream_name] = {
                    'key': definition['key'],
                    'length': info['length'],
                    'max_length': definition['max_length'],
                    'description': definition['description'],
                    'priority': definition['priority']
                }
            except Exception as e:
                # 使用错误处理器处理Stream获取错误
                error_result = await self.error_handler.handle_error(e, stream_context)

                # 记录错误详情
                errors.append({
                    "stream": stream_name,
                    "error_category": error_result.get("category"),
                    "recovered": error_result.get("recovered", False),
                    "action": error_result.get("action")
                })

                # 如果错误已恢复，可以尝试提供降级信息
                if error_result.get("recovered", False):
                    stream_stats[stream_name] = {
                        'key': definition['key'],
                        'error': 'temporarily_unavailable',
                        'recovery_action': error_result.get("action"),
                        'description': definition['description'],
                        'priority': definition['priority']
                    }
                else:
                    stream_stats[stream_name] = {
                        'key': definition['key'],
                        'error': str(e)[:200],
                        'error_category': error_result.get("category"),
                        'description': definition['description'],
                        'priority': definition['priority']
                    }

        # 构建最终结果
        result = {
            'event_bus': event_stats,
            'streams': stream_stats,
            'total_streams': len(self._stream_definitions),
            'timestamp': asyncio.get_event_loop().time()
        }

        # 如果有错误，添加错误摘要
        if errors:
            result['errors_summary'] = {
                'total_errors': len(errors),
                'recovered_errors': sum(1 for e in errors if e.get('recovered', False)),
                'by_category': {},
                'errors': errors[:10]  # 限制错误数量
            }

            # 按类别统计
            for error in errors:
                category = error.get('error_category', 'unknown')
                result['errors_summary']['by_category'][category] = \
                    result['errors_summary']['by_category'].get(category, 0) + 1

        return result

    async def _get_stats_fallback(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """降级模式的统计获取方法"""
        try:
            # 事件总线统计
            event_stats = await self.event_bus.get_event_stats() if hasattr(self.event_bus, 'get_event_stats') else {}

            # Stream统计
            stream_stats = {}
            for stream_name, definition in self._stream_definitions.items():
                try:
                    info = await self.redis.xinfo_stream(definition['key'])
                    stream_stats[stream_name] = {
                        'key': definition['key'],
                        'length': info['length'],
                        'max_length': definition['max_length'],
                        'description': definition['description'],
                        'priority': definition['priority']
                    }
                except Exception as e:
                    stream_stats[stream_name] = {'error': str(e), 'key': definition.get('key', '未知')}

            return {
                'event_bus': event_stats,
                'streams': stream_stats,
                'total_streams': len(self._stream_definitions),
                'timestamp': asyncio.get_event_loop().time()
            }

        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {'error': str(e)}
    
    def get_stream_definitions(self) -> Dict[str, Dict[str, Any]]:
        """获取Stream定义（只读）"""
        return dict(self._stream_definitions)
