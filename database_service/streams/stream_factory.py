"""
Stream 增强工厂 - 重试增强版
在原有工厂基础上添加 Stream 管理器创建功能和重试配置
"""
import logging
from typing import Optional, Dict, Any

# 将相对导入改为绝对导入
from database_service.config import DatabaseConfig, get_config as get_base_config
from database_service.streams.stream_config import EnhancedDatabaseConfig, get_enhanced_config
from database_service.streams.stream_manager import RedisStreamManager
from database_service.streams.producers.news_producer import NewsProducer
from database_service.streams.producers.event_producer import EventProducer
from database_service.streams.producers.theme_producer import ThemeProducer
from database_service.managers.redis_cached_manager import RedisCachedDatabaseManager
from database_service.streams.utils.retry_manager import RetryManager, RetryStrategy
from database_service.streams.stream_interface import RetryConfig, create_retry_config

logger = logging.getLogger(__name__)


class RetryEnhancedFactory:
    """重试增强的 Stream 工厂"""
    
    def __init__(self):
        self._stream_managers = {}
        self._producers = {}
        self._retry_managers = {}
        self._initialized = False
        self.default_retry_config = create_retry_config()
        
        # 默认重试配置
        self._default_retry_configs = {
            'stream_manager': {
                'max_retries': 3,
                'base_delay': 1.0,
                'strategy': 'exponential',
                'retry_on_exception': ['ConnectionError', 'TimeoutError']
            },
            'producer': {
                'max_retries': 2,
                'base_delay': 0.5,
                'strategy': 'fixed'
            },
            'database_operation': {
                'max_retries': 3,
                'base_delay': 0.5,
                'strategy': 'exponential'
            }
        }
    
    async def initialize(self, config: Optional[EnhancedDatabaseConfig] = None,
                        default_retry_config: Optional[RetryConfig] = None):
        """初始化工厂（带重试配置）"""
        if self._initialized:
            logger.info("🔄 工厂已初始化，更新配置")
            return
        
        logger.info("🚀 初始化重试增强的 Stream 工厂...")
        
        try:
            # 获取配置
            self.config = config or get_enhanced_config()
            
            # 设置默认重试配置
            if default_retry_config:
                self.default_retry_config = default_retry_config
            
            # 检查是否启用 Stream
            if not self.config.enable_stream_processing:
                logger.info("⏭️  Stream 处理未启用，跳过初始化")
                self._initialized = True
                return
            
            if not self.config.redis.enabled:
                logger.warning("⚠️  Redis 未启用，无法初始化 Stream")
                self._initialized = True
                return
            
            logger.info("✅ 重试增强的 Stream 工厂初始化完成")
            logger.info(f"   - 默认重试策略: {self.default_retry_config.strategy.value}")
            logger.info(f"   - 默认最大重试: {self.default_retry_config.max_retries}次")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ 重试增强的 Stream 工厂初始化失败: {e}")
            raise
    
    def update_default_retry_config(self, config_type: str, config_updates: Dict[str, Any]):
        """更新默认重试配置"""
        if config_type in self._default_retry_configs:
            self._default_retry_configs[config_type].update(config_updates)
            logger.info(f"✅ 更新 {config_type} 的默认重试配置")
        else:
            self._default_retry_configs[config_type] = config_updates
            logger.info(f"✅ 添加 {config_type} 的默认重试配置")
    
    def get_default_retry_config(self, config_type: str) -> RetryConfig:
        """获取默认重试配置"""
        if config_type in self._default_retry_configs:
            return RetryConfig.from_dict(self._default_retry_configs[config_type])
        return self.default_retry_config
    
    async def create_stream_manager(self, redis_url: str = None,
                                   retry_config: Optional[RetryConfig] = None) -> RedisStreamManager:
        """创建带重试的 Redis Stream 管理器"""
        try:
            if not self._initialized:
                await self.initialize()
            
            if not self.config.redis_stream.enabled:
                raise ValueError("Redis Stream 未启用")
            
            # 使用配置中的 Redis URL 或参数
            if redis_url is None:
                if self.config.redis.password:
                    redis_url = f"redis://:{self.config.redis.password}@{self.config.redis.host}:{self.config.redis.port}/{self.config.redis.db}"
                else:
                    redis_url = f"redis://{self.config.redis.host}:{self.config.redis.port}/{self.config.redis.db}"
            
            # 获取重试配置
            config = retry_config or self.get_default_retry_config('stream_manager')
            
            # 创建带重试的 Stream 管理器
            stream_manager = RedisStreamManager(redis_url)
            
            # 创建重试管理器
            retry_manager = RetryManager(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                strategy=config.strategy,
                max_delay=config.max_delay,
                jitter=config.jitter,
                retry_on_exception=config.retry_on_exception,
                stop_on_exception=config.stop_on_exception
            )
            
            # 缓存管理器
            manager_key = redis_url
            self._stream_managers[manager_key] = stream_manager
            self._retry_managers[manager_key] = retry_manager
            
            # 使用重试连接
            try:
                await retry_manager.execute_with_retry(
                    stream_manager.connect,
                    context={"operation": "connect_stream_manager", "url": redis_url}
                )
            except Exception as e:
                logger.error(f"Stream 管理器连接失败: {e}")
                raise
            
            logger.info(f"✅ 创建带重试的 Redis Stream 管理器: {redis_url}")
            logger.info(f"   - 重试配置: {config.strategy.value}策略, 最多{config.max_retries}次重试")
            
            return stream_manager
            
        except Exception as e:
            logger.error(f"创建带重试的 Redis Stream 管理器失败: {e}")
            raise
    
    async def create_news_producer(self, stream_manager: RedisStreamManager = None,
                                  retry_config: Optional[RetryConfig] = None) -> NewsProducer:
        """创建带重试的新闻生产者"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # 如果没有提供 Stream 管理器，创建一个
            if stream_manager is None:
                stream_manager = await self.create_stream_manager(retry_config=retry_config)
            
            # 获取重试配置
            config = retry_config or self.get_default_retry_config('producer')
            
            # 创建新闻生产者
            producer = NewsProducer(stream_manager)
            
            # 为生产者添加重试管理器
            producer_key = f"news_{id(producer)}"
            self._producers[producer_key] = producer
            self._retry_managers[producer_key] = RetryManager(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                strategy=config.strategy,
                max_delay=config.max_delay,
                jitter=config.jitter
            )
            
            logger.info("✅ 创建带重试的新闻生产者")
            
            return producer
            
        except Exception as e:
            logger.error(f"创建带重试的新闻生产者失败: {e}")
            raise
    
    async def create_event_producer(self, stream_manager: RedisStreamManager = None,
                                   retry_config: Optional[RetryConfig] = None) -> EventProducer:
        """创建带重试的事件生产者"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # 如果没有提供 Stream 管理器，创建一个
            if stream_manager is None:
                stream_manager = await self.create_stream_manager(retry_config=retry_config)
            
            # 获取重试配置
            config = retry_config or self.get_default_retry_config('producer')
            
            # 创建事件生产者
            producer = EventProducer(stream_manager)
            
            # 为生产者添加重试管理器
            producer_key = f"event_{id(producer)}"
            self._producers[producer_key] = producer
            self._retry_managers[producer_key] = RetryManager(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                strategy=config.strategy,
                max_delay=config.max_delay,
                jitter=config.jitter
            )
            
            logger.info("✅ 创建带重试的事件生产者")
            
            return producer
            
        except Exception as e:
            logger.error(f"创建带重试的事件生产者失败: {e}")
            raise
    
    async def create_theme_producer(self, stream_manager: RedisStreamManager = None,
                                   retry_config: Optional[RetryConfig] = None) -> ThemeProducer:
        """创建带重试的主题生产者"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # 如果没有提供 Stream 管理器，创建一个
            if stream_manager is None:
                stream_manager = await self.create_stream_manager(retry_config=retry_config)
            
            # 获取重试配置
            config = retry_config or self.get_default_retry_config('producer')
            
            # 创建主题生产者
            producer = ThemeProducer(stream_manager)
            
            # 为生产者添加重试管理器
            producer_key = f"theme_{id(producer)}"
            self._producers[producer_key] = producer
            self._retry_managers[producer_key] = RetryManager(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                strategy=config.strategy,
                max_delay=config.max_delay,
                jitter=config.jitter
            )
            
            logger.info("✅ 创建带重试的主题生产者")
            
            return producer
            
        except Exception as e:
            logger.error(f"创建带重试的主题生产者失败: {e}")
            raise
    
    async def create_all_producers(self, retry_config: Optional[Dict[str, RetryConfig]] = None) -> Dict[str, Any]:
        """创建所有带重试的生产者"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # 创建 Stream 管理器
            manager_retry_config = None
            if retry_config and 'stream_manager' in retry_config:
                manager_retry_config = retry_config['stream_manager']
            
            stream_manager = await self.create_stream_manager(
                retry_config=manager_retry_config
            )
            
            # 创建所有生产者
            producers = {}
            
            # 新闻生产者
            news_retry_config = None
            if retry_config and 'news' in retry_config:
                news_retry_config = retry_config['news']
            
            producers['news'] = await self.create_news_producer(
                stream_manager, retry_config=news_retry_config
            )
            
            # 事件生产者
            event_retry_config = None
            if retry_config and 'event' in retry_config:
                event_retry_config = retry_config['event']
            
            producers['event'] = await self.create_event_producer(
                stream_manager, retry_config=event_retry_config
            )
            
            # 主题生产者
            theme_retry_config = None
            if retry_config and 'theme' in retry_config:
                theme_retry_config = retry_config['theme']
            
            producers['theme'] = await self.create_theme_producer(
                stream_manager, retry_config=theme_retry_config
            )
            
            logger.info("✅ 创建所有带重试的生产者")
            
            return producers
            
        except Exception as e:
            logger.error(f"创建所有带重试的生产者失败: {e}")
            raise
    
    async def create_enhanced_database_manager(self, base_manager, 
                                              config: Optional[EnhancedDatabaseConfig] = None,
                                              enable_retry: bool = True,
                                              retry_config: Optional[Dict[str, Any]] = None):
        """创建重试增强的数据库管理器（支持 Stream 发布）"""
        try:
            if not self._initialized:
                await self.initialize(config)
            
            # 获取配置
            current_config = config or self.config
            
            # 检查是否启用 Stream
            if not current_config.enable_stream_processing:
                logger.info("⏭️  Stream 处理未启用，返回原始管理器")
                return base_manager
            
            # 创建 Stream 管理器
            stream_manager = await self.create_stream_manager()
            
            # 创建生产者
            producers = await self.create_all_producers()
            
            # 包装原始管理器
            from .stream_gateway import StreamEnhancedGateway
            
            enhanced_manager = StreamEnhancedGateway(
                base_gateway=base_manager,
                stream_manager=stream_manager,
                enable_retry=enable_retry,
                retry_config=retry_config
            )
            
            logger.info("✅ 创建重试增强的数据库管理器（支持 Stream）")
            logger.info(f"   - 重试功能: {'启用' if enable_retry else '禁用'}")
            
            return enhanced_manager
            
        except Exception as e:
            logger.error(f"创建重试增强的数据库管理器失败: {e}")
            # 降级：返回原始管理器
            return base_manager
    
    async def create_cached_manager_with_streams(self, postgres_manager, 
                                                config: Optional[EnhancedDatabaseConfig] = None,
                                                enable_retry: bool = True,
                                                retry_config: Optional[Dict[str, Any]] = None):
        """创建带缓存和 Stream 支持的重试增强数据库管理器"""
        try:
            if not self._initialized:
                await self.initialize(config)
            
            current_config = config or self.config
            
            # 第一步：创建 Redis 缓存管理器
            cached_manager = RedisCachedDatabaseManager(postgres_manager, current_config)
            
            # 第二步：增强为支持 Stream 和重试
            if current_config.enable_stream_processing:
                enhanced_manager = await self.create_enhanced_database_manager(
                    cached_manager, current_config, enable_retry, retry_config
                )
                return enhanced_manager
            
            return cached_manager
            
        except Exception as e:
            logger.error(f"创建带缓存和 Stream 的重试增强数据库管理器失败: {e}")
            raise
    
    async def create_retry_manager(self, config_type: str = None, 
                                  custom_config: Optional[Dict[str, Any]] = None) -> RetryManager:
        """创建重试管理器"""
        try:
            # 获取配置
            if custom_config:
                config = RetryConfig.from_dict(custom_config)
            elif config_type:
                config = self.get_default_retry_config(config_type)
            else:
                config = self.default_retry_config
            
            # 创建重试管理器
            retry_manager = RetryManager(
                max_retries=config.max_retries,
                base_delay=config.base_delay,
                strategy=config.strategy,
                max_delay=config.max_delay,
                jitter=config.jitter,
                retry_on_exception=config.retry_on_exception,
                stop_on_exception=config.stop_on_exception
            )
            
            manager_key = f"retry_{config.strategy.value}_{config.max_retries}"
            self._retry_managers[manager_key] = retry_manager
            
            logger.debug(f"✅ 创建重试管理器: {config.strategy.value}策略")
            
            return retry_manager
            
        except Exception as e:
            logger.error(f"创建重试管理器失败: {e}")
            raise
    
    async def wrap_with_retry(self, obj, method_name: str = None,
                             retry_config: Optional[Dict[str, Any]] = None):
        """为对象包装重试功能"""
        try:
            from .stream_interface import RetryAdapter
            
            # 创建重试配置
            config = retry_config or self.get_default_retry_config('database_operation').to_dict()
            
            # 创建适配器
            adapter = RetryAdapter(obj, RetryConfig.from_dict(config))
            
            if method_name:
                # 包装特定方法
                async def wrapped_method(*args, **kwargs):
                    return await adapter.execute_with_retry(method_name, *args, **kwargs)
                return wrapped_method
            else:
                # 返回适配器对象
                return adapter
                
        except Exception as e:
            logger.error(f"为对象包装重试功能失败: {e}")
            return obj  # 降级：返回原始对象
    
    async def close_all(self):
        """关闭所有资源"""
        try:
            # 关闭所有 Stream 管理器
            for manager_key, manager in self._stream_managers.items():
                if hasattr(manager, 'redis'):
                    await manager.redis.close()
                    logger.debug(f"关闭 Stream 管理器: {manager_key}")
            
            # 清空缓存
            self._stream_managers.clear()
            self._producers.clear()
            self._retry_managers.clear()
            
            self._initialized = False
            
            logger.info("✅ 重试增强的 Stream 工厂已关闭所有资源")
            
        except Exception as e:
            logger.error(f"关闭资源失败: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取工厂统计信息"""
        return {
            'initialized': self._initialized,
            'stream_managers_count': len(self._stream_managers),
            'producers_count': len(self._producers),
            'retry_managers_count': len(self._retry_managers),
            'config': {
                'enable_stream_processing': self.config.enable_stream_processing if hasattr(self, 'config') else False,
                'redis_stream_enabled': self.config.redis_stream.enabled if hasattr(self, 'config') else False
            } if hasattr(self, 'config') else {},
            'default_retry_configs': {
                k: self.get_default_retry_config(k).to_dict() 
                for k in self._default_retry_configs.keys()
            }
        }
    
    async def get_retry_stats(self) -> Dict[str, Any]:
        """获取重试统计信息"""
        stats = {
            'total_managers': len(self._retry_managers),
            'managers_by_type': {},
            'total_operations': 0,
            'total_retries': 0
        }
        
        for key, manager in self._retry_managers.items():
            if hasattr(manager, 'get_stats'):
                manager_stats = manager.get_stats()
                stats['total_operations'] += manager_stats.get('total_retries', 0)
                stats['total_retries'] += manager_stats.get('successful_retries', 0) + manager_stats.get('failed_retries', 0)
                
                # 按类型分组
                manager_type = key.split('_')[0] if '_' in key else 'unknown'
                if manager_type not in stats['managers_by_type']:
                    stats['managers_by_type'][manager_type] = 0
                stats['managers_by_type'][manager_type] += 1
        
        return stats
    
    def print_retry_report(self):
        """打印重试报告"""
        print("\n📊 重试增强工厂报告")
        print("=" * 60)
        
        # 默认配置
        print("默认重试配置:")
        for config_type, config in self._default_retry_configs.items():
            print(f"  {config_type}: {config.get('strategy', 'exponential')}策略, "
                  f"最多{config.get('max_retries', 3)}次重试")
        
        # 统计
        print(f"\n已创建的组件:")
        print(f"  Stream 管理器: {len(self._stream_managers)}")
        print(f"  生产者: {len(self._producers)}")
        print(f"  重试管理器: {len(self._retry_managers)}")
        
        # 全局重试配置
        print(f"\n全局重试配置:")
        print(f"  策略: {self.default_retry_config.strategy.value}")
        print(f"  最大重试: {self.default_retry_config.max_retries}次")
        print(f"  基础延迟: {self.default_retry_config.base_delay}秒")
        
        print("=" * 60)


# 全局工厂实例
_factory_instance: Optional[RetryEnhancedFactory] = None


async def get_retry_enhanced_factory(
    default_retry_config: Optional[RetryConfig] = None
) -> RetryEnhancedFactory:
    """获取全局重试增强的 Stream 工厂实例"""
    global _factory_instance
    
    if _factory_instance is None:
        _factory_instance = RetryEnhancedFactory()
        await _factory_instance.initialize(
            default_retry_config=default_retry_config
        )
    
    return _factory_instance


async def create_stream_manager_with_retry(
    redis_url: str = None,
    retry_config: Optional[RetryConfig] = None
) -> RedisStreamManager:
    """快捷方法：创建带重试的 Stream 管理器"""
    factory = await get_retry_enhanced_factory()
    return await factory.create_stream_manager(redis_url, retry_config)


async def create_all_producers_with_retry(
    retry_config: Optional[Dict[str, RetryConfig]] = None
) -> Dict[str, Any]:
    """快捷方法：创建所有带重试的生产者"""
    factory = await get_retry_enhanced_factory()
    return await factory.create_all_producers(retry_config)


async def enhance_database_manager_with_retry(
    base_manager,
    enable_retry: bool = True,
    retry_config: Optional[Dict[str, Any]] = None
) -> Any:
    """快捷方法：增强数据库管理器以支持 Stream 和重试"""
    factory = await get_retry_enhanced_factory()
    return await factory.create_enhanced_database_manager(
        base_manager, 
        enable_retry=enable_retry,
        retry_config=retry_config
    )


async def create_retry_manager(
    config_type: str = None,
    custom_config: Optional[Dict[str, Any]] = None
) -> RetryManager:
    """快捷方法：创建重试管理器"""
    factory = await get_retry_enhanced_factory()
    return await factory.create_retry_manager(config_type, custom_config)


async def wrap_with_retry(
    obj,
    method_name: str = None,
    retry_config: Optional[Dict[str, Any]] = None
):
    """快捷方法：为对象包装重试功能"""
    factory = await get_retry_enhanced_factory()
    return await factory.wrap_with_retry(obj, method_name, retry_config)


async def close_retry_enhanced_factory():
    """关闭重试增强的 Stream 工厂"""
    global _factory_instance
    
    if _factory_instance:
        await _factory_instance.close_all()
        _factory_instance = None
        logger.info("✅ 重试增强的 Stream 工厂已关闭")


# 向后兼容的别名
get_stream_factory = get_retry_enhanced_factory
create_stream_manager = create_stream_manager_with_retry
create_all_producers = create_all_producers_with_retry
enhance_database_manager = enhance_database_manager_with_retry
close_stream_factory = close_retry_enhanced_factory


# 示例：如何使用
async def example_usage():
    """使用示例"""
    # 1. 获取工厂
    factory = await get_retry_enhanced_factory()
    
    # 2. 创建带重试的 Stream 管理器
    stream_manager = await factory.create_stream_manager(
        retry_config=create_retry_config(max_retries=5, strategy="exponential")
    )
    
    # 3. 创建带重试的生产者
    producers = await factory.create_all_producers_with_retry({
        'news': create_retry_config(max_retries=3, strategy="fixed"),
        'event': create_retry_config(max_retries=2, strategy="exponential")
    })
    
    # 4. 获取统计
    stats = await factory.get_stats()
    print(f"工厂统计: {stats}")
    
    # 5. 打印重试报告
    factory.print_retry_report()
    
    # 6. 使用快捷方法包装对象
    from ..gateway import DatabaseGateway
    gateway = await DatabaseGateway.get_instance()
    
    # 为特定方法添加重试
    retry_save_theme = await wrap_with_retry(
        gateway, 
        'save_theme',
        {'max_retries': 3, 'strategy': 'exponential'}
    )
    
    # 使用带重试的方法
    # result = await retry_save_theme(theme_data)


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())