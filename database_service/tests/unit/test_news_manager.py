# tests/unit/test_news_manager.py
"""
新闻管理器单元测试
"""
import pytest
import json
from datetime import datetime, date
from unittest.mock import AsyncMock, patch

class TestNewsManager:
    """新闻管理器测试"""
    
    @pytest.mark.asyncio
    async def test_create_news_success(self):
        """测试成功创建新闻"""
        # 模拟PostgreSQL管理器
        mock_postgres = AsyncMock()
        mock_postgres.create_news.return_value = "test_news_001"
        
        # 模拟Redis
        mock_redis = AsyncMock()
        
        # 测试配置
        from config import DatabaseType, RedisConfig
        redis_config = RedisConfig()
        redis_config.enabled = True
        redis_config.cache_ttl = {'news': 300}
        
        class TestConfig:
            db_type = DatabaseType.POSTGRESQL
            redis = redis_config
        
        config = TestConfig()
        
        # 创建管理器
        from managers.redis_cached_manager import RedisCachedDatabaseManager
        manager = RedisCachedDatabaseManager(mock_postgres, config)
        manager.redis = mock_redis
        manager.test_mode = False
        
        # 测试数据
        news_data = {
            "news_id": "test_news_001",
            "title": "测试新闻标题",
            "content": "测试新闻内容",
            "source": "test_source",
            "publish_date": date.today().isoformat(),
            "publish_time": "10:30:00",
            "market": "A股",
            "keywords": ["测试", "单元测试"]
        }
        
        # 调用方法
        result = await manager.create_news(news_data)
        
        # 验证
        assert result == "test_news_001"
        mock_postgres.create_news.assert_called_once()
        mock_redis.setex.assert_called_once()
        assert manager.cache_stats['writes'] == 1
    
    @pytest.mark.asyncio
    async def test_get_news_cache_hit(self):
        """测试获取新闻 - 缓存命中"""
        mock_postgres = AsyncMock()
        mock_redis = AsyncMock()
        
        # 配置缓存数据
        cache_data = {
            "data": {
                "news_id": "cached_news_001",
                "title": "缓存的新闻"
            },
            "cached_at": datetime.now().isoformat()
        }
        mock_redis.get.return_value = json.dumps(cache_data)
        
        # 创建管理器
        from managers.redis_cached_manager import RedisCachedDatabaseManager
        from config import DatabaseType, RedisConfig
        
        redis_config = RedisConfig()
        redis_config.enabled = True
        
        class TestConfig:
            db_type = DatabaseType.POSTGRESQL
            redis = redis_config
        
        manager = RedisCachedDatabaseManager(mock_postgres, TestConfig())
        manager.redis = mock_redis
        manager.test_mode = False
        
        # 调用方法
        result = await manager.get_news("cached_news_001")
        
        # 验证
        assert result["news_id"] == "cached_news_001"
        assert result["title"] == "缓存的新闻"
        mock_redis.get.assert_called_once()
        mock_postgres.get_news.assert_not_called()  # 不应该调用数据库
        assert manager.cache_stats['hits'] == 1
    
    @pytest.mark.asyncio
    async def test_get_news_cache_miss(self):
        """测试获取新闻 - 缓存未命中"""
        mock_postgres = AsyncMock()
        mock_redis = AsyncMock()
        
        # 配置缓存未命中
        mock_redis.get.return_value = None
        # 配置数据库返回
        db_news = {
            "news_id": "db_news_001",
            "title": "数据库中的新闻"
        }
        mock_postgres.get_news.return_value = db_news
        
        # 创建管理器
        from managers.redis_cached_manager import RedisCachedDatabaseManager
        from config import DatabaseType, RedisConfig
        
        redis_config = RedisConfig()
        redis_config.enabled = True
        
        class TestConfig:
            db_type = DatabaseType.POSTGRESQL
            redis = redis_config
        
        manager = RedisCachedDatabaseManager(mock_postgres, TestConfig())
        manager.redis = mock_redis
        manager.test_mode = False
        
        # 调用方法
        result = await manager.get_news("db_news_001")
        
        # 验证
        assert result["news_id"] == "db_news_001"
        mock_redis.get.assert_called_once()
        mock_postgres.get_news.assert_called_once_with("db_news_001")
        assert manager.cache_stats['misses'] == 1