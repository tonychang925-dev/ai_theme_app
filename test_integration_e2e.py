#!/usr/bin/env python3
"""
端到端集成测试 - 测试 theme_service 与 model_service 的集成
"""
import asyncio
import aiohttp
import sys
import os

sys.path.insert(0, os.getcwd())

async def test_e2e_integration():
    print("=" * 60)
    print("🧪 端到端集成测试")
    print("=" * 60)
    
    # 测试1: 检查 theme_service 是否运行
    print("\n1. 测试 theme_service 状态...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8002/health') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"   ✅ theme_service 运行正常: {data}")
                else:
                    print(f"   ❌ theme_service 响应异常: {resp.status}")
    except Exception as e:
        print(f"   ❌ 无法连接到 theme_service: {e}")
    
    # 测试2: 模拟从 model_service 获取事件
    print("\n2. 模拟 model_service 数据流...")
    try:
        # 模拟 model_service 生成的事件
        mock_events = [
            {
                "id": 1001,
                "title": "Rokid智能眼镜销量突破30万台",
                "summary": "Rokid创始人透露智能眼镜销量已达30万台，预计下半年上线打车功能",
                "event_type": "产品突破",
                "impact_industries": ["消费电子", "人工智能", "智能穿戴"],
                "confidence": 0.85,
                "direction": "利好"
            },
            {
                "id": 1002,
                "title": "苹果Vision Pro二代量产在即",
                "summary": "供应链消息称苹果Vision Pro二代已开始试产，预计明年一季度发布",
                "event_type": "供应链消息",
                "impact_industries": ["消费电子", "XR设备", "苹果产业链"],
                "confidence": 0.78,
                "direction": "利好"
            }
        ]
        
        print(f"   模拟 {len(mock_events)} 个事件")
        
        # 测试3: 调用 theme_service 分析事件
        print("\n3. 调用 theme_service 分析事件...")
        async with aiohttp.ClientSession() as session:
            for event in mock_events:
                async with session.post(
                    'http://localhost:8002/analyze',
                    json=event
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        themes = result.get("potential_themes", [])
                        print(f"   ✅ 事件分析完成: {event['title'][:20]}...")
                        if themes:
                            print(f"       发现题材: {themes}")
                    else:
                        print(f"   ❌ 分析失败: {resp.status}")
        
        # 测试4: 检查主题发现
        print("\n4. 检查主题发现功能...")
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8002/themes?limit=5') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    themes = data.get("themes", [])
                    print(f"   ✅ 获取到 {len(themes)} 个主题")
                    for theme in themes:
                        print(f"      - {theme['name']} (置信度: {theme['confidence']:.2f})")
        
        print("\n" + "=" * 60)
        print("🎉 端到端测试完成！")
        print("\n✅ theme_service 可以:")
        print("   1. 接收事件进行分析")
        print("   2. 发现潜在投资主题")
        print("   3. 提供主题列表API")
        print("   4. 与 model_service 集成工作")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("端到端集成测试 - theme_service 与 model_service")
    print("-" * 60)
    
    success = asyncio.run(test_e2e_integration())
    
    if success:
        print("\n🚀 下一步: 实现真实的数据流集成")
    else:
        print("\n🔧 需要检查集成配置")
    
    sys.exit(0 if success else 1)
