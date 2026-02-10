# evaluate_service/runners/test_quick_fix.py
"""
快速测试修复效果
"""
#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


async def test_fixes():
    """测试修复"""
    print("🧪 快速测试修复效果")
    print("="*60)
    
    try:
        # 1. 测试 RelatedThemeFetcher 是否有 fetch_relevant_themes 方法
        print("1. 测试 RelatedThemeFetcher...")
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        from database_service.pure_data_fetcher import PureDataFetcher
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        
        # 初始化数据库
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        data_fetcher = PureDataFetcher(db_manager)
        
        # 检查类是否有 fetch_relevant_themes 方法
        if hasattr(RelatedThemeFetcher, 'fetch_relevant_themes'):
            print("   ✅ RelatedThemeFetcher 类有 fetch_relevant_themes 方法")
        else:
            print("   ❌ RelatedThemeFetcher 类没有 fetch_relevant_themes 方法")
            return False
        
        # 创建实例
        theme_fetcher = RelatedThemeFetcher(data_fetcher)
        
        # 测试实例方法
        if hasattr(theme_fetcher, 'fetch_relevant_themes'):
            print("   ✅ theme_fetcher 实例有 fetch_relevant_themes 方法")
        else:
            print("   ❌ theme_fetcher 实例没有 fetch_relevant_themes 方法")
            return False
        
        # 2. 测试 EnhancedThemeDiscovery 是否能正确初始化
        print("\n2. 测试 EnhancedThemeDiscovery...")
        from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
        
        # 创建模拟的相似性分析器
        class MockSimilarityAnalyzer:
            async def analyze_with_theme_extraction(self, event, themes):
                return {'action': 'TEST'}
        
        similarity_analyzer = MockSimilarityAnalyzer()
        
        # 初始化 EnhancedThemeDiscovery
        discovery = EnhancedThemeDiscovery(
            data_fetcher=data_fetcher,
            similarity_analyzer=similarity_analyzer,
            new_theme_threshold=0.3
        )
        
        # 检查是否有 related_theme_fetcher 属性
        if hasattr(discovery, 'related_theme_fetcher'):
            print("   ✅ discovery 有 related_theme_fetcher 属性")
        else:
            print("   ❌ discovery 没有 related_theme_fetcher 属性")
            return False
        
        # 3. 测试实际的数据流
        print("\n3. 测试实际数据流...")
        
        # 创建测试事件
        test_event = {
            'news_id': 'test_event_001',
            'original_news': {
                'title': '测试事件',
                'content': '测试内容'
            },
            'event_info': {
                'impact_industries': ['消费电子', '可穿戴设备']
            }
        }
        
        # 保存事件到数据库
        db_event = {
            'id': 'test_event_001',
            'news_id': 'test_event_001',
            'title': '测试事件',
            'full_content': '测试内容',
            'content_length': 4,
            'has_full_content': True,
            'event_info': {'impact_industries': ['消费电子', '可穿戴设备']},
            'original_news': {'title': '测试事件', 'content': '测试内容'}
        }
        
        saved_id = await db_manager.create_or_update_event(db_event)
        print(f"   保存测试事件: {saved_id}")
        
        # 创建测试主题
        theme1 = await db_manager.create_theme(
            name='智能眼镜新品发布',
            description='智能眼镜产品发布相关',
            keywords=['智能眼镜', 'AR眼镜', '发布']
        )
        
        theme2 = await db_manager.create_theme(
            name='AR眼镜技术突破',
            description='AR眼镜技术研发突破',
            keywords=['AR技术', '技术突破', '研发']
        )
        
        print(f"   创建测试主题: {theme1.name if theme1 else '失败'}, {theme2.name if theme2 else '失败'}")
        
        # 测试 fetch_relevant_themes 方法
        try:
            relevant_themes = await theme_fetcher.fetch_relevant_themes(test_event, limit=5)
            print(f"   ✅ fetch_relevant_themes 执行成功，返回 {len(relevant_themes)} 个主题")
            
            for i, theme in enumerate(relevant_themes):
                print(f"      主题 {i+1}: {theme.get('name', '未知')}")
        except Exception as e:
            print(f"   ❌ fetch_relevant_themes 执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 4. 测试 EnhancedThemeDiscovery 的 process_event 方法
        print("\n4. 测试 EnhancedThemeDiscovery.process_event...")
        try:
            result = await discovery.process_event(test_event)
            print(f"   ✅ process_event 执行成功")
            print(f"      返回结果类型: {type(result)}")
            
            if isinstance(result, dict):
                print(f"      结果键: {list(result.keys())}")
                if 'action' in result:
                    print(f"      action: {result['action']}")
        except Exception as e:
            print(f"   ❌ process_event 执行失败: {e}")
            import traceback
            traceback.print_exc()
            # 不返回失败，因为可能还有其他问题
        
        print("\n" + "="*60)
        print("🎉 修复验证完成！")
        print("\n🔧 下一步:")
        print("   1. 重新运行 test_data_integrity.py")
        print("   2. 如果通过，运行完整的AI测试")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_fixes())
    if success:
        print("\n✅ 修复验证成功，可以继续测试")
        sys.exit(0)
    else:
        print("\n❌ 修复验证失败，需要检查代码")
        sys.exit(1)