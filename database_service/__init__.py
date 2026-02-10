"""
Database Service Module
统一数据网关服务，提供Redis缓存优化的数据库访问
简化版本，避免导入链导致的 aioredis 兼容性问题
"""
__version__ = "1.0.0"
__author__ = "AI Investment Assistant Team"

# 延迟导入以避免 aioredis 问题
def __getattr__(name):
    """延迟导入模块属性"""
    if name == 'DatabaseGateway':
        from .gateway import DatabaseGateway
        return DatabaseGateway
    elif name == 'DatabaseManagerFactory':
        from .factory import DatabaseManagerFactory
        return DatabaseManagerFactory
    elif name == 'DatabaseClient':
        from .client import DatabaseClient
        return DatabaseClient
    elif name == 'get_config':
        from .config import get_config
        return get_config
    elif name == 'DatabaseConfig':
        from .config import DatabaseConfig
        return DatabaseConfig
    raise AttributeError(f"module 'database_service' has no attribute '{name}'")

# 仍然直接导出版本信息
__all__ = [
    'DatabaseGateway',
    'DatabaseManagerFactory', 
    'DatabaseClient',
    'get_config',
    'DatabaseConfig'
]