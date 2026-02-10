
import sys
import os
sys.path.insert(0, 'database_service')

try:
    from streams.stream_gateway import StreamEnhancedGateway
    print('✅ 导入成功')
    
    class MockGateway:
        async def close(self):
            pass
    
    import asyncio
    
    async def test():
        gateway = StreamEnhancedGateway(MockGateway())
        
        # 测试事件发布
        try:
            result = await gateway.publish_event({
                'id': 'test_event',
                'classification': 'test'
            })
            print(f'✅ 事件发布: {result}')
        except Exception as e:
            print(f'❌ 事件发布失败: {e}')
    
    asyncio.run(test())
    
except Exception as e:
    print(f'❌ 导入失败: {e}')
    import traceback
    traceback.print_exc()
