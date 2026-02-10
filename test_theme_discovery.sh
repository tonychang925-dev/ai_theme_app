#!/bin/bash
# test_theme_discovery.sh - 测试主题发现引擎
echo "🧪 测试主题发现引擎"
echo "=================="

python -c "
import asyncio
import sys
sys.path.insert(0, '.')

async def test():
    print('1. 导入模块测试...')
    try:
        from theme_service.services.theme_discovery import ThemeDiscoveryEngine
        print('   ✅ ThemeDiscoveryEngine 导入成功')
        
        # 创建模拟客户端
        class MockAIClient:
            async def analyze_event_for_themes(self, event_data):
                return {
                    'potential_themes': ['AI眼镜', '智能穿戴'],
                    'certainty': 0.8,
                    'theme_strength': {'score': 7, 'reason': '测试'}
                }
        
        print('2. 实例化测试...')
        ai_client = MockAIClient()
        engine = ThemeDiscoveryEngine(ai_client)
        print('   ✅ 引擎实例化成功')
        
        print('3. 功能测试...')
        test_events = [
            {
                'id': 1001,
                'title': '测试事件1',
                'summary': '测试摘要',
                'event_type': '测试',
                'impact_industries': ['消费电子']
            }
        ]
        
        themes = await engine.discover_from_events(test_events)
        print(f'   ✅ 发现 {len(themes)} 个主题')
        
        if themes:
            for theme in themes:
                print(f'      主题: {theme[\"name\"]}, 置信度: {theme[\"confidence\"]:.2f}')
        
        return True
        
    except Exception as e:
        print(f'❌ 测试失败: {e}')
        import traceback
        traceback.print_exc()
        return False

# 运行测试
import asyncio
success = asyncio.run(test())

print('\\n' + '=' * 40)
if success:
    print('🎉 主题发现引擎测试通过！')
else:
    print('⚠️  测试失败，需要检查代码')
print('=' * 40)
"

# 检查文件
echo ""
echo "📁 当前 theme_service 结构:"
find theme_service -name "*.py" | sort | sed 's/^/  /'
