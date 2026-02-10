#!/usr/bin/env python3
"""
数据保存完整性验证 - 精简版
直接在集成测试环境下验证数据是否按原始格式保存
"""
import asyncio
import sys
from pathlib import Path
import json
from datetime import datetime

# 项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def test_data_saving_integrity():
    """验证数据保存完整性"""
    print("🔍 数据保存完整性验证")
    print("=" * 80)
    
    try:
        # 1. 初始化内存数据库（使用相同的配置）
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 清空数据库
        if hasattr(db_manager, 'clear_all_data'):
            await db_manager.clear_all_data()
            print("✅ 数据库已清空")
        
        # 2. 使用你集成测试中的 EventPreparer 逻辑
        print("\n📝 测试：模拟集成测试中的事件保存逻辑")
        
        # 创建测试数据（与你的测试数据格式一致）
        test_event = {
            'news_id': 'TEST_AR_001',
            'event_info': {
                'event_type': '产品发布',
                'impact_industries': ['消费电子', 'AR'],
                'direction': '利好'
            },
            'theme_discovery_directive': {
                'action': 'CREATE_NEW',
                'decision_confidence': 0.85,
                'reason': '测试新主题'
            },
            'original_news': {
                'title': 'AR眼镜产品发布会',
                'content': 'Meta与Oakley合作开发的智能眼镜产品于6月20日举行发布会。',
                'content_length': 34,
                'date': '2025年6月20日'
            }
        }
        
        # 3. 按照你的集成测试中的 EventPreparer 逻辑保存事件
        print("\n💾 按照集成测试逻辑保存事件...")
        
        event_id = test_event.get('news_id', 'TEST_AR_001')
        
        # 🔥 关键：这是你的集成测试中的保存逻辑
        db_event = {
            'id': event_id,
            'news_id': event_id,
            'title': test_event.get('original_news', {}).get('title', ''),
            'full_content': test_event.get('original_news', {}).get('content', ''),
            'content_length': len(test_event.get('original_news', {}).get('content', '')),
            'has_full_content': True,
            'event_info': test_event.get('event_info', {}),
            'original_news': test_event.get('original_news', {}),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        print(f"📄 准备保存的事件结构:")
        print(f"  id: {db_event['id']}")
        print(f"  news_id: {db_event['news_id']}")
        print(f"  original_news 类型: {type(db_event['original_news'])}")
        print(f"  original_news 键: {list(db_event['original_news'].keys())}")
        print(f"  original_news.content 长度: {len(db_event['original_news']['content'])}")
        
        # 保存到数据库
        saved_id = await db_manager.create_or_update_event(db_event)
        print(f"✅ 保存结果: {saved_id}")
        
        # 4. 立即验证数据库中的数据
        print("\n🔍 立即验证数据库中的数据完整性...")
        
        retrieved_event = await db_manager.get_event(event_id)
        
        if not retrieved_event:
            print("❌ 错误：无法从数据库获取事件！")
            return False
        
        print(f"✅ 成功从数据库获取事件")
        print(f"  返回类型: {type(retrieved_event)}")
        
        # 检查数据结构
        if isinstance(retrieved_event, dict):
            print(f"  事件包含的键: {list(retrieved_event.keys())}")
            
            # 🔥 关键检查：original_news 字段
            if 'original_news' in retrieved_event:
                original_news = retrieved_event['original_news']
                print(f"  ✅ 存在 original_news 字段")
                print(f"    original_news 类型: {type(original_news)}")
                
                if isinstance(original_news, dict):
                    print(f"    original_news 包含的键: {list(original_news.keys())}")
                    
                    # 🔥 关键检查：content 字段
                    if 'content' in original_news:
                        content = original_news['content']
                        print(f"    ✅ 存在 content 字段")
                        print(f"      内容长度: {len(content)}字符")
                        print(f"      内容预览: {content[:60]}...")
                        
                        # 验证内容是否与原始数据一致
                        original_content = test_event['original_news']['content']
                        if content == original_content:
                            print(f"    ✅ 内容与原始数据完全一致")
                        else:
                            print(f"    ❌ 内容与原始数据不一致！")
                            print(f"      原始: {original_content}")
                            print(f"      保存: {content}")
                            return False
                    else:
                        print(f"    ❌ original_news 中缺少 content 字段！")
                        print(f"      实际字段: {list(original_news.keys())}")
                        return False
                else:
                    print(f"    ❌ original_news 不是字典！类型: {type(original_news)}")
                    print(f"      值: {original_news}")
                    return False
            else:
                print(f"  ❌ 缺少 original_news 字段！")
                print(f"    实际字段: {list(retrieved_event.keys())}")
                return False
        else:
            print(f"  ❌ 返回的不是字典！类型: {type(retrieved_event)}")
            return False
        
        # 5. 测试主题创建逻辑（模拟你的集成测试）
        print("\n🔍 测试主题创建和关联逻辑...")
        
        # 模拟你的 ThemeDiscoverySaver._save_new_theme 逻辑
        theme_name = "AR智能眼镜产品发布"
        theme_desc = "Meta与Oakley合作开发的智能眼镜产品发布会"
        
        print(f"  创建主题: {theme_name}")
        
        # 检查主题是否已存在
        existing_theme = await db_manager.get_theme_by_name(theme_name)
        if existing_theme:
            print(f"  ✅ 主题已存在，跳过创建")
        else:
            # 创建新主题
            saved_theme = await db_manager.create_theme(
                name=theme_name,
                description=theme_desc,
                keywords=["AR", "智能眼镜"],
                discovery_source='test_integrity',
                discovery_confidence=0.8
            )
            
            if saved_theme:
                print(f"  ✅ 主题创建成功")
                
                # 获取主题ID
                theme_id = None
                if hasattr(saved_theme, 'id'):
                    theme_id = saved_theme.id
                elif isinstance(saved_theme, dict):
                    theme_id = saved_theme.get('id')
                
                if theme_id:
                    print(f"    主题ID: {theme_id}")
                    
                    # 创建事件-主题关联（模拟你的集成测试）
                    print(f"  创建事件-主题关联...")
                    
                    relation = await db_manager.create_event_theme_relation(
                        event_id=event_id,
                        theme_id=theme_id,
                        confidence=0.9,
                        confidence_level='high'
                    )
                    
                    if relation:
                        print(f"  ✅ 事件-主题关联创建成功")
                        
                        # 验证关联
                        theme = await db_manager.get_theme(theme_id)
                        if theme:
                            # 检查相关事件
                            if hasattr(theme, 'related_events'):
                                related_events = theme.related_events
                                if event_id in related_events:
                                    print(f"    ✅ 事件 {event_id} 在主题关联列表中")
                                else:
                                    print(f"    ❌ 事件 {event_id} 不在主题关联列表中")
                                    return False
                            else:
                                print(f"    ⚠️  主题没有 related_events 属性")
                else:
                    print(f"  ❌ 无法获取主题ID")
                    return False
            else:
                print(f"  ❌ 主题创建失败")
                return False
        
        # 6. 模拟 RelatedThemeFetcher 获取主题数据
        print("\n🔍 模拟 RelatedThemeFetcher 获取主题数据...")
        
        # 获取所有活动主题
        all_themes = await db_manager.get_all_active_themes(limit=100)
        print(f"  数据库返回主题数: {len(all_themes)}")
        
        if all_themes:
            # 检查第一个主题的结构
            first_theme = all_themes[0]
            print(f"  第一个主题结构:")
            
            # 检查主题是对象还是字典
            if isinstance(first_theme, dict):
                print(f"    类型: 字典")
                print(f"    包含的键: {list(first_theme.keys())}")
                
                # 检查关键字段
                for key in ['id', 'name', 'related_events']:
                    if key in first_theme:
                        value = first_theme[key]
                        if key == 'related_events':
                            print(f"    {key}: {len(value)} 个事件" if isinstance(value, list) else f"    {key}: {value}")
                        else:
                            print(f"    {key}: {value}")
                    else:
                        print(f"    ❌ 缺少 {key} 字段")
            else:
                # 可能是 ThemeRecord 对象
                print(f"    类型: {type(first_theme)}")
                print(f"    属性列表: {dir(first_theme)}")
                
                # 尝试获取关键属性
                for attr in ['id', 'name', 'related_events']:
                    if hasattr(first_theme, attr):
                        value = getattr(first_theme, attr)
                        if attr == 'related_events':
                            print(f"    {attr}: {len(value)} 个事件" if isinstance(value, list) else f"    {attr}: {value}")
                        else:
                            print(f"    {attr}: {value}")
                    else:
                        print(f"    ⚠️  没有 {attr} 属性")
            
            # 获取主题的关联事件内容
            print(f"\n  获取主题关联事件的完整内容...")
            
            # 假设主题有 related_events 属性
            if isinstance(first_theme, dict):
                related_events = first_theme.get('related_events', [])
            else:
                related_events = getattr(first_theme, 'related_events', [])
            
            print(f"    关联事件数: {len(related_events)}")
            
            # 获取每个事件的完整内容
            for i, event_id in enumerate(related_events[:2]):  # 只检查前2个
                event_data = await db_manager.get_event(event_id)
                if event_data:
                    content = event_data.get('original_news', {}).get('content', '')
                    if content:
                        print(f"    事件 {i+1}: {event_id}")
                        print(f"      内容长度: {len(content)}字符")
                        print(f"      内容预览: {content[:60]}...")
                    else:
                        print(f"    ⚠️  事件 {event_id} 没有内容！")
                        
                        # 检查事件数据完整结构
                        print(f"      事件数据键: {list(event_data.keys())}")
                        if 'original_news' in event_data:
                            print(f"      original_news 键: {list(event_data['original_news'].keys())}")
                else:
                    print(f"    ❌ 无法获取事件 {event_id}")
        
        # 7. 验证 EnhancedThemeDiscovery 可能遇到的问题
        print("\n🔍 模拟 EnhancedThemeDiscovery 内部逻辑...")
        
        # 创建测试数据获取器
        from database_service.pure_data_fetcher import PureDataFetcher
        data_fetcher = PureDataFetcher(db_manager)
        
        # 模拟 fetch_themes_with_complete_news_content 逻辑
        print(f"  模拟 fetch_themes_with_complete_news_content 逻辑")
        
        # 获取所有主题
        all_themes = await db_manager.get_all_active_themes(limit=100)
        themes_with_content = []
        
        for theme in all_themes:
            # 获取主题ID
            if isinstance(theme, dict):
                theme_id = theme.get('id')
                theme_name = theme.get('name', '')
            else:
                theme_id = getattr(theme, 'id', None)
                theme_name = getattr(theme, 'name', '')
            
            # 获取关联事件
            if isinstance(theme, dict):
                related_events = theme.get('related_events', [])
            else:
                related_events = getattr(theme, 'related_events', [])
            
            # 获取每个事件的完整内容
            related_news_full_contents = []
            for event_id in related_events[:2]:  # 只取前2个事件
                event_data = await db_manager.get_event(event_id)
                if event_data and 'original_news' in event_data:
                    original_news = event_data['original_news']
                    if 'content' in original_news and original_news['content']:
                        related_news_full_contents.append({
                            'title': original_news.get('title', ''),
                            'content': original_news['content'],
                            'content_length': len(original_news['content']),
                            'date': original_news.get('date', ''),
                            'event_id': event_id
                        })
            
            # 判断是否有完整内容
            has_complete_content = len(related_news_full_contents) > 0
            
            print(f"    主题: {theme_name}")
            print(f"      关联事件数: {len(related_events)}")
            print(f"      有完整内容的新闻数: {len(related_news_full_contents)}")
            print(f"      has_complete_content: {has_complete_content}")
            
            # 🔥 关键问题点：如果 has_complete_content 为 False，主题会被过滤掉
            if not has_complete_content:
                print(f"      ⚠️  警告：此主题将被过滤，不会传递给AI分析！")
            
            if has_complete_content:
                themes_with_content.append(theme)
        
        print(f"\n📊 主题过滤结果:")
        print(f"  总主题数: {len(all_themes)}")
        print(f"  有完整内容的主题数: {len(themes_with_content)}")
        print(f"  将被过滤的主题数: {len(all_themes) - len(themes_with_content)}")
        
        if len(themes_with_content) < len(all_themes):
            print("\n🔥 发现问题：部分主题将被过滤，导致AI只能分析部分主题！")
            print("💡 建议：检查事件保存时 original_news.content 字段是否正确保存")
        
        await db_manager.disconnect()
        
        print("\n" + "=" * 80)
        print("✅ 数据保存完整性验证完成")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 验证过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

async def check_integration_test_logic():
    """检查集成测试的逻辑问题"""
    print("\n🔍 检查集成测试逻辑问题")
    print("=" * 80)
    
    # 分析你的集成测试中可能导致问题的代码
    print("\n📋 可能的问题点分析:")
    print("1. 事件保存时 original_news 结构可能被破坏")
    print("2. RelatedThemeFetcher.fetch_themes_with_complete_news_content 过滤了没有完整内容的主题")
    print("3. 主题关联事件的内容可能没有被正确保存")
    
    # 读取你的集成测试代码，查找问题
    test_file = project_root / "evaluate_service" / "integrated_evaluator.py"
    if test_file.exists():
        print(f"\n📄 分析集成测试文件: {test_file}")
        
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找关键代码段
        keywords = {
            'original_news': '检查 original_news 字段的处理',
            'fetch_themes_with_complete_news_content': '主题过滤逻辑',
            'has_complete_content': '内容完整性检查',
            'related_news_full_contents': '关联新闻内容'
        }
        
        for keyword, description in keywords.items():
            if keyword in content:
                print(f"  ✅ 找到相关代码: {description}")
    
    print("\n💡 建议的修复:")
    print("1. 在 EventPreparer 中，确保 original_news 按原始格式保存")
    print("2. 修改 fetch_themes_with_complete_news_content，不要过滤没有完整内容的主题")
    print("3. 或者在保存事件时，确保所有事件都有完整的 content 字段")

async def main():
    """主函数"""
    print("开始验证数据保存完整性")
    print("=" * 80)
    
    # 运行数据保存完整性测试
    success = await test_data_saving_integrity()
    
    if success:
        # 检查集成测试逻辑问题
        await check_integration_test_logic()
        
        print("\n" + "=" * 80)
        print("🎯 验证总结")
        print("=" * 80)
        print("1. ✅ 事件数据可以按原始格式保存")
        print("2. ⚠️  主题过滤逻辑可能导致AI只分析部分主题")
        print("3. 🔧 建议修复主题获取逻辑，不要过滤没有完整内容的主题")
        print("\n📁 在集成测试中添加以下检查:")
        print("   - 验证每个事件保存后 original_news.content 字段")
        print("   - 检查主题关联事件的内容完整性")
        print("   - 修改 fetch_themes_with_complete_news_content 的过滤逻辑")
    else:
        print("\n❌ 数据保存完整性验证失败！")
        print("请检查内存数据库的实现和事件保存逻辑。")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))