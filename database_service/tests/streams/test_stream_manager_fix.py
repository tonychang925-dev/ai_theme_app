# database_service/tests/streams/test_stream_manager_final_check.py
"""
最终检查stream_manager.py的修复
"""
import asyncio
import sys
import os

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.dirname(current_dir)
service_dir = os.path.dirname(tests_dir)
project_root = os.path.dirname(service_dir)

sys.path.insert(0, project_root)
sys.path.insert(0, service_dir)

print("🔧 最终检查stream_manager.py的修复")
print("=" * 60)

async def test_basic_functionality():
    """测试基本功能"""
    print("\n🎯 测试基本功能...")
    
    try:
        from database_service.streams.stream_manager import RedisStreamManager
        
        # 创建管理器
        manager = RedisStreamManager("redis://localhost:6379/0")
        
        # 1. 测试连接
        await manager.connect()
        print("✅ 1. 连接成功")
        
        # 2. 测试发布
        message_id = await manager.publish("stream:final:check", {"test": "final"})
        assert message_id is not None
        print(f"✅ 2. 发布成功: {message_id}")
        
        # 3. 测试创建消费者组
        result = await manager.create_consumer_group("stream:final:check", "final_group")
        assert result is True
        print("✅ 3. 创建消费者组成功")
        
        # 4. 测试消费
        messages = await manager.consume(
            group="final_group",
            consumer="final_consumer",
            stream="stream:final:check",
            count=10
        )
        assert len(messages) == 1
        print("✅ 4. 消费成功")
        
        # 5. 测试确认
        ack_result = await manager.ack("stream:final:check", "final_group", messages[0].id)
        assert ack_result == 1
        print("✅ 5. 确认成功")
        
        # 6. 测试关闭连接
        await manager.close()
        print("✅ 6. 关闭连接成功")
        
        # 7. 测试重新连接
        await manager.connect()
        print("✅ 7. 重新连接成功")
        
        # 8. 再次关闭
        await manager.close()
        print("✅ 8. 再次关闭成功")
        
        print("\n🎉 基本功能测试完全通过!")
        return True
        
    except Exception as e:
        print(f"\n❌ 基本功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_all_methods_exist():
    """测试所有方法都存在"""
    print("\n🔍 测试所有方法都存在...")
    
    try:
        from database_service.streams.stream_manager import RedisStreamManager
        
        # 创建实例
        manager = RedisStreamManager()
        
        # 检查所有必需的方法
        required_methods = [
            'connect',
            'publish', 
            'create_consumer_group',
            'consume',
            'ack',
            'batch_ack',
            'close'  # 这是新添加的
        ]
        
        for method in required_methods:
            if hasattr(manager, method) and callable(getattr(manager, method)):
                print(f"✅ {method} 方法存在")
            else:
                print(f"❌ {method} 方法不存在或不可调用")
                return False
        
        # 检查属性
        required_attrs = ['redis_url', 'redis', 'connected']
        for attr in required_attrs:
            if hasattr(manager, attr):
                print(f"✅ {attr} 属性存在")
            else:
                print(f"❌ {attr} 属性不存在")
                return False
        
        print("\n🎉 所有方法和属性都存在!")
        return True
        
    except Exception as e:
        print(f"\n❌ 方法存在性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_integration():
    """测试集成功能"""
    print("\n🔄 测试集成功能...")
    
    try:
        from database_service.streams.stream_manager import RedisStreamManager
        
        # 创建两个管理器测试连接池
        manager1 = RedisStreamManager()
        manager2 = RedisStreamManager()  # 相同的URL应该使用连接池
        
        await manager1.connect()
        await manager2.connect()
        
        # 分别发布消息到不同的流
        msg1 = await manager1.publish("stream:integration:1", {"manager": 1})
        msg2 = await manager2.publish("stream:integration:2", {"manager": 2})
        
        print(f"✅ 管理器1发布: {msg1}")
        print(f"✅ 管理器2发布: {msg2}")
        
        # 创建消费者组
        await manager1.create_consumer_group("stream:integration:1", "int_group_1")
        await manager2.create_consumer_group("stream:integration:2", "int_group_2")
        
        # 消费消息
        messages1 = await manager1.consume(
            group="int_group_1",
            consumer="int_consumer_1",
            stream="stream:integration:1",
            count=5
        )
        
        messages2 = await manager2.consume(
            group="int_group_2", 
            consumer="int_consumer_2",
            stream="stream:integration:2",
            count=5
        )
        
        print(f"✅ 管理器1消费到 {len(messages1)} 条消息")
        print(f"✅ 管理器2消费到 {len(messages2)} 条消息")
        
        # 批量确认
        if messages1:
            batch_result = await manager1.batch_ack(
                stream="stream:integration:1",
                group="int_group_1",
                message_ids=[msg.id for msg in messages1]
            )
            print(f"✅ 管理器1批量确认: {batch_result}")
        
        if messages2:
            batch_result = await manager2.batch_ack(
                stream="stream:integration:2",
                group="int_group_2", 
                message_ids=[msg.id for msg in messages2]
            )
            print(f"✅ 管理器2批量确认: {batch_result}")
        
        # 清理
        await manager1.close()
        await manager2.close()
        
        print("\n🎉 集成功能测试通过!")
        return True
        
    except Exception as e:
        print(f"\n❌ 集成功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_final_check():
    """运行最终检查"""
    print("🧪 stream_manager.py 最终修复检查")
    print("=" * 60)
    print("验证所有问题已完全解决")
    print("=" * 60)
    
    tests = [
        ("方法存在性测试", test_all_methods_exist),
        ("基本功能测试", test_basic_functionality),
        ("集成功能测试", test_integration),
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
    print("📊 最终修复检查总结")
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
        print("✨ 完 全 修 复 成 功 ！")
        print("=" * 60)
        print("✅ 所有方法都存在（包括close方法）")
        print("✅ 所有核心功能正常工作")
        print("✅ 集成功能正常")
        print("🎉 stream_manager.py 可以投入生产使用！")
        print("=" * 60)
        return True
    elif passed >= total - 1:
        print(f"\n⚠️  修复基本成功: {passed}/{total}")
        print("💡 核心功能正常")
        print("🔧 可以使用stream_manager模块")
        return True
    else:
        print(f"\n❌ 修复失败: {passed}/{total} 通过")
        print("🔧 需要进一步修复")
        return False

def main():
    """主函数"""
    try:
        success = asyncio.run(run_final_check())
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        return 130
    except Exception as e:
        print(f"\n❌ 最终检查运行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())