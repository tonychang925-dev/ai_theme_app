#!/usr/bin/env python3
"""
通用测试脚本 - 解决所有导入问题
"""
import os
import sys

# 设置Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"项目根目录: {current_dir}")
print(f"Python路径已设置")

async def test_all():
    """测试所有组件"""
    print("\n🧪 测试所有组件...")
    
    # 检查环境
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("⚠️  DEEPSEEK_API_KEY未设置")
        print("请设置: export DEEPSEEK_API_KEY='your-api-key'")
        return False
    
    try:
        # 1. 测试数据库
        print("\n1. 测试数据库...")
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.client import DatabaseClient
        from database_service.pure_data_fetcher import PureDataFetcher
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        db_client = DatabaseClient(db_manager)
        
        # 添加测试数据
        await db_manager.create_theme(
            name="人工智能",
            keywords=["AI", "机器学习"],
            description="人工智能技术"
        )
        
        stats = await db_manager.get_stats()
        print(f"✅ 数据库测试成功，主题数: {stats['total_themes']}")
        
        # 2. 测试AI解析器
        print("\n2. 测试AI解析器...")
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        
        ai_parser = ReliableDeepSeekParser(config={'timeout': 30})
        health = await ai_parser.health_check()
        print(f"✅ AI解析器健康: {health['is_healthy']}")
        
        # 3. 测试AI相似性分析器
        print("\n3. 测试AI相似性分析器...")
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        
        similarity_analyzer = AIThemeSimilarityAnalyzer(ai_parser)
        
        test_event = {
            "id": "test_all_001",
            "title": "AI芯片技术突破",
            "impact_industries": ["人工智能"]
        }
        
        test_themes = [
            {"name": "人工智能", "description": "AI技术", "keywords": ["AI"]}
        ]
        
        result = await similarity_analyzer.analyze_similarity(test_event, test_themes)
        print(f"✅ 相似性分析成功，最相似: {result.get('most_similar_theme', {}).get('theme_name', '无')}")
        
        # 4. 测试主题检索器
        print("\n4. 测试主题检索器...")
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        data_fetcher = PureDataFetcher(db_manager)
        fetcher = RelatedThemeFetcher(data_fetcher, similarity_analyzer)
        
        themes = await fetcher.fetch_related_themes(test_event, limit=2)
        print(f"✅ 主题检索成功，找到 {len(themes)} 个相关主题")
        
        # 5. 测试AI客户端
        print("\n5. 测试AI客户端...")
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        
        ai_client = EnhancedAIThemeClient()
        health = await ai_client._check_ai_health()
        print(f"✅ AI客户端健康: {health.get('status', 'unknown')}")
        
        # 6. 测试主题发现引擎
        print("\n6. 测试主题发现引擎...")
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            database_client=db_client,
            similarity_analyzer=similarity_analyzer
        )
        
        print(f"✅ 引擎初始化成功: {engine.get_engine_info()['engine_version']}")
        
        # 清理资源
        await ai_parser.close()
        await db_manager.disconnect()
        
        print("\n🎉 所有组件测试成功！")
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("当前Python路径:")
        for path in sys.path[:5]:
            print(f"  {path}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("="*70)
    print("金融投资AI助理 - 组件集成测试")
    print("="*70)
    
    success = await test_all()
    
    print("\n" + "="*70)
    if success:
        print("🎉 所有组件集成测试通过！")
        print("新架构已就绪，可以运行完整测试。")
    else:
        print("❌ 组件集成测试失败")
        print("请检查错误信息")
    print("="*70)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
