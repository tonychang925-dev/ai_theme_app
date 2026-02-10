"""
直接修复路径问题的测试脚本
"""
import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path.cwd()
sys.path.insert(0, str(current_dir))

print(f"当前目录: {current_dir}")
print(f"Python路径: {sys.path[:3]}")

# 检查目录
print("\n📁 检查目录结构:")
for dir_name in ['model_service', 'model_service/service', 'model_service/llm_parser']:
    dir_path = current_dir / dir_name
    print(f"  {dir_name}: {'✅' if dir_path.exists() else '❌'} {dir_path}")
    
    # 如果目录存在，检查是否有 __init__.py
    if dir_path.exists():
        init_file = dir_path / '__init__.py'
        if not init_file.exists():
            print(f"    创建 __init__.py: {init_file}")
            init_file.touch()

# 现在尝试导入
print("\n🔧 尝试导入...")
try:
    # 直接导入文件
    import importlib.util
    
    # 导入 event_extractor.py
    spec = importlib.util.spec_from_file_location(
        "event_extractor", 
        current_dir / "model_service" / "service" / "event_extractor.py"
    )
    event_extractor_module = importlib.util.module_from_spec(spec)
    sys.modules["event_extractor"] = event_extractor_module
    spec.loader.exec_module(event_extractor_module)
    
    from model_service.service.event_extractor import AIEventExtractor
    print("✅ 成功导入 AIEventExtractor!")
    
    # 测试创建实例
    import asyncio
    
    async def test():
        extractor = AIEventExtractor()
        print("✅ 成功创建AIEventExtractor实例")
        
        # 测试健康检查
        health = await extractor.health_check()
        print(f"✅ 健康检查: {health}")
        
        return True
    
    asyncio.run(test())
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
