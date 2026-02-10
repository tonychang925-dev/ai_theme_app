"""
数据库管理器工厂 - 增强版
支持 Redis Stream 集成
"""
import logging
from typing import Optional, Dict, Any
import sys
import os

logger = logging.getLogger(__name__)

# ========== 简单的导入方案 ==========
# 直接导入，让Python处理相对/绝对导入
try:
    # 基础模块 - 使用绝对导入
    from database_service.config import DatabaseConfig, get_config
    from database_service.interface import DatabaseManager
    from database_service.managers.memory_manager import MemoryDatabaseManager
    from database_service.managers.postgres_manager import PostgresDatabaseManager
    from database_service.managers.redis_cached_manager import RedisCachedDatabaseManager
    logger.debug("✅ 基础模块导入成功（绝对导入）")
except ImportError as e:
    logger.error(f"❌ 无法导入基础模块: {e}")
    # 创建存根类
    class DatabaseConfig:
        def __init__(self):
            self.db_type = type('DatabaseType', (), {'value': 'memory'})()

    def get_config():
        return DatabaseConfig()

    class DatabaseManager:
        pass

    class MemoryDatabaseManager(DatabaseManager):
        pass

    class PostgresDatabaseManager(DatabaseManager):
        pass

    class RedisCachedDatabaseManager(DatabaseManager):
        pass

# Stream 相关导入（可选）
try:
    # 使用绝对导入
    from database_service.streams.stream_factory import StreamEnhancedFactory, get_stream_factory
    from database_service.streams.stream_config import EnhancedDatabaseConfig, get_enhanced_config
    STREAM_SUPPORT = True
    logger.debug("✅ Stream 功能可用（绝对导入）")
except ImportError:
    STREAM_SUPPORT = False
    logger.debug("⚠️  Stream 模块未安装，Stream 功能不可用")
    
    # 创建存根类
    class StreamEnhancedFactory:
        pass
    
    def get_stream_factory(*args, **kwargs):
        return StreamEnhancedFactory()
    
    class EnhancedDatabaseConfig:
        pass
    
    def get_enhanced_config(*args, **kwargs):
        return EnhancedDatabaseConfig()


