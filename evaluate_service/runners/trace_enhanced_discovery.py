#!/usr/bin/env python3
"""
精确追踪：EnhancedThemeDiscovery内部数据截断问题
"""
import asyncio
import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def trace_enhanced_discovery_internal():
    """追踪EnhancedThemeDiscovery内部数据流"""
    print("🔍 追踪EnhancedThemeDiscovery内部数据截断问题")
    print("=" * 80)
    
    try:
        # 1. 创建带追踪的EnhancedThemeDiscovery
        from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
        
        class TracedEnhancedDiscovery(EnhancedThemeDiscovery):
            """带追踪的EnhancedThemeDiscovery"""
            
            async def process_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
                print("\n" + "=" * 80)
                print("🔍 EnhancedThemeDiscovery.process_event() 开始执行")
                print("=" * 80)
                
                # 记录传入的事件数据
                event_id = event_data.get('news_id', 'unknown')
                original_content = event_data.get('original_news', {}).get('content', '')
                print(f"📥 传入的事件数据:")
                print(f"  事件ID: {event_id}")
                print(f"  内容长度: {len(original_content)}字符")
                print(f"  内容预览: {original_content[:80]}...")
                
                # 调用父类方法
                result = await super().process_event(event_data)
                return result
            
            async def _fetch_existing_themes(self, event_data: Dict[str, Any]) -> List[Dict[str, Any]]:
                print("\n🔍 EnhancedThemeDiscovery._fetch_existing_themes() 被调用")
                themes = await super()._fetch_existing_themes(event_data)
                
                print(f"📊 获取到 {len(themes)} 个主题")
                
                # 检查主题内容
                if themes:
                    first_theme = themes[0]
                    print(f"  第一个主题字段: {list(first_theme.keys())}")
                    
                    # 检查是否有完整内容
                    if 'related_news_full_contents' in first_theme:
                        related_news = first_theme['related_news_full_contents']
                        print(f"  关联新闻数: {len(related_news)}")
                        
                        for i, news in enumerate(related_news[:2]):
                            content = news.get('content', '')
                            print(f"    新闻{i+1}内容长度: {len(content)}字符")
                            if content:
                                print(f"      预览: {content[:60]}...")
                
                return themes
        
        # 2. 创建带追踪的AI分析器
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        
        class TracedAIAnalyzer(AIThemeSimilarityAnalyzer):
            """带追踪的AI分析器"""
            
            async def analyze_with_theme_extraction(self, event: Dict[str, Any], themes: List[Dict[str, Any]]) -> Dict[str, Any]:
                print("\n" + "=" * 80)
                print("🔍 AIThemeSimilarityAnalyzer.analyze_with_theme_extraction() 被调用")
                print("=" * 80)
                
                # 记录传入的事件数据
                print(f"📥 AI分析器接收的事件数据:")
                event_content = event.get('original_news', {}).get('content', '')
                print(f"  事件内容长度: {len(event_content)}字符")
                print(f"  事件内容预览: {event_content[:80]}...")
                
                # 记录传入的主题数据
                print(f"\n📥 AI分析器接收的主题数据:")
                print(f"  主题数量: {len(themes)}")
                
                if themes:
                    first_theme = themes[0]
                    print(f"  第一个主题名称: {first_theme.get('name', '未知')}")
                    
                    # 检查主题中的内容
                    total_content_length = 0
                    if 'related_news_full_contents' in first_theme:
                        related_news = first_theme['related_news_full_contents']
                        for i, news in enumerate(related_news):
                            content = news.get('content', '')
                            if content:
                                total_content_length += len(content)
                                if i < 2:  # 只显示前2个
                                    print(f"    关联新闻{i+1}: {len(content)}字符")
                    
                    print(f"  主题关联内容总长度: {total_content_length}字符")
                
                # 构建提示词并分析
                print("\n🔍 构建提示词...")
                prompt = self._build_enhanced_prompt(event, themes)
                
                # 分析提示词内容
                print(f"📊 提示词分析:")
                print(f"  提示词总长度: {len(prompt)}字符")
                
                # 检查是否包含完整内容
                if "完整内容" in prompt:
                    print("  ✅ 提示词包含'完整内容'标记")
                else:
                    print("  ❌ 提示词缺少'完整内容'标记")
                
                # 检查事件内容是否在提示词中
                if event_content and event_content in prompt:
                    print(f"  ✅ 事件完整内容在提示词中")
                elif event_content and len(event_content) > 50:
                    # 检查是否至少有部分内容
                    if event_content[:50] in prompt:
                        print(f"  ⚠️  事件内容部分在提示词中")
                    else:
                        print(f"  ❌ 事件内容不在提示词中！")
                
                # 调用父类方法（模拟）
                print("\n⚠️  注意：这只是追踪，不会实际调用AI API")
                return {
                    'metadata': {'status': 'traced_only'}
                }
        
        # 3. 创建带追踪的主题获取器
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        class TracedThemeFetcher(RelatedThemeFetcher):
            """带追踪的主题获取器"""
            
            async def fetch_themes_with_complete_news_content(self, event: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
                print("\n🔍 RelatedThemeFetcher.fetch_themes_with_complete_news_content() 被调用")
                
                # 记录传入的事件数据
                print(f"📥 传入事件内容长度: {len(event.get('original_news', {}).get('content', ''))}字符")
                
                # 调用父类方法
                themes = await super().fetch_themes_with_complete_news_content(event, limit)
                
                print(f"📊 返回 {len(themes)} 个主题")
                
                # 详细检查返回的数据
                if themes:
                    for i, theme in enumerate(themes[:2]):  # 只检查前2个
                        print(f"\n  主题{i+1}分析:")
                        print(f"    主题名称: {theme.get('name', '未知')}")
                        
                        # 检查关键字段
                        if 'has_complete_content' in theme:
                            print(f"    has_complete_content: {theme['has_complete_content']}")
                        
                        if 'related_news_full_contents' in theme:
                            related_news = theme['related_news_full_contents']
                            print(f"    related_news_full_contents: {len(related_news)}个新闻")
                            
                            # 检查每个新闻的内容
                            for j, news in enumerate(related_news[:2]):
                                content = news.get('content', '')
                                print(f"      新闻{j+1}:")
                                print(f"        内容长度: {len(content)}字符")
                                print(f"        标题: {news.get('title', '无标题')}")
                                
                                if content:
                                    print(f"        内容预览: {content[:60]}...")
                        else:
                            print(f"    ❌ 缺少related_news_full_contents字段！")
                            print(f"    可用字段: {list(theme.keys())}")
                
                return themes
        
        # 4. 准备测试环境
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.config import DatabaseConfig
        from database_service.pure_data_fetcher import PureDataFetcher
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 清空数据库
        if hasattr(db_manager, 'clear_all_data'):
            await db_manager.clear_all_data()
        
        # 5. 创建测试数据
        test_event = {
            'news_id': 'TRACE_TEST_001',
            'event_info': {
                'event_type': '产品发布',
                'impact_industries': ['消费电子', 'AR']
            },
            'original_news': {
                'title': '追踪测试AR眼镜事件',
                'content': '这是一个用于追踪EnhancedThemeDiscovery内部数据流的测试事件内容。内容应该被完整传递，不应该被截断。完整的分析需要足够的上下文信息。',
                'date': '2025-01-15'
            }
        }
        
        # 6. 保存一个事件到数据库（模拟已有主题）
        db_event = {
            'id': test_event['news_id'],
            'news_id': test_event['news_id'],
            'title': test_event['original_news']['title'],
            'full_content': test_event['original_news']['content'],
            'content_length': len(test_event['original_news']['content']),
            'has_full_content': True,
            'original_news': test_event['original_news'],
            'event_info': test_event['event_info']
        }
        
        saved_id = await db_manager.create_or_update_event(db_event)
        
        # 创建主题并关联
        theme_record = await db_manager.create_theme(
            name="追踪测试主题",
            description="用于追踪数据流的测试主题",
            keywords=["追踪", "测试", "AR"]
        )
        
        await db_manager.create_event_theme_relation(
            event_id=saved_id,
            theme_id=theme_record.id,
            confidence=0.9,
            confidence_level="high"
        )
        
        print(f"✅ 创建测试环境完成")
        print(f"  事件: {saved_id}")
        print(f"  主题: {theme_record.name}")
        
        # 7. 创建带追踪的组件
        data_fetcher = PureDataFetcher(db_manager)
        
        # 使用带追踪的主题获取器
        traced_theme_fetcher = TracedThemeFetcher(data_fetcher)
        
        # 创建AI分析器
        llm_parser = ReliableDeepSeekParser(config={'max_retries': 1, 'timeout': 10})
        traced_analyzer = TracedAIAnalyzer(llm_parser)
        
        # 创建EnhancedThemeDiscovery，注入追踪组件
        enhanced_discovery = TracedEnhancedDiscovery(
            data_fetcher=data_fetcher,
            similarity_analyzer=traced_analyzer,
            new_theme_threshold=0.3
        )
        
        # 🔥 关键：替换内部的主题获取器
        enhanced_discovery.related_theme_fetcher = traced_theme_fetcher
        
        # 8. 运行测试
        print("\n" + "=" * 80)
        print("🚀 开始执行EnhancedThemeDiscovery.process_event()")
        print("=" * 80)
        
        try:
            result = await enhanced_discovery.process_event(test_event)
            print(f"\n✅ EnhancedThemeDiscovery处理完成")
            print(f"  结果: {result.get('action', 'UNKNOWN')}")
        except Exception as e:
            print(f"\n⚠️  处理过程中出现错误（预期中）: {e}")
        
        await db_manager.disconnect()
        
        print("\n" + "=" * 80)
        print("📋 追踪总结")
        print("=" * 80)
        
        # 分析可能的问题点
        print("\n🎯 可能的问题点检查:")
        print("1. ✅ fetch_themes_with_complete_news_content 被正确调用")
        print("2. 🔍 检查该方法返回的数据结构")
        print("3. 🔍 检查数据从主题获取器传递到AI分析器的过程")
        print("4. 🔍 检查AI提示词构建时是否使用了完整内容")
        
    except Exception as e:
        print(f"❌ 追踪失败: {e}")
        import traceback
        traceback.print_exc()

async def inspect_enhanced_discovery_code():
    """检查EnhancedThemeDiscovery的源代码"""
    print("\n" + "=" * 80)
    print("🔍 检查EnhancedThemeDiscovery源代码")
    print("=" * 80)
    
    try:
        import inspect
        from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
        
        # 检查关键方法
        methods_to_check = ['process_event', '_fetch_existing_themes', '_handle_create_new', '_handle_cluster']
        
        for method_name in methods_to_check:
            if hasattr(EnhancedThemeDiscovery, method_name):
                print(f"\n📜 {method_name}() 方法:")
                print("-" * 40)
                
                try:
                    method = getattr(EnhancedThemeDiscovery, method_name)
                    source = inspect.getsource(method)
                    
                    # 查找关键代码段
                    lines = source.split('\n')
                    
                    # 查找与内容处理相关的代码
                    content_keywords = ['content', 'original_news', 'full_content', 'related_news']
                    found_lines = []
                    
                    for i, line in enumerate(lines):
                        if any(keyword in line.lower() for keyword in content_keywords):
                            # 显示上下文
                            start = max(0, i-1)
                            end = min(len(lines), i+2)
                            context = '\n'.join(lines[start:end])
                            if context not in found_lines:
                                found_lines.append(context)
                    
                    # 显示找到的关键代码
                    for context in found_lines[:5]:  # 最多显示5个
                        print(context)
                        print("-" * 40)
                        
                except Exception as e:
                    print(f"  无法获取源码: {e}")
            else:
                print(f"❌ 没有找到 {method_name} 方法")
    
    except Exception as e:
        print(f"❌ 检查源代码失败: {e}")

async def main():
    """主函数"""
    print("开始追踪EnhancedThemeDiscovery内部数据截断问题")
    
    # 追踪内部数据流
    await trace_enhanced_discovery_internal()
    
    # 检查源代码
    await inspect_enhanced_discovery_code()

if __name__ == "__main__":
    from typing import Dict, Any, List
    asyncio.run(main())