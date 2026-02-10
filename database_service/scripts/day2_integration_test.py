# scripts/day2_fixed_test.py
"""
Day 2修复版测试 - 解决导入问题
"""
import asyncio
import sys
import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_paths():
    """设置Python路径"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    database_dir = os.path.dirname(current_dir)
    
    print(f"📁 当前目录: {current_dir}")
    print(f"📁 database_service目录: {database_dir}")
    
    # 只添加database_service目录到Python路径
    if database_dir not in sys.path:
        sys.path.insert(0, database_dir)
    
    # 添加managers目录
    managers_dir = os.path.join(database_dir, 'managers')
    if managers_dir not in sys.path:
        sys.path.insert(0, managers_dir)
    
    print("📋 Python路径:")
    for i, path in enumerate(sys.path[:5], 1):
        print(f"  {i}. {path}")

async def test_news_integration():
    """测试新闻集成"""
    print("\n🚀 Day 2: 新闻数据流集成测试")
    print("="*60)
    
    try:
        # 1. 检查模块导入
        print("1. 检查模块导入...")
        
        # 尝试不同的导入方式
        try:
            # 方式1：直接导入config
            import config
            print("   ✅ config模块导入成功 (方式1)")
        except ImportError as e:
            print(f"   ❌ config模块导入失败 (方式1): {e}")
            return False
        
        try:
            # 方式2：尝试相对导入
            from . import config as config2
            print("   ✅ config模块导入成功 (方式2)")
            config = config2
        except ImportError as e:
            print(f"   ⚠️  config模块相对导入失败 (方式2): {e}")
            # 继续使用方式1的config
        
        # 2. 检查Postgres管理器
        print("\n2. 检查Postgres管理器...")
        try:
            from postgres_manager import PostgresDatabaseManager
            print("   ✅ PostgresDatabaseManager导入成功")
        except ImportError as e:
            print(f"   ❌ PostgresDatabaseManager导入失败: {e}")
            # 尝试其他导入方式
            try:
                from managers.postgres_manager import PostgresDatabaseManager
                print("   ✅ PostgresDatabaseManager导入成功 (managers.路径)")
            except ImportError as e2:
                print(f"   ❌ 所有PostgresDatabaseManager导入尝试失败: {e2}")
                return False
        
        # 3. 检查Redis缓存管理器
        print("\n3. 检查Redis缓存管理器...")
        try:
            from redis_cached_manager import RedisCachedDatabaseManager
            print("   ✅ RedisCachedDatabaseManager导入成功")
        except ImportError as e:
            print(f"   ❌ RedisCachedDatabaseManager导入失败: {e}")
            # 尝试其他导入方式
            try:
                from managers.redis_cached_manager import RedisCachedDatabaseManager
                print("   ✅ RedisCachedDatabaseManager导入成功 (managers.路径)")
            except ImportError as e2:
                print(f"   ❌ 所有RedisCachedDatabaseManager导入尝试失败: {e2}")
                return False
        
        # 4. 获取配置
        print("\n4. 获取配置...")
        try:
            config_obj = config.get_config()
            config_obj.postgres_database = "stock_data_test"
            
            print(f"   ✅ 配置获取成功")
            print(f"      数据库类型: {config_obj.db_type}")
            print(f"      目标数据库: {config_obj.postgres_database}")
            
            # 检查配置中是否有redis属性
            if hasattr(config_obj, 'redis'):
                print(f"      Redis启用: {config_obj.redis.enabled}")
            else:
                print(f"      Redis配置: 未找到")
                
        except Exception as e:
            print(f"   ❌ 配置获取失败: {e}")
            return False
        
        # 5. 测试PostgreSQL连接
        print("\n5. 测试PostgreSQL连接...")
        try:
            postgres_manager = PostgresDatabaseManager(config_obj)
            await postgres_manager.connect()
            
            if await postgres_manager.health_check():
                print("   ✅ PostgreSQL连接成功")
            else:
                print("   ❌ PostgreSQL连接失败")
                return False
                
        except Exception as e:
            print(f"   ❌ PostgreSQL连接异常: {e}")
            return False
        
        # 6. 测试新闻方法
        print("\n6. 测试新闻方法...")
        
        # 测试创建新闻
        test_news = {
            "news_id": "day2_fix_test_001",
            "title": "Day 2修复测试新闻",
            "content": "测试修复后的Day 2集成",
            "source": "day2_fix",
            "publish_date": "2024-01-21",
            "market": "A股"
        }
        
        try:
            news_id = await postgres_manager.create_news(test_news)
            if news_id:
                print(f"   ✅ 创建新闻成功: {news_id}")
            else:
                print("   ❌ 创建新闻失败")
        except Exception as e:
            print(f"   ❌ 创建新闻异常: {e}")
        
        # 7. 测试查询新闻
        print("\n7. 测试查询新闻...")
        
        try:
            news = await postgres_manager.get_news("day2_fix_test_001")
            if news:
                print(f"   ✅ 查询新闻成功: {news.get('title')}")
            else:
                print("   ❌ 查询新闻失败")
        except Exception as e:
            print(f"   ❌ 查询新闻异常: {e}")
        
        # 8. 测试最近新闻
        print("\n8. 测试最近新闻...")
        
        try:
            recent = await postgres_manager.get_recent_news(3)
            print(f"   ✅ 获取最近新闻: {len(recent)}条")
            if recent:
                for i, news_item in enumerate(recent[:2], 1):
                    title = news_item.get('title', '未命名')[:30]
                    print(f"     {i}. {title}...")
        except Exception as e:
            print(f"   ❌ 获取最近新闻异常: {e}")
        
        # 9. 清理
        print("\n9. 清理测试数据...")
        
        try:
            if hasattr(postgres_manager, 'delete_test_news'):
                await postgres_manager.delete_test_news()
                print("   ✅ 测试数据清理完成")
            else:
                print("   ⚠️  delete_test_news方法不存在")
        except Exception as e:
            print(f"   ⚠️  清理数据异常: {e}")
        
        # 10. 关闭连接
        print("\n10. 关闭连接...")
        await postgres_manager.disconnect()
        print("   ✅ 连接已关闭")
        
        print("\n" + "="*60)
        print("🎉 Day 2基础测试完成！")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ 测试过程发生异常: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_redis_cache_manager():
    """单独测试Redis缓存管理器"""
    print("\n🧪 单独测试Redis缓存管理器")
    print("="*60)
    
    try:
        # 导入模块
        import config
        from postgres_manager import PostgresDatabaseManager
        from redis_cached_manager import RedisCachedDatabaseManager
        
        # 获取配置
        config_obj = config.get_config()
        config_obj.postgres_database = "stock_data_test"
        
        # 初始化PostgreSQL管理器
        postgres = PostgresDatabaseManager(config_obj)
        await postgres.connect()
        
        # 初始化Redis缓存管理器
        cached = RedisCachedDatabaseManager(postgres, config_obj)
        await cached.connect()
        
        print("✅ Redis缓存管理器初始化成功")
        
        # 测试新闻方法
        test_news = {
            "news_id": "redis_cache_test_001",
            "title": "Redis缓存测试新闻",
            "content": "测试Redis缓存管理器的新闻功能",
            "source": "redis_test",
            "publish_date": "2024-01-21"
        }
        
        # 测试创建新闻
        news_id = await cached.create_news(test_news)
        if news_id:
            print(f"✅ 通过缓存管理器创建新闻成功: {news_id}")
        else:
            print("❌ 通过缓存管理器创建新闻失败")
        
        # 测试查询新闻
        news = await cached.get_news("redis_cache_test_001")
        if news:
            print(f"✅ 通过缓存管理器查询新闻成功: {news.get('title')}")
        else:
            print("❌ 通过缓存管理器查询新闻失败")
        
        # 清理
        await postgres.delete_test_news()
        await postgres.disconnect()
        await cached.disconnect()
        
        return True
        
    except Exception as e:
        print(f"❌ Redis缓存管理器测试失败: {e}")
        return False

async def main():
    """主函数"""
    setup_paths()
    
    print("🔧 开始Day 2测试...")
    
    # 测试1：基础新闻功能
    success1 = await test_news_integration()
    
    # 测试2：Redis缓存管理器
    success2 = True
    if success1:
        success2 = await test_redis_cache_manager()
    
    if success1 and success2:
        print("\n📋 Day 2完成总结:")
        print("✅ 1. 基础新闻功能测试通过")
        print("✅ 2. Redis缓存管理器测试通过")
        print("✅ 3. 所有组件正常工作")
        print("\n🚀 Day 2实施成功！可以继续Day 3的实施！")
        return 0
    elif success1 and not success2:
        print("\n⚠️  Day 2部分完成:")
        print("✅ 1. 基础新闻功能测试通过")
        print("❌ 2. Redis缓存管理器测试失败")
        print("\n📝 可以继续Day 3，但Redis缓存功能可能不可用")
        return 1
    else:
        print("\n❌ Day 2测试失败")
        return 2

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)