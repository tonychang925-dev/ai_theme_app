"""
Redis消息总线 - 用于服务间通信
适配28字段表结构的事件支持
"""
import asyncio
import json
try:
    import redis.asyncio as aioredis
except ImportError:
    # 创建模拟的Redis客户端用于测试
    class MockRedis:
        class RedisError(Exception):
            pass
        
        class ResponseError(Exception):
            pass
        
        async def xgroup_create(self, *args, **kwargs):
            pass
        
        async def xadd(self, *args, **kwargs):
            return "mock_id"
        
        async def xread(self, *args, **kwargs):
            return []
        
        async def xreadgroup(self, *args, **kwargs):
            return []
        
        async def publish(self, *args, **kwargs):
            return 1
        
        async def xack(self, *args, **kwargs):
            return 1
        
        async def xinfo_stream(self, *args, **kwargs):
            return {'length': 0}
        
        async def xinfo_groups(self, *args, **kwargs):
            return []
        
        async def xpending_range(self, *args, **kwargs):
            return []
        
        async def xclaim(self, *args, **kwargs):
            return []
    
    aioredis = MockRedis()
from typing import Dict, Any, Optional, AsyncGenerator, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class RedisEventBus:
    """基于Redis的消息总线 - 适配28字段表结构"""
    
    def __init__(self, redis_client, config):
        self.redis = redis_client
        self.config = config
        
        # Streams配置 - 新增更多事件类型
        self.streams_config = {
            'theme_events': {
                'key': 'stream:theme_events',
                'group': f"{config.redis.consumer_group}:themes",
                'max_length': config.redis.stream_max_length,
                'description': '主题相关事件'
            },
            'relation_events': {
                'key': 'stream:relation_events',
                'group': f"{config.redis.consumer_group}:relations",
                'max_length': config.redis.stream_max_length,
                'description': '关联关系事件'
            },
            'cache_events': {
                'key': 'stream:cache_events',
                'group': f"{config.redis.consumer_group}:cache",
                'max_length': config.redis.stream_max_length,
                'description': '缓存相关事件'
            },
            'stats_events': {
                'key': 'stream:stats_events',
                'group': f"{config.redis.consumer_group}:stats",
                'max_length': config.redis.stream_max_length,
                'description': '统计事件'
            }
        }
        
        # 事件类型映射到Stream
        self.event_to_stream_map = {
            # 主题事件
            'theme_created': 'theme_events',
            'theme_updated': 'theme_events',
            'theme_deleted': 'theme_events',
            'theme_heat_changed': 'theme_events',
            'theme_mentioned': 'theme_events',
            'theme_code_changed': 'theme_events',
            
            # 关联事件
            'relation_created': 'relation_events',
            'relation_updated': 'relation_events',
            'relation_deleted': 'relation_events',
            
            # 缓存事件
            'cache_invalidated': 'cache_events',
            'cache_cleared': 'cache_events',
            'cache_hit': 'cache_events',
            'cache_miss': 'cache_events',
            
            # 统计事件
            'stats_updated': 'stats_events',
            'performance_metrics': 'stats_events',
            'database_health': 'stats_events'
        }
        
        # 启动时确保消费者组存在
        asyncio.create_task(self._ensure_consumer_groups())
    
    async def _ensure_consumer_groups(self):
        """确保所有消费者组都存在"""
        for stream_name, config in self.streams_config.items():
            try:
                await self.redis.xgroup_create(
                    config['key'],
                    config['group'],
                    id='0',
                    mkstream=True
                )
                logger.info(f"✅ 创建消费者组: {config['group']} - {config['description']}")
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    logger.error(f"创建消费者组失败 {stream_name}: {e}")
    
    async def publish(self, event_type: str, data: Dict[str, Any], stream: str = None, 
                     metadata: Dict[str, Any] = None):
        """
        发布事件 - 增强版
        
        Args:
            event_type: 事件类型，如 'theme_created'
            data: 事件数据
            stream: 指定Stream，如不指定则根据event_type自动选择
            metadata: 附加元数据
        """
        try:
            # 确定Stream
            if stream is None:
                stream_name = self.event_to_stream_map.get(
                    event_type, 
                    'theme_events'  # 默认主题事件
                )
                stream_config = self.streams_config[stream_name]
                stream_key = stream_config['key']
            else:
                stream_key = stream
            
            # 构建完整事件
            event = {
                'type': event_type,
                'data': data,
                'metadata': metadata or {},
                'timestamp': datetime.now().isoformat(),
                'timestamp_epoch': asyncio.get_event_loop().time(),
                'source': 'database_service',
                'version': '1.1'  # 事件版本
            }
            
            # 添加28字段结构相关信息
            if event_type.startswith('theme_'):
                event['schema_version'] = '28_fields_v1'
                if 'theme_data' in data:
                    event['data']['has_28_fields'] = all([
                        data.get('theme_data', {}).get('code'),
                        data.get('theme_data', {}).get('level1_category'),
                        data.get('theme_data', {}).get('level2_category'),
                        data.get('theme_data', {}).get('level3_category'),
                        data.get('theme_data', {}).get('tags')
                    ])
            
            # 发布到Stream
            await self.redis.xadd(
                stream_key,
                event,
                maxlen=self.config.redis.stream_max_length
            )
            
            logger.debug(f"📤 发布事件: {event_type} -> {stream_key}")
            
            # 同时发布到Pub/Sub（用于实时通知）
            pubsub_channel = f"events:{event_type}"
            await self.redis.publish(pubsub_channel, json.dumps(event, default=str))
            
            # 发布到通用事件频道
            await self.redis.publish("events:all", json.dumps(event, default=str))
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 发布事件失败 {event_type}: {e}")
            return False
    
    async def publish_theme_event(self, event_type: str, theme_data: Dict[str, Any], 
                                 changes: Dict[str, Any] = None, user: str = None):
        """
        发布主题事件 - 专用方法
        
        Args:
            event_type: 主题事件类型
            theme_data: 主题数据（28字段结构）
            changes: 变更的字段
            user: 操作用户
        """
        event_data = {
            'theme_id': theme_data.get('id'),
            'theme_name': theme_data.get('name'),
            'theme_code': theme_data.get('code'),
            'theme_data': theme_data,
            'changes': changes or {},
            'user': user or 'system'
        }
        
        # 添加分类信息
        if theme_data.get('level1_category'):
            event_data['category'] = {
                'level1': theme_data.get('level1_category'),
                'level2': theme_data.get('level2_category'),
                'level3': theme_data.get('level3_category')
            }
        
        # 添加标签信息
        if theme_data.get('tags'):
            tags = theme_data.get('tags', {})
            if isinstance(tags, dict):
                event_data['tags_info'] = {
                    'keywords': tags.get('keywords', [])[:5],
                    'heat_level': tags.get('heat_level'),
                    'industries': tags.get('industries', [])[:3]
                }
        
        return await self.publish(event_type, event_data)
    
    async def publish_relation_event(self, event_type: str, relation_data: Dict[str, Any],
                                    event_data: Dict[str, Any] = None, theme_data: Dict[str, Any] = None):
        """
        发布关联事件 - 专用方法
        
        Args:
            event_type: 关联事件类型
            relation_data: 关联数据
            event_data: 关联的事件数据
            theme_data: 关联的主题数据
        """
        event_payload = {
            'relation_id': relation_data.get('id'),
            'event_id': relation_data.get('event_id'),
            'theme_id': relation_data.get('theme_id'),
            'confidence': relation_data.get('confidence'),
            'confidence_level': relation_data.get('confidence_level'),
            'match_type': relation_data.get('match_type'),
            'matched_keywords': relation_data.get('matched_keywords', []),
            'relation_data': relation_data
        }
        
        if event_data:
            event_payload['event_info'] = {
                'title': event_data.get('title'),
                'keywords': event_data.get('keywords', [])[:5],
                'impact_industries': event_data.get('impact_industries', [])[:3]
            }
        
        if theme_data:
            event_payload['theme_info'] = {
                'name': theme_data.get('name'),
                'code': theme_data.get('code'),
                'heat_score': theme_data.get('heat_score'),
                'category': f"{theme_data.get('level1_category', '')}/{theme_data.get('level2_category', '')}"
            }
        
        return await self.publish(event_type, event_payload)
    
    async def publish_cache_event(self, event_type: str, cache_key: str, 
                                 operation: str, details: Dict[str, Any] = None):
        """
        发布缓存事件 - 专用方法
        
        Args:
            event_type: 缓存事件类型
            cache_key: 缓存键
            operation: 操作类型 (hit/miss/set/delete)
            details: 详细信息
        """
        event_data = {
            'cache_key': cache_key,
            'operation': operation,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        
        # 解析缓存键信息
        if cache_key and ':' in cache_key:
            parts = cache_key.split(':')
            if len(parts) >= 3:
                event_data['cache_info'] = {
                    'type': parts[1] if len(parts) > 1 else '',
                    'identifier': parts[2] if len(parts) > 2 else '',
                    'suffix': parts[3] if len(parts) > 3 else ''
                }
        
        return await self.publish(event_type, event_data)
    
    async def subscribe(self, stream: str = None, consumer_name: str = None, 
                       start_from: str = '>') -> AsyncGenerator:
        """
        订阅Stream事件 - 增强版
        
        Args:
            stream: Stream名称，如为None则订阅所有Stream
            consumer_name: 消费者名称
            start_from: 起始ID，'>'表示只接收新消息，'0-0'表示从头开始
            
        Yields:
            (stream_name, event_type, event_data) 元组
        """
        if stream and stream not in self.streams_config:
            raise ValueError(f"未知的Stream: {stream}")
        
        if stream:
            streams = [(self.streams_config[stream]['key'], start_from)]
        else:
            # 订阅所有Stream
            streams = [
                (config['key'], start_from) 
                for config in self.streams_config.values()
            ]
        
        consumer_name = consumer_name or f"consumer_{datetime.now().timestamp()}"
        
        logger.info(f"🔔 开始订阅Stream: {stream or 'all'} (消费者: {consumer_name})")
        
        while True:
            try:
                # 从Stream读取
                messages = await self.redis.xread(
                    streams=dict(streams),
                    count=10,
                    block=5000  # 5秒超时
                )
                
                if not messages:
                    continue
                
                for stream_key, message_list in messages:
                    stream_name = self._get_stream_name_by_key(stream_key)
                    
                    for message_id, message_data in message_list:
                        # 处理消息
                        event_type = message_data.get('type')
                        event_data = message_data.get('data', {})
                        
                        yield stream_name, event_type, event_data, message_id
                
            except asyncio.CancelledError:
                logger.info(f"取消订阅: {stream or 'all'}")
                break
            except Exception as e:
                logger.error(f"订阅事件失败: {e}")
                await asyncio.sleep(1)
    
    async def subscribe_with_group(self, stream: str, consumer_name: str = None) -> AsyncGenerator:
        """
        使用消费者组订阅Stream
        
        Args:
            stream: Stream名称
            consumer_name: 消费者名称
            
        Yields:
            (event_type, event_data) 元组
        """
        if stream not in self.streams_config:
            raise ValueError(f"未知的Stream: {stream}")
        
        config = self.streams_config[stream]
        consumer_name = consumer_name or f"consumer_{datetime.now().timestamp()}"
        
        logger.info(f"🔔 开始消费者组订阅: {stream} (消费者: {consumer_name})")
        
        last_id = '>'  # 只接收新消息
        
        while True:
            try:
                # 从Stream读取（消费者组模式）
                messages = await self.redis.xreadgroup(
                    groupname=config['group'],
                    consumername=consumer_name,
                    streams={config['key']: last_id},
                    count=10,
                    block=5000  # 5秒超时
                )
                
                if not messages:
                    continue
                
                for stream_key, message_list in messages:
                    for message_id, message_data in message_list:
                        # 处理消息
                        event_type = message_data.get('type')
                        event_data = message_data.get('data', {})
                        
                        yield event_type, event_data
                        
                        # 确认消息已处理
                        await self.redis.xack(config['key'], config['group'], message_id)
                
            except asyncio.CancelledError:
                logger.info(f"取消消费者组订阅: {stream}")
                break
            except Exception as e:
                logger.error(f"消费者组订阅失败 {stream}: {e}")
                await asyncio.sleep(1)
    
    def _get_stream_name_by_key(self, stream_key: str) -> str:
        """根据Stream键获取Stream名称"""
        for name, config in self.streams_config.items():
            if config['key'] == stream_key:
                return name
        return 'unknown'
    
    async def publish_to_channel(self, channel: str, data: Dict[str, Any]):
        """发布到指定频道（Pub/Sub）"""
        try:
            await self.redis.publish(channel, json.dumps(data, default=str))
            logger.debug(f"📤 发布到频道: {channel}")
        except Exception as e:
            logger.error(f"❌ 频道发布失败 {channel}: {e}")
    
    async def subscribe_to_channel(self, channel: str) -> AsyncGenerator:
        """订阅频道"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        
        logger.info(f"🔔 开始订阅频道: {channel}")
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    yield data
        except asyncio.CancelledError:
            logger.info(f"取消频道订阅: {channel}")
        finally:
            await pubsub.unsubscribe(channel)
    
    async def get_stream_info(self, stream: str = None) -> Dict[str, Any]:
        """获取Stream信息"""
        result = {}
        
        streams_to_check = [stream] if stream else self.streams_config.keys()
        
        for stream_name in streams_to_check:
            if stream_name not in self.streams_config:
                continue
                
            config = self.streams_config[stream_name]
            
            try:
                info = await self.redis.xinfo_stream(config['key'])
                groups = await self.redis.xinfo_groups(config['key'])
                
                result[stream_name] = {
                    'key': config['key'],
                    'description': config.get('description', ''),
                    'length': info['length'],
                    'max_length': config['max_length'],
                    'groups': [
                        {
                            'name': group['name'],
                            'consumers': group['consumers'],
                            'pending': group['pending'],
                            'last_delivered_id': group['last-delivered-id']
                        }
                        for group in groups
                    ]
                }
            except Exception as e:
                logger.error(f"获取Stream信息失败 {stream_name}: {e}")
                result[stream_name] = {'error': str(e)}
        
        return result if stream is None else result.get(stream, {})
    
    async def get_pending_messages(self, stream: str, group: str = None, count: int = 100) -> list:
        """获取待处理的消息"""
        if stream not in self.streams_config:
            return []
        
        config = self.streams_config[stream]
        group = group or config['group']
        
        try:
            pending = await self.redis.xpending_range(
                config['key'],
                group,
                min_idle_time=0,
                count=count
            )
            return pending
        except Exception as e:
            logger.error(f"获取待处理消息失败: {e}")
            return []
    
    async def claim_stuck_messages(self, stream: str, consumer: str, 
                                  group: str = None, min_idle_time: int = 60000) -> list:
        """认领卡住的消息"""
        if stream not in self.streams_config:
            return []
        
        config = self.streams_config[stream]
        group = group or config['group']
        
        try:
            pending = await self.get_pending_messages(stream, group, 100)
            
            stuck_message_ids = []
            for msg in pending:
                if msg['idle'] > min_idle_time:  # 空闲超过指定时间
                    stuck_message_ids.append(msg['message_id'])
            
            if stuck_message_ids:
                # 尝试认领
                claimed = await self.redis.xclaim(
                    config['key'],
                    group,
                    consumer,
                    min_idle_time=min_idle_time,
                    ids=stuck_message_ids
                )
                return claimed
            
            return []
        except Exception as e:
            logger.error(f"认领卡住消息失败: {e}")
            return []
    
    async def cleanup_old_messages(self, stream: str, max_age_hours: int = 24) -> int:
        """清理旧消息"""
        if stream not in self.streams_config:
            return 0
        
        config = self.streams_config[stream]
        
        try:
            # 获取Stream信息
            info = await self.redis.xinfo_stream(config['key'])
            total_before = info['length']
            
            # 这里需要根据实际情况实现清理逻辑
            # 例如，可以基于消息ID或时间戳进行清理
            
            # 简化实现：依赖Redis的maxlen自动清理
            logger.info(f"Stream {stream} 当前长度: {total_before}")
            return 0
            
        except Exception as e:
            logger.error(f"清理旧消息失败: {e}")
            return 0
    
    async def get_event_stats(self, hours: int = 24) -> Dict[str, Any]:
        """获取事件统计信息"""
        stats = {
            'total_events': 0,
            'by_stream': {},
            'by_type': {},
            'timeline': []
        }
        
        try:
            # 这里可以添加统计逻辑
            # 例如，通过分析Stream消息来生成统计
            
            for stream_name, config in self.streams_config.items():
                info = await self.get_stream_info(stream_name)
                if isinstance(info, dict) and 'length' in info:
                    stats['by_stream'][stream_name] = info['length']
                    stats['total_events'] += info['length']
            
            return stats
            
        except Exception as e:
            logger.error(f"获取事件统计失败: {e}")
            return stats