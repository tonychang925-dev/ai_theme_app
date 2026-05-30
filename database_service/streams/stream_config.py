"""
Redis Stream 配置扩展
基于现有的 config.py 进行扩展
"""
from typing import Dict, List, Optional,Any
from dataclasses import dataclass, field
from enum import Enum
import os
import yaml

# 将相对导入改为绝对导入
from database_service.config import DatabaseConfig, RedisConfig


class StreamPriority(Enum):
    """Stream优先级"""
    HIGH = "high"      # 高优先级，用于实时处理
    MEDIUM = "medium"  # 中优先级，用于批量处理
    LOW = "low"       # 低优先级，用于后台任务


class ConsumerStrategy(Enum):
    """消费者策略"""
    SINGLE = "single"          # 单个消费者
    WORKER_POOL = "worker_pool" # 工作池模式
    BROADCAST = "broadcast"    # 广播模式


@dataclass
class StreamDefinition:
    """Stream定义"""
    name: str                          # Stream名称
    description: str                   # 描述
    priority: StreamPriority          # 优先级
    max_length: int = 10000           # 最大消息数
    auto_trim: bool = True            # 自动清理
    enable_compression: bool = True   # 启用压缩
    compression_threshold: int = 1024  # 压缩阈值（字节）
    
    # 监控配置
    alert_on_backlog: bool = True     # 积压告警
    backlog_threshold: int = 1000     # 积压阈值
    alert_on_stuck: bool = True       # 卡住消息告警
    stuck_threshold_ms: int = 30000   # 卡住阈值（毫秒）


@dataclass
class ConsumerGroupConfig:
    """消费者组配置"""
    name: str                          # 组名
    stream: str                        # 消费的Stream
    strategy: ConsumerStrategy         # 消费策略
    workers: int = 1                   # 工作线程数
    batch_size: int = 10               # 批量大小
    block_time_ms: int = 5000          # 阻塞时间（毫秒）
    max_retries: int = 3               # 最大重试次数
    retry_delay_ms: int = 1000         # 重试延迟（毫秒）
    
    # 性能配置
    enable_batch_processing: bool = True  # 启用批量处理
    batch_timeout_seconds: int = 30       # 批量超时时间
    max_concurrent_messages: int = 100    # 最大并发消息数
    
    # 死信队列配置
    enable_dlq: bool = True            # 启用死信队列
    dlq_max_length: int = 1000         # 死信队列最大长度
    dlq_retention_days: int = 7        # 死信队列保留天数


