
import sys
import os
sys.path.insert(0, 'database_service')

try:
    # 创建模拟的 EventProducer 测试
    class MockEventProducer:
        async def publish(self, event_data, is_major=False):
            print(f"MockEventProducer.publish called with:")
            print(f"  event_data keys: {list(event_data.keys())}")
            print(f"  is_major: {is_major}")
            return f"mock_event_id_{is_major}"
    
    # 临时替换
    import streams.stream_gateway as sg
    original_event_producer = None
    
    # 测试调用
    import asyncio
    async def test():
        # 创建实例但不实际调用
        print("测试准备完成 - 需要实际运行完整测试验证")
    
    asyncio.run(test())
    
    print("✅ 测试准备完成")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
