"""
集成测试脚本 - 验证新架构
"""
import asyncio
import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

async def test_ai_similarity_analyzer():
    """测试AI相似性分析器"""
    print("\n" + "="*60)
    print("测试AI相似性分析器")
    print("="*60)
    
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("跳过真实测试（无API密钥）")
        return True
    
    try:
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        
        parser = ReliableDeepSeekParser(config={'timeout': 60})
        analyzer = AIThemeSimilarityAnalyzer(parser)
        
        test_event = {
            "id": "test_integ_001",
            "title": "微软发布AI芯片",
            "summary": "微软发布自研AI芯片，性能提升显著",
            "event_type": "技术突破",
            "impact_industries": ["人工智能", "半导体"]
        }
        
        test_themes = [
            {"name": "人工智能芯片", "description": "AI专用芯片", "keywords": ["AI", "芯片"], "event_count": 20},
            {"name": "云计算", "description": "云服务技术", "keywords": ["云", "服务器"], "event_count": 30}
        ]
        
        print("分析相似性...")
        result = await analyzer.analyze_similarity(test_event, test_themes)
        
        if result.get('is_fallback_result'):
            print(f"❌ 分析失败: {result.get('error')}")
            return False
        
        print(f"✅ 分析成功!")
        print(f"  最相似: {result.get('most_similar_theme', {}).get('theme_name', '无')}")
        print(f"  相似度: {result.get('most_similar_theme', {}).get('similarity_score', 0):.2f}")
        
        await parser.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

async def test_related_theme_fetcher():
    """测试新的RelatedThemeFetcher"""
    print("\n" + "="*60)
    print("测试新的RelatedThemeFetcher")
    print("="*60)
    
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("跳过真实测试（无API密钥）")
        return True
    
    try:
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        # 初始化数据库
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 添加测试数据
        await db_manager.create_theme(name="AI芯片", keywords=["AI", "芯片"], description="AI芯片技术")
        await db_manager.create_theme(name="新能源汽车", keywords=["新能源", "汽车"], description="新能源汽车")
        
        # 创建fetcher
        data_fetcher = PureDataFetcher(db_manager)
        ai_parser = ReliableDeepSeekParser(config={'timeout': 60})
        similarity_analyzer = AIThemeSimilarityAnalyzer(ai_parser)
        fetcher = RelatedThemeFetcher(data_fetcher, similarity_analyzer)
        
        # 测试
        event = {
            "id": "test_fetcher_001",
            "title": "英伟达发布新一代AI芯片",
            "summary": "英伟达发布性能更强的AI芯片",
            "event_type": "产品发布",
            "impact_industries": ["人工智能", "半导体"]
        }
        
        print("检索相关主题...")
        themes = await fetcher.fetch_related_themes(event, limit=2)
        
        print(f"✅ 检索到 {len(themes)} 个相关主题")
        for i, theme in enumerate(themes, 1):
            print(f"  {i}. {theme.get('name')}")
        
        # 清理
        await ai_parser.close()
        await db_manager.disconnect()
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_enhanced_ai_client():
    """测试增强的AI客户端"""
    print("\n" + "="*60)
    print("测试增强的AI客户端")
    print("="*60)
    
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("跳过真实测试（无API密钥）")
        return True
    
    try:
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        
        client = EnhancedAIThemeClient()
        
        # 健康检查
        health = await client._check_ai_health()
        print(f"AI健康状态: {health.get('status', 'unknown')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("="*70)
    print("新架构集成测试")
    print("="*70)
    
    # 检查环境
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("⚠️  注意: DEEPSEEK_API_KEY环境变量未设置")
        print("部分测试将跳过真实API调用")
    
    # 运行测试
    tests = [
        ("AI相似性分析器", test_ai_similarity_analyzer),
        ("相关主题检索器", test_related_theme_fetcher),
        ("增强AI客户端", test_enhanced_ai_client),
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n🔧 运行测试: {test_name}")
        try:
            success = await test_func()
            results[test_name] = success
            status = "✅ 通过" if success else "❌ 失败"
            print(f"   结果: {status}")
        except Exception as e:
            results[test_name] = False
            print(f"   结果: ❌ 异常: {e}")
    
    # 总结
    print("\n" + "="*70)
    print("测试总结:")
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {test_name}")
    
    print(f"\n📊 通过率: {passed}/{total} ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！新架构验证成功！")
    else:
        print(f"\n⚠️  部分测试失败，请检查问题")
    
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
