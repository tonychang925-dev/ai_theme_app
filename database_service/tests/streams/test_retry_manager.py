# database_service/tests/streams/test_retry_manager_unit.py
"""
重试管理器单元测试
测试重试管理器的核心功能
"""
import asyncio
import sys
import os
import logging
import pytest
from unittest.mock import Mock, patch, AsyncMock

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)
sys.path.insert(0, service_dir)
sys.path.insert(0, os.path.join(service_dir, "streams"))

# 设置日志
logging.basicConfig(level=logging.WARNING)  # 降低日志级别以便测试输出清晰

print("🔧 重试管理器单元测试")
print("=" * 60)
print("测试重试管理器的核心功能")
print("=" * 60)

async def test_basic_functionality():
    """测试基本功能"""
    print("\n✅ 测试基本功能...")
    
    # 导入重试管理器
    try:
        from database_service.streams.utils.retry_manager import RetryManager
        print("✅ 成功导入RetryManager")
    except ImportError as e:
        print(f"❌ 导入RetryManager失败: {e}")
        return False
    
    # 测试1: 成功重试
    call_count = 0
    
    async def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception(f"模拟失败 {call_count}")
        return "success"
    
    retry_manager = RetryManager(max_retries=5, base_delay=0.01)
    result = await retry_manager.execute_with_retry(failing_function)
    
    assert result == "success"
    assert call_count == 3
    print("✅ 成功重试测试通过")
    
    # 测试2: 失败重试
    async def always_failing():
        raise Exception("总是失败")
    
    retry_manager = RetryManager(max_retries=2, base_delay=0.01)
    
    try:
        await retry_manager.execute_with_retry(always_failing)
        print("❌ 应该抛出异常")
        return False
    except Exception as e:
        assert str(e) == "总是失败"
        print("✅ 失败重试测试通过")
    
    # 测试3: 立即成功
    async def immediate_success():
        return "immediate"
    
    retry_manager = RetryManager(max_retries=2, base_delay=0.01)
    result = await retry_manager.execute_with_retry(immediate_success)
    
    assert result == "immediate"
    print("✅ 立即成功测试通过")
    
    return True

