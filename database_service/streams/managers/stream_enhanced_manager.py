"""
Stream 增强的数据库管理器 - 重试增强版
包装原有的数据库管理器，添加 Stream 发布功能和重试机制
"""
import logging
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Type, Union
from dataclasses import asdict

from ...interface import DatabaseManager, ThemeRecord, EventThemeRelation
from .stream_manager import RedisStreamManager
from .interface import (
    RetryConfig, RetryStats, RetryEnhancedDatabaseManager,
    create_retry_config, should_retry_message, calculate_retry_delay
)

# 尝试导入重试管理器
try:
    from .utils.retry_manager import RetryManager, with_retry, RetryStrategy
    RETRY_MANAGER_AVAILABLE = True
except ImportError as e:
    RETRY_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)


class RetryEnhancedDatabaseManager(DatabaseManager, RetryEnhancedDatabaseManager):
    """重试增强的 Stream 数据库管理器"""
    
    def __init__(self, base_manager: DatabaseManager, 
                 stream_manager: RedisStreamManager,
                 producers: Dict[str, Any],
                 config: Any,
                 enable_retry: bool = True,
                 retry_config: Optional[Dict[str, Any]] = None):
        """
        初始化重试增强管理器
        
        Args:
            base_manager: 基础数据库管理器
            stream_manager: Redis Stream 管理器
            producers: 生产者字典
            config: 配置对象
            enable_retry: 是否启用重试功能
            retry_config: 重试配置
        """
        self.base_manager = base_manager
        self.stream_manager = stream_manager
        self.producers = producers
        self.config = config
        self.enable_retry = enable_retry and RETRY_MANAGER_AVAILABLE
        
        # 重试配置
        self.retry_config = retry_config or {}
        self._default_retry_configs = {
            'publish_theme_event': create_retry_config(max_retries=3, strategy="exponential"),
            'publish_news_event': create_retry_config(max_retries=2, strategy="fixed"),
            'publish_event_theme_relation': create_retry_config(max_retries=3, strategy="exponential"),
            'database_operation': create_retry_config(max_retries=3, strategy="exponential")
        }
        
        # 更新默认配置
        for key, config in self.retry_config.items():
            if key in self._default_retry_configs:
                self._default_retry_configs[key] = create_retry_config(**config)
        
        # 重试管理器
        self._retry_managers = {}
        
        # 统计信息
        self.stats = {
            'stream_publishes': 0,
            'stream_errors': 0,
            'stream_events': {
                'theme_create': 0,
                'theme_update': 0,
                'theme_heat_increment': 0,
                'event_theme_relation_create': 0,
                'news_publish': 0
            }
        }
        
        # 重试统计
        self.retry_stats = RetryStats()
        
        logger.info("✅ 创建重试增强的 Stream 数据库管理器")
        logger.info(f"   - 重试功能: {'启用' if self.enable_retry else '禁用'}")
    
    def _get_retry_manager(self, operation_type: str) -> Optional[RetryManager]:
        """获取操作类型的重试管理器"""
        if not self.enable_retry or not RETRY_MANAGER_AVAILABLE:
            return None
        
        if operation_type not in self._retry_managers:
            config = self._default_retry_configs.get(
                operation_type, 
                self._default_retry_configs.get('database_operation')
            )
            
            self._retry_managers[operation_type] = RetryManager(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                strategy=config.strategy,
                max_delay=config.max_delay,
                jitter=config.jitter,
                retry_on_exception=config.retry_on_exception,
                stop_on_exception=config.stop_on_exception
            )
        
        return self._retry_managers[operation_type]
    
    async def _execute_with_retry(self, func, operation_type: str, 
                                 context: Optional[Dict] = None, *args, **kwargs):
        """带重试执行操作"""
        retry_manager = self._get_retry_manager(operation_type)
        
        if not retry_manager:
            return await func(*args, **kwargs)
        
        try:
            result = await retry_manager.execute_with_retry(
                func, *args, 
                context=context or {"operation": operation_type},
                **kwargs
            )
            
            # 更新重试统计
            if retry_manager.stats["total_retries"] > 0:
                self.retry_stats.total_retries += retry_manager.stats["total_retries"]
                self.retry_stats.successful_retries += 1
                self.retry_stats.last_retry_time = datetime.now()
                self.retry_stats.update_success_rate()
                
                # 记录历史
                self.retry_stats.retry_history.append({
                    "operation": operation_type,
                    "timestamp": datetime.now().isoformat(),
                    "attempts": retry_manager.stats["total_retries"],
                    "success": True
                })
            
            return result
            
        except Exception as e:
            logger.error(f"带重试的 {operation_type} 失败: {e}")
            self.retry_stats.failed_retries += 1
            raise
    
    # ========== 重试配置管理 ==========
    
    async def enable_retry_function(self, enable: bool = True):
        """启用或禁用重试功能"""
        old_status = self.enable_retry
        self.enable_retry = enable and RETRY_MANAGER_AVAILABLE
        
        if old_status != self.enable_retry:
            if self.enable_retry:
                logger.info("✅ 重试功能已启用")
            else:
                logger.info("⏸️  重试功能已禁用")
    
    async def get_retry_config(self, operation_type: str = None) -> RetryConfig:
        """获取重试配置"""
        if operation_type and operation_type in self._default_retry_configs:
            return self._default_retry_configs[operation_type]
        return create_retry_config()
    
    async def update_retry_config(self, config_updates: Dict[str, Any], 
                                 operation_type: str = None):
        """更新重试配置"""
        if operation_type:
            # 更新特定操作配置
            if operation_type in self._default_retry_configs:
                self._default_retry_configs[operation_type] = create_retry_config(**config_updates)
                logger.info(f"✅ 更新 {operation_type} 重试配置")
            else:
                self._default_retry_configs[operation_type] = create_retry_config(**config_updates)
                logger.info(f"✅ 添加 {operation_type} 重试配置")
            
            # 重置对应的重试管理器
            if operation_type in self._retry_managers:
                del self._retry_managers[operation_type]
        else:
            # 更新全局配置
            self.retry_config.update(config_updates)
            logger.info("✅ 更新全局重试配置")
    
    async def get_retry_stats(self) -> RetryStats:
        """获取重试统计"""
        return self.retry_stats
    
    # ========== Stream 发布方法（带重试） ==========
    
    async def publish_theme_event(self, theme_data: Dict[str, Any], event_type: str = "update"):
        """发布主题事件到 Stream（带重试）"""
        return await self._execute_with_retry(
            self._publish_theme_event_internal,
            "publish_theme_event",
            context={"operation": "publish_theme_event", "event_type": event_type},
            theme_data=theme_data,
            event_type=event_type
        )
    
    async def _publish_theme_event_internal(self, theme_data: Dict[str, Any], event_type: str = "update"):
        """内部发布主题事件方法"""
        try:
            if 'news_producer' in self.producers:
                producer = self.producers['news_producer']
            elif 'theme' in self.producers:
                producer = self.producers['theme']
            else:
                logger.warning("没有可用的生产者，跳过 Stream 发布")
                return None
            
            # 添加元数据
            event_data = {
                **theme_data,
                "event_type": f"theme_{event_type}",
                "timestamp": datetime.now().isoformat(),
                "source": "database_manager"
            }
            
            # 发布到 Stream
            message_id = await producer.publish(event_data)
            
            if message_id:
                self.stats['stream_publishes'] += 1
                self.stats['stream_events'][f'theme_{event_type}'] += 1
                logger.debug(f"✅ 发布主题 {event_type} 事件到 Stream: {message_id}")
            
            return message_id
            
        except Exception as e:
            self.stats['stream_errors'] += 1
            logger.error(f"发布主题事件失败: {e}")
            return None
    
    async def publish_news_event(self, news_data: Dict[str, Any]):
        """发布新闻事件到 Stream（带重试）"""
        return await self._execute_with_retry(
            self._publish_news_event_internal,
            "publish_news_event",
            context={"operation": "publish_news_event"},
            news_data=news_data
        )
    
    async def _publish_news_event_internal(self, news_data: Dict[str, Any]):
        """内部发布新闻事件方法"""
        try:
            if 'news' in self.producers:
                producer = self.producers['news']
            elif 'news_producer' in self.producers:
                producer = self.producers['news_producer']
            else:
                logger.warning("没有可用的新闻生产者，跳过 Stream 发布")
                return None
            
            # 发布到 Stream
            message_id = await producer.publish(news_data)
            
            if message_id:
                self.stats['stream_publishes'] += 1
                self.stats['stream_events']['news_publish'] += 1
                logger.info(f"✅ 发布新闻事件到 Stream: {message_id}")
            
            return message_id
            
        except Exception as e:
            self.stats['stream_errors'] += 1
            logger.error(f"发布新闻事件失败: {e}")
            return None
    
    async def publish_event_theme_relation(self, relation_data: Dict[str, Any]):
        """发布事件-主题关联事件到 Stream（带重试）"""
        return await self._execute_with_retry(
            self._publish_event_theme_relation_internal,
            "publish_event_theme_relation",
            context={"operation": "publish_event_theme_relation"},
            relation_data=relation_data
        )
    
    async def _publish_event_theme_relation_internal(self, relation_data: Dict[str, Any]):
        """内部发布事件-主题关联事件方法"""
        try:
            if 'event' in self.producers:
                producer = self.producers['event']
            else:
                logger.warning("没有可用的事件生产者，跳过 Stream 发布")
                return None
            
            # 发布到 Stream
            message_id = await producer.publish(relation_data)
            
            if message_id:
                self.stats['stream_publishes'] += 1
                self.stats['stream_events']['event_theme_relation_create'] += 1
                logger.debug(f"✅ 发布事件-主题关联事件到 Stream: {message_id}")
            
            return message_id
            
        except Exception as e:
            self.stats['stream_errors'] += 1
            logger.error(f"发布事件-主题关联事件失败: {e}")
            return None
    
    # ========== 智能发布方法 ==========
    
    async def smart_publish(self, data: Dict[str, Any], 
                           data_type: Optional[str] = None,
                           retry_config: Optional[RetryConfig] = None) -> Optional[str]:
        """智能发布（自动识别数据类型）"""
        # 自动检测数据类型
        if data_type is None:
            if "title" in data and "content" in data:
                data_type = "news"
            elif "theme_id" in data:
                data_type = "theme"
            elif "event_id" in data and "theme_id" in data:
                data_type = "relation"
            else:
                data_type = "generic"
        
        # 根据数据类型选择发布方法
        if data_type == "news":
            return await self.publish_news_event(data)
        elif data_type == "theme":
            event_type = data.get("action", "update")
            return await self.publish_theme_event(data, event_type)
        elif data_type == "relation":
            return await self.publish_event_theme_relation(data)
        else:
            # 通用发布
            try:
                message_id = await self.stream_manager.publish("generic:events", data)
                if message_id:
                    self.stats['stream_publishes'] += 1
                return message_id
            except Exception as e:
                logger.error(f"通用发布失败: {e}")
                return None
    
    async def batch_publish(self, items: List[Dict[str, Any]], 
                           data_type: Optional[str] = None,
                           max_concurrent: int = 5,
                           retry_config: Optional[RetryConfig] = None) -> List[Optional[str]]:
        """批量发布（带并发控制和重试）"""
        import asyncio
        
        logger.info(f"📦 批量发布开始: {len(items)} 条数据")
        
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def publish_with_semaphore(item):
            async with semaphore:
                return await self.smart_publish(item, data_type, retry_config)
        
        # 创建任务
        tasks = [publish_with_semaphore(item) for item in items]
        
        # 并发执行
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            success_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"批量发布失败第 {i} 项: {result}")
                    results[i] = None
                elif result:
                    success_count += 1
            
            logger.info(f"📦 批量发布完成: {success_count}/{len(items)} 成功")
            
        except Exception as e:
            logger.error(f"批量发布整体失败: {e}")
            results = [None] * len(items)
        
        return results
    
    # ========== 增强的基础管理器方法（带重试） ==========
    
    async def get_theme(self, theme_id: int) -> Optional[ThemeRecord]:
        """获取主题（带重试）"""
        return await self._execute_with_retry(
            self.base_manager.get_theme,
            "database_operation",
            context={"operation": "get_theme", "theme_id": theme_id},
            theme_id=theme_id
        )
    
    async def create_theme(self, name: str, code: str, **kwargs) -> Optional[ThemeRecord]:
        """创建主题（重写以发布 Stream 事件，带重试）"""
        # 调用基础管理器创建主题
        theme = await self._execute_with_retry(
            self.base_manager.create_theme,
            "database_operation",
            context={"operation": "create_theme", "name": name, "code": code},
            name=name,
            code=code,
            **kwargs
        )
        
        if theme:
            # 发布到 Stream
            theme_data = {
                "theme_id": theme.id,
                "name": theme.name,
                "code": theme.code,
                "action": "create",
                "timestamp": datetime.now().isoformat()
            }
            
            await self.publish_theme_event(theme_data, "create")
            
            logger.info(f"✅ 创建主题并发布到 Stream: {name} ({code})")
        
        return theme
    
    async def update_theme(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
        """更新主题（重写以发布 Stream 事件，带重试）"""
        # 调用基础管理器更新主题
        theme = await self._execute_with_retry(
            self.base_manager.update_theme,
            "database_operation",
            context={"operation": "update_theme", "theme_id": theme_id},
            theme_id=theme_id,
            updates=updates
        )
        
        if theme:
            # 发布到 Stream
            update_data = {
                "theme_id": theme_id,
                "updates": updates,
                "action": "update",
                "timestamp": datetime.now().isoformat()
            }
            
            await self.publish_theme_event(update_data, "update")
            
            logger.debug(f"✅ 更新主题并发布到 Stream: {theme_id}")
        
        return theme
    
    async def increment_theme_heat(self, theme_id: int, increment: int = 1) -> None:
        """增加主题热度（重写以发布 Stream 事件，带重试）"""
        # 调用基础管理器增加热度
        await self._execute_with_retry(
            self.base_manager.increment_theme_heat,
            "database_operation",
            context={"operation": "increment_theme_heat", "theme_id": theme_id},
            theme_id=theme_id,
            increment=increment
        )
        
        # 发布到 Stream
        heat_data = {
            "theme_id": theme_id,
            "increment": increment,
            "action": "heat_increment",
            "timestamp": datetime.now().isoformat()
        }
        
        await self.publish_theme_event(heat_data, "heat_increment")
        
        logger.debug(f"✅ 增加主题热度并发布到 Stream: {theme_id} +{increment}")
    
    async def create_event_theme_relation(self, event_id: int, theme_id: int, **kwargs) -> Optional[EventThemeRelation]:
        """创建事件-主题关联（重写以发布 Stream 事件，带重试）"""
        # 调用基础管理器创建关联
        relation = await self._execute_with_retry(
            self.base_manager.create_event_theme_relation,
            "database_operation",
            context={"operation": "create_event_theme_relation", 
                    "event_id": event_id, "theme_id": theme_id},
            event_id=event_id,
            theme_id=theme_id,
            **kwargs
        )
        
        if relation:
            # 发布到 Stream
            relation_data = {
                "event_id": event_id,
                "theme_id": theme_id,
                "confidence": getattr(relation, 'confidence', kwargs.get('confidence', 0.0)),
                "action": "create_relation",
                "timestamp": datetime.now().isoformat()
            }
            
            await self.publish_event_theme_relation(relation_data)
            
            logger.debug(f"✅ 创建事件-主题关联并发布到 Stream: event={event_id}, theme={theme_id}")
        
        return relation
    
    async def publish_news(self, news_data: Dict[str, Any]) -> Optional[str]:
        """发布新闻（带重试）"""
        # 验证新闻数据
        required_fields = ["id", "title", "content"]
        for field in required_fields:
            if field not in news_data:
                raise ValueError(f"新闻数据缺少必要字段: {field}")
        
        # 发布到 Stream（带重试）
        message_id = await self.publish_news_event(news_data)
        
        # 同时保存到数据库（如果需要，也带重试）
        if hasattr(self.base_manager, 'save_news'):
            try:
                await self._execute_with_retry(
                    self.base_manager.save_news,
                    "database_operation",
                    context={"operation": "save_news", "news_id": news_data.get("id")},
                    news_data=news_data
                )
            except Exception as e:
                logger.warning(f"保存新闻到数据库失败: {e}")
        
        return message_id
    
    # ========== 代理所有其他方法到基础管理器 ==========
    
    def __getattr__(self, name):
        """代理所有未定义的方法到基础管理器"""
        return getattr(self.base_manager, name)
    
    # ========== 统计和监控方法 ==========
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        base_stats = await self.base_manager.get_stats()
        
        # 添加 Stream 和重试统计
        enhanced_stats = {
            **base_stats,
            "stream_enhanced": True,
            "retry_enabled": self.enable_retry,
            "stream_stats": {
                "stream_publishes": self.stats['stream_publishes'],
                "stream_errors": self.stats['stream_errors'],
                "stream_events": self.stats['stream_events'],
                "success_rate": self.stats['stream_publishes'] / max(self.stats['stream_publishes'] + self.stats['stream_errors'], 1)
            },
            "retry_stats": self.retry_stats.to_dict(),
            "retry_manager_available": RETRY_MANAGER_AVAILABLE
        }
        
        return enhanced_stats
    
    async def get_stream_stats(self) -> Dict[str, Any]:
        """获取 Stream 统计信息"""
        return {
            "stream_publishes": self.stats['stream_publishes'],
            "stream_errors": self.stats['stream_errors'],
            "stream_events": self.stats['stream_events'],
            "success_rate": self.stats['stream_publishes'] / max(self.stats['stream_publishes'] + self.stats['stream_errors'], 1)
        }
    
    async def health_check(self) -> bool:
        """健康检查（包含 Stream 和重试检查）"""
        # 检查基础管理器健康状态
        base_healthy = await self._execute_with_retry(
            self.base_manager.health_check,
            "health_check",
            context={"operation": "health_check_base"},
            enable_retry=False  # 健康检查本身不重试
        )
        
        # 检查 Stream 连接
        stream_healthy = True
        try:
            await self._execute_with_retry(
                self._check_stream_connection,
                "health_check",
                context={"operation": "health_check_stream"},
                enable_retry=False
            )
        except Exception as e:
            stream_healthy = False
            logger.warning(f"Stream 健康检查失败: {e}")
        
        return base_healthy and stream_healthy
    
    async def _check_stream_connection(self):
        """检查 Stream 连接"""
        if hasattr(self.stream_manager, 'redis'):
            await self.stream_manager.redis.ping()
    
    async def health_check_with_retry(self) -> Dict[str, Any]:
        """带重试的健康检查（返回详细信息）"""
        try:
            # 带重试的健康检查
            health_result = await self._execute_with_retry(
                self._detailed_health_check,
                "health_check",
                context={"operation": "detailed_health_check"}
            )
            
            return health_result
            
        except Exception as e:
            logger.error(f"带重试的健康检查失败: {e}")
            return {
                "overall": False,
                "database": {"healthy": False, "error": str(e)},
                "stream": {"healthy": False, "error": "检查失败"},
                "retry": {"healthy": False, "error": "检查失败"},
                "timestamp": datetime.now().isoformat()
            }
    
    async def _detailed_health_check(self) -> Dict[str, Any]:
        """详细健康检查"""
        base_healthy = False
        stream_healthy = False
        retry_healthy = self.enable_retry and RETRY_MANAGER_AVAILABLE
        
        base_error = None
        stream_error = None
        
        # 检查基础管理器
        try:
            base_healthy = await self.base_manager.health_check()
        except Exception as e:
            base_error = str(e)
        
        # 检查 Stream 连接
        try:
            if hasattr(self.stream_manager, 'redis'):
                await self.stream_manager.redis.ping()
                stream_healthy = True
        except Exception as e:
            stream_error = str(e)
        
        return {
            "overall": base_healthy and stream_healthy and retry_healthy,
            "database": {
                "healthy": base_healthy,
                "error": base_error,
                "message": "数据库连接正常" if base_healthy else f"数据库连接异常: {base_error}"
            },
            "stream": {
                "healthy": stream_healthy,
                "error": stream_error,
                "message": "Stream 连接正常" if stream_healthy else f"Stream 连接异常: {stream_error}"
            },
            "retry": {
                "healthy": retry_healthy,
                "enabled": self.enable_retry,
                "available": RETRY_MANAGER_AVAILABLE,
                "message": "重试系统正常" if retry_healthy else "重试系统异常"
            },
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_enhanced_stats_with_retry(self) -> Dict[str, Any]:
        """获取包含重试统计的增强统计信息"""
        try:
            # 获取原有统计
            stats = await self.get_stats()
            
            # 添加重试详细信息
            stats["retry_details"] = {
                "default_configs": {
                    k: v.to_dict() for k, v in self._default_retry_configs.items()
                },
                "retry_managers_count": len(self._retry_managers),
                "active_retry_operations": len([
                    m for m in self._retry_managers.values() 
                    if hasattr(m, 'stats') and m.stats.get('total_retries', 0) > 0
                ])
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取增强重试统计失败: {e}")
            return await self.get_stats()
    
    def print_retry_report(self):
        """打印重试报告"""
        print("\n📊 重试增强数据库管理器报告")
        print("=" * 60)
        
        # 基本统计
        print(f"重试功能: {'✅ 启用' if self.enable_retry else '⏸️ 禁用'}")
        print(f"重试管理器可用: {'✅ 是' if RETRY_MANAGER_AVAILABLE else '❌ 否'}")
        
        # 操作统计
        print(f"\n操作统计:")
        print(f"  Stream 发布: {self.stats['stream_publishes']}")
        print(f"  Stream 错误: {self.stats['stream_errors']}")
        print(f"  发布成功率: {self.stats['stream_publishes'] / max(self.stats['stream_publishes'] + self.stats['stream_errors'], 1):.1%}")
        
        # 重试统计
        retry_stats = self.retry_stats.to_dict()
        print(f"\n重试统计:")
        print(f"  总重试次数: {retry_stats['total_retries']}")
        print(f"  成功重试: {retry_stats['successful_retries']}")
        print(f"  失败重试: {retry_stats['failed_retries']}")
        print(f"  重试成功率: {retry_stats['retry_success_rate']:.1%}")
        
        # 默认配置
        print(f"\n默认重试配置:")
        for op, config in self._default_retry_configs.items():
            print(f"  {op}: {config.strategy.value}策略, 最多{config.max_retries}次重试")
        
        print("=" * 60)
    
    async def close(self):
        """关闭连接"""
        # 关闭基础管理器
        await self.base_manager.close()
        
        # 关闭 Stream 连接
        if hasattr(self.stream_manager, 'redis'):
            await self.stream_manager.redis.close()
        
        logger.info("✅ 重试增强的 Stream 数据库管理器已关闭")


# 向后兼容的别名
StreamEnhancedDatabaseManager = RetryEnhancedDatabaseManager


# 示例：使用装饰器的重试版本
if RETRY_MANAGER_AVAILABLE:
    from .utils.retry_manager import with_retry
    
    class DecoratedRetryEnhancedDatabaseManager(RetryEnhancedDatabaseManager):
        """使用装饰器的重试增强管理器"""
        
        @with_retry(max_retries=3, base_delay=1.0, strategy="exponential")
        async def create_theme_with_retry(self, name: str, code: str, **kwargs) -> Optional[ThemeRecord]:
            """使用装饰器的创建主题方法"""
            # 调用基础管理器创建主题
            theme = await self.base_manager.create_theme(name, code, **kwargs)
            
            if theme:
                # 发布到 Stream
                theme_data = {
                    "theme_id": theme.id,
                    "name": theme.name,
                    "code": theme.code,
                    "action": "create",
                    "timestamp": datetime.now().isoformat()
                }
                
                await self.publish_theme_event(theme_data, "create")
                
                logger.info(f"✅ 创建主题并发布到 Stream: {name} ({code})")
            
            return theme
        
        @with_retry(max_retries=3, base_delay=0.5, strategy="exponential")
        async def update_theme_with_retry(self, theme_id: int, updates: Dict[str, Any]) -> Optional[ThemeRecord]:
            """使用装饰器的更新主题方法"""
            # 调用基础管理器更新主题
            theme = await self.base_manager.update_theme(theme_id, updates)
            
            if theme:
                # 发布到 Stream
                update_data = {
                    "theme_id": theme_id,
                    "updates": updates,
                    "action": "update",
                    "timestamp": datetime.now().isoformat()
                }
                
                await self.publish_theme_event(update_data, "update")
                
                logger.debug(f"✅ 更新主题并发布到 Stream: {theme_id}")
            
            return theme


# 便捷函数
async def create_retry_enhanced_manager(
    base_manager: DatabaseManager,
    stream_manager: RedisStreamManager,
    producers: Dict[str, Any],
    config: Any,
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> RetryEnhancedDatabaseManager:
    """创建重试增强管理器的便捷函数"""
    manager = RetryEnhancedDatabaseManager(
        base_manager=base_manager,
        stream_manager=stream_manager,
        producers=producers,
        config=config,
        enable_retry=enable_retry,
        retry_config=retry_config
    )
    
    logger.info("✅ 重试增强管理器创建完成")
    return manager