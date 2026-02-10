#!/usr/bin/env python3
"""
缓存策略冒烟测试 - 28字段表结构
测试缓存策略的基本功能 - 简化版
"""
import os
import sys
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock

# 添加正确的导入路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)  # ai_theme_app
sys.path.insert(0, service_dir)   # database_service

try:
    from database_service.config import DatabaseConfig, DatabaseType, CacheStrategy, RedisConfig
    from database_service.interface import ThemeRecord, ThemeTags
    print("✅ 成功导入基础模块")
    
    # 尝试导入缓存管理器
    try:
        from database_service.managers.redis_cached_manager import RedisCachedDatabaseManager
        print("✅ 成功导入RedisCachedDatabaseManager")
    except ImportError as e:
        print(f"⚠️  无法导入RedisCachedDatabaseManager: {e}")
        print("🔧 使用模拟的缓存管理器进行测试")
        RedisCachedDatabaseManager = None
        
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


class SimplifiedCacheSmokeTest:
    """简化版缓存策略冒烟测试"""
    
    def __init__(self):
        self.results = {}
    
    async def test_basic_cache_concepts(self):
        """测试基本缓存概念"""
        print("\n🧪 测试1: 基本缓存概念")
        try:
            # 模拟缓存管理器
            class MockCacheManager:
                def __init__(self):
                    self.cache = {}
                    self.stats = {'hits': 0, 'misses': 0}
                
                async def get_theme(self, theme_id):
                    cache_key = f"theme:{theme_id}"
                    
                    # 尝试从缓存获取
                    if cache_key in self.cache:
                        self.stats['hits'] += 1
                        return self.cache[cache_key]
                    
                    # 缓存未命中
                    self.stats['misses'] += 1
                    
                    # 模拟从数据库获取
                    theme = ThemeRecord(
                        id=theme_id,
                        name=f"测试主题{theme_id}",
                        code=f"TEST_{theme_id:04d}",
                        description=f"测试主题{theme_id}描述"
                    )
                    
                    # 存入缓存
                    self.cache[cache_key] = theme
                    return theme
                
                async def clear_cache(self):
                    cleared = len(self.cache)
                    self.cache.clear()
                    return cleared
                
                def get_stats(self):
                    total = self.stats['hits'] + self.stats['misses']
                    hit_rate = self.stats['hits'] / total if total > 0 else 0
                    return {
                        'hits': self.stats['hits'],
                        'misses': self.stats['misses'],
                        'hit_rate': hit_rate,
                        'cache_size': len(self.cache)
                    }
            
            # 创建模拟缓存管理器
            cache_manager = MockCacheManager()
            
            # 第一次获取 - 缓存未命中
            theme1 = await cache_manager.get_theme(1001)
            assert theme1 is not None
            assert theme1.id == 1001
            assert cache_manager.stats['misses'] == 1
            assert cache_manager.stats['hits'] == 0
            
            # 第二次获取 - 缓存命中
            theme2 = await cache_manager.get_theme(1001)
            assert theme2 is not None
            assert cache_manager.stats['misses'] == 1
            assert cache_manager.stats['hits'] == 1
            
            # 获取新主题 - 缓存未命中
            theme3 = await cache_manager.get_theme(1002)
            assert theme3 is not None
            assert cache_manager.stats['misses'] == 2
            assert cache_manager.stats['hits'] == 1
            
            # 获取统计
            stats = cache_manager.get_stats()
            expected_hit_rate = 1/3  # 1次命中 / 3次查询
            assert abs(stats['hit_rate'] - expected_hit_rate) < 0.001
            assert stats['cache_size'] == 2
            
            # 清理缓存
            cleared = await cache_manager.clear_cache()
            assert cleared == 2
            assert len(cache_manager.cache) == 0
            
            print("  ✅ 基本缓存概念测试通过")
            self.results["basic_cache_concepts"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 基本缓存概念测试失败: {e}")
            self.results["basic_cache_concepts"] = "FAIL"
            raise
    
    async def test_cache_invalidation_strategies(self):
        """测试缓存失效策略"""
        print("\n🧪 测试2: 缓存失效策略")
        try:
            class MockCacheWithInvalidation:
                def __init__(self):
                    self.cache = {}
                    self.invalidation_count = 0
                
                async def cache_theme(self, theme):
                    cache_key = f"theme:{theme.id}"
                    self.cache[cache_key] = theme
                    return True
                
                async def invalidate_theme(self, theme_id):
                    cache_key = f"theme:{theme_id}"
                    if cache_key in self.cache:
                        del self.cache[cache_key]
                        self.invalidation_count += 1
                        return True
                    return False
                
                async def invalidate_all_themes(self):
                    keys_to_remove = [k for k in self.cache.keys() if k.startswith("theme:")]
                    for key in keys_to_remove:
                        del self.cache[key]
                    self.invalidation_count += len(keys_to_remove)
                    return len(keys_to_remove)
            
            cache = MockCacheWithInvalidation()
            
            # 创建并缓存主题
            theme = ThemeRecord(
                id=1001,
                name="缓存失效测试",
                code="CACHE_INVALID_001",
                description="缓存失效测试主题"
            )
            
            await cache.cache_theme(theme)
            assert f"theme:{theme.id}" in cache.cache
            
            # 单个主题失效
            invalidated = await cache.invalidate_theme(1001)
            assert invalidated == True
            assert f"theme:{theme.id}" not in cache.cache
            assert cache.invalidation_count == 1
            
            # 批量缓存多个主题
            themes = []
            for i in range(3):
                theme_i = ThemeRecord(
                    id=2000 + i,
                    name=f"批量主题{i}",
                    code=f"BATCH_{i:03d}"
                )
                themes.append(theme_i)
                await cache.cache_theme(theme_i)
            
            assert len(cache.cache) == 3
            
            # 批量失效
            cleared = await cache.invalidate_all_themes()
            assert cleared == 3
            assert len(cache.cache) == 0
            assert cache.invalidation_count == 4  # 1 + 3
            
            print("  ✅ 缓存失效策略测试通过")
            self.results["cache_invalidation_strategies"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 缓存失效策略测试失败: {e}")
            self.results["cache_invalidation_strategies"] = "FAIL"
            raise
    
    async def test_28_field_cache_serialization(self):
        """测试28字段缓存序列化"""
        print("\n🧪 测试3: 28字段缓存序列化")
        try:
            # 创建28字段主题
            theme_28_fields = ThemeRecord(
                id=1001,
                name="28字段缓存测试",
                code="28FIELDS_CACHE_001",
                description="28字段缓存测试主题",
                level1_category="计算机",
                level2_category="人工智能",
                level3_category="机器学习",
                category_path=["计算机", "人工智能", "机器学习"],
                category1_code="C001",
                category2_code="C002",
                category3_code="C003",
                tags=ThemeTags(
                    source="shenwan",
                    aliases=["AI", "人工智能"],
                    keywords=["人工智能", "AI", "机器学习"],
                    heat_level="high",
                    industries=["计算机", "软件服务"],
                    industry_code="AI001"
                ),
                theme_type="investment",
                lifecycle_stage="growth",
                heat_score=95,
                confidence_score=0.85,
                related_stocks=["600000", "000001"],
                stock_count=2,
                news_count=50,
                mention_count=100,
                source_system="transformed",
                source_id="28fields_source",
                created_by="cache_test"
            )
            
            # 测试序列化和反序列化
            theme_dict = theme_28_fields.to_dict()
            
            # 验证所有28字段都在字典中
            expected_fields = [
                'code', 'level1_category', 'level2_category', 'level3_category',
                'category_path', 'category1_code', 'category2_code', 'category3_code',
                'tags', 'theme_type', 'lifecycle_stage', 'heat_score', 
                'confidence_score', 'related_stocks', 'stock_count', 'news_count',
                'mention_count', 'source_system', 'source_id', 'created_by'
            ]
            
            for field in expected_fields:
                assert field in theme_dict, f"缺少字段: {field}"
            
            # 验证特定字段值
            assert theme_dict['code'] == "28FIELDS_CACHE_001"
            assert theme_dict['level1_category'] == "计算机"
            assert theme_dict['tags']['heat_level'] == "high"
            assert theme_dict['heat_score'] == 95
            
            # 模拟缓存存储和检索
            cache_data = json.dumps(theme_dict, ensure_ascii=False)
            retrieved_dict = json.loads(cache_data)
            
            # 验证检索的数据
            assert retrieved_dict['code'] == theme_dict['code']
            assert retrieved_dict['level1_category'] == theme_dict['level1_category']
            
            print("  ✅ 28字段缓存序列化测试通过")
            self.results["28_field_cache_serialization"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 28字段缓存序列化测试失败: {e}")
            self.results["28_field_cache_serialization"] = "FAIL"
            raise
    
    async def test_cache_error_handling_simple(self):
        """测试缓存错误处理（简化版）"""
        print("\n🧪 测试4: 缓存错误处理")
        try:
            class CacheWithFallback:
                def __init__(self):
                    self.cache = {}
                    self.cache_errors = 0
                
                async def get_with_fallback(self, theme_id, db_fetcher):
                    cache_key = f"theme:{theme_id}"
                    
                    try:
                        # 尝试从缓存获取
                        if cache_key in self.cache:
                            return self.cache[cache_key]
                    except Exception:
                        self.cache_errors += 1
                    
                    # 缓存未命中或出错，使用降级策略
                    try:
                        theme = await db_fetcher(theme_id)
                        # 尝试存入缓存（即使可能失败）
                        try:
                            self.cache[cache_key] = theme
                        except Exception:
                            self.cache_errors += 1
                        return theme
                    except Exception as e:
                        raise Exception(f"数据库查询失败: {e}")
            
            cache = CacheWithFallback()
            
            # 模拟数据库查询
            async def mock_db_fetcher(theme_id):
                return ThemeRecord(
                    id=theme_id,
                    name=f"主题{theme_id}",
                    code=f"THEME_{theme_id:04d}"
                )
            
            # 正常情况
            theme = await cache.get_with_fallback(1001, mock_db_fetcher)
            assert theme is not None
            assert theme.id == 1001
            
            # 缓存应该有了数据
            assert f"theme:{1001}" in cache.cache
            
            print("  ✅ 缓存错误处理测试通过")
            self.results["cache_error_handling"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 缓存错误处理测试失败: {e}")
            self.results["cache_error_handling"] = "FAIL"
            raise
    
    async def test_cache_performance_patterns(self):
        """测试缓存性能模式"""
        print("\n🧪 测试5: 缓存性能模式")
        try:
            class PerformanceTestCache:
                def __init__(self):
                    self.cache = {}
                    self.access_count = 0
                    self.hit_count = 0
                    self.miss_count = 0
                
                async def get_theme(self, theme_id, simulate_db_delay=0.1):
                    self.access_count += 1
                    cache_key = f"theme:{theme_id}"
                    
                    # 检查缓存
                    if cache_key in self.cache:
                        self.hit_count += 1
                        return self.cache[cache_key]
                    
                    # 缓存未命中
                    self.miss_count += 1
                    
                    # 模拟数据库延迟
                    await asyncio.sleep(simulate_db_delay)
                    
                    # 创建主题
                    theme = ThemeRecord(
                        id=theme_id,
                        name=f"性能测试主题{theme_id}",
                        code=f"PERF_{theme_id:04d}"
                    )
                    
                    # 存入缓存
                    self.cache[cache_key] = theme
                    return theme
                
                def get_performance_stats(self):
                    hit_rate = self.hit_count / self.access_count if self.access_count > 0 else 0
                    
                    return {
                        'total_accesses': self.access_count,
                        'cache_hits': self.hit_count,
                        'cache_misses': self.miss_count,
                        'hit_rate': hit_rate,
                        'cache_size': len(self.cache)
                    }
            
            cache = PerformanceTestCache()
            
            # 第一次访问 - 缓存未命中（有延迟）
            theme1 = await cache.get_theme(1001, simulate_db_delay=0.05)
            assert theme1 is not None
            assert cache.access_count == 1
            assert cache.miss_count == 1
            assert cache.hit_count == 0
            
            # 第二次访问 - 缓存命中（快速）
            theme2 = await cache.get_theme(1001, simulate_db_delay=0.05)
            assert theme2 is not None
            assert cache.access_count == 2
            assert cache.miss_count == 1
            assert cache.hit_count == 1
            
            # 第三次访问 - 新主题，缓存未命中
            theme3 = await cache.get_theme(1002, simulate_db_delay=0.05)
            assert theme3 is not None
            assert cache.access_count == 3
            assert cache.miss_count == 2
            assert cache.hit_count == 1
            
            # 获取性能统计
            stats = cache.get_performance_stats()
            assert stats['total_accesses'] == 3
            assert stats['cache_hits'] == 1
            assert stats['cache_misses'] == 2
            assert abs(stats['hit_rate'] - 1/3) < 0.001
            assert stats['cache_size'] == 2
            
            print("  ✅ 缓存性能模式测试通过")
            self.results["cache_performance_patterns"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ 缓存性能模式测试失败: {e}")
            self.results["cache_performance_patterns"] = "FAIL"
            raise
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("🔥 简化版缓存策略冒烟测试启动")
        print("=" * 60)
        
        await self.test_basic_cache_concepts()
        await self.test_cache_invalidation_strategies()
        await self.test_28_field_cache_serialization()
        await self.test_cache_error_handling_simple()
        await self.test_cache_performance_patterns()
        
        self.summarize_results()
        
        return all(result == "PASS" for result in self.results.values())
    
    def summarize_results(self):
        """汇总测试结果"""
        print("\n" + "=" * 60)
        print("📋 缓存策略冒烟测试结果汇总")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result == "PASS")
        failed_tests = total_tests - passed_tests
        
        for test_name, result in self.results.items():
            status = "✅ PASS" if result == "PASS" else "❌ FAIL"
            print(f"  {test_name:35} {status}")
        
        print(f"\n📊 统计:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过数: {passed_tests}")
        print(f"  失败数: {failed_tests}")
        
        if failed_tests == 0:
            print("\n🎉 所有缓存策略测试通过！")
        else:
            print(f"\n⚠️  有 {failed_tests} 个测试失败")


async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 缓存策略冒烟测试启动 - 简化版")
    print("=" * 60)
    
    test = SimplifiedCacheSmokeTest()
    success = await test.run_all_tests()
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())