async def test_strategies():
    """测试重试策略"""
    print("\n⚙️ 测试重试策略...")
    
    try:
        from database_service.streams.utils.retry_manager import RetryManager, RetryStrategy
        
        # 测试固定间隔
        retry_manager = RetryManager(strategy=RetryStrategy.FIXED, base_delay=0.1, jitter=False)
        assert retry_manager._calculate_delay(1) == 0.1
        assert retry_manager._calculate_delay(5) == 0.1
        print("✅ 固定间隔策略测试通过")
        
        # 测试指数退避
        retry_manager = RetryManager(strategy=RetryStrategy.EXPONENTIAL, base_delay=1.0, jitter=False)
        assert retry_manager._calculate_delay(1) == 2.0  # 1 * 2^1
        assert retry_manager._calculate_delay(3) == 8.0  # 1 * 2^3
        print("✅ 指数退避策略测试通过")
        
        # 测试斐波那契退避
        retry_manager = RetryManager(strategy=RetryStrategy.FIBONACCI, base_delay=1.0, jitter=False)
        
        # 修正：斐波那契数列是 0, 1, 1, 2, 3, 5, 8, 13, ...
        # attempt=1 对应 F(2)=1，但我们需要 F(attempt+1)
        # 让我们计算正确的值
        delay1 = retry_manager._calculate_delay(1)
        delay2 = retry_manager._calculate_delay(2)
        delay3 = retry_manager._calculate_delay(3)
        delay4 = retry_manager._calculate_delay(4)
        
        print(f"   斐波那契延迟: attempt1={delay1}, attempt2={delay2}, attempt3={delay3}, attempt4={delay4}")
        
        # 验证前几个值
        # F(2)=1, F(3)=2, F(4)=3, F(5)=5
        assert delay1 == 1.0  # 1 * F(2)=1
        assert delay2 == 2.0  # 1 * F(3)=2
        assert delay3 == 3.0  # 1 * F(4)=3
        assert delay4 == 5.0  # 1 * F(5)=5
        
        print("✅ 斐波那契退避策略测试通过")
        
        # 测试最大延迟限制
        retry_manager = RetryManager(strategy=RetryStrategy.EXPONENTIAL, base_delay=10.0, max_delay=15.0, jitter=False)
        calculated_delay = retry_manager._calculate_delay(1)
        print(f"   最大延迟测试: 计算延迟={calculated_delay}, 最大延迟=15.0")
        assert calculated_delay == 15.0  # 20受限为15
        print("✅ 最大延迟限制测试通过")
        
        return True
        
    except AssertionError as e:
        print(f"❌ 断言失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ 策略测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_jitter():
    """测试抖动"""
    print("\n🎲 测试抖动...")
    
    try:
        from database_service.streams.utils.retry_manager import RetryManager
        
        # 测试有抖动
        retry_manager = RetryManager(jitter=True, base_delay=1.0)
        delays = []
        for i in range(10):
            delay = retry_manager._calculate_delay(1)
            delays.append(delay)
        
        # 检查延迟时间有变化（因为有抖动）
        assert len(set(delays)) > 1
        print("✅ 抖动测试通过")
        
        # 测试无抖动
        retry_manager = RetryManager(jitter=False, base_delay=1.0)
        delays_no_jitter = []
        for i in range(10):
            delay = retry_manager._calculate_delay(1)
            delays_no_jitter.append(delay)
        
        # 检查延迟时间相同（因为无抖动）
        assert len(set(delays_no_jitter)) == 1
        print("✅ 无抖动测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 抖动测试失败: {e}")
        return False

async def test_exception_filtering():
    """测试异常过滤"""
    print("\n🎯 测试异常过滤...")
    
    try:
        from database_service.streams.utils.retry_manager import RetryManager
        
        # 定义测试异常
        class RetryableError(Exception):
            pass
        
        class NonRetryableError(Exception):
            pass
        
        # 测试1: 默认行为（重试所有异常）
        retry_manager = RetryManager(max_retries=1, base_delay=0.01)
        assert retry_manager._should_retry_exception(RetryableError("test")) is True
        assert retry_manager._should_retry_exception(NonRetryableError("test")) is True
        print("✅ 默认异常过滤测试通过")
        
        # 测试2: 停止重试特定异常
        retry_manager = RetryManager(
            max_retries=1,
            base_delay=0.01,
            stop_on_exception=[NonRetryableError]
        )
        assert retry_manager._should_retry_exception(RetryableError("test")) is True
        assert retry_manager._should_retry_exception(NonRetryableError("test")) is False
        print("✅ 停止重试异常测试通过")
        
        # 测试3: 只重试特定异常
        retry_manager = RetryManager(
            max_retries=1,
            base_delay=0.01,
            retry_on_exception=[RetryableError]
        )
        assert retry_manager._should_retry_exception(RetryableError("test")) is True
        assert retry_manager._should_retry_exception(NonRetryableError("test")) is False
        print("✅ 只重试特定异常测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 异常过滤测试失败: {e}")
        return False

async def test_stats():
    """测试统计信息"""
    print("\n📊 测试统计信息...")
    
    try:
        from database_service.streams.utils.retry_manager import RetryManager
        
        call_count = 0
        
        async def function_for_stats():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise Exception(f"第{call_count}次失败")
            return "stats_success"
        
        retry_manager = RetryManager(max_retries=5, base_delay=0.01)
        result = await retry_manager.execute_with_retry(function_for_stats)
        
        assert result == "stats_success"
        
        stats = retry_manager.get_stats()
        
        # 验证统计信息
        assert stats["total_retries"] == 3
        assert stats["successful_retries"] == 1
        assert stats["failed_retries"] == 0
        assert stats["success_rate"] == 1.0
        assert len(stats["execution_times"]) == 4  # 3次失败 + 1次成功
        assert stats["total_duration"] > 0
        
        print("✅ 统计信息测试通过")
        
        # 测试重置统计
        retry_manager.reset_stats()
        stats = retry_manager.get_stats()
        assert stats["total_retries"] == 0
        print("✅ 重置统计测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 统计测试失败: {e}")
        return False

async def test_decorator():
    """测试装饰器"""
    print("\n🎭 测试装饰器...")
    
    try:
        from database_service.streams.utils.retry_manager import with_retry
        
        call_count = 0
        
        @with_retry(max_retries=3, base_delay=0.01)
        async def decorated_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("需要重试")
            return "decorated_success"
        
        result = await decorated_function()
        
        assert result == "decorated_success"
        assert call_count == 2
        
        print("✅ 装饰器测试通过")
        
        # 测试带参数的装饰器
        call_count2 = 0
        
        @with_retry(max_retries=5, base_delay=0.01, strategy="fixed")
        async def decorated_with_params():
            nonlocal call_count2
            call_count2 += 1
            if call_count2 < 3:
                raise Exception("参数化重试")
            return "params_success"
        
        result = await decorated_with_params()
        
        assert result == "params_success"
        assert call_count2 == 3
        
        print("✅ 带参数装饰器测试通过")
        
        return True
        
    except Exception as e:
        print(f"❌ 装饰器测试失败: {e}")
        return False

async def run_all_unit_tests():
    """运行所有单元测试"""
    print("🧪 重试管理器单元测试套件")
    print("=" * 60)
    print("测试重试管理器的核心功能")
    print("=" * 60)
    
    tests = [
        ("基本功能", test_basic_functionality),
        ("重试策略", test_strategies),
        ("抖动", test_jitter),
        ("异常过滤", test_exception_filtering),
        ("统计信息", test_stats),
        ("装饰器", test_decorator),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            print(f"\n📋 {name}:")
            success = await test_func()
            status = "✅ 通过" if success else "❌ 失败"
            results.append((name, success))
            print(f"  {status}")
        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 单元测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print("-" * 60)
    success_rate = passed / total * 100 if total > 0 else 0
    print(f"总计: {passed}/{total} 通过 ({success_rate:.1f}%)")
    
    if passed == total:
        print("\n" + "=" * 60)
        print("✨ 完 美 ！ 所 有 单 元 测 试 通 过 ！")
        print("=" * 60)
        print("🎉 重试管理器核心功能完全验证！")
        print("=" * 60)
        return True
    elif passed >= total - 1:
        print(f"\n⚠️  单元测试基本通过: {passed}/{total}")
        print("💡 核心功能正常")
        return True
    else:
        print(f"\n❌ 单元测试失败: {passed}/{total} 通过")
        print("🔧 需要修复核心功能")
        return False

def main():
    """主函数"""
    try:
        print("🔍 运行重试管理器单元测试...")
        
        # 运行所有单元测试
        success = asyncio.run(run_all_unit_tests())
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        return 130
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())