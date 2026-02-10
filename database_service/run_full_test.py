# run_full_test.py
"""
运行完整的数据库服务测试
"""
import sys
import os
import asyncio

print("=" * 60)
print("🚀 开始完整数据库服务测试")
print("=" * 60)

# 设置Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"📁 工作目录: {current_dir}")

# 导入测试
print("\n📦 导入测试...")
try:
    import config
    import factory
    import interface
    import managers.memory_manager
    
    print("✅ 所有关键模块导入成功")
    
    # 检查关键类
    print("\n🔍 检查关键类...")
    
    # config模块
    assert hasattr(config, 'DatabaseConfig'), "缺少DatabaseConfig类"
    assert hasattr(config, 'RedisConfig'), "缺少RedisConfig类"
    assert hasattr(config, 'DatabaseType'), "缺少DatabaseType类"
    print("✅ config模块检查通过")
    
    # factory模块
    assert hasattr(factory, 'DatabaseManagerFactory'), "缺少DatabaseManagerFactory类"
    print("✅ factory模块检查通过")
    
    # interface模块
    assert hasattr(interface, 'DatabaseManager'), "缺少DatabaseManager接口"
    print("✅ interface模块检查通过")
    
    # memory_manager模块
    assert hasattr(managers.memory_manager, 'MemoryDatabaseManager'), "缺少MemoryDatabaseManager类"
    print("✅ memory_manager模块检查通过")
    
except Exception as e:
    print(f"❌ 导入测试失败: {e}")
    sys.exit(1)

# 功能测试
print("\n🧪 功能测试...")

async def test_memory_database():
    """测试内存数据库功能"""
    print("\n1. 测试内存数据库...")
    
    try:
        # 创建配置
        cfg = config.DatabaseConfig(
            db_type=config.DatabaseType.MEMORY,
            redis=config.RedisConfig(enabled=False)
        )
        print(f"   ✅ 创建配置: {cfg.db_type}")
        
        # 使用工厂创建管理器
        manager = await factory.DatabaseManagerFactory.create_manager(cfg)
        print(f"   ✅ 创建管理器: {type(manager).__name__}")
        
        # 测试连接
        await manager.connect()
        print("   ✅ 连接成功")
        
        # 测试健康检查
        health = await manager.health_check()
        print(f"   ✅ 健康检查: {health}")
        
        # 测试获取统计
        stats = await manager.get_stats()
        print(f"   ✅ 获取统计: 包含{len(stats)}个分类")
        
        # 测试断开连接
        await manager.disconnect()
        print("   ✅ 断开连接")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 内存数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_factory_functions():
    """测试工厂功能"""
    print("\n2. 测试工厂功能...")
    
    try:
        # 测试URL生成函数
        cfg = config.DatabaseConfig(
            db_type=config.DatabaseType.MEMORY
        )
        memory_url = factory.get_database_url(cfg)
        print(f"   ✅ 内存数据库URL: {memory_url}")
        
        # 测试配置摘要
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            factory.print_config_summary(cfg)
        
        output = f.getvalue()
        print(f"   ✅ 配置摘要输出长度: {len(output)} 字符")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 工厂功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_direct_memory_manager():
    """直接测试内存管理器"""
    print("\n3. 直接测试内存管理器...")
    
    try:
        # 直接创建内存管理器（不通过工厂）
        cfg = config.DatabaseConfig(
            db_type=config.DatabaseType.MEMORY,
            redis=config.RedisConfig(enabled=False)
        )
        
        manager = managers.memory_manager.MemoryDatabaseManager(cfg)
        print(f"   ✅ 直接创建MemoryDatabaseManager")
        
        # 测试异步方法
        await manager.connect()
        print("   ✅ 直接连接成功")
        
        await manager.disconnect()
        print("   ✅ 直接断开连接")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 直接内存管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

# 运行所有测试
print("\n" + "=" * 50)
print("开始运行所有功能测试...")
print("=" * 50)

async def run_all_tests():
    results = []
    
    results.append(await test_memory_database())
    results.append(await test_factory_functions())
    results.append(await test_direct_memory_manager())
    
    return all(results)

# 执行测试
success = asyncio.run(run_all_tests())

print("\n" + "=" * 50)
if success:
    print("🎉 所有测试通过！")
    print("\n✅ 数据库服务基本功能验证完成")
    print("✅ 模块导入正常")
    print("✅ 工厂模式正常工作")
    print("✅ 内存管理器功能正常")
else:
    print("⚠️  部分测试失败")
    
print("=" * 50)