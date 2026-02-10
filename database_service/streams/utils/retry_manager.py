# database_service/streams/utils/retry_manager.py
"""
重试管理器 - 生产就绪版本
支持多种重试策略和详细的统计
"""
import asyncio
import logging
import time
import random
from typing import Callable, Any, Optional, Dict, List, Union, Type
from datetime import datetime
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)

class RetryStrategy(Enum):
    """重试策略"""
    FIXED = "fixed"           # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    FIBONACCI = "fibonacci"   # 斐波那契退避
    RANDOM = "random"         # 随机退避

class RetryManager:
    """重试管理器"""
    
    def __init__(self, 
                 max_retries: int = 3, 
                 base_delay: float = 1.0,
                 strategy: Union[str, RetryStrategy] = RetryStrategy.EXPONENTIAL,
                 max_delay: float = 60.0,
                 jitter: bool = True,
                 retry_on_exception: Optional[List[Type[Exception]]] = None,
                 stop_on_exception: Optional[List[Type[Exception]]] = None):
        """
        初始化重试管理器
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            strategy: 重试策略
            max_delay: 最大延迟时间（秒）
            jitter: 是否添加随机抖动
            retry_on_exception: 需要重试的异常类型列表
            stop_on_exception: 不需要重试的异常类型列表
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        
        if isinstance(strategy, str):
            self.strategy = RetryStrategy(strategy)
        else:
            self.strategy = strategy
            
        self.max_delay = max_delay
        self.jitter = jitter
        
        # 异常处理配置
        self.retry_on_exception = retry_on_exception or []
        self.stop_on_exception = stop_on_exception or []
        
        # 统计信息
        self.stats = {
            "total_retries": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "retry_history": [],
            "execution_times": [],
            "start_time": None,
            "end_time": None
        }
        
        # Fibonacci序列缓存
        self._fib_cache = {0: 0, 1: 1}
    
    def _get_fibonacci(self, n: int) -> int:
        """获取斐波那契数"""
        if n in self._fib_cache:
            return self._fib_cache[n]
        
        self._fib_cache[n] = self._get_fibonacci(n-1) + self._get_fibonacci(n-2)
        return self._fib_cache[n]
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        if attempt <= 0:
            return 0
        
        if self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2 ** attempt)
        elif self.strategy == RetryStrategy.FIBONACCI:
            delay = self.base_delay * self._get_fibonacci(attempt + 1)
        elif self.strategy == RetryStrategy.RANDOM:
            delay = self.base_delay * random.uniform(0.5, 1.5)
        else:
            delay = self.base_delay
        
        # 限制最大延迟
        delay = min(delay, self.max_delay)
        
        # 添加抖动（±10%）
        if self.jitter:
            jitter_factor = random.uniform(0.9, 1.1)
            delay = delay * jitter_factor
        
        return round(delay, 2)
    
    def _should_retry_exception(self, error: Exception) -> bool:
        """根据异常类型判断是否应该重试"""
        error_type = type(error)
        
        # 检查停止重试的异常
        for stop_exception in self.stop_on_exception:
            if issubclass(error_type, stop_exception):
                return False
        
        # 如果指定了需要重试的异常，只重试这些异常
        if self.retry_on_exception:
            for retry_exception in self.retry_on_exception:
                if issubclass(error_type, retry_exception):
                    return True
            return False
        
        # 默认情况下，重试所有异常（除了明确的停止异常）
        return True
    
    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """综合判断是否应该重试"""
        if attempt >= self.max_retries:
            return False
        
        if not self._should_retry_exception(error):
            return False
        
        # 检查错误信息
        error_str = str(error).lower()
        non_retryable_keywords = [
            "validation_error",
            "invalid_format",
            "permission_denied",
            "not_found",
            "unauthorized",
            "invalid_request"
        ]
        
        for keyword in non_retryable_keywords:
            if keyword in error_str:
                return False
        
        return True
    
    async def execute_with_retry(self, func: Callable, *args, 
                                 context: Optional[Dict] = None,
                                 **kwargs) -> Any:
        """
        带重试的执行
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            context: 上下文信息（会记录在统计中）
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            Exception: 如果所有重试都失败
        """
        self.stats["start_time"] = datetime.now().isoformat()
        last_exception = None
        context = context or {}
        
        for attempt in range(self.max_retries + 1):  # +1 包含第一次尝试
            try:
                start_time = time.time()
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # 记录执行时间
                self.stats["execution_times"].append(execution_time)
                
                # 记录成功重试
                if attempt > 0:
                    self.stats["successful_retries"] += 1
                    logger.info(f"✅ 重试成功 (尝试 {attempt}/{self.max_retries}，耗时: {execution_time:.3f}s)")
                
                self.stats["end_time"] = datetime.now().isoformat()
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time if 'start_time' in locals() else 0
                self.stats["execution_times"].append(execution_time)
                
                last_exception = e
                
                # 判断是否应该重试
                if not self._should_retry(e, attempt):
                    self.stats["failed_retries"] += 1
                    logger.error(f"❌ 不需要重试的异常 (尝试 {attempt + 1}/{self.max_retries + 1}): {type(e).__name__}: {e}")
                    break
                
                # 如果是最后一次尝试，不再重试
                if attempt == self.max_retries:
                    self.stats["failed_retries"] += 1
                    logger.error(f"❌ 所有重试失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {type(e).__name__}: {e}")
                    break
                
                # 计算延迟时间
                delay = self._calculate_delay(attempt)
                
                # 记录重试
                self.stats["total_retries"] += 1
                self.stats["retry_history"].append({
                    "attempt": attempt + 1,
                    "timestamp": datetime.now().isoformat(),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "delay": delay,
                    "execution_time": execution_time,
                    "context": context
                })
                
                logger.warning(f"⚠️ 重试 {attempt + 1}/{self.max_retries} in {delay}s: {type(e).__name__}: {e}")
                
                # 等待
                await asyncio.sleep(delay)
        
        self.stats["end_time"] = datetime.now().isoformat()
        
        # 所有尝试都失败，抛出最后一个异常
        raise last_exception
    
    def get_stats(self) -> Dict[str, Any]:
        """获取详细的统计信息"""
        stats = self.stats.copy()
        
        # 计算成功率
        total_attempts = stats["successful_retries"] + stats["failed_retries"]
        if total_attempts > 0:
            stats["success_rate"] = stats["successful_retries"] / total_attempts
        else:
            stats["success_rate"] = 0
        
        # 计算平均重试次数
        if stats["failed_retries"] > 0:
            stats["avg_retries_per_failure"] = stats["total_retries"] / stats["failed_retries"]
        else:
            stats["avg_retries_per_failure"] = 0
        
        # 计算执行时间统计
        if stats["execution_times"]:
            times = stats["execution_times"]
            stats["avg_execution_time"] = sum(times) / len(times)
            stats["min_execution_time"] = min(times)
            stats["max_execution_time"] = max(times)
            stats["total_execution_time"] = sum(times)
        else:
            stats["avg_execution_time"] = 0
            stats["min_execution_time"] = 0
            stats["max_execution_time"] = 0
            stats["total_execution_time"] = 0
        
        # 计算总耗时
        if stats["start_time"] and stats["end_time"]:
            start = datetime.fromisoformat(stats["start_time"])
            end = datetime.fromisoformat(stats["end_time"])
            stats["total_duration"] = (end - start).total_seconds()
        else:
            stats["total_duration"] = 0
        
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_retries": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "retry_history": [],
            "execution_times": [],
            "start_time": None,
            "end_time": None
        }
    
    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()
        
        print("\n📊 重试统计信息")
        print("=" * 50)
        print(f"总重试次数: {stats['total_retries']}")
        print(f"成功重试: {stats['successful_retries']}")
        print(f"失败重试: {stats['failed_retries']}")
        print(f"成功率: {stats['success_rate']:.1%}")
        print(f"平均重试次数/失败: {stats['avg_retries_per_failure']:.2f}")
        print(f"总耗时: {stats['total_duration']:.2f}s")
        print(f"平均执行时间: {stats['avg_execution_time']:.3f}s")
        print(f"总执行时间: {stats['total_execution_time']:.2f}s")
        
        if stats["retry_history"]:
            print("\n📋 重试历史:")
            for i, retry in enumerate(stats["retry_history"], 1):
                print(f"  {i}. 尝试 {retry['attempt']} - {retry['timestamp']}")
                print(f"     错误: {retry['error_type']}: {retry['error_message'][:50]}...")
                print(f"     延迟: {retry['delay']}s, 执行时间: {retry['execution_time']:.3f}s")

# 便捷装饰器
def with_retry(max_retries: int = 3, 
               base_delay: float = 1.0,
               strategy: Union[str, RetryStrategy] = "exponential",
               max_delay: float = 60.0,
               jitter: bool = True,
               retry_on_exception: Optional[List[Type[Exception]]] = None,
               stop_on_exception: Optional[List[Type[Exception]]] = None):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        strategy: 重试策略
        max_delay: 最大延迟时间（秒）
        jitter: 是否添加随机抖动
        retry_on_exception: 需要重试的异常类型列表
        stop_on_exception: 不需要重试的异常类型列表
    """
    if isinstance(strategy, str):
        strategy = RetryStrategy(strategy)
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从kwargs中提取context
            context = kwargs.pop('retry_context', {}) if 'retry_context' in kwargs else {}
            
            retry_manager = RetryManager(
                max_retries=max_retries,
                base_delay=base_delay,
                strategy=strategy,
                max_delay=max_delay,
                jitter=jitter,
                retry_on_exception=retry_on_exception,
                stop_on_exception=stop_on_exception
            )
            
            return await retry_manager.execute_with_retry(
                func, *args, context=context, **kwargs
            )
        return wrapper
    return decorator

# 快速使用的函数
async def retry_async(func: Callable, *args, **kwargs):
    """快速重试函数（异步）"""
    retry_manager = RetryManager()
    return await retry_manager.execute_with_retry(func, *args, **kwargs)

def retry_sync(func: Callable, *args, **kwargs):
    """快速重试函数（同步）"""
    retry_manager = RetryManager()
    
    async def async_wrapper():
        return await retry_manager.execute_with_retry(
            lambda: asyncio.sleep(0) or func(*args, **kwargs)
        )
    
    return asyncio.run(async_wrapper())