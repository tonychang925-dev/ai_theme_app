"""
Stream 消息接口定义 - 重试增强版
扩展原有的数据库接口，支持 Redis Stream 功能和重试机制
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable, AsyncIterator, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

from database_service.interface import ThemeRecord, EventThemeRelation
from database_service.streams.database_interface_ext import StreamEnhancedDatabaseManager

class StreamPriority(Enum):
    """Stream优先级"""
    CRITICAL = "critical"    # 关键：立即处理
    HIGH = "high"           # 高：快速处理
    MEDIUM = "medium"       # 中：普通处理
    LOW = "low"             # 低：后台处理


class MessageStatus(Enum):
    """消息状态"""
    PENDING = "pending"      # 待处理
    PROCESSING = "processing"  # 处理中
    SUCCESS = "success"      # 成功
    FAILED = "failed"        # 失败
    RETRYING = "retrying"    # 重试中
    DEAD_LETTER = "dead_letter"  # 死信
    RETRY_EXHAUSTED = "retry_exhausted"  # 重试耗尽


class MessageType(Enum):
    """消息类型"""
    NEWS = "news"                     # 新闻消息
    NEWS_RAW = "news_raw"             # 原始新闻
    EVENT_EXTRACTION = "event_extraction"  # 事件提取
    EVENT_CLASSIFICATION = "event_classification"  # 事件分类
    EVENT_MAJOR = "event_major"       # 重大事件
    EVENT_NORMAL = "event_normal"     # 普通事件
    THEME_UPDATE = "theme_update"     # 主题更新
    THEME_CREATE = "theme_create"     # 主题创建
    THEME_HEAT_CHANGE = "theme_heat_change"  # 主题热度变化
    THEME_MATCH = "theme_match"       # 主题匹配
    RELATION_CREATE = "relation_create"  # 关联创建
    DEAD_LETTER = "dead_letter"       # 死信消息
    SYSTEM_EVENT = "system_event"     # 系统事件
    HEALTH_CHECK = "health_check"     # 健康检查
    METRICS = "metrics"               # 指标数据
    RETRY_ATTEMPT = "retry_attempt"   # 重试尝试
    RETRY_SUCCESS = "retry_success"   # 重试成功
    RETRY_FAILED = "retry_failed"     # 重试失败


class RetryStrategy(Enum):
    """重试策略（与 RetryManager 保持一致）"""
    FIXED = "fixed"           # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    FIBONACCI = "fibonacci"   # 斐波那契退避
    RANDOM = "random"         # 随机退避


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_delay: float = 60.0
    jitter: bool = True
    retry_on_exception: Optional[List[str]] = None
    stop_on_exception: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "strategy": self.strategy.value,
            "max_delay": self.max_delay,
            "jitter": self.jitter,
            "retry_on_exception": self.retry_on_exception,
            "stop_on_exception": self.stop_on_exception
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryConfig':
        """从字典创建RetryConfig"""
        strategy = RetryStrategy(data.get("strategy", "exponential"))
        return cls(
            max_retries=data.get("max_retries", 3),
            base_delay=data.get("base_delay", 1.0),
            strategy=strategy,
            max_delay=data.get("max_delay", 60.0),
            jitter=data.get("jitter", True),
            retry_on_exception=data.get("retry_on_exception"),
            stop_on_exception=data.get("stop_on_exception")
        )


@dataclass
class RetryStats:
    """重试统计"""
    total_retries: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    retry_history: List[Dict[str, Any]] = field(default_factory=list)
    last_retry_time: Optional[datetime] = None
    retry_success_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_retries": self.total_retries,
            "successful_retries": self.successful_retries,
            "failed_retries": self.failed_retries,
            "retry_history_count": len(self.retry_history),
            "last_retry_time": self.last_retry_time.isoformat() if self.last_retry_time else None,
            "retry_success_rate": self.retry_success_rate
        }
    
    def update_success_rate(self):
        """更新成功率"""
        total = self.successful_retries + self.failed_retries
        if total > 0:
            self.retry_success_rate = self.successful_retries / total


@dataclass
class StreamMessage:
    """Stream消息封装（重试增强版）"""
    id: str                           # 消息ID
    stream: str                       # Stream名称
    type: MessageType                 # 消息类型
    data: Dict[str, Any]              # 消息数据
    metadata: Dict[str, Any] = field(default_factory=lambda: {
        "priority": StreamPriority.MEDIUM.value,
        "status": MessageStatus.PENDING.value,
        "attempts": 0,
        "max_retries": 3,
        "retry_strategy": RetryStrategy.EXPONENTIAL.value,
        "retry_delay": 0.0,
        "last_error": None,
        "retry_history": [],
        "created_at": datetime.now().isoformat()
    })
    timestamp: Optional[datetime] = None  # 消息时间戳
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "stream": self.stream,
            "type": self.type.value,
            "data": self.data,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StreamMessage':
        """从字典创建StreamMessage"""
        # 解析消息类型
        message_type = MessageType(data.get("type", "unknown"))
        
        # 解析时间戳
        timestamp_str = data.get("timestamp")
        timestamp = None
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                pass
        
        return cls(
            id=data["id"],
            stream=data["stream"],
            type=message_type,
            data=data.get("data", {}),
            metadata=data.get("metadata", {}),
            timestamp=timestamp
        )
    
    @property
    def priority(self) -> StreamPriority:
        """获取优先级"""
        priority_str = self.metadata.get("priority", "medium")
        return StreamPriority(priority_str)
    
    @property
    def status(self) -> MessageStatus:
        """获取状态"""
        status_str = self.metadata.get("status", "pending")
        return MessageStatus(status_str)
    
    @property
    def attempts(self) -> int:
        """获取尝试次数"""
        return self.metadata.get("attempts", 0)
    
    @property
    def max_retries(self) -> int:
        """获取最大重试次数"""
        return self.metadata.get("max_retries", 3)
    
    @property
    def can_retry(self) -> bool:
        """检查是否还可以重试"""
        return self.attempts < self.max_retries and self.status != MessageStatus.DEAD_LETTER
    
    def increment_attempts(self):
        """增加尝试次数"""
        self.metadata["attempts"] = self.attempts + 1
    
    def update_status(self, status: MessageStatus):
        """更新状态"""
        self.metadata["status"] = status.value
        
        # 如果是重试状态，记录时间
        if status == MessageStatus.RETRYING:
            self.metadata["last_retry_time"] = datetime.now().isoformat()
    
    def record_retry_attempt(self, error: str = None, delay: float = 0.0):
        """记录重试尝试"""
        self.increment_attempts()
        self.update_status(MessageStatus.RETRYING)
        
        retry_record = {
            "attempt": self.attempts,
            "timestamp": datetime.now().isoformat(),
            "delay": delay,
            "error": error
        }
        
        # 更新重试历史
        history = self.metadata.get("retry_history", [])
        history.append(retry_record)
        self.metadata["retry_history"] = history
        
        # 记录最后错误
        if error:
            self.metadata["last_error"] = error
        
        # 记录延迟
        self.metadata["retry_delay"] = delay
    
    def record_success(self):
        """记录成功"""
        self.update_status(MessageStatus.SUCCESS)
        self.metadata["processed_at"] = datetime.now().isoformat()
    
    def record_failure(self, error: str = None):
        """记录失败"""
        if self.can_retry:
            self.update_status(MessageStatus.RETRYING)
        else:
            self.update_status(MessageStatus.RETRY_EXHAUSTED)
        
        if error:
            self.metadata["last_error"] = error
    
    def mark_as_dead_letter(self, error: str = None):
        """标记为死信"""
        self.update_status(MessageStatus.DEAD_LETTER)
        if error:
            self.metadata["dead_letter_reason"] = error
        self.metadata["dead_letter_time"] = datetime.now().isoformat()
    
    def get_retry_history(self) -> List[Dict[str, Any]]:
        """获取重试历史"""
        return self.metadata.get("retry_history", [])
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'StreamMessage':
        """从JSON字符串创建StreamMessage"""
        data = json.loads(json_str)
        return cls.from_dict(data)


# ========== 消息类定义保持不变，但添加重试支持 ==========

@dataclass
class NewsMessage:
    """新闻消息"""
    id: str                           # 新闻ID
    title: str                        # 标题
    content: str                      # 内容
    source: str = "unknown"           # 来源
    publish_time: Optional[datetime] = None  # 发布时间
    keywords: List[str] = field(default_factory=list)  # 关键词
    categories: List[str] = field(default_factory=list)  # 分类
    entities: Dict[str, List[str]] = field(default_factory=dict)  # 实体
    sentiment_score: float = 0.0      # 情感评分
    retry_config: Optional[RetryConfig] = None  # 重试配置
    
    def to_stream_message(self, stream: str = "news:raw") -> StreamMessage:
        """转换为StreamMessage"""
        message = StreamMessage(
            id=f"news_{self.id}",
            stream=stream,
            type=MessageType.NEWS_RAW,
            data={
                "id": self.id,
                "title": self.title,
                "content": self.content,
                "source": self.source,
                "publish_time": self.publish_time.isoformat() if self.publish_time else None,
                "keywords": self.keywords,
                "categories": self.categories,
                "entities": self.entities,
                "sentiment_score": self.sentiment_score
            },
            timestamp=self.publish_time or datetime.now()
        )
        
        # 添加重试配置
        if self.retry_config:
            message.metadata.update(self.retry_config.to_dict())
        
        return message
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NewsMessage':
        """从字典创建NewsMessage"""
        # 解析时间戳
        publish_time_str = data.get("publish_time")
        publish_time = None
        if publish_time_str:
            try:
                publish_time = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
            except:
                pass
        
        # 解析重试配置
        retry_config = None
        if "max_retries" in data or "retry_strategy" in data:
            retry_config = RetryConfig.from_dict(data)
        
        return cls(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            content=data.get("content", ""),
            source=data.get("source", "unknown"),
            publish_time=publish_time,
            keywords=data.get("keywords", []),
            categories=data.get("categories", []),
            entities=data.get("entities", {}),
            sentiment_score=data.get("sentiment_score", 0.0),
            retry_config=retry_config
        )


# ... 其他消息类（EventExtractionMessage, ThemeUpdateMessage等）的更新方式类似
# 为每个消息类添加 retry_config 字段，并在 to_stream_message 方法中处理
class StreamProducer:
    """流生产者接口"""
    async def publish(self, stream_name: str, data: dict) -> str:
        """发布消息到流"""
        raise NotImplementedError
    
    async def close(self):
        """关闭连接"""
        pass


# ========== 基础流消费者接口 ==========
class StreamConsumer:
    """流消费者接口"""
    async def consume(self, stream_name: str, consumer_group: str, consumer_name: str,
                     count: int = 10, block_ms: int = 1000) -> list:
        """消费消息"""
        raise NotImplementedError
    
    async def acknowledge(self, stream_name: str, message_id: str):
        """确认消息"""
        pass
    
    async def close(self):
        """关闭连接"""
        pass


# ========== 增强的接口定义 ==========

class RetryEnhancedStreamProducer(StreamProducer):
    """重试增强的Stream生产者接口"""
    
    @abstractmethod
    async def publish_with_retry(self, message: StreamMessage, 
                                retry_config: Optional[RetryConfig] = None) -> str:
        """带重试的发布消息到Stream"""
        pass
    
    @abstractmethod
    async def publish_batch_with_retry(self, messages: List[StreamMessage],
                                      retry_config: Optional[RetryConfig] = None) -> List[str]:
        """带重试的批量发布消息"""
        pass
    
    @abstractmethod
    async def smart_publish(self, data: Dict[str, Any], 
                           data_type: Optional[str] = None,
                           retry_config: Optional[RetryConfig] = None) -> str:
        """智能发布（自动识别数据类型）"""
        pass
    
    @abstractmethod
    async def get_retry_stats(self) -> RetryStats:
        """获取重试统计"""
        pass


class RetryEnhancedStreamConsumer(StreamConsumer):
    """重试增强的Stream消费者接口"""
    
    @abstractmethod
    async def consume_with_retry(self, count: int = 10, 
                                retry_config: Optional[RetryConfig] = None) -> List[StreamMessage]:
        """带重试的消费消息"""
        pass
    
    @abstractmethod
    async def process_with_retry(self, message: StreamMessage,
                                handler: Callable,
                                retry_config: Optional[RetryConfig] = None) -> bool:
        """带重试的处理消息"""
        pass
    
    @abstractmethod
    async def get_retry_config(self, operation_type: str = None) -> RetryConfig:
        """获取重试配置"""
        pass
    
    @abstractmethod
    async def update_retry_config(self, config: RetryConfig, 
                                 operation_type: str = None):
        """更新重试配置"""
        pass


# ========== 重试增强的数据库管理器接口 ==========

class RetryEnhancedDatabaseManager(StreamEnhancedDatabaseManager):
    """重试增强的数据库管理器接口"""
    
    # 重试配置管理
    @abstractmethod
    async def enable_retry_function(self, enable: bool = True):
        """启用或禁用重试功能"""
        pass
    
    @abstractmethod
    async def get_retry_config(self, operation_type: str = None) -> RetryConfig:
        """获取重试配置"""
        pass
    
    @abstractmethod
    async def update_retry_config(self, config_updates: Dict[str, Any], 
                                 operation_type: str = None):
        """更新重试配置"""
        pass
    
    # 重试增强的Stream发布方法
    @abstractmethod
    async def publish_to_stream_with_retry(self, stream_key: str, 
                                          data: Dict[str, Any],
                                          retry_config: Optional[RetryConfig] = None) -> Optional[str]:
        """带重试的发布消息到Stream"""
        pass
    
    @abstractmethod
    async def smart_publish(self, data: Dict[str, Any], 
                           data_type: Optional[str] = None,
                           retry_config: Optional[RetryConfig] = None) -> Optional[str]:
        """智能发布（自动识别数据类型）"""
        pass
    
    @abstractmethod
    async def batch_publish(self, items: List[Dict[str, Any]], 
                           data_type: Optional[str] = None,
                           max_concurrent: int = 5,
                           retry_config: Optional[RetryConfig] = None) -> List[Optional[str]]:
        """批量发布（带并发控制和重试）"""
        pass
    
    # 重试增强的数据库操作
    @abstractmethod
    async def create_theme_with_retry(self, name: str, code: str, 
                                     retry_config: Optional[RetryConfig] = None,
                                     **kwargs) -> Optional[ThemeRecord]:
        """带重试的主题创建"""
        pass
    
    @abstractmethod
    async def update_theme_with_retry(self, theme_id: int, 
                                     updates: Dict[str, Any],
                                     retry_config: Optional[RetryConfig] = None) -> Optional[ThemeRecord]:
        """带重试的主题更新"""
        pass
    
    # 重试统计和监控
    @abstractmethod
    async def get_retry_stats(self) -> RetryStats:
        """获取重试统计"""
        pass
    
    @abstractmethod
    async def get_enhanced_stats_with_retry(self) -> Dict[str, Any]:
        """获取包含重试统计的增强统计信息"""
        pass
    
    @abstractmethod
    async def health_check_with_retry(self) -> Dict[str, Any]:
        """带重试的健康检查"""
        pass
    
    @abstractmethod
    async def print_retry_report(self):
        """打印重试报告"""
        pass


# ========== 重试事件监听器 ==========

class RetryEventListener(StreamEventListener):
    """重试事件监听器接口"""
    
    @abstractmethod
    async def on_retry_attempt(self, message: StreamMessage, attempt: int, delay: float):
        """重试尝试时触发"""
        pass
    
    @abstractmethod
    async def on_retry_success(self, message: StreamMessage, total_attempts: int):
        """重试成功时触发"""
        pass
    
    @abstractmethod
    async def on_retry_failed(self, message: StreamMessage, total_attempts: int, error: Exception):
        """重试失败时触发"""
        pass
    
    @abstractmethod
    async def on_retry_exhausted(self, message: StreamMessage, max_retries: int):
        """重试耗尽时触发"""
        pass


class RetryEventBus(EventBus):
    """重试事件总线接口"""
    
    @abstractmethod
    async def subscribe_retry_event(self, event_type: MessageType, listener: RetryEventListener):
        """订阅重试事件"""
        pass
    
    @abstractmethod
    async def publish_retry_attempt(self, message: StreamMessage):
        """发布重试尝试事件"""
        pass
    
    @abstractmethod
    async def publish_retry_success(self, message: StreamMessage):
        """发布重试成功事件"""
        pass
    
    @abstractmethod
    async def publish_retry_failed(self, message: StreamMessage, error: Exception):
        """发布重试失败事件"""
        pass


# ========== 重试策略工厂 ==========

class RetryStrategyFactory:
    """重试策略工厂"""
    
    @staticmethod
    def create_strategy(strategy_type: RetryStrategy, base_delay: float = 1.0) -> Callable[[int], float]:
        """创建重试策略函数"""
        strategies = {
            RetryStrategy.FIXED: lambda attempt: base_delay,
            RetryStrategy.EXPONENTIAL: lambda attempt: base_delay * (2 ** (attempt - 1)),
            RetryStrategy.FIBONACCI: lambda attempt: base_delay * RetryStrategyFactory._fibonacci(attempt + 1),
            RetryStrategy.RANDOM: lambda attempt: base_delay * (0.5 + (0.5 * (attempt - 1))),
        }
        
        return strategies.get(strategy_type, strategies[RetryStrategy.EXPONENTIAL])
    
    @staticmethod
    def _fibonacci(n: int) -> int:
        """计算斐波那契数"""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b


# ========== 重试工具函数 ==========

def create_retry_config(max_retries: int = 3, base_delay: float = 1.0,
                       strategy: Union[str, RetryStrategy] = "exponential",
                       max_delay: float = 60.0, jitter: bool = True) -> RetryConfig:
    """创建重试配置"""
    if isinstance(strategy, str):
        strategy = RetryStrategy(strategy)
    
    return RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        strategy=strategy,
        max_delay=max_delay,
        jitter=jitter
    )


def should_retry_message(message: StreamMessage, error: Exception = None) -> bool:
    """判断是否应该重试消息"""
    # 检查状态
    if message.status in [MessageStatus.SUCCESS, MessageStatus.DEAD_LETTER, MessageStatus.RETRY_EXHAUSTED]:
        return False
    
    # 检查尝试次数
    if message.attempts >= message.max_retries:
        return False
    
    # 检查错误类型（如果有）
    if error and hasattr(error, '__name__'):
        error_name = error.__name__
        # 从元数据获取停止重试的异常列表
        stop_on_exception = message.metadata.get("stop_on_exception", [])
        if error_name in stop_on_exception:
            return False
    
    return True


def calculate_retry_delay(message: StreamMessage, strategy: RetryStrategy = None) -> float:
    """计算重试延迟"""
    if strategy is None:
        strategy_str = message.metadata.get("retry_strategy", "exponential")
        strategy = RetryStrategy(strategy_str)
    
    base_delay = message.metadata.get("base_delay", 1.0)
    max_delay = message.metadata.get("max_delay", 60.0)
    jitter = message.metadata.get("jitter", True)
    
    # 计算基础延迟
    strategy_func = RetryStrategyFactory.create_strategy(strategy, base_delay)
    delay = strategy_func(message.attempts)
    
    # 添加抖动（如果有）
    if jitter:
        import random
        jitter_factor = random.uniform(0.9, 1.1)
        delay = delay * jitter_factor
    
    # 限制最大延迟
    delay = min(delay, max_delay)
    
    return round(delay, 2)


def create_retry_message(original_message: StreamMessage, error: str = None) -> StreamMessage:
    """为重试创建新消息"""
    retry_message = StreamMessage(
        id=f"retry_{original_message.id}_{original_message.attempts + 1}",
        stream=original_message.stream,
        type=MessageType.RETRY_ATTEMPT,
        data={
            "original_message": original_message.to_dict(),
            "retry_attempt": original_message.attempts + 1,
            "error": error,
            "retry_timestamp": datetime.now().isoformat()
        },
        metadata={
            "priority": StreamPriority.HIGH.value,
            "status": MessageStatus.RETRYING.value,
            "original_message_id": original_message.id,
            "original_stream": original_message.stream
        },
        timestamp=datetime.now()
    )
    
    return retry_message


# ========== 消息验证增强 ==========

def validate_message_for_retry(message: StreamMessage) -> List[str]:
    """验证消息是否适合重试"""
    issues = []
    
    # 检查必要字段
    if not message.id:
        issues.append("消息ID为空")
    
    if not message.stream:
        issues.append("Stream名称为空")
    
    if not message.data:
        issues.append("消息数据为空")
    
    # 检查元数据
    if "max_retries" not in message.metadata:
        issues.append("未指定最大重试次数")
    
    if "retry_strategy" not in message.metadata:
        issues.append("未指定重试策略")
    
    # 检查状态
    if message.status in [MessageStatus.SUCCESS, MessageStatus.DEAD_LETTER]:
        issues.append(f"消息状态不允许重试: {message.status.value}")
    
    return issues


# ========== 接口适配器 ==========

class RetryAdapter:
    """重试适配器（将现有接口适配为重试接口）"""
    
    def __init__(self, target, retry_config: Optional[RetryConfig] = None):
        self.target = target
        self.retry_config = retry_config or create_retry_config()
        self.stats = RetryStats()
    
    async def execute_with_retry(self, method_name: str, *args, **kwargs):
        """带重试执行目标方法"""
        import asyncio
        
        method = getattr(self.target, method_name, None)
        if not method:
            raise AttributeError(f"目标对象没有方法 {method_name}")
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                result = await method(*args, **kwargs)
                
                if attempt > 0:
                    self.stats.successful_retries += 1
                    self.stats.last_retry_time = datetime.now()
                
                self.stats.update_success_rate()
                return result
                
            except Exception as e:
                # 检查是否应该停止重试
                if self._should_stop_retry(e, attempt):
                    self.stats.failed_retries += 1
                    raise
                
                # 如果是最后一次尝试，抛出异常
                if attempt == self.retry_config.max_retries:
                    self.stats.failed_retries += 1
                    raise
                
                # 计算延迟并等待
                delay = calculate_retry_delay(
                    StreamMessage(
                        id=f"adapter_{method_name}",
                        stream="adapter",
                        type=MessageType.SYSTEM_EVENT,
                        data={"method": method_name},
                        metadata={
                            "max_retries": self.retry_config.max_retries,
                            "retry_strategy": self.retry_config.strategy.value,
                            "base_delay": self.retry_config.base_delay,
                            "jitter": self.retry_config.jitter
                        }
                    ),
                    strategy=self.retry_config.strategy
                )
                
                # 记录重试历史
                self.stats.total_retries += 1
                self.stats.retry_history.append({
                    "method": method_name,
                    "attempt": attempt + 1,
                    "delay": delay,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                
                await asyncio.sleep(delay)
    
    def _should_stop_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该停止重试"""
        # 检查异常类型
        error_name = type(error).__name__
        if self.retry_config.stop_on_exception and error_name in self.retry_config.stop_on_exception:
            return True
        
        # 检查是否需要重试的异常
        if self.retry_config.retry_on_exception and error_name not in self.retry_config.retry_on_exception:
            return True
        
        return False
    
    def get_stats(self) -> RetryStats:
        """获取统计信息"""
        return self.stats


