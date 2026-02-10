# tests/conftest.py
"""
测试配置和夹具 - 修复版
"""
import asyncio
import pytest
import pytest_asyncio
import os
import sys
import types
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# ============================================
# 第一步：先安全地设置 aioredis 模块
# ============================================

def setup_aioredis_safely():
    """安全地设置 aioredis 模块"""
    try:
        # 首先尝试使用 redis.asyncio
        import redis.asyncio as aioredis
        print("✅ 使用 redis.asyncio 作为 aioredis")
        return True
    except ImportError:
        print("⚠️  redis.asyncio 不可用")
    
    try:
        # 其次尝试直接导入 aioredis
        import aioredis
        print("✅ 使用原版 aioredis")
        return True
    except ImportError:
        print("⚠️  aioredis 不可用")
    
    # 最后创建虚拟模块
    try:
        class AioredisStub(types.ModuleType):
            def __init__(self):
                super().__init__('aioredis')
                self.exceptions = types.ModuleType('aioredis.exceptions')
                
                class RedisError(Exception):
                    pass
                
                class TimeoutError(RedisError):
                    pass
                
                class ConnectionError(RedisError):
                    pass
                
                self.exceptions.RedisError = RedisError
                self.exceptions.TimeoutError = TimeoutError
                self.exceptions.ConnectionError = ConnectionError
        
        sys.modules['aioredis'] = AioredisStub()
        sys.modules['aioredis.exceptions'] = sys.modules['aioredis'].exceptions
        print("✅ 使用虚拟 aioredis 模块")
        return True
    except Exception as e:
        print(f"❌ 无法设置 aioredis: {e}")
        return False

# 立即执行设置
setup_aioredis_safely()

# ============================================
# 第二步：设置导入路径
# ============================================

# 获取项目根目录路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent

# 将项目根目录添加到 Python 路径
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 将 database_service 目录添加到 Python 路径
database_service_dir = project_root / "database_service"
if str(database_service_dir) not in sys.path:
    sys.path.insert(0, str(database_service_dir))

print(f"📁 Python 路径设置:")
print(f"  - 项目根目录: {project_root}")
print(f"  - 服务目录: {database_service_dir}")

# ============================================
# 第三步：导入配置
# ============================================

try:
    from config import DatabaseConfig, DatabaseType, RedisConfig
    print("✅ config 导入成功")
except ImportError as e:
    print(f"❌ config 导入失败: {e}")
    
    # 创建替代配置类
    from enum import Enum
    
    class DatabaseType(Enum):
        MEMORY = "memory"
        POSTGRESQL = "postgresql"
    
    class RedisConfig:
        def __init__(self, enabled=False, host="localhost", port=6379, cache_ttl=None):
            self.enabled = enabled
            self.host = host
            self.port = port
            self.cache_ttl = cache_ttl or {'default': 5}
    
    class DatabaseConfig:
        def __init__(self, db_type, **kwargs):
            self.db_type = db_type
            self.postgres_host = kwargs.get('postgres_host', 'localhost')
            self.postgres_port = kwargs.get('postgres_port', 5432)
            self.postgres_database = kwargs.get('postgres_database', 'stock_data')
            self.postgres_username = kwargs.get('postgres_username', 'postgres')
            self.postgres_password = kwargs.get('postgres_password', '')
            self.postgres_pool_size = kwargs.get('postgres_pool_size', 20)
            self.table_names_config = kwargs.get('table_names_config', {})
            self.redis = RedisConfig(**kwargs.get('redis', {}) if 'redis' in kwargs else {})
    
    print("✅ 使用替代配置类")

# ============================================
# pytest 夹具定义
# ============================================

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    try:
        loop = asyncio.get_event_loop_policy().new_event_loop()
        yield loop
        loop.close()
    except RuntimeError:
        # 如果已经有事件循环，使用现有的
        loop = asyncio.get_event_loop()
        yield loop


@pytest.fixture
def memory_db_config():
    """内存数据库配置"""
    config = DatabaseConfig(
        db_type=DatabaseType.MEMORY,
        postgres_pool_size=20
    )
    config.redis.enabled = False
    return config


