#!/usr/bin/env python3
"""
测试Redis Stream模块错误处理器
"""
import asyncio
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup_before_test():
    """测试前清理残留资源"""
    try:
        print("\n🧹 测试前清理残留资源...")
        from database_service.streams.utils.test_cleanup_tool import cleanup_test_environment

        result = await cleanup_test_environment(dry_run=False)

        if "error" in result:
            print(f"⚠️  清理失败: {result['error']}")
        else:
            print(f"✅ 测试前清理完成:")
            print(f"  清理Stream: {result.get('streams_cleaned', 0)} 个")
            print(f"  清理消费者组: {result.get('groups_cleaned', 0)} 个")

    except ImportError:
        print("⚠️  清理工具不可用，跳过测试前清理")
    except Exception as e:
        print(f"⚠️  清理过程出错: {e}")


async def cleanup_after_test():
    """测试后清理测试资源"""
    try:
        print("\n🧹 测试后清理测试资源...")
        from database_service.streams.utils.test_cleanup_tool import cleanup_test_environment

        result = await cleanup_test_environment(dry_run=False)

        if "error" in result:
            print(f"⚠️  清理失败: {result['error']}")
        else:
            print(f"✅ 测试后清理完成:")
            print(f"  清理Stream: {result.get('streams_cleaned', 0)} 个")
            print(f"  清理消费者组: {result.get('groups_cleaned', 0)} 个")

    except ImportError:
        print("⚠️  清理工具不可用，跳过测试后清理")
    except Exception as e:
        print(f"⚠️  清理过程出错: {e}")


async def test_error_handler():
    """测试错误处理器"""
    try:
        # 测试前清理
        await cleanup_before_test()

        from database_service.streams.stream_manager import RetryEnhancedRedisStreamManager

        # 创建管理器
        manager = RetryEnhancedRedisStreamManager(
            redis_url="redis://localhost:6379/0",
            enable_retry=True
        )

        await manager.connect()
        print("✅ Redis连接成功")

        # 测试错误处理器是否存在
        if manager.error_handler:
            print(f"✅ 错误处理器已加载: {manager.error_handler.__class__.__name__}")

            # 获取统计
            stats = manager.error_handler.get_stats()
            print(f"✅ 错误处理器统计: 总错误数={stats['total_errors']}")
        else:
            print("⚠️  错误处理器未加载")

        # 测试消费者组管理器
        if hasattr(manager, 'consumer_group_manager'):
            print(f"✅ 消费者组管理器已加载")
        else:
            print("⚠️  消费者组管理器未加载")

        # 测试发布消息（正常）
        test_stream = "stream:test:error_handler"
        test_data = {"test": "message", "timestamp": "2026-04-09"}

        try:
            message_id = await manager.publish(test_stream, test_data, max_len=10)
            print(f"✅ 发布消息成功: {message_id}")
        except Exception as e:
            print(f"❌ 发布消息失败: {e}")

        # 测试消费消息
        test_group = "test_error_handler_group"
        test_consumer = "test_consumer"

        # 确保消费者组存在
        try:
            await manager.create_consumer_group(test_stream, test_group)
            print(f"✅ 创建消费者组成功")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                print(f"✅ 消费者组已存在")
            else:
                print(f"❌ 创建消费者组失败: {e}")

        # 消费消息
        try:
            messages = await manager.consume(test_group, test_consumer, test_stream, count=1, block_ms=1000)
            print(f"✅ 消费消息成功: 收到 {len(messages)} 条消息")

            for msg in messages:
                print(f"  消息ID: {msg.id}, 数据: {msg.data}")
                # 确认消息
                ack_result = await manager.ack(test_stream, test_group, msg.id)
                print(f"  确认消息结果: {ack_result}")
        except Exception as e:
            print(f"❌ 消费消息失败: {e}")

        # 测试错误场景：向不存在的Stream消费（应触发错误处理器）
        non_existent_stream = "stream:non:existent"
        try:
            messages = await manager.consume(test_group, test_consumer, non_existent_stream, count=1, block_ms=100)
            print(f"消费不存在的Stream结果: {len(messages)} 条消息")
        except Exception as e:
            print(f"✅ 预期错误: {e}")
            if manager.error_handler:
                print(f"✅ 错误应已被错误处理器捕获")

        # 打印管理器统计
        manager_stats = manager.get_stats()
        print(f"\n📊 管理器统计:")
        print(f"  发布操作: {manager_stats['operation_stats']['publish_operations']}")
        print(f"  消费操作: {manager_stats['operation_stats']['consume_operations']}")
        print(f"  确认操作: {manager_stats['operation_stats']['ack_operations']}")

        # 打印错误处理器统计（如果有）
        if manager.error_handler:
            error_stats = manager.error_handler.get_stats()
            print(f"\n📊 错误处理器统计:")
            print(f"  总错误数: {error_stats['total_errors']}")
            print(f"  恢复错误: {error_stats['recovered_errors']}")
            print(f"  恢复率: {error_stats['recovery_rate']:.1%}")
            print(f"  死信队列消息: {error_stats['dead_letter_messages']}")

        # 清理测试Stream
        try:
            # 删除测试Stream
            from redis.asyncio import Redis
            redis_client = await Redis.from_url("redis://localhost:6379/0", decode_responses=True)
            await redis_client.delete(test_stream)
            await redis_client.close()
            print(f"✅ 清理测试Stream: {test_stream}")
        except Exception as e:
            print(f"清理失败: {e}")

        await manager.close()
        print("✅ 测试完成")

        # 测试后清理
        await cleanup_after_test()

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_error_handler())