# database_service/managers/__init__.py
"""
数据库管理器模块 - 延迟导入版本
避免在导入模块时就加载所有依赖
"""
import sys
from typing import Any

__all__ = [
    'BaseDatabaseManager',
    'PostgresDatabaseManager',
    'MemoryDatabaseManager',
    'RedisCachedDatabaseManager',
    'RedisEventBus',
    'UnifiedRedisStreamBus',
]

# 延迟导入函数
def __getattr__(name: str) -> Any:
    if name == 'PostgresDatabaseManager':
        from .postgres_manager import PostgresDatabaseManager
        return PostgresDatabaseManager
    elif name == 'BaseDatabaseManager':
        from .base_manager import BaseDatabaseManager
        return BaseDatabaseManager
    elif name == 'MemoryDatabaseManager':
        from .memory_manager import MemoryDatabaseManager
        return MemoryDatabaseManager
    elif name == 'RedisCachedDatabaseManager':
        from .redis_cached_manager import RedisCachedDatabaseManager
        return RedisCachedDatabaseManager
    elif name == 'RedisEventBus':
        from .redis_event_bus import RedisEventBus
        return RedisEventBus
    elif name == 'UnifiedRedisStreamBus':
        from .redis_stream_bus import UnifiedRedisStreamBus
        return UnifiedRedisStreamBus
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 可选：为了方便，也可以提供直接的导入，但用try-except包装
try:
    from .base_manager import BaseDatabaseManager
    from .memory_manager import MemoryDatabaseManager
    from .redis_cached_manager import RedisCachedDatabaseManager
    from .redis_event_bus import RedisEventBus
    from .redis_stream_bus import UnifiedRedisStreamBus
except ImportError as e:
    print(f"⚠️  部分模块导入失败: {e}")
    
# 异步导入Postgres，避免一开始就失败
_postgres_available = False
try:
    import asyncpg
    _postgres_available = True
except ImportError:
    print("⚠️  asyncpg未安装，PostgresDatabaseManager将不可用")

if _postgres_available:
    try:
        from .postgres_manager import PostgresDatabaseManager
    except ImportError as e:
        print(f"⚠️  PostgresDatabaseManager导入失败: {e}")
        PostgresDatabaseManager = None
else:
    PostgresDatabaseManager = None