class DatabaseManagerFactory:
    """数据库管理器工厂（增强版）"""
    
    _MANAGER_TYPES = {
        'memory': MemoryDatabaseManager,
        'postgresql': PostgresDatabaseManager,
        'postgres': PostgresDatabaseManager,
        'hybrid': RedisCachedDatabaseManager
    }
    
    @classmethod
    async def create_manager(cls, config: Optional[DatabaseConfig] = None, 
                           enable_streams: bool = None) -> DatabaseManager:
        """创建数据库管理器
        
        Args:
            config: 数据库配置，如果为None则使用默认配置
            enable_streams: 是否启用 Stream 支持，如果为None则根据配置决定
            
        Returns:
            数据库管理器实例
        """
        if config is None:
            config = get_config()
        
        logger.info(f"📦 创建数据库管理器，类型: {config.db_type.value}")
        
        # 创建基础管理器
        base_manager = cls._create_base_manager(config)
        
        # 初始化管理器
        await cls._initialize_manager(base_manager, config)
        
        # 检查是否需要启用 Stream
        should_enable_streams = enable_streams
        if should_enable_streams is None:
            should_enable_streams = cls._should_enable_streams(config)
        
        # 如果启用 Stream，创建增强管理器
        if should_enable_streams and STREAM_SUPPORT:
            try:
                base_manager = await cls._enhance_with_streams(base_manager, config)
                logger.info("✅ 数据库管理器已增强 Stream 支持")
            except Exception as e:
                logger.warning(f"⚠️  启用 Stream 支持失败，使用基础管理器: {e}")
        
        return base_manager
    
    @classmethod
    def _create_base_manager(cls, config: DatabaseConfig) -> DatabaseManager:
        """创建基础数据库管理器"""
        db_type = config.db_type.value
        
        if db_type == "memory":
            logger.info("📝 创建内存数据库管理器（28字段测试数据）")
            manager = MemoryDatabaseManager(config)
        elif db_type in ("postgresql", "postgres"):
            logger.info("🐘 创建PostgreSQL数据库管理器（28字段结构）")
            manager = PostgresDatabaseManager(config)
        elif db_type == "hybrid":
            logger.info("🔥 创建混合数据库管理器（PostgreSQL + Redis缓存）")
            # 先创建PostgreSQL管理器，再包装为缓存管理器
            postgres_manager = PostgresDatabaseManager(config)
            manager = RedisCachedDatabaseManager(postgres_manager, config)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
        
        return manager
    
    @classmethod
    async def _initialize_manager(cls, manager: DatabaseManager, config: DatabaseConfig) -> None:
        """初始化数据库管理器"""
        try:
            # 连接数据库
            await manager.connect()
            logger.info("✅ 数据库连接成功")
            
            # 执行健康检查
            health_status = await manager.health_check()
            if health_status:
                logger.info("✅ 数据库健康检查通过")
            else:
                logger.warning("⚠️  数据库健康检查未通过")
            
            # 验证表结构（如果支持）
            if hasattr(manager, 'validate_schema'):
                try:
                    await manager.validate_schema()
                    logger.info("✅ 表结构验证通过")
                except Exception as e:
                    logger.warning(f"⚠️  表结构验证失败: {e}")
            
            # 初始化统计
            if hasattr(manager, 'get_stats'):
                try:
                    stats = await manager.get_stats()
                    logger.info(f"📊 数据库统计: {stats}")
                except Exception as e:
                    logger.debug(f"统计获取失败（可能正常）: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 数据库管理器初始化失败: {e}")
            raise
    
    @classmethod
    def _should_enable_streams(cls, config: DatabaseConfig) -> bool:
        """检查是否应该启用 Stream"""
        if not STREAM_SUPPORT:
            return False
        
        # 检查配置
        try:
            # 尝试获取增强配置
            enhanced_config = get_enhanced_config()
            return (enhanced_config.enable_stream_processing and 
                   enhanced_config.redis_stream.enabled and 
                   enhanced_config.redis.enabled)
        except:
            # 如果无法获取增强配置，检查基础配置
            return getattr(config, 'redis_enabled', False)
    
    @classmethod
    async def _enhance_with_streams(cls, base_manager: DatabaseManager, config: DatabaseConfig) -> DatabaseManager:
        """使用 Stream 增强数据库管理器"""
        try:
            # 获取 Stream 工厂
            stream_factory = await get_stream_factory()
            
            # 转换配置为增强配置
            if isinstance(config, EnhancedDatabaseConfig):
                enhanced_config = config
            else:
                # 从基础配置创建增强配置
                enhanced_config = EnhancedDatabaseConfig()
                # 复制属性
                for attr in config.__dataclass_fields__:
                    if hasattr(config, attr):
                        setattr(enhanced_config, attr, getattr(config, attr))
            
            # 使用 Stream 工厂增强管理器
            enhanced_manager = await stream_factory.create_enhanced_database_manager(
                base_manager, enhanced_config
            )
            
            return enhanced_manager
            
        except Exception as e:
            logger.error(f"Stream 增强失败: {e}")
            raise
    
    @classmethod
    async def create_client(cls, config: Optional[DatabaseConfig] = None, 
                          auto_connect: bool = True,
                          enable_streams: bool = None) -> Any:
        """创建数据库客户端（增强版）
        
        Args:
            config: 数据库配置
            auto_connect: 是否自动连接
            enable_streams: 是否启用 Stream 支持
            
        Returns:
            数据库客户端实例
        """
        from client import DatabaseClient
        
        manager = await cls.create_manager(config, enable_streams)
        client = DatabaseClient(manager)
        
        if auto_connect and hasattr(manager, 'connected') and not manager.connected:
            await manager.connect()
        
        return client
    
    @classmethod
    async def create_stream_enhanced_client(cls, config: Optional[DatabaseConfig] = None) -> Any:
        """创建 Stream 增强的数据库客户端（快捷方法）"""
        return await cls.create_client(config, enable_streams=True)
    
    @classmethod
    async def create_manager_for_testing(cls, use_cache: bool = False, 
                                       use_streams: bool = False) -> DatabaseManager:
        """创建测试用的数据库管理器（增强版）
        
        Args:
            use_cache: 是否启用Redis缓存
            use_streams: 是否启用 Stream 支持
            
        Returns:
            DatabaseManager: 测试用的数据库管理器
        """
        from config import DatabaseConfig
        
        # 创建测试配置
        test_config = DatabaseConfig(
            db_type="memory",
            redis_enabled=use_cache or use_streams,  # 如果启用 Stream，必须启用 Redis
            cache_strategy="aggressive" if use_cache else "none"
        )
        
        return await cls.create_manager(test_config, enable_streams=use_streams)
    
    @classmethod
    async def create_benchmark_manager(cls, config_type: str = "postgres",
                                     with_streams: bool = False) -> DatabaseManager:
        """创建基准测试用的数据库管理器（增强版）
        
        Args:
            config_type: 配置类型 ('memory', 'postgres', 'cached')
            with_streams: 是否启用 Stream 支持
            
        Returns:
            DatabaseManager: 基准测试用的数据库管理器
        """
        from config import DatabaseConfig
        
        config_map = {
            'memory': DatabaseConfig(db_type="memory"),
            'postgres': DatabaseConfig(
                db_type="postgresql",
                redis_enabled=with_streams,  # 如果启用 Stream，必须启用 Redis
                cache_strategy="none"
            ),
            'cached': DatabaseConfig(
                db_type="postgresql",
                redis_enabled=True,  # 缓存需要 Redis
                cache_strategy="aggressive"
            )
        }
        
        if config_type not in config_map:
            raise ValueError(f"不支持的配置类型: {config_type}")
        
        return await cls.create_manager(config_map[config_type], enable_streams=with_streams)
    
    @classmethod
    async def create_stream_manager(cls, config: Optional[DatabaseConfig] = None) -> Any:
        """创建独立的 Redis Stream 管理器
        
        Args:
            config: 数据库配置
            
        Returns:
            Redis Stream 管理器
        """
        if not STREAM_SUPPORT:
            raise ImportError("Stream 模块未安装")
        
        if config is None:
            config = get_config()
        
        try:
            # 获取 Stream 工厂
            stream_factory = await get_stream_factory()
            
            # 创建 Stream 管理器
            return await stream_factory.create_stream_manager()
            
        except Exception as e:
            logger.error(f"创建 Stream 管理器失败: {e}")
            raise