@dataclass
class RedisStreamConfig:
    """Redis Stream 配置"""
    enabled: bool = True  # 是否启用Stream处理
    
    # Stream定义
    streams: Dict[str, StreamDefinition] = field(default_factory=lambda: {
        "news_raw": StreamDefinition(
            name="news:raw",
            description="原始新闻流",
            priority=StreamPriority.HIGH,
            max_length=50000,
            alert_on_backlog=True,
            backlog_threshold=2000
        ),
        "events_major": StreamDefinition(
            name="events:major",
            description="重大事件流",
            priority=StreamPriority.HIGH,
            max_length=5000,
            alert_on_stuck=True,
            stuck_threshold_ms=60000  # 1分钟
        ),
        "events_normal": StreamDefinition(
            name="events:normal",
            description="普通事件流",
            priority=StreamPriority.MEDIUM,
            max_length=20000,
            alert_on_backlog=True,
            backlog_threshold=5000
        ),
        "events_structured": StreamDefinition(
            name="events:structured",
            description="结构化事件流",
            priority=StreamPriority.HIGH,
            max_length=20000,
            alert_on_backlog=True,
            backlog_threshold=5000
        ),
        "event_feed": StreamDefinition(
            name="event:feed",
            description="情报台事件输出流",
            priority=StreamPriority.HIGH,
            max_length=5000,
            alert_on_backlog=True,
            backlog_threshold=2000
        ),
        "themes_updates": StreamDefinition(
            name="themes:updates",
            description="主题更新流",
            priority=StreamPriority.MEDIUM,
            max_length=2000
        ),
        "dead_letter": StreamDefinition(
            name="dead:letter",
            description="死信队列",
            priority=StreamPriority.LOW,
            max_length=1000,
            auto_trim=False  # 死信队列不自动清理
        )
    })
    
    # 消费者组配置
    consumer_groups: Dict[str, ConsumerGroupConfig] = field(default_factory=lambda: {
        "news_processors": ConsumerGroupConfig(
            name="news_processors",
            stream="news:raw",
            strategy=ConsumerStrategy.WORKER_POOL,
            workers=3,
            batch_size=50,
            block_time_ms=2000,
            max_retries=3
        ),
        "major_workers": ConsumerGroupConfig(
            name="major_workers",
            stream="events:major",
            strategy=ConsumerStrategy.SINGLE,
            workers=2,
            batch_size=5,
            block_time_ms=10000,  # 重大事件处理需要更长时间
            max_retries=5
        ),
        "theme_workers": ConsumerGroupConfig(
            name="theme_workers",
            stream="events:normal",
            strategy=ConsumerStrategy.WORKER_POOL,
            workers=4,
            batch_size=20,
            block_time_ms=5000,
            enable_batch_processing=True,
            batch_timeout_seconds=60
        )
    })
    
    # 性能配置
    max_connections: int = 50                     # Redis最大连接数
    connection_timeout: int = 5                   # 连接超时（秒）
    read_timeout: int = 10                        # 读取超时（秒）
    write_timeout: int = 10                       # 写入超时（秒）
    
    # 监控配置
    enable_monitoring: bool = True               # 启用监控
    metrics_interval: int = 30                   # 指标收集间隔（秒）
    health_check_interval: int = 60              # 健康检查间隔（秒）
    
    # 清理配置
    auto_cleanup: bool = True                    # 自动清理
    cleanup_interval_hours: int = 24             # 清理间隔（小时）
    max_stream_age_days: int = 30                # Stream最大保留天数
    
    # 迁移配置（用于从List/PubSub迁移到Stream）
    enable_migration: bool = True                # 启用迁移模式
    dual_write_mode: bool = True                 # 双写模式（同时写入Stream和List）
    migration_batch_size: int = 100              # 迁移批次大小


@dataclass
class ExternalServiceConfig:
    """外部服务配置"""
    
    model_service: Dict[str, any] = field(default_factory=lambda: {
        "url": os.getenv("MODEL_SERVICE_URL", "http://localhost:8001"),
        "timeout": int(os.getenv("MODEL_SERVICE_TIMEOUT", "30")),
        "retry_count": int(os.getenv("MODEL_SERVICE_RETRY_COUNT", "3")),
        "retry_delay": float(os.getenv("MODEL_SERVICE_RETRY_DELAY", "1.0")),
        "health_check_endpoint": os.getenv("MODEL_SERVICE_HEALTH_CHECK", "/health"),
        "extract_endpoint": os.getenv("MODEL_SERVICE_EXTRACT_ENDPOINT", "/api/event_extract"),
        "batch_extract_endpoint": os.getenv("MODEL_SERVICE_BATCH_EXTRACT_ENDPOINT", "/api/batch_extract")
    })
    
    theme_service: Dict[str, any] = field(default_factory=lambda: {
        "url": os.getenv("THEME_SERVICE_URL", "http://localhost:8002"),
        "timeout": int(os.getenv("THEME_SERVICE_TIMEOUT", "30")),
        "retry_count": int(os.getenv("THEME_SERVICE_RETRY_COUNT", "3")),
        "retry_delay": float(os.getenv("THEME_SERVICE_RETRY_DELAY", "1.0")),
        "health_check_endpoint": os.getenv("THEME_SERVICE_HEALTH_CHECK", "/health"),
        "match_endpoint": os.getenv("THEME_SERVICE_MATCH_ENDPOINT", "/api/theme_match"),
        "update_endpoint": os.getenv("THEME_SERVICE_UPDATE_ENDPOINT", "/api/theme_update")
    })
    
    crawler_service: Dict[str, any] = field(default_factory=lambda: {
        "url": os.getenv("CRAWLER_SERVICE_URL", "http://localhost:8003"),
        "timeout": int(os.getenv("CRAWLER_SERVICE_TIMEOUT", "60")),
        "retry_count": int(os.getenv("CRAWLER_SERVICE_RETRY_COUNT", "5")),
        "retry_delay": float(os.getenv("CRAWLER_SERVICE_RETRY_DELAY", "2.0"))
    })
    
    def validate(self):
        """验证配置"""
        services = ["model_service", "theme_service", "crawler_service"]
        for service_name in services:
            service_config = getattr(self, service_name)
            if not service_config.get("url"):
                raise ValueError(f"{service_name} URL must be configured")
    
    def get_service_url(self, service_name: str) -> str:
        """获取服务URL"""
        service_config = getattr(self, service_name, {})
        return service_config.get("url", "")


