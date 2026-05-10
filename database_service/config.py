"""
数据库服务配置管理
支持生产环境(PostgreSQL+Redis)和测试环境(内存)的无缝切换
🚀 新增Redis配置支持
"""
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import yaml


class DatabaseType(Enum):
    """数据库类型枚举"""
    POSTGRESQL = "postgresql"
    MEMORY = "memory"  # 用于测试


class CacheStrategy(Enum):
    """缓存策略枚举"""
    AGGRESSIVE = "aggressive"  # 积极缓存，高TTL
    CONSERVATIVE = "conservative"  # 保守缓存，低TTL
    NONE = "none"  # 不缓存
    INTELLIGENT = "intelligent"  # 智能缓存，根据访问频率调整


@dataclass
class RedisConfig:
    """Redis配置"""
    enabled: bool = True
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 20
    decode_responses: bool = True
    
    # 缓存TTL配置（秒）
    cache_ttl: Dict[str, int] = field(default_factory=lambda: {
        'theme': 600,          # 10分钟
        'event': 300,          # 5分钟
        'themes_list': 120,    # 2分钟
        'related_themes': 180, # 3分钟
        'stats': 60,           # 1分钟
        'hot_themes': 300,     # 5分钟（热门主题）
    })
    
    # Streams配置
    stream_max_length: int = 10000  # 每个Stream保留的最大消息数
    consumer_group: str = "database_service_group"
    
    # 为了向后兼容，添加 redis_enabled 属性
    @property
    def redis_enabled(self) -> bool:
        return self.enabled
    
    @redis_enabled.setter
    def redis_enabled(self, value: bool):
        self.enabled = value


@dataclass
class ConnectionPoolConfig:
    """连接池配置"""
    max_size: int = 20
    min_size: int = 5
    max_queries: int = 50000
    max_inactive_connection_lifetime: float = 300.0  # 秒
    connection_timeout: int = 30  # 秒
    command_timeout: int = 120  # 秒


@dataclass
class CacheConfig:
    """缓存配置"""
    strategy: CacheStrategy = CacheStrategy.INTELLIGENT
    enable_cache_warming: bool = True
    warm_cache_on_startup: bool = True
    warm_cache_items: int = 100  # 预热项目数
    
    # 智能缓存配置
    hot_threshold: int = 10  # 访问多少次算热门
    hot_item_ttl_multiplier: float = 3.0  # 热门项目TTL倍数