# ========== 导出所有类型和接口 ==========

__all__ = [
    # 枚举
    'StreamPriority',
    'MessageStatus',
    'MessageType',
    'RetryStrategy',
    
    # 配置和统计
    'RetryConfig',
    'RetryStats',
    
    # 消息类
    'StreamMessage',
    'NewsMessage',
    'EventExtractionMessage',
    'ThemeUpdateMessage',
    'ThemeMatchMessage',
    'DeadLetterMessage',
    
    # 接口
    'StreamProducer',
    'StreamConsumer',
    'MessageHandler',
    'StreamManager',
    'StreamEnhancedDatabaseManager',
    'RetryEnhancedStreamProducer',
    'RetryEnhancedStreamConsumer',
    'RetryEnhancedDatabaseManager',
    'StreamEventListener',
    'RetryEventListener',
    'EventBus',
    'RetryEventBus',
    
    # 工具
    'RetryStrategyFactory',
    'create_retry_config',
    'should_retry_message',
    'calculate_retry_delay',
    'create_retry_message',
    'validate_message_for_retry',
    'RetryAdapter',
    
    # 工厂函数
    'create_news_message',
    'create_event_extraction_message',
    'create_theme_update_message_from_record',
    'create_theme_match_message_from_relation',
    'create_dead_letter_message',
    'validate_message_data',
    'get_message_priority',
]