# 扩展现有的 DatabaseConfig 类
@dataclass
class EnhancedDatabaseConfig(DatabaseConfig):
    """增强的数据库配置，包含Stream配置"""
    
    # Redis Stream 配置
    redis_stream: RedisStreamConfig = field(default_factory=RedisStreamConfig)
    
    # 外部服务配置
    external_services: ExternalServiceConfig = field(default_factory=ExternalServiceConfig)
    
    # 功能开关（用于渐进式迁移）
    enable_stream_processing: bool = True                    # 启用Stream处理
    enable_legacy_event_bus: bool = False                   # 保持旧版事件总线兼容
    dual_write_mode: bool = True                            # 双写模式
    
    # 性能优化
    max_processing_threads: int = 10                        # 最大处理线程数
    thread_pool_size: int = 5                              # 线程池大小
    queue_max_size: int = 1000                             # 队列最大大小
    
    # 错误处理
    max_error_rate: float = 0.01                           # 最大错误率（1%）
    circuit_breaker_enabled: bool = True                   # 启用熔断器
    circuit_breaker_threshold: int = 10                    # 熔断器阈值
    circuit_breaker_timeout: int = 60                      # 熔断器超时（秒）
    
    def __post_init__(self):
        """初始化后处理"""
        super().__post_init__()
        
        # 验证外部服务配置
        self.external_services.validate()
        
        # 如果Redis未启用，则Stream也不能启用
        if not self.redis.enabled:
            self.redis_stream.enabled = False
            self.enable_stream_processing = False
        
        # 确保Stream名称使用正确的格式
        for stream_name, stream_def in self.redis_stream.streams.items():
            if not stream_def.name.startswith("stream:"):
                stream_def.name = f"stream:{stream_def.name}"
    
    @classmethod
    def from_env(cls) -> 'EnhancedDatabaseConfig':
        """从环境变量加载配置"""
        # 首先调用父类的方法
        base_config = super().from_env()
        
        # 创建增强配置
        config = cls()
        
        # 复制父类属性
        for attr in base_config.__dataclass_fields__:
            if hasattr(base_config, attr):
                setattr(config, attr, getattr(base_config, attr))
        
        # 加载Stream配置
        config.redis_stream.enabled = os.getenv('REDIS_STREAM_ENABLED', 'true').lower() == 'true'
        
        # 加载外部服务配置
        model_timeout = os.getenv('MODEL_SERVICE_TIMEOUT', '30')
        config.external_services.model_service['timeout'] = int(model_timeout)
        
        theme_timeout = os.getenv('THEME_SERVICE_TIMEOUT', '30')
        config.external_services.theme_service['timeout'] = int(theme_timeout)
        
        # 功能开关
        config.enable_stream_processing = os.getenv('ENABLE_STREAM_PROCESSING', 'true').lower() == 'true'
        config.enable_legacy_event_bus = os.getenv('ENABLE_LEGACY_EVENT_BUS', 'false').lower() == 'true'
        config.dual_write_mode = os.getenv('DUAL_WRITE_MODE', 'true').lower() == 'true'
        
        return config
    
    @classmethod
    def from_yaml(cls, filepath: str) -> 'EnhancedDatabaseConfig':
        """从YAML文件加载配置"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 首先调用父类的方法
        base_config = super().from_yaml(filepath)
        
        # 创建增强配置
        config = cls()
        
        # 复制父类属性
        for attr in base_config.__dataclass_fields__:
            if hasattr(base_config, attr):
                setattr(config, attr, getattr(base_config, attr))
        
        # 加载Stream配置
        if 'redis_stream' in data:
            stream_data = data['redis_stream']
            config.redis_stream.enabled = stream_data.get('enabled', True)
            
            # 加载Stream定义
            if 'streams' in stream_data:
                for stream_key, stream_def in stream_data['streams'].items():
                    if stream_key in config.redis_stream.streams:
                        existing = config.redis_stream.streams[stream_key]
                        # 更新现有的Stream定义
                        for key, value in stream_def.items():
                            if hasattr(existing, key):
                                setattr(existing, key, value)
            
            # 加载消费者组配置
            if 'consumer_groups' in stream_data:
                for group_key, group_config in stream_data['consumer_groups'].items():
                    if group_key in config.redis_stream.consumer_groups:
                        existing = config.redis_stream.consumer_groups[group_key]
                        # 更新现有的消费者组配置
                        for key, value in group_config.items():
                            if hasattr(existing, key):
                                setattr(existing, key, value)
        
        # 加载外部服务配置
        if 'external_services' in data:
            ext_data = data['external_services']
            
            if 'model_service' in ext_data:
                config.external_services.model_service.update(ext_data['model_service'])
            
            if 'theme_service' in ext_data:
                config.external_services.theme_service.update(ext_data['theme_service'])
            
            if 'crawler_service' in ext_data:
                config.external_services.crawler_service.update(ext_data['crawler_service'])
        
        # 加载功能开关
        if 'features' in data:
            features = data['features']
            config.enable_stream_processing = features.get('enable_stream_processing', True)
            config.enable_legacy_event_bus = features.get('enable_legacy_event_bus', False)
            config.dual_write_mode = features.get('dual_write_mode', True)
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        base_dict = super().to_dict()
        
        # 添加Stream配置
        base_dict['redis_stream'] = {
            'enabled': self.redis_stream.enabled,
            'streams': {
                key: {
                    'name': stream.name,
                    'description': stream.description,
                    'priority': stream.priority.value,
                    'max_length': stream.max_length
                }
                for key, stream in self.redis_stream.streams.items()
            },
            'consumer_groups': {
                key: {
                    'name': group.name,
                    'stream': group.stream,
                    'strategy': group.strategy.value,
                    'workers': group.workers,
                    'batch_size': group.batch_size
                }
                for key, group in self.redis_stream.consumer_groups.items()
            }
        }
        
        # 添加外部服务配置
        base_dict['external_services'] = {
            'model_service': self.external_services.model_service,
            'theme_service': self.external_services.theme_service,
            'crawler_service': self.external_services.crawler_service
        }
        
        # 添加功能开关
        base_dict['features'] = {
            'enable_stream_processing': self.enable_stream_processing,
            'enable_legacy_event_bus': self.enable_legacy_event_bus,
            'dual_write_mode': self.dual_write_mode
        }
        
        return base_dict
    
    def get_stream_url(self, stream_key: str) -> str:
        """获取Stream的完整名称"""
        if stream_key in self.redis_stream.streams:
            return self.redis_stream.streams[stream_key].name
        
        # 如果传递的是完整名称，直接返回
        if stream_key.startswith("stream:"):
            return stream_key
        
        # 否则添加前缀
        return f"stream:{stream_key}"
    
    def get_consumer_group_config(self, group_key: str) -> Optional[ConsumerGroupConfig]:
        """获取消费者组配置"""
        return self.redis_stream.consumer_groups.get(group_key)
    
    def get_stream_config(self, stream_key: str) -> Optional[StreamDefinition]:
        """获取Stream配置"""
        return self.redis_stream.streams.get(stream_key)


# 扩展配置文件示例
STREAM_CONFIG_EXAMPLE = """
# Redis Stream 配置示例
# 将此配置合并到现有的 config.yaml 中

