# tests/integration/test_real_redis_integration.py
"""
真实Redis集成测试 - 需要Redis服务运行
"""
import pytest
import asyncio
import json
import time
from pathlib import Path
import sys

# 设置正确的Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)  # ai_theme_app
sys.path.insert(0, service_dir)   # database_service

from database_service.config import DatabaseConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.managers.redis_cached_manager import RedisCachedDatabaseManager
from database_service.interface import ThemeRecord


@pytest.mark.integration
@pytest.mark.redis
@pytest.mark.asyncio
class TestRealRedisIntegration:
    """真实Redis集成测试"""
    
    @classmethod
    async def setup_class(cls):
        """测试类设置"""
        print("\n🔴 准备真实Redis集成测试...")
        
        # 检查Redis是否运行
        try:
            import aioredis
            redis = await aioredis.from_url("redis://localhost:6379")
            await redis.ping()
            await redis.close()
            print("  ✅ Redis服务运行正常")
        except Exception as e:
            pytest.skip(f"Redis服务不可用: {e}")
        
        # 使用测试配置
        cls.config = DatabaseConfig(
            db_type="postgresql",
            postgres_host="localhost",
            postgres_port=5432,
            postgres_database="stock_data_test",  # 使用测试数据库
            postgres_username="postgres",
            postgres_password="zxbzj~925",
            redis_enabled=True,
            redis_host="localhost",
            redis_port=6379,
            redis_cache_ttl={
                'theme': 30,      # 30秒，便于测试
                'themes_list': 15,
                'default': 10
            }
        )
        
        cls.postgres_manager = None
        cls.redis_manager = None
    
    async def setup_method(self):
        """每个测试方法前执行"""
        if not self.postgres_manager:
            try:
                # 创建PostgreSQL管理器
                self.postgres_manager = PostgresDatabaseManager(self.config)
                await self.postgres_manager.connect()
                print("  ✅ PostgreSQL连接成功")
                
                # 创建Redis缓存管理器
                self.redis_manager = RedisCachedDatabaseManager(
                    self.postgres_manager, 
                    self.config
                )
                await self.redis_manager.connect()
                print("  ✅ Redis缓存管理器连接成功")
                
                # 清理测试缓存
                await self.redis_manager.clear_cache("*")
                print("  🗑️  测试缓存已清理")
                
            except Exception as e:
                pytest.skip(f"数据库连接失败: {e}")
    
    async def teardown_method(self):
        """每个测试方法后执行"""
        if self.redis_manager:
            # 清理测试缓存
            await self.redis_manager.clear_cache("*")
            
            await self.redis_manager.disconnect()
            self.redis_manager = None
        
        if self.postgres_manager:
            await self.postgres_manager.disconnect()
            self.postgres_manager = None
    
    async def test_01_real_cache_workflow(self):
        """测试真实缓存工作流"""
        print("\n🔄 测试真实缓存工作流:")
        
        # 1. 缓存未命中测试
        print("  1. 测试缓存未命中...")
        
        # 先清理缓存
        await self.redis_manager.clear_cache("theme:*")
        
        # 获取一个主题（应该缓存未命中）
        theme = await self.redis_manager.get_theme(1)
        
        if theme:
            print(f"    获取到主题: {theme.name}")
            
            # 2. 缓存命中测试
            print("  2. 测试缓存命中...")
            
            # 立即再次获取（应该命中缓存）
            start = time.perf_counter()
            cached_theme = await self.redis_manager.get_theme(1)
            cache_time = (time.perf_counter() - start) * 1000
            
            assert cached_theme is not None
            assert cached_theme.id == theme.id
            print(f"    缓存命中时间: {cache_time:.2f}ms")
            
            # 3. 测试缓存TTL
            print("  3. 测试缓存TTL...")
            
            # 等待TTL过期
            await asyncio.sleep(35)  # TTL是30秒
            
            # 再次获取（应该缓存未命中，重新加载）
            start = time.perf_counter()
            reloaded_theme = await self.redis_manager.get_theme(1)
            reload_time = (time.perf_counter() - start) * 1000
            
            assert reloaded_theme is not None
            print(f"    TTL过期后重新加载时间: {reload_time:.2f}ms")
            
            print("  ✅ 缓存工作流测试完成")
        else:
            print("  ⚠️  未找到主题ID=1，跳过详细测试")
    
    async def test_02_real_cache_invalidation(self):
        """测试真实缓存失效"""
        print("\n🗑️  测试真实缓存失效:")
        
        # 1. 创建测试数据
        print("  1. 创建测试缓存...")
        
        test_keys = []
        for i in range(10):
            key = f"test:cache:{i}"
            value = {"id": i, "data": f"测试数据{i}"}
            await self.redis_manager.redis.setex(key, 60, json.dumps(value))
            test_keys.append(key)
        
        print(f"    创建了 {len(test_keys)} 个测试缓存")
        
        # 2. 验证缓存存在
        print("  2. 验证缓存存在...")
        
        for key in test_keys[:3]:
            cached = await self.redis_manager.redis.get(key)
            assert cached is not None
            print(f"    确认缓存存在: {key}")
        
        # 3. 执行缓存失效
        print("  3. 执行缓存失效...")
        
        cleared = await self.redis_manager.clear_cache("test:cache:*")
        print(f"    清除了 {cleared} 个缓存键")
        assert cleared == 10
        
        # 4. 验证缓存已失效
        print("  4. 验证缓存已失效...")
        
        for key in test_keys[:3]:
            cached = await self.redis_manager.redis.get(key)
            assert cached is None
            print(f"    确认缓存已失效: {key}")
        
        print("  ✅ 缓存失效测试完成")
    
    async def test_03_real_cache_stats(self):
        """测试真实缓存统计"""
        print("\n📊 测试真实缓存统计:")
        
        # 执行一些操作来生成统计
        for i in range(20):
            await self.redis_manager.get_theme(i + 1000)  # 使用不存在的ID
        
        # 获取缓存统计
        stats = await self.redis_manager.get_cache_stats()
        
        print("  缓存统计信息:")
        print(f"    命中次数: {stats.get('hits', 0)}")
        print(f"    未命中次数: {stats.get('misses', 0)}")
        print(f"    写入次数: {stats.get('writes', 0)}")
        print(f"    命中率: {stats.get('cache_hit_rate', 0):.1%}")
        
        if 'redis_memory_used' in stats:
            print(f"    Redis内存使用: {stats['redis_memory_used']}")
        
        # 验证统计信息完整
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'cache_hit_rate' in stats
        
        print("  ✅ 缓存统计测试完成")
    
    async def test_04_real_cache_concurrency(self):
        """测试真实缓存并发"""
        print("\n🔀 测试真实缓存并发:")
        
        # 准备测试数据
        test_count = 50
        
        async def cache_operation(i):
            """并发的缓存操作"""
            key = f"concurrent:test:{i}"
            value = {"id": i, "timestamp": time.time()}
            
            # 写入缓存
            await self.redis_manager.redis.setex(key, 10, json.dumps(value))
            
            # 读取缓存
            cached = await self.redis_manager.redis.get(key)
            if cached:
                return json.loads(cached)
            return None
        
        # 并发执行
        print(f"  启动 {test_count} 个并发操作...")
        
        start_time = time.perf_counter()
        tasks = [cache_operation(i) for i in range(test_count)]
        results = await asyncio.gather(*tasks)
        
        total_time = (time.perf_counter() - start_time) * 1000
        avg_time = total_time / test_count
        throughput = test_count / (total_time / 1000)
        
        print(f"  总时间: {total_time:.1f}ms")
        print(f"  平均每个操作: {avg_time:.2f}ms")
        print(f"  吞吐量: {throughput:.0f} 操作/秒")
        
        # 验证所有操作成功
        successful = [r for r in results if r is not None]
        print(f"  成功操作: {len(successful)}/{test_count}")
        
        assert len(successful) == test_count
        print("  ✅ 缓存并发测试完成")
    
    async def test_05_real_cache_persistence(self):
        """测试缓存持久性和一致性"""
        print("\n💾 测试缓存持久性和一致性:")
        
        # 测试数据
        test_data = {
            "id": 999,
            "name": "持久性测试主题",
            "keywords": ["测试", "持久性"],
            "heat_score": 100
        }
        
        # 1. 写入缓存
        print("  1. 写入缓存...")
        
        cache_key = self.redis_manager._build_cache_key("theme", 999)
        await self.redis_manager._set_to_cache(
            cache_key, test_data, ttl=30
        )
        
        # 2. 立即读取
        print("  2. 立即读取验证...")
        
        cached = await self.redis_manager._get_from_cache(cache_key)
        assert cached is not None
        assert cached["id"] == 999
        print(f"    读取成功: {cached['name']}")
        
        # 3. 使用管理器方法读取
        print("  3. 使用管理器方法读取...")
        
        # 模拟PostgreSQL返回
        theme_record = ThemeRecord(**test_data)
        self.postgres_manager.get_theme = AsyncMock(return_value=theme_record)
        
        # 设置缓存未命中（测试一致性）
        original_get = self.redis_manager.redis.get
        self.redis_manager.redis.get = AsyncMock(return_value=None)
        
        try:
            theme = await self.redis_manager.get_theme(999)
            assert theme is not None
            assert theme.id == 999
            print(f"    管理器读取成功: {theme.name}")
        finally:
            # 恢复原始方法
            self.redis_manager.redis.get = original_get
        
        # 4. 验证缓存写入
        print("  4. 验证缓存写入...")
        
        # 等待异步缓存写入完成
        await asyncio.sleep(0.1)
        
        # 直接读取Redis验证
        redis_data = await self.redis_manager.redis.get(cache_key)
        assert redis_data is not None
        
        loaded = json.loads(redis_data)
        assert loaded["id"] == 999
        print(f"    Redis中验证成功: {loaded['name']}")
        
        print("  ✅ 缓存持久性和一致性测试完成")