@pytest.fixture
def postgres_test_config():
    """PostgreSQL测试配置"""
    config = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host="localhost",
        postgres_port=5432,
        postgres_database="stock_data_test",
        postgres_username="postgres",
        postgres_password="zxbzj~925",
        postgres_pool_size=20
    )
    config.redis.enabled = True
    config.redis.host = "localhost"
    config.redis.port = 6379
    config.redis.cache_ttl = {
        'theme': 10,
        'themes_list': 5,
        'related_themes': 5,
        'default': 5
    }
    return config


@pytest.fixture
def mock_redis():
    """模拟Redis客户端"""
    redis = Mock()
    redis.get = AsyncMock()
    redis.set = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.keys = AsyncMock(return_value=[])
    redis.ping = AsyncMock(return_value=True)
    redis.info = AsyncMock(return_value={'used_memory_human': '1MB'})
    redis.close = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    redis.expire = AsyncMock()
    redis.ttl = AsyncMock(return_value=-1)
    
    # 添加异步上下文管理器支持
    redis.__aenter__ = AsyncMock(return_value=redis)
    redis.__aexit__ = AsyncMock()
    
    return redis


@pytest.fixture
def mock_postgres_manager():
    """模拟PostgreSQL管理器"""
    manager = Mock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.get_theme = AsyncMock()
    manager.get_all_active_themes = AsyncMock()
    manager.create_theme = AsyncMock()
    manager.find_related_themes = AsyncMock()
    manager.get_theme_by_name = AsyncMock()
    manager.update_theme = AsyncMock()
    manager.health_check = AsyncMock(return_value=True)
    
    # 事务上下文管理器
    manager.transaction = Mock()
    manager.transaction.return_value.__aenter__ = AsyncMock()
    manager.transaction.return_value.__aexit__ = AsyncMock()
    
    return manager


@pytest.fixture
def sample_theme_data():
    """示例主题数据"""
    return {
        'id': 1,
        'name': '人工智能',
        'keywords': ['AI', '人工智能', '机器学习', '深度学习'],
        'keywords_weight': [0.9, 0.95, 0.8, 0.7],
        'description': '人工智能相关技术与应用',
        'abstract': 'AI技术在各行业的应用与发展',
        'background': '人工智能自20世纪50年代诞生以来...',
        'impact_analysis': '推动产业升级，创造新就业机会',
        'influence_scope': ['科技', '制造', '金融', '医疗'],
        'influence_level': 0.85,
        'development_stage': 'growth',
        'potential_score': 92,
        'risk_assessment': '技术发展可能带来就业结构调整',
        'risk_level': 'medium',
        'attention_score': 88,
        'sentiment_score': 0.75,
        'sentiment_trend': 'rising',
        'source_reliability': 0.9,
        'heat_score': 90,
        'heat_trend': 'rising',
        'emergence_time': '2024-01-01T00:00:00',
        'estimated_duration': 365,
        'region_tags': ['全球', '中国', '美国'],
        'industry_tags': ['科技', '互联网', '智能制造'],
        'event_tags': ['AI大会', '政策发布', '技术突破'],
        'theme_category': '科技前沿',
        'discovery_source': 'enhanced_engine',
        'discovery_confidence': 0.85,
        'lifecycle_stage': 'active',
        'is_active': True,
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00'
    }


# ============================================
# pytest 配置
# ============================================

def pytest_configure(config):
    """pytest配置钩子"""
    os.environ['TESTING'] = 'true'
    
    if not config.getoption("--run-integration"):
        config.option.markexpr = "not integration"
    
    print(f"\n🔧 测试环境配置:")
    print(f"  工作目录: {os.getcwd()}")
    print(f"  测试标记: {config.option.markexpr}")


def pytest_sessionstart(session):
    """测试会话开始时调用"""
    print(f"\n🚀 开始测试会话")
    print(f"  项目根目录: {project_root}")


def pytest_addoption(parser):
    """添加命令行选项"""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="运行集成测试（需要外部服务）"
    )