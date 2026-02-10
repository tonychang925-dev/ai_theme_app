# evaluate_service/scripts/debug_ai_data_reception.py
"""
调试AI分析器接收的数据
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

async def debug_ai_data_reception():
    """调试AI分析器接收的数据"""
    print("🔍 调试：AI分析器接收的主题数据")
    print("="*60)
    
    try:
        # 1. 初始化数据库
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        print("✅ 数据库初始化完成")
        
        # 2. 创建测试主题
        print("\n💾 创建测试主题...")
        test_theme = await db_manager.create_theme(
            name="智能眼镜新品发布",
            description="智能眼镜产品发布相关，包括Meta、Apple等公司的新品发布",
            keywords=['智能眼镜', 'AR眼镜', '发布', '消费电子']
        )
        print(f"   创建主题: 智能眼镜新品发布 (ID: {test_theme.id if hasattr(test_theme, 'id') else 'N/A'})")
        
        # 3. 创建测试事件
        test_event = {
            'news_id': 'test_event_1',
            'original_news': {
                'title': 'Meta智能眼镜发布会',
                'content': 'Meta公司举行智能眼镜新品发布会'
            },
            'event_info': {
                'impact_industries': ['消费电子', '可穿戴设备']
            }
        }
        
        # 4. 获取主题数据
        print("\n📊 获取主题数据...")
        
        # 方法A：通过 data_fetcher
        data_fetcher = PureDataFetcher(db_manager)
        themes_via_fetcher = await data_fetcher.get_all_active_themes()
        print(f"   通过data_fetcher获取的主题数: {len(themes_via_fetcher)}")
        
        # 方法B：通过 theme_fetcher
        theme_fetcher = RelatedThemeFetcher(data_fetcher)
        themes_via_theme_fetcher = await theme_fetcher.fetch_relevant_themes(test_event)
        print(f"   通过theme_fetcher获取的主题数: {len(themes_via_theme_fetcher)}")
        
        # 5. 🔥 关键：检查主题数据的完整性
        print("\n🔍 检查主题数据完整性:")
        print("-"*40)
        
        for i, themes_list in enumerate([themes_via_fetcher, themes_via_theme_fetcher]):
            method_name = "data_fetcher" if i == 0 else "theme_fetcher"
            print(f"\n   方法: {method_name}")
            
            if themes_list:
                theme = themes_list[0]
                print(f"   主题数据结构:")
                print(f"      类型: {type(theme)}")
                print(f"      键: {list(theme.keys())}")
                
                # 检查关键字段
                required_fields = ['name', 'description', 'keywords', 'id']
                missing_fields = []
                
                for field in required_fields:
                    if field not in theme:
                        missing_fields.append(field)
                    else:
                        value = theme[field]
                        value_type = type(value).__name__
                        value_preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                        print(f"      {field}: {value_preview} (类型: {value_type})")
                
                if missing_fields:
                    print(f"      ⚠️  缺少字段: {missing_fields}")
                else:
                    print(f"      ✅ 所有必需字段都存在")
                
                # 检查字段内容
                if 'description' in theme and not theme['description']:
                    print(f"      ⚠️  描述为空")
                if 'keywords' in theme and not theme['keywords']:
                    print(f"      ⚠️  关键词列表为空")
                    
            else:
                print(f"    ⚠️  没有获取到主题")
        
        # 6. 模拟AI分析器接收的数据
        print("\n🔍 模拟AI分析器接收的数据:")
        print("-"*40)
        
        # 创建AI分析器（不实际调用API）
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        
        llm_config = {
            'api_key': 'test-key',
            'model_name': 'deepseek-chat'
        }
        
        llm_parser = ReliableDeepSeekParser(config=llm_config)
        analyzer = AIThemeSimilarityAnalyzer(llm_parser)
        
        # 检查主题数据格式是否符合AI分析器的期望
        print("   检查主题数据格式...")
        
        # 获取主题数据的实际格式
        if themes_via_theme_fetcher:
            sample_theme = themes_via_theme_fetcher[0]
            
            # 检查是否符合AI分析器期望的格式
            print(f"   主题名: {sample_theme.get('name', 'N/A')}")
            print(f"   描述长度: {len(sample_theme.get('description', ''))}")
            print(f"   关键词数: {len(sample_theme.get('keywords', []))}")
            print(f"   是否有ID: {'id' in sample_theme}")
            
            # 检查是否是字典类型
            if isinstance(sample_theme, dict):
                print("   ✅ 主题是字典类型")
            else:
                print(f"   ⚠️  主题类型: {type(sample_theme)}")
        
        # 7. 检查数据库查询的原始SQL/方法
        print("\n🔍 检查数据库查询方法:")
        print("-"*40)
        
        # 查看 memory_manager 的 get_all_active_themes 实现
        import inspect
        try:
            source = inspect.getsource(db_manager.get_all_active_themes)
            print("   get_all_active_themes 方法源码:")
            print("   " + "   ".join(source.split('\n')[:5]))
        except:
            print("   无法获取方法源码")
        
        return True
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_enhanced_theme_fetching():
    """测试增强主题获取"""
    print("\n\n🧪 测试增强主题获取")
    print("="*60)
    
    try:
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        print("✅ 数据库初始化完成")
        
        # 创建测试主题
        await db_manager.create_theme(
            name="智能眼镜测试主题",
            description="测试主题描述",
            keywords=['测试']
        )
        
        # 测试增强获取
        data_fetcher = PureDataFetcher(db_manager)
        
        print("\n📊 测试不同获取方法:")
        
        # 方法1: get_all_active_themes
        themes_basic = await data_fetcher.get_all_active_themes()
        print(f"   1. get_all_active_themes: {len(themes_basic)} 个主题")
        
        # 方法2: get_all_active_themes_with_context
        if hasattr(data_fetcher, 'get_all_active_themes_with_context'):
            themes_enhanced = await data_fetcher.get_all_active_themes_with_context()
            print(f"   2. get_all_active_themes_with_context: {len(themes_enhanced)} 个主题")
            
            if themes_enhanced:
                theme = themes_enhanced[0]
                print(f"      增强主题字段: {list(theme.keys())}")
                print(f"      has_full_context: {theme.get('has_full_context', 'N/A')}")
        else:
            print("   2. get_all_active_themes_with_context: 方法不存在")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

async def main():
    print("🔍 调试AI数据接收问题")
    print("="*60)
    
    # 运行调试
    success1 = await debug_ai_data_reception()
    
    # 测试增强获取
    success2 = await test_enhanced_theme_fetching()
    
    print("\n💡 分析结果:")
    if success1 and success2:
        print("   数据获取正常，问题可能在AI分析逻辑")
    else:
        print("   数据获取有问题，需要修复数据库查询")

if __name__ == "__main__":
    asyncio.run(main())