redis_stream:
  enabled: true
  
  # Stream定义
  streams:
    news_raw:
      name: "news:raw"
      description: "原始新闻流"
      priority: "high"
      max_length: 10000
      alert_on_backlog: true
      backlog_threshold: 2000
    
    events_major:
      name: "events:major"
      description: "重大事件流"
      priority: "high"
      max_length: 5000
      alert_on_stuck: true
      stuck_threshold_ms: 60000
    
    events_normal:
      name: "events:normal"
      description: "普通事件流"
      priority: "medium"
      max_length: 20000
      alert_on_backlog: true
      backlog_threshold: 5000
    
    themes_updates:
      name: "themes:updates"
      description: "主题更新流"
      priority: "medium"
      max_length: 2000
    
    dead_letter:
      name: "dead:letter"
      description: "死信队列"
      priority: "low"
      max_length: 1000
      auto_trim: false
  
  # 消费者组配置
  consumer_groups:
    news_processors:
      name: "news_processors"
      stream: "news:raw"
      strategy: "worker_pool"
      workers: 3
      batch_size: 10
      block_time_ms: 5000
      max_retries: 3
    
    major_workers:
      name: "major_workers"
      stream: "events:major"
      strategy: "single"
      workers: 2
      batch_size: 5
      block_time_ms: 10000
      max_retries: 5
    
    theme_workers:
      name: "theme_workers"
      stream: "events:normal"
      strategy: "worker_pool"
      workers: 4
      batch_size: 20
      block_time_ms: 5000
      enable_batch_processing: true
      batch_timeout_seconds: 60

