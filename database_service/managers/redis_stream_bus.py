# database_service/managers/redis_stream_bus.py

"""
统一的Redis Stream总线
合并原有的事件总线和新的Stream功能
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List

try:
    import redis.asyncio as aioredis
except ImportError:
    # 模拟Redis客户端（用于测试）
    aioredis = None

logger = logging.getLogger(__name__)


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
        
        logger.info(f"🚀 创建统一的Redis Stream总线，加载了 {len(self._stream_definitions)} 个Stream定义")
    
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
                            'data': dict(msg_data),  # 原始数据
                            'metadata': {
                                'stream_key': stream_key,
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
    
    async def ensure_consumer_group(self, stream: str, group: str):
        """确保消费者组存在"""
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
        """获取总线统计"""
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