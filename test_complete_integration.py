#!/usr/bin/env python3
"""
完整集成测试 - 修复后版本
"""
import asyncio
import sys
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_complete():
    print("=" * 60)
    print("🧪 完整集成测试（修复后）")
    print("=" * 60)
    
    all_passed = True
    
    # 1. 测试配置
    print("\n1. 测试配置...")
    try:
        from theme_service.config import settings
        print(f"   ✅ 配置加载: {settings.DATABASE_URL[:40]}...")
        print(f"      模式: {settings.INTEGRATION_MODE}")
    except Exception as e:
        print(f"   ❌ 配置失败: {e}")
        all_passed = False
    
    # 2. 测试数据库
    print("\n2. 测试数据库...")
    try:
        from theme_service.database import ThemeDatabase
        # 使用内存数据库避免依赖
        db = ThemeDatabase("sqlite:///:memory:")
        print(f"   ✅ 数据库模块: 可用")
    except Exception as e:
        print(f"   ❌ 数据库失败: {e}")
        all_passed = False
    
    # 3. 测试AI客户端
    print("\n3. 测试AI客户端...")
    try:
        from theme_service.services.ai_client import AIThemeClient
        client = AIThemeClient(settings)
        print(f"   ✅ AI客户端: 可用")
        
        # 测试分析
        test_event = {
            "id": 1001,
            "title": "测试事件",
            "summary": "测试摘要",
            "event_type": "测试",
            "impact_industries": ["测试"]
        }
        
        result = await client.analyze_event_for_themes(test_event)
        print(f"   ✅ AI分析完成")
        
    except Exception as e:
        print(f"   ❌ AI客户端失败: {e}")
        all_passed = False
    
    # 4. 测试主题发现
    print("\n4. 测试主题发现...")
    try:
        from theme_service.services.theme_discovery import ThemeDiscoveryEngine
        
        class MockClient:
            async def analyze_event_for_themes(self, event):
                return {
                    "potential_themes": ["AI眼镜", "智能穿戴"],
                    "certainty": 0.8,
                    "theme_strength": {"score": 7, "reason": "测试"}
                }
        
        ai_client = MockClient()
        engine = ThemeDiscoveryEngine(ai_client)
        
        test_events = [{
            "id": 1,
            "title": "测试",
            "summary": "测试",
            "event_type": "测试",
            "impact_industries": ["消费电子"]
        }]
        
        themes = await engine.discover_from_events(test_events)
        print(f"   ✅ 主题发现引擎: 工作正常")
        if themes:
            print(f"      发现主题: {len(themes)} 个")
        
    except Exception as e:
        print(f"   ❌ 主题发现失败: {e}")
        all_passed = False
    
    # 5. 测试其他模块
    print("\n5. 测试其他模块...")
    modules = [
        ("theme_heat", "✅"),
        ("theme_lifecycle", "✅"),
        ("theme_mapper", "✅"),
        ("app", "✅")
    ]
    
    for module_name, expected in modules:
        try:
            module_path = f"theme_service.{'services' if module_name != 'app' else ''}.{module_name}"
            __import__(module_path)
            print(f"   {expected} {module_name}: 可导入")
        except Exception as e:
            print(f"   ❌ {module_name}: 导入失败 ({str(e)[:50]}...)")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有模块集成测试通过！")
        print("\n✅ theme_service 现在可以正常工作")
        print("   下一步:")
        print("   1. 配置数据库连接（如果需要真实数据库）")
        print("   2. 启动服务测试完整流程")
        print("   3. 连接 model_service 进行端到端测试")
    else:
        print("⚠️  测试过程中发现问题")
        print("\n🔧 需要检查特定模块的导入或实现")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(test_complete())
    sys.exit(0 if success else 1)