def get_database_url(config: DatabaseConfig) -> str:
    """获取数据库连接URL"""
    if config.db_type.value == "memory":
        return "memory://test"
    
    # PostgreSQL URL
    password_part = f":{config.postgres_password}" if config.postgres_password else ""
    
    url = (f"postgresql://{config.postgres_username}{password_part}"
           f"@{config.postgres_host}:{config.postgres_port}"
           f"/{config.postgres_database}")
    
    # 添加连接参数
    params = []
    if config.postgres_ssl_mode:
        params.append(f"sslmode={config.postgres_ssl_mode}")
    if config.postgres_pool_size:
        params.append(f"pool_size={config.postgres_pool_size}")
    if hasattr(config, "postgres_connect_timeout") and config.postgres_connect_timeout:
        params.append(f"connect_timeout={config.postgres_connect_timeout}")
    
    if params:
        url += "?" + "&".join(params)
    
    return url


def get_redis_url(config: DatabaseConfig) -> Optional[str]:
    """获取Redis连接URL"""
    if not config.redis.enabled:
        return None
    
    password_part = f":{config.redis.password}" if config.redis.password else ""
    auth_part = f"{password_part}@" if password_part else ""
    
    return f"redis://{auth_part}{config.redis.host}:{config.redis.port}/{config.redis.db}"


def get_stream_redis_url(config: DatabaseConfig) -> Optional[str]:
    """获取 Stream 专用的 Redis 连接URL"""
    if not STREAM_SUPPORT:
        return None
    
    try:
        # 尝试获取增强配置
        enhanced_config = get_enhanced_config()
        if not enhanced_config.redis.enabled:
            return None
        
        password_part = f":{enhanced_config.redis.password}" if enhanced_config.redis.password else ""
        auth_part = f"{password_part}@" if password_part else ""
        
        return f"redis://{auth_part}{enhanced_config.redis.host}:{enhanced_config.redis.port}/{enhanced_config.redis.db}"
        
    except:
        # 降级：使用基础配置
        return get_redis_url(config)


def print_config_summary(config: DatabaseConfig) -> None:
    """打印配置摘要（增强版）"""
    logger.info("📋 数据库配置摘要")
    logger.info(f"   数据库类型: {config.db_type.value}")
    
    if config.db_type.value != "memory":
        logger.info(f"   主机: {config.postgres_host}:{config.postgres_port}")
        logger.info(f"   数据库: {config.postgres_database}")
        logger.info(f"   用户: {config.postgres_username}")
    
    if config.table_names_config:
        for table_type, table_name in config.table_names_config.items():
            logger.info(f"   表名: {table_name}")
    
    logger.info(f"   Redis: {'启用' if config.redis.enabled else '禁用'}")
    if config.redis.enabled:
        logger.info(f"   Redis主机: {config.redis.host}:{config.redis.port}")
    
    if hasattr(config, 'cache_strategy'):
        logger.info(f"   缓存策略: {config.cache_strategy.value}")
    
    # Stream 配置信息
    if STREAM_SUPPORT:
        try:
            enhanced_config = get_enhanced_config()
            logger.info(f"   Stream支持: {'启用' if enhanced_config.enable_stream_processing else '禁用'}")
            if enhanced_config.enable_stream_processing:
                logger.info(f"   Stream数量: {len(enhanced_config.redis_stream.streams)}")
                logger.info(f"   消费者组: {len(enhanced_config.redis_stream.consumer_groups)}")
        except:
            logger.info("   Stream支持: 配置不可用")