@dataclass 
class DatabaseConfig:
    """完整的数据库配置"""
    # 数据库类型
    db_type: DatabaseType = DatabaseType.MEMORY
    
    # PostgreSQL配置
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_database: str = "stock_data_test"
    postgres_username: str = "postgres"
    postgres_password: str = ""
    postgres_schema: str = "public"
    postgres_ssl_mode: str = "prefer"  # 添加缺失的 postgres_ssl_mode 参数
    postgres_pool_size: int = 20  
    
    # 连接池配置
    connection_pool: ConnectionPoolConfig = field(default_factory=ConnectionPoolConfig)
    
    # Redis配置
    redis: RedisConfig = field(default_factory=RedisConfig)
    
    # 缓存配置
    cache: CacheConfig = field(default_factory=CacheConfig)
    
    # 表名配置（为了向后兼容）
    table_names_config: Dict[str, str] = field(default_factory=lambda: {
        'theme_master': 'theme_master',
        'event_master': 'event_master',
        'theme_event_relation': 'theme_event_relation',
        'theme_audit_log': 'theme_audit_log'
    })
    
    # 性能配置
    enable_query_logging: bool = True
    slow_query_threshold: float = 1.0  # 秒
    max_retry_attempts: int = 3
    retry_delay: float = 1.0
    
    # 监控配置
    enable_metrics: bool = True
    metrics_port: int = 9090
    enable_health_check: bool = True
    health_check_interval: int = 30  # 秒
    
    # 为了向后兼容，添加 table_names 属性
    @property
    def table_names(self) -> Dict[str, str]:
        return self.table_names_config
    
    @table_names.setter 
    def table_names(self, value: Dict[str, str]):
        self.table_names_config = value
    
    # 为了向后兼容，添加 redis_enabled 属性
    @property
    def redis_enabled(self) -> bool:
        return self.redis.enabled
    
    @redis_enabled.setter
    def redis_enabled(self, value: bool):
        self.redis.enabled = value
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保 Redis 配置正确
        if not hasattr(self.redis, 'enabled'):
            self.redis.enabled = True
        
        # 确保表名配置存在
        if not hasattr(self, 'table_names_config'):
            self.table_names_config = {
                'theme_master': 'theme_master',
                'event_master': 'event_master',
                'theme_event_relation': 'theme_event_relation',
                'theme_audit_log': 'theme_audit_log'
            }
    
    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """从环境变量加载配置"""
        config = cls()
        
        # 数据库类型
        db_type = os.getenv('DB_TYPE', 'memory').lower()
        config.db_type = DatabaseType(db_type)
        
        if config.db_type == DatabaseType.POSTGRESQL:
            # 加载PostgreSQL配置
            config.postgres_host = os.getenv('PG_HOST', 'localhost')
            config.postgres_port = int(os.getenv('PG_PORT', '5432'))
            config.postgres_database = os.getenv('PG_DATABASE', 'stock_data')
            config.postgres_username = os.getenv('PG_USERNAME', 'postgres')
            config.postgres_password = os.getenv('PG_PASSWORD', '')
            config.postgres_ssl_mode = os.getenv('PG_SSL_MODE', 'prefer')
        
        # Redis配置
        config.redis.enabled = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'
        config.redis.host = os.getenv('REDIS_HOST', 'localhost')
        config.redis.port = int(os.getenv('REDIS_PORT', '6379'))
        config.redis.password = os.getenv('REDIS_PASSWORD')
        config.redis.max_connections = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
        
        # 缓存配置
        cache_strategy = os.getenv('CACHE_STRATEGY', 'intelligent').lower()
        config.cache.strategy = CacheStrategy(cache_strategy)
        config.cache.enable_cache_warming = os.getenv('ENABLE_CACHE_WARMING', 'true').lower() == 'true'
        
        # 连接池配置
        config.connection_pool.max_size = int(os.getenv('DB_POOL_MAX_SIZE', '20'))
        config.connection_pool.min_size = int(os.getenv('DB_POOL_MIN_SIZE', '5'))
        
        return config
    
    @classmethod
    def from_yaml(cls, filepath: str) -> 'DatabaseConfig':
        """从YAML文件加载配置"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        config = cls()
        
        if 'database' in data:
            db_config = data['database']
            config.db_type = DatabaseType(db_config.get('type', 'memory'))
            
            if config.db_type == DatabaseType.POSTGRESQL:
                config.postgres_host = db_config.get('host', 'localhost')
                config.postgres_port = db_config.get('port', 5432)
                config.postgres_database = db_config.get('database', 'stock_data')
                config.postgres_username = db_config.get('username', 'postgres')
                config.postgres_password = db_config.get('password', '')
                config.postgres_ssl_mode = db_config.get('ssl_mode', 'prefer')
        
        if 'redis' in data:
            redis_config = data['redis']
            config.redis.enabled = redis_config.get('enabled', True)
            if config.redis.enabled:
                config.redis.host = redis_config.get('host', 'localhost')
                config.redis.port = redis_config.get('port', 6379)
                config.redis.password = redis_config.get('password')
                if 'cache_ttl' in redis_config:
                    config.redis.cache_ttl.update(redis_config['cache_ttl'])
        
        if 'cache' in data:
            cache_config = data['cache']
            config.cache.strategy = CacheStrategy(cache_config.get('strategy', 'intelligent'))
            config.cache.enable_cache_warming = cache_config.get('enable_cache_warming', True)
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'db_type': self.db_type.value,
            'postgres': {
                'host': self.postgres_host,
                'port': self.postgres_port,
                'database': self.postgres_database,
                'username': self.postgres_username,
                'schema': self.postgres_schema,
                'ssl_mode': self.postgres_ssl_mode
            } if self.db_type == DatabaseType.POSTGRESQL else None,
            'redis': {
                'enabled': self.redis.enabled,
                'host': self.redis.host,
                'port': self.redis.port,
                'cache_ttl': self.redis.cache_ttl
            } if self.redis.enabled else None,
            'cache': {
                'strategy': self.cache.strategy.value,
                'enable_cache_warming': self.cache.enable_cache_warming
            },
            'connection_pool': {
                'max_size': self.connection_pool.max_size,
                'min_size': self.connection_pool.min_size,
                'connection_timeout': self.connection_pool.connection_timeout
            },
            'table_names': self.table_names_config
        }
    
    @property
    def database_config(self) -> Dict[str, Any]:
        """返回数据库连接配置字典"""
        return {
            'host': self.postgres_host,
            'port': self.postgres_port,
            'database': self.postgres_database,
            'username': self.postgres_username,
            'password': self.postgres_password,
            'schema': self.postgres_schema,
            'ssl_mode': self.postgres_ssl_mode,
            'pool_size': self.postgres_pool_size
        }
    
    @database_config.setter
    def database_config(self, value: Dict[str, Any]):
        """从字典设置数据库配置"""
        if value:
            self.postgres_host = value.get('host', self.postgres_host)
            self.postgres_port = value.get('port', self.postgres_port)
            self.postgres_database = value.get('database', self.postgres_database)
            self.postgres_username = value.get('username', self.postgres_username)
            self.postgres_password = value.get('password', self.postgres_password)
            self.postgres_schema = value.get('schema', self.postgres_schema)
            self.postgres_ssl_mode = value.get('ssl_mode', self.postgres_ssl_mode)
            self.postgres_pool_size = value.get('pool_size', self.postgres_pool_size)


# 全局配置实例
_config: Optional[DatabaseConfig] = None


def get_config() -> DatabaseConfig:
    """获取全局配置"""
    global _config
    if _config is None:
        # 尝试从环境变量加载
        _config = DatabaseConfig.from_env()
    return _config


def init_config(config: DatabaseConfig):
    """初始化配置"""
    global _config
    _config = config


def reload_config():
    """重新加载配置"""
    global _config
    _config = None
    return get_config()