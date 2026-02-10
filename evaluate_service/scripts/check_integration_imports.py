#!/usr/bin/env python3
"""
集成测试前的模块导入验证
确保所有必要组件都能正确导入
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_module_imports():
    """检查所有必要的模块导入"""
    print("🔍 检查模块导入...")
    
    checks = [
        {
            "name": "数据库管理器",
            "import_path": "database_service.memory_manager.MemoryDatabaseManager",
            "required": True
        },
        {
            "name": "配置管理",
            "import_path": "database_service.config.DatabaseConfig", 
            "required": True
        },
        {
            "name": "PureDataFetcher",
            "import_path": "database_service.pure_data_fetcher.PureDataFetcher",
            "required": True
        },
        {
            "name": "数据库客户端",
            "import_path": "database_service.client.DatabaseClient",
            "required": False  # 可能不存在
        },
        {
            "name": "RelatedThemeFetcher",
            "import_path": "theme_service.related_theme_fetcher.RelatedThemeFetcher",
            "required": True
        },
        {
            "name": "AI客户端",
            "import_path": "theme_service.enhanced_ai_client.EnhancedAIThemeClient",
            "required": True
        },
        {
            "name": "AI相似性分析器",
            "import_path": "theme_service.ai_similarity_analyzer.AIThemeSimilarityAnalyzer",
            "required": True
        },
        {
            "name": "主题发现引擎",
            "import_path": "theme_service.enhanced_theme_discovery.EnhancedThemeDiscoveryEngine",
            "required": True
        }
    ]
    
    results = []
    
    for check in checks:
        try:
            # 动态导入
            module_parts = check["import_path"].split('.')
            module_name = '.'.join(module_parts[:-1])
            class_name = module_parts[-1]
            
            # 检查模块是否存在
            __import__(module_name)
            module = sys.modules[module_name]
            
            # 检查类是否存在
            if hasattr(module, class_name):
                results.append({
                    "name": check["name"],
                    "status": "✅",
                    "message": "导入成功"
                })
                print(f"✅ {check['name']} ({check['import_path']})")
            else:
                results.append({
                    "name": check["name"],
                    "status": "❌",
                    "message": f"模块中没有类 {class_name}"
                })
                print(f"❌ {check['name']}: 模块中没有类 {class_name}")
                
        except ModuleNotFoundError as e:
            results.append({
                "name": check["name"],
                "status": "❌",
                "message": f"模块不存在: {e.name}"
            })
            print(f"❌ {check['name']}: 模块不存在 - {e.name}")
        except Exception as e:
            results.append({
                "name": check["name"],
                "status": "❌", 
                "message": f"导入错误: {str(e)[:50]}"
            })
            print(f"❌ {check['name']}: 导入错误 - {str(e)[:50]}")
    
    # 统计结果
    total = len(results)
    success = sum(1 for r in results if r["status"] == "✅")
    required_checks = [c for c in checks if c["required"]]
    required_success = sum(1 for c in required_checks 
                          if any(r["status"] == "✅" for r in results 
                                 if r["name"] == c["name"]))
    
    print(f"\n📊 导入检查结果:")
    print(f"  总计: {success}/{total}")
    print(f"  必要组件: {required_success}/{len(required_checks)}")
    
    # 显示失败详情
    failed = [r for r in results if r["status"] == "❌"]
    if failed:
        print(f"\n⚠️  失败的导入:")
        for f in failed:
            print(f"  • {f['name']}: {f['message']}")
    
    return success >= len(required_checks)  # 所有必要组件必须成功

async def test_minimal_integration():
    """测试最小集成"""
    print("\n🔧 测试最小集成...")
    
    try:
        # 导入已验证的模块
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        # 初始化最小系统
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        data_fetcher = PureDataFetcher(db_manager)
        theme_fetcher = RelatedThemeFetcher(data_fetcher)
        
        # 测试基本功能
        print("  测试数据获取...")
        themes = await theme_fetcher.fetch_all_active_themes(limit=5)
        print(f"    获取到 {len(themes)} 个主题")
        
        print("  测试事件处理...")
        # 创建一个测试事件
        test_event = {
            "news_id": "integration_test_event",
            "event_info": {
                "event_type": "集成测试",
                "impact_industries": ["测试"],
                "direction": "中性"
            },
            "original_news": {
                "title": "集成测试事件",
                "content": "这是一个集成测试事件，用于验证系统集成。",
                "date": "2025-01-13"
            }
        }
        
        event_id = await db_manager.create_or_update_event(test_event)
        print(f"    创建事件成功: {event_id}")
        
        await db_manager.cleanup()
        print("  ✅ 最小集成测试通过")
        return True
        
    except Exception as e:
        print(f"  ❌ 最小集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def check_ai_client():
    """检查AI客户端"""
    print("\n🤖 检查AI客户端...")
    
    try:
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        
        ai_client = EnhancedAIThemeClient()
        
        # 检查配置
        config = ai_client.config if hasattr(ai_client, 'config') else {}
        print(f"  AI客户端配置: {config}")
        
        # 检查是否有LLM解析器
        if hasattr(ai_client, 'llm_parser'):
            print(f"  ✅ 有LLM解析器")
        else:
            print(f"  ⚠️  没有LLM解析器属性")
        
        # 简单API调用测试（如果可能）
        try:
            if hasattr(ai_client, 'health_check'):
                health = await ai_client.health_check()
                print(f"  ✅ AI客户端健康检查: {health}")
            else:
                print(f"  ⚠️  没有健康检查方法")
        except:
            print(f"  ⚠️  健康检查失败")
        
        return True
        
    except Exception as e:
        print(f"  ❌ AI客户端检查失败: {e}")
        return False

async def check_enhanced_engine():
    """检查增强引擎"""
    print("\n🚀 检查EnhancedThemeDiscoveryEngine...")
    
    try:
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        from database_service.pure_data_fetcher import PureDataFetcher
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.config import DatabaseConfig
        
        # 初始化依赖
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        data_fetcher = PureDataFetcher(db_manager)
        ai_client = EnhancedAIThemeClient()
        
        # 检查是否支持DatabaseClient
        try:
            from database_service.client import DatabaseClient
            db_client = DatabaseClient(db_manager)
            print("  ✅ 找到DatabaseClient")
        except:
            print("  ⚠️  DatabaseClient不存在，可能需要适配")
            # 使用替代方案
            db_client = None
        
        # 检查相似性分析器
        try:
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            similarity_analyzer = AIThemeSimilarityAnalyzer(ai_client.llm_parser)
            print("  ✅ 找到AIThemeSimilarityAnalyzer")
        except Exception as e:
            print(f"  ❌ AIThemeSimilarityAnalyzer导入失败: {e}")
            similarity_analyzer = None
        
        # 尝试创建引擎
        if db_client and similarity_analyzer:
            engine = EnhancedThemeDiscoveryEngine(
                ai_client=ai_client,
                database_client=db_client,
                similarity_analyzer=similarity_analyzer,
                data_fetcher=data_fetcher,
                config={'enable_detailed_logging': True}
            )
            print(f"  ✅ 引擎创建成功")
            
            # 检查引擎方法
            if hasattr(engine, 'get_engine_info'):
                info = engine.get_engine_info()
                print(f"    引擎版本: {info.get('engine_version', 'unknown')}")
            else:
                print(f"  ⚠️  引擎没有get_engine_info方法")
            
            await db_manager.cleanup()
            return True
        else:
            print(f"  ❌ 缺少必要组件，无法创建引擎")
            await db_manager.cleanup()
            return False
        
    except Exception as e:
        print(f"  ❌ 引擎检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主验证函数"""
    print("="*60)
    print("🔧 集成测试前置验证")
    print("="*60)
    
    # 1. 检查模块导入
    import_success = check_module_imports()
    
    if not import_success:
        print("\n❌ 必要模块导入失败，无法继续集成测试")
        print("\n💡 建议:")
        print("  1. 检查模块文件是否存在")
        print("  2. 更新 __init__.py 文件")
        print("  3. 修复导入路径")
        return False
    
    print("\n✅ 所有必要模块导入成功")
    
    # 2. 测试最小集成
    integration_success = await test_minimal_integration()
    
    # 3. 检查AI客户端
    ai_client_success = await check_ai_client()
    
    # 4. 检查增强引擎
    engine_success = await check_enhanced_engine()
    
    # 最终评估
    print("\n" + "="*60)
    print("📊 集成验证结果")
    print("="*60)
    
    results = [
        ("模块导入", import_success),
        ("最小集成", integration_success),
        ("AI客户端", ai_client_success),
        ("增强引擎", engine_success)
    ]
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {name}: {status}")
    
    all_success = all(success for _, success in results)
    
    if all_success:
        print("\n🎉 所有验证通过，可以运行完整集成测试！")
        print("\n下一步: 运行 integrated_test_runner_fixed.py")
    else:
        print("\n⚠️  存在验证失败，需要先修复问题")
        
        # 提供具体建议
        if not integration_success:
            print("\n💡 最小集成失败建议:")
            print("  检查数据库组件配置")
            print("  验证事件数据结构")
        
        if not ai_client_success:
            print("\n💡 AI客户端失败建议:")
            print("  检查AI客户端实现")
            print("  确认API密钥配置")
        
        if not engine_success:
            print("\n💡 增强引擎失败建议:")
            print("  检查EnhancedThemeDiscoveryEngine实现")
            print("  确认所有依赖组件可用")
    
    return all_success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n验证被用户中断")
        sys.exit(130)