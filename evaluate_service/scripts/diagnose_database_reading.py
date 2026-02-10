# evaluate_service/scripts/diagnose_database_reading.py
"""
诊断数据库读取问题 - 对比手动测试和自动测试的差异
"""
#!/usr/bin/env python3
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def compare_data_reading():
    """对比两个测试的数据读取方式"""
    print("🔍 对比手动测试与自动测试的数据读取")
    print("="*60)
    
    try:
        # 1. 加载测试数据
        data_path = project_root / "evaluate_service" / "data" / "processed" / "validation_events_fixed.json"
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get('events', data) if isinstance(data, dict) else data
        test_events = [e for e in events if 'AI_AR眼镜' in e.get('news_id', '')][:10]
        
        print(f"📊 加载 {len(test_events)} 个测试事件")
        
        # 2. 初始化数据库（与手动测试相同）
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        print("✅ 数据库初始化完成")
        
        # 3. 先保存事件到数据库
        for i, event in enumerate(test_events):
            event_id = event.get('news_id', f'event_{i}')
            
            db_event = {
                'id': event_id,
                'news_id': event_id,
                'title': event.get('original_news', {}).get('title', ''),
                'full_content': event.get('original_news', {}).get('content', ''),
                'content_length': len(event.get('original_news', {}).get('content', '')),
                'has_full_content': True,
                'event_info': event.get('event_info', {}),
                'original_news': event.get('original_news', {}),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            await db_manager.create_or_update_event(db_event)
        
        print("✅ 事件保存到数据库完成")
        
        # 4. 🔥 关键：创建一些主题，模拟已有主题的情况
        print("\n💾 创建测试主题...")
        test_themes = [
            {
                'name': '智能眼镜新品发布',
                'description': '智能眼镜产品发布相关',
                'keywords': ['智能眼镜', 'AR眼镜', '发布']
            },
            {
                'name': 'AR眼镜技术突破',
                'description': 'AR眼镜技术研发突破',
                'keywords': ['AR技术', '技术突破', '研发']
            }
        ]
        
        for theme in test_themes:
            saved_theme = await db_manager.create_theme(
                name=theme['name'],
                description=theme['description'],
                keywords=theme['keywords']
            )
            print(f"  创建主题: {theme['name']}")
        
        # 5. 验证数据库中的主题
        all_themes = await db_manager.get_all_active_themes(limit=100)
        print(f"📊 数据库主题总数: {len(all_themes)}")
        for theme in all_themes:
            print(f"  - {theme.get('name')} (ID: {theme.get('id', 'N/A')})")
        
        # 6. 🔥 关键对比：两种获取主题的方式
        test_event = test_events[0]
        event_id = test_event.get('news_id', 'test_1')
        
        print(f"\n🔍 测试事件: {event_id}")
        print(f"   标题: {test_event.get('original_news', {}).get('title', '')[:60]}...")
        print(f"   行业: {test_event.get('event_info', {}).get('impact_industries', [])}")
        
        # 方法A：手动测试的方法
        print("\n📋 方法A：手动测试的方法")
        print("-"*40)
        
        from database_service.pure_data_fetcher import PureDataFetcher
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        data_fetcher = PureDataFetcher(db_manager)
        theme_fetcher = RelatedThemeFetcher(data_fetcher)
        
        # 手动测试的调用方式
        relevant_themes = await theme_fetcher.fetch_relevant_themes(test_event)
        print(f"   获取到 {len(relevant_themes)} 个相关主题")
        
        if relevant_themes:
            for i, theme in enumerate(relevant_themes[:5]):
                print(f"   主题 {i+1}: {theme.get('name', '未知')}")
                print(f"      描述: {theme.get('description', '')[:30]}...")
                print(f"      关键词: {theme.get('keywords', [])[:3]}")
        else:
            print("   ⚠️  未获取到主题")
        
        # 方法B：自动测试的方法（通过 EnhancedThemeDiscovery）
        print("\n📋 方法B：自动测试的方法")
        print("-"*40)
        
        from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        
        # 创建AI分析器（简化）
        llm_config = {
            'api_key': 'test-key',  # 不实际调用AI
            'model_name': 'deepseek-chat',
        }
        
        llm_parser = ReliableDeepSeekParser(config=llm_config)
        similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
        
        # 创建主题发现模块
        discovery = EnhancedThemeDiscovery(
            data_fetcher=data_fetcher,
            similarity_analyzer=similarity_analyzer,
            new_theme_threshold=0.3
        )
        
        # 检查 discovery 的主题获取
        if hasattr(discovery, 'related_theme_fetcher'):
            print("✅ EnhancedThemeDiscovery 有 related_theme_fetcher")
            
            try:
                # 通过 discovery 获取主题
                themes_via_discovery = await discovery.related_theme_fetcher.fetch_relevant_themes(test_event)
                print(f"   通过 discovery 获取的主题数: {len(themes_via_discovery)}")
                
                if themes_via_discovery:
                    for i, theme in enumerate(themes_via_discovery[:5]):
                        print(f"   主题 {i+1}: {theme.get('name', '未知')}")
                else:
                    print("   ⚠️  通过 discovery 未获取到主题")
                    
            except Exception as e:
                print(f"   ❌ discovery 获取主题失败: {e}")
        else:
            print("❌ EnhancedThemeDiscovery 没有 related_theme_fetcher")
        
        # 7. 🔥 关键检查：检查相关主题获取器的实现
        print("\n🔍 检查 RelatedThemeFetcher 实现")
        print("-"*40)
        
        fetcher_file = project_root / "theme_service" / "related_theme_fetcher.py"
        if fetcher_file.exists():
            with open(fetcher_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查关键方法
            import re
            fetch_method = re.search(r'async def fetch_relevant_themes.*?(?=async def|def |\Z)', content, re.DOTALL)
            
            if fetch_method:
                method_content = fetch_method.group(0)
                print(f"   fetch_relevant_themes 方法长度: {len(method_content)} 字符")
                
                # 检查关键代码
                if 'get_all_active_themes' in method_content:
                    print("   ✅ 方法中包含 get_all_active_themes 调用")
                else:
                    print("   ⚠️  方法中不包含 get_all_active_themes 调用")
                
                # 检查是否有过滤逻辑
                if 'filter' in method_content or 'industry' in method_content:
                    print("   ✅ 方法中有过滤逻辑")
                else:
                    print("   ⚠️  方法中可能没有过滤逻辑")
            else:
                print("   ❌ 未找到 fetch_relevant_themes 方法")
        
        # 8. 直接检查数据库查询
        print("\n🔍 直接数据库查询验证")
        print("-"*40)
        
        # 获取数据库中的所有主题
        direct_themes = await db_manager.get_all_active_themes(limit=100)
        print(f"   直接查询数据库主题数: {len(direct_themes)}")
        
        # 尝试按照行业筛选
        industries = test_event.get('event_info', {}).get('impact_industries', [])
        print(f"   事件行业: {industries}")
        
        # 检查主题与行业的相关性
        relevant_count = 0
        for theme in direct_themes:
            theme_name = theme.get('name', '').lower()
            theme_desc = theme.get('description', '').lower()
            
            is_relevant = False
            for industry in industries:
                industry_lower = industry.lower()
                if industry_lower in theme_name or industry_lower in theme_desc:
                    is_relevant = True
                    break
            
            if is_relevant:
                relevant_count += 1
        
        print(f"   按行业相关性筛选的主题数: {relevant_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_minimal_test():
    """创建最小测试来复现问题"""
    print("\n\n🧪 创建最小测试复现问题")
    print("="*60)
    
    minimal_code = '''#!/usr/bin/env python3
# evaluate_service/runners/minimal_test.py
"""
最小测试：复现数据库读取问题
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def test_theme_fetching():
    """测试主题获取"""
    from database_service.config import DatabaseConfig
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.pure_data_fetcher import PureDataFetcher
    from theme_service.related_theme_fetcher import RelatedThemeFetcher
    
    # 1. 初始化
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    await db_manager.connect()
    
    # 2. 创建测试主题
    await db_manager.create_theme(
        name="智能眼镜新品发布",
        description="测试主题",
        keywords=[]
    )
    
    # 3. 创建测试事件
    test_event = {
        'news_id': 'test_event_1',
        'original_news': {
            'title': 'Meta智能眼镜发布会',
            'content': 'Meta发布智能眼镜'
        },
        'event_info': {
            'impact_industries': ['消费电子', '可穿戴设备']
        }
    }
    
    # 4. 测试主题获取器
    data_fetcher = PureDataFetcher(db_manager)
    theme_fetcher = RelatedThemeFetcher(data_fetcher)
    
    themes = await theme_fetcher.fetch_relevant_themes(test_event)
    
    print(f"📊 获取到 {len(themes)} 个主题")
    if themes:
        print(f"   主题: {themes[0].get('name', '未知')}")
    else:
        print("   ⚠️  未获取到主题")
    
    return len(themes) > 0

if __name__ == "__main__":
    success = asyncio.run(test_theme_fetching())
    if success:
        print("✅ 测试成功")
    else:
        print("❌ 测试失败")
'''
    
    # 保存最小测试
    test_file = project_root / "evaluate_service" / "runners" / "minimal_test.py"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(minimal_code)
    
    print(f"✅ 最小测试已创建: {test_file}")
    print("\n运行命令:")
    print(f"  python {test_file}")

async def main():
    print("🔍 诊断数据库读取问题")
    print("="*60)
    
    # 运行诊断
    success = await compare_data_reading()
    
    # 创建最小测试
    create_minimal_test()
    
    print("\n💡 下一步:")
    print("1. 运行最小测试: python evaluate_service/runners/minimal_test.py")
    print("2. 查看结果，如果获取不到主题，说明 RelatedThemeFetcher 有问题")
    print("3. 根据诊断结果直接修复代码")

if __name__ == "__main__":
    asyncio.run(main())