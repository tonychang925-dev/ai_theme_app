#!/usr/bin/env python3
"""
最小化真实引擎测试 - 直接使用您的ThemeDiscoveryEngine
"""
import asyncio
import sys
sys.path.insert(0, '..')

async def test_real_engine():
    try:
        # 1. 导入您的真实模块
        from theme_service.services.ai_client import AIThemeClient
        from theme_service.services.theme_discovery import ThemeDiscoveryEngine
        from theme_service.config import settings
        
        print("✅ 成功导入真实模块")
        
        # 2. 创建实例
        ai_client = AIThemeClient(settings)
        engine = ThemeDiscoveryEngine(ai_client)
        
        print("✅ 成功创建引擎实例")
        
        # 3. 测试一个简单事件
        test_event = {
            "id": "test_001",
            "title": "Meta与Oakley合作开发的智能眼镜产品举行发布会",
            "summary": "Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会",
            "content": "Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会",
            "impact_industries": ["消费电子", "人工智能"]
        }
        
        print("🔬 测试真实引擎处理事件...")
        result = await engine.process_single_event(test_event)
        
        print(f"✅ 引擎处理完成!")
        print(f"   发现的题材: {result.get('themes_found', [])}")
        print(f"   置信度: {result.get('confidence', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_real_engine())
    sys.exit(0 if success else 1)
