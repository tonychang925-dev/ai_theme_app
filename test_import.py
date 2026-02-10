
import sys
import os

# 设置正确的路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database_service.streams.stream_gateway import StreamEnhancedGateway
    print('✅ 成功导入 StreamEnhancedGateway')
    
    class MockGateway:
        async def create_theme(self, name, code):
            class Theme:
                def __init__(self):
                    self.id = 1
                    self.name = name
                    self.code = code
            return Theme()
    
    import asyncio
    async def test():
        gateway = StreamEnhancedGateway(MockGateway())
        print('✅ 成功创建实例')
        
    asyncio.run(test())
    
except Exception as e:
    print(f'❌ 导入失败: {e}')
    import traceback
    traceback.print_exc()