# 外部服务配置
external_services:
  model_service:
    url: "http://localhost:8001"
    timeout: 30
    retry_count: 3
    retry_delay: 1.0
    health_check_endpoint: "/health"
    extract_endpoint: "/api/event_extract"
    batch_extract_endpoint: "/api/batch_extract"
  
  theme_service:
    url: "http://localhost:8002"
    timeout: 30
    retry_count: 3
    retry_delay: 1.0
    health_check_endpoint: "/health"
    match_endpoint: "/api/theme_match"
    update_endpoint: "/api/theme_update"
  
  crawler_service:
    url: "http://localhost:8003"
    timeout: 60
    retry_count: 5
    retry_delay: 2.0

# 功能开关
features:
  enable_stream_processing: true
  enable_legacy_event_bus: false
  dual_write_mode: true
"""


# 全局配置实例
_config: Optional[EnhancedDatabaseConfig] = None


def get_enhanced_config() -> EnhancedDatabaseConfig:
    """获取增强的全局配置"""
    global _config
    if _config is None:
        # 尝试从环境变量加载
        _config = EnhancedDatabaseConfig.from_env()
    return _config


def init_enhanced_config(config: EnhancedDatabaseConfig):
    """初始化增强配置"""
    global _config
    _config = config


def reload_enhanced_config():
    """重新加载增强配置"""
    global _config
    _config = None
    return get_enhanced_config()


def get_stream_config() -> RedisStreamConfig:
    """获取Stream配置（快捷方法）"""
    config = get_enhanced_config()
    return config.redis_stream


def get_external_service_config() -> ExternalServiceConfig:
    """获取外部服务配置（快捷方法）"""
    config = get_enhanced_config()
    return config.external_services


# 向后兼容的函数
def get_config() -> EnhancedDatabaseConfig:
    """获取配置（覆盖原函数，返回增强配置）"""
    return get_enhanced_config()
