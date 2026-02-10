"""
测试正确的路径
"""
import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path.cwd()
sys.path.insert(0, str(current_dir))

print(f"当前目录: {current_dir}")
print("\n📁 检查目录结构:")

# 检查正确的路径
correct_paths = [
    'model_service/services/event_extractor.py',
    'model_service/llm_parser/factory.py',
    'model_service/llm_parser/reliable_deepseek_parser.py'
]

for path in correct_paths:
    full_path = current_dir / path
    exists = full_path.exists()
    print(f"  {path}: {'✅' if exists else '❌'} {full_path}")
    
    if not exists:
        print(f"    实际文件: {list((current_dir / 'model_service').rglob('event_extractor.py'))}")

# 尝试导入
print("\n🔧 尝试导入正确的模块...")
try:
    # 直接导入文件
    import importlib.util
    
    # 导入 event_extractor.py (正确的路径)
    spec = importlib.util.spec_from_file_location(
        "event_extractor", 
        current_dir / "model_service" / "services" / "event_extractor.py"
    )
    event_extractor_module = importlib.util.module_from_spec(spec)
    sys.modules["event_extractor"] = event_extractor_module
    spec.loader.exec_module(event_extractor_module)
    
    from model_service.services.event_extractor import AIEventExtractor
    print("✅ 成功从 model_service.services.event_extractor 导入 AIEventExtractor!")
    
    # 测试创建实例
    import asyncio
    
    async def test():
        extractor = AIEventExtractor()
        print("✅ 成功创建AIEventExtractor实例")
        
        # 测试健康检查
        health = await extractor.health_check()
        print(f"✅ 健康检查结果: {health}")
        
        # 测试提取事件
        test_news = {
            'news_id': 'test_001',
            'title': '苹果发布新一代iPhone',
            'content': '苹果公司今日发布新一代iPhone 16，搭载更强大的A18芯片...'
        }
        
        print(f"\n📰 测试提取事件: {test_news['title']}")
        event_data = await extractor.extract_event(test_news)
        
        if event_data:
            print("✅ 成功提取事件数据!")
            print(f"  事件类型: {event_data.get('event_type')}")
            print(f"  摘要长度: {len(event_data.get('summary', ''))} 字符")
            print(f"  主题指令: {event_data.get('theme_directive', {}).get('action')}")
            
            if 'original_data' in event_data:
                content_len = len(event_data['original_data'].get('content', ''))
                print(f"  原始内容保存: {content_len} 字符")
        else:
            print("❌ 提取器返回None")
        
        return True
    
    asyncio.run(test())
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
