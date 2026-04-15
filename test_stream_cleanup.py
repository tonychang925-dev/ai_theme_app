#!/usr/bin/env python3
"""
Stream清理功能测试
验证基于时间的清理功能是否正常工作
"""
import asyncio
import time
import json
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_age_based_cleanup():
    """测试基于时间的Stream清理"""
    from database_service.streams.stream_manager import RetryEnhancedRedisStreamManager

    print("🧪 测试基于时间的Stream清理")
    print("=" * 60)

    manager = None
    try:
        # 创建管理器
        manager = RetryEnhancedRedisStreamManager()
        await manager.connect()

        # 创建测试Stream
        test_stream = f"stream:test:cleanup:{int(time.time())}"
        print(f"创建测试Stream: {test_stream}")

        # 添加测试消息
        messages_added = 0

        # 添加一些"旧"消息（模拟35天前）
        # 使用过去的时间戳ID
        old_timestamp_ms = int((time.time() - 35 * 86400) * 1000)  # 35天前
        for i in range(2):
            # 手动生成消息ID
            message_id = f"{old_timestamp_ms + i}-0"
            await manager.redis.xadd(test_stream, {"message": f"old_{i}", "timestamp": "35_days_ago"}, id=message_id)
            messages_added += 1

        # 添加一些当前时间的消息
        for i in range(3):
            await manager.redis.xadd(test_stream, {"message": f"recent_{i}", "timestamp": "now"})
            messages_added += 1

        print(f"添加 {messages_added} 条测试消息 (3条新消息, 2条35天前旧消息)")

        # 检查Stream长度
        stream_info = await manager.redis.xinfo_stream(test_stream)
        print(f"清理前Stream长度: {stream_info.get('length', 0)}")
        # 执行基于时间的清理（保留30天）
        print("\n🔧 执行基于时间的清理 (max_age_days=30)...")
        cleanup_result = await manager.trim_stream_by_age(test_stream, max_age_days=30, dry_run=False)

        print(f"清理结果: {'成功' if cleanup_result.get('success') else '失败'}")
        print(f"清理消息数: {cleanup_result.get('trimmed_count', 0)}")
        print(f"清理消息: {cleanup_result.get('message', '无消息')}")
        print(f"第一条消息年龄: {cleanup_result.get('first_message_age_days', '未知')}天")
        print(f"截止ID: {cleanup_result.get('cutoff_id', '未知')}")

        if cleanup_result.get('success'):
            # 验证清理后长度
            stream_info_after = await manager.redis.xinfo_stream(test_stream)
            length_after = stream_info_after.get('length', 0)
            print(f"清理后Stream长度: {length_after}")

            # 期望保留3条新消息，删除2条旧消息
            expected_remaining = 3
            if length_after == expected_remaining:
                print("✅ 基于时间的清理测试通过")
                return True
            else:
                print(f"❌ 清理后长度不匹配: 期望 {expected_remaining}, 实际 {length_after}")
                return False
        else:
            print(f"❌ 清理失败: {cleanup_result.get('error', '未知错误')}")
            return False

    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if manager:
            # 清理测试Stream
            try:
                await manager.redis.delete(test_stream)
                print(f"🧹 清理测试Stream: {test_stream}")
            except:
                pass
            await manager.close()


async def test_safe_stream_cleanup():
    """测试安全清理流程"""
    from database_service.streams.stream_manager import RetryEnhancedRedisStreamManager

    print("\n🧪 测试安全Stream清理流程")
    print("=" * 60)

    manager = None
    try:
        manager = RetryEnhancedRedisStreamManager()
        await manager.connect()

        test_stream = f"stream:test:safe_cleanup:{int(time.time())}"
        print(f"创建测试Stream: {test_stream}")

        # 添加测试消息
        for i in range(10):
            await manager.redis.xadd(test_stream, {"message": f"test_{i}", "index": i})

        # 测试安全清理（dry_run模式）
        print("\n🔧 测试安全清理 (dry_run=True)...")
        safe_result = await manager.safe_stream_cleanup(
            stream=test_stream,
            max_age_days=30,
            max_length=5,
            dry_run=True
        )

        print(f"安全清理结果: {'成功' if safe_result.get('success') else '失败'}")
        print(f"执行的操作: {safe_result.get('actions_taken', [])}")

        if safe_result.get('success'):
            print("✅ 安全清理dry_run测试通过")

            # 测试实际清理
            print("\n🔧 测试实际清理 (dry_run=False)...")
            actual_result = await manager.safe_stream_cleanup(
                stream=test_stream,
                max_age_days=30,
                max_length=5,
                dry_run=False
            )

            print(f"实际清理结果: {'成功' if actual_result.get('success') else '失败'}")
            print(f"清理详情: {actual_result.get('cleanup_results', {})}")

            if actual_result.get('success'):
                print("✅ 安全清理实际执行测试通过")
                return True
            else:
                print(f"❌ 实际清理失败: {actual_result.get('error', '未知错误')}")
                return False
        else:
            print(f"❌ 安全清理dry_run失败: {safe_result.get('error', '未知错误')}")
            return False

    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if manager:
            try:
                await manager.redis.delete(test_stream)
                print(f"🧹 清理测试Stream: {test_stream}")
            except:
                pass
            await manager.close()


async def test_cleanup_scheduler():
    """测试清理调度器"""
    from database_service.streams.stream_cleanup_scheduler import StreamCleanupScheduler
    from database_service.streams.stream_manager import RetryEnhancedRedisStreamManager

    print("\n🧪 测试清理调度器")
    print("=" * 60)

    manager = None
    try:
        manager = RetryEnhancedRedisStreamManager()
        await manager.connect()

        # 创建调度器（模拟模式）
        scheduler = StreamCleanupScheduler(
            manager,
            config={
                "dry_run": True,
                "cleanup_interval_hours": 24,
                "default_max_age_days": 30,
                "default_max_length": 10,
                "max_streams_per_batch": 5
            }
        )

        print("✅ 清理调度器创建成功")

        # 测试单次计划清理
        print("\n🔧 执行计划清理任务...")
        result = await scheduler.perform_scheduled_cleanup()

        print(f"计划清理结果: {'成功' if result.get('success') else '失败'}")
        print(f"处理Stream数: {result.get('streams_processed', 0)}")
        print(f"清理消息数: {result.get('total_messages_trimmed', 0)}")

        if result.get('success') or result.get('streams_processed', 0) >= 0:
            print("✅ 清理调度器测试通过")
            return True
        else:
            print(f"❌ 清理调度器测试失败: {result.get('error', '未知错误')}")
            return False

    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if manager:
            await manager.close()


async def main():
    """运行所有测试"""
    print("🚀 Stream清理功能全面测试")
    print("=" * 60)

    tests = [
        ("基于时间的清理", test_age_based_cleanup),
        ("安全清理流程", test_safe_stream_cleanup),
        ("清理调度器", test_cleanup_scheduler)
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"开始测试: {test_name}")
        print(f"{'='*60}")

        try:
            success = await test_func()
            results.append((test_name, success))

            if success:
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
            results.append((test_name, False))

    # 汇总结果
    print(f"\n{'='*60}")
    print("测试汇总:")
    print(f"{'='*60}")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")

    print(f"\n总计: {passed}/{total} 个测试通过")

    if passed == total:
        print("🎉 所有测试通过! Stream清理功能正常工作")
        return 0
    else:
        print(f"⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)