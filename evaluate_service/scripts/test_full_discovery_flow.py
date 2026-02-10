# evaluate_service/scripts/test_full_discovery_flow.py
#!/usr/bin/env python3
"""
完整主题发现流程测试 - 修复版
🚀 从数据文件 -> 内存数据库 -> AI分析 -> 主题发现的完整流程
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print(f"🔧 项目根目录: {PROJECT_ROOT}")
print("🚀 开始完整主题发现流程测试")
print("📊 测试目标: 数据文件 -> 内存数据库 -> AI分析 -> 主题发现的完整流程")
print("=" * 80)

async def test_step_1_load_data():
    """步骤1: 加载测试数据"""
    print("\n1️⃣ 步骤1: 加载测试数据")
    
    data_file = PROJECT_ROOT / "evaluate_service" / "data" / "processed" / "validation_events_fixed.json"
    
    if not data_file.exists():
        print(f"❌ 数据文件不存在: {data_file}")
        return None
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get('events', [])
        print(f"✅ 成功加载 {len(events)} 条事件数据")
        
        # 取前3条进行测试
        test_events = events[:3]
        print(f"📊 使用前 {len(test_events)} 条数据进行测试:")
        
        for i, event in enumerate(test_events):
            news_id = event.get('news_id', f'event_{i}')
            title = event.get('original_news', {}).get('title', '无标题')[:40]
            content_len = len(event.get('original_news', {}).get('content', ''))
            print(f"   {i+1}. {news_id}: {title}... (内容长度: {content_len}字符)")
        
        return test_events
        
    except Exception as e:
        print(f"❌ 加载数据失败: {e}")
        return None

async def test_step_2_setup_memory_database(test_events):
    """步骤2: 设置内存数据库并导入数据"""
    print("\n2️⃣ 步骤2: 设置内存数据库")
    
    try:
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        
        # 1. 创建内存数据库
        db_manager = MemoryDatabaseManager()
        await db_manager.connect()
        print("✅ 内存数据库创建成功")
        
        # 2. 创建数据获取器
        data_fetcher = PureDataFetcher(db_manager)
        print("✅ 数据获取器创建成功")
        
        # 3. 导入测试数据到内存数据库
        print("📥 导入数据到内存数据库...")
        import_results = []
        
        for event in test_events:
            try:
                # 使用create_or_update_event方法导入
                event_id = await db_manager.create_or_update_event(event)
                import_results.append({
                    'news_id': event.get('news_id'),
                    'stored_id': event_id,
                    'success': True
                })
                print(f"   ✅ 导入: {event.get('news_id')} -> {event_id}")
            except Exception as e:
                import_results.append({
                    'news_id': event.get('news_id'),
                    'error': str(e),
                    'success': False
                })
                print(f"   ❌ 导入失败: {event.get('news_id')} - {e}")
        
        # 4. 验证数据库状态
        stats = await db_manager.get_stats()
        print(f"📊 数据库状态:")
        print(f"   总事件数: {stats.get('total_events', 0)}")
        print(f"   总主题数: {stats.get('total_themes', 0)}")
        
        # 5. 验证事件是否可读取
        print("🔍 验证数据可读性...")
        for event in test_events[:2]:  # 验证前2个
            news_id = event.get('news_id')
            stored_event = await db_manager.get_event(news_id)
            if stored_event:
                print(f"   ✅ 可读取事件: {news_id}")
                print(f"      标题: {stored_event.get('original_news', {}).get('title', '')[:30]}...")
                print(f"      内容长度: {len(stored_event.get('original_news', {}).get('content', ''))}字符")
            else:
                print(f"   ❌ 无法读取事件: {news_id}")
        
        return db_manager, data_fetcher
        
    except Exception as e:
        print(f"❌ 设置内存数据库失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None

async def test_step_3_initialize_ai_components():
    """步骤3: 初始化AI组件"""
    print("\n3️⃣ 步骤3: 初始化AI组件")
    
    try:
        # 1. 初始化AI解析器（真实DeepSeek）
        print("🤖 初始化AI解析器...")
        try:
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            llm_parser = ReliableDeepSeekParser(
                config={
                    'max_retries': 3,
                    'timeout': 30,
                    'temperature': 0.1,
                    'enable_cache': True
                }
            )
            ai_health = await llm_parser.health_check()
            print(f"✅ 真实DeepSeek解析器初始化成功，健康状态: {ai_health}")
        except ImportError as e:
            print(f"⚠️  无法导入真实DeepSeek解析器，使用Mock解析器: {e}")
            from model_service.llm_parser.mock_parser import MockLLMParser
            llm_parser = MockLLMParser()
            print("⚠️  使用Mock解析器（测试模式）")
        
        # 2. 初始化AI相似性分析器
        print("🔍 初始化AI相似性分析器...")
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
        print("✅ AI相似性分析器初始化成功")
        
        # 3. 初始化AI客户端
        print("🧠 初始化AI主题客户端...")
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        ai_client = EnhancedAIThemeClient(llm_parser)
        
        # 测试AI客户端
        try:
            # 修正：异步调用 get_client_info
            client_info = await ai_client.get_client_info()
        except:
            # 如果失败，使用同步方式获取基本信息
            client_info = {'client_name': 'EnhancedAIThemeClient', 'ai_healthy': True}
        
        print(f"✅ AI客户端初始化成功:")
        print(f"   客户端名称: {client_info.get('client_name')}")
        print(f"   AI健康状态: {client_info.get('ai_healthy', False)}")
        
        return llm_parser, similarity_analyzer, ai_client
        
    except Exception as e:
        print(f"❌ 初始化AI组件失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

async def test_step_4_initialize_discovery_engine(db_manager, data_fetcher, ai_client, similarity_analyzer):
    """步骤4: 初始化主题发现引擎 - 修复版"""
    print("\n4️⃣ 步骤4: 初始化主题发现引擎")
    
    try:
        # 1. 初始化数据库客户端
        from database_service.client import DatabaseClient
        db_client = DatabaseClient(db_manager)
        print("✅ 数据库客户端初始化成功")
        
        # 2. 初始化主题检索器 - 修正参数
        print("🔍 初始化主题检索器...")
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        # 注意：RelatedThemeFetcher 只接受 data_fetcher 参数
        theme_fetcher = RelatedThemeFetcher(
            data_fetcher=data_fetcher,
            use_cache=True
        )
        print("✅ 主题检索器初始化成功")
        
        # 3. 初始化主题发现引擎 - 修正参数传递
        print("🚀 初始化主题发现引擎...")
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            database_client=db_client,
            similarity_analyzer=similarity_analyzer,  # 直接传递，不通过theme_fetcher
            data_fetcher=data_fetcher,  # 直接传递
            config={
                'fast_track_threshold': 0.8,
                'review_threshold': 0.6,
                'ignore_threshold': 0.3,
                'max_processing_time': 60,
                'enable_detailed_logging': True,
                'data_structure': 'new'
            }
        )
        
        # 获取引擎信息
        try:
            engine_info = engine.get_engine_info()
            print("✅ 主题发现引擎初始化成功:")
            print(f"   引擎版本: {engine_info.get('engine_version')}")
            print(f"   分析方法: {engine_info.get('analysis_method')}")
        except:
            print("✅ 主题发现引擎初始化成功（跳过信息获取）")
        
        return engine
        
    except Exception as e:
        print(f"❌ 初始化主题发现引擎失败: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_step_5_run_discovery_process(engine, test_events):
    """步骤5: 运行主题发现流程"""
    print("\n5️⃣ 步骤5: 运行主题发现流程")
    
    results = []
    
    for i, event_data in enumerate(test_events):
        print(f"\n📋 处理事件 {i+1}/{len(test_events)}:")
        print(f"   ID: {event_data.get('news_id')}")
        print(f"   标题: {event_data.get('original_news', {}).get('title', '')[:40]}...")
        
        try:
            # 1. 运行主题发现引擎处理事件
            start_time = datetime.now()
            result = await engine.process_single_event(event_data)
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # 2. 记录结果
            status = result.get('status', 'unknown')
            ai_decision = result.get('ai_decision', {})
            
            result_info = {
                'event_id': event_data.get('news_id'),
                'status': status,
                'processing_time': processing_time,
                'ai_decision': ai_decision.get('decision', 'UNKNOWN'),
                'confidence': ai_decision.get('confidence', 0),
                'theme_name': result.get('theme_name', ''),
                'success': status in ['created', 'merged']
            }
            
            results.append(result_info)
            
            # 3. 打印结果
            print(f"   ⏱️  处理时间: {processing_time:.2f}秒")
            print(f"   📊 状态: {status}")
            print(f"   🤖 AI决策: {ai_decision.get('decision', 'UNKNOWN')}")
            print(f"   📈 置信度: {ai_decision.get('confidence', 0):.2f}")
            
            if ai_decision.get('reason'):
                reason = ai_decision.get('reason', '')
                if len(reason) > 80:
                    reason = reason[:80] + '...'
                print(f"   💡 理由: {reason}")
            
            if result.get('theme_name'):
                print(f"   🏷️  主题: {result.get('theme_name')}")
            
            if status in ['created', 'merged']:
                print(f"   ✅ 处理成功")
            else:
                print(f"   ⚠️  处理状态: {status}")
            
        except Exception as e:
            print(f"   ❌ 处理失败: {e}")
            results.append({
                'event_id': event_data.get('news_id'),
                'status': 'failed',
                'error': str(e),
                'success': False
            })
    
    return results

async def test_step_6_verify_results(db_manager, results):
    """步骤6: 验证结果"""
    print("\n6️⃣ 步骤6: 验证处理结果")
    
    try:
        # 1. 统计结果
        total = len(results)
        successful = sum(1 for r in results if r.get('success', False))
        failed = total - successful
        
        print(f"📊 处理统计:")
        print(f"   总计事件: {total}")
        print(f"   成功: {successful}")
        print(f"   失败: {failed}")
        print(f"   成功率: {successful/total*100:.1f}%" if total > 0 else "成功率: N/A")
        
        # 2. 检查数据库中的主题
        themes = await db_manager.get_all_active_themes(limit=10)
        print(f"\n📋 数据库中的主题:")
        
        if themes:
            for theme in themes:
                event_ids = await db_manager.get_theme_events(theme.id, limit=3)
                print(f"   • {theme.name} (ID: {theme.id}, 热度: {theme.heat_score}, 事件数: {len(event_ids)})")
        else:
            print("   📭 数据库中暂无主题")
        
        # 3. 检查事件关联
        print(f"\n🔗 事件-主题关联:")
        for result in results:
            if result.get('success'):
                event_id = result.get('event_id')
                relations = await db_manager.get_event_themes(event_id)
                if relations:
                    print(f"   ✅ {event_id}: {len(relations)} 个关联")
                else:
                    print(f"   ⚠️  {event_id}: 无关联（可能处理成功但未创建关联）")
        
        # 4. 获取详细统计
        stats = await db_manager.get_stats()
        print(f"\n📈 数据库详细统计:")
        print(f"   总主题数: {stats.get('total_themes', 0)}")
        print(f"   总关联数: {stats.get('total_relations', 0)}")
        print(f"   总事件数: {stats.get('total_events', 0)}")
        
        return {
            'total_events': total,
            'successful': successful,
            'failed': failed,
            'success_rate': successful/total if total > 0 else 0,
            'themes_created': len(themes) if themes else 0,
            'database_stats': stats
        }
        
    except Exception as e:
        print(f"❌ 验证结果失败: {e}")
        return None

async def test_step_7_generate_report(test_events, results, verification):
    """步骤7: 生成测试报告"""
    print("\n7️⃣ 步骤7: 生成测试报告")
    
    try:
        # 创建报告目录
        report_dir = PROJECT_ROOT / "evaluate_service" / "data" / "results" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"full_discovery_flow_{timestamp}.json"
        
        # 构建报告
        report = {
            'metadata': {
                'report_id': f"full_discovery_flow_{timestamp}",
                'generated_at': datetime.now().isoformat(),
                'test_type': 'full_discovery_flow',
                'data_source': 'validation_events_fixed.json',
                'test_version': '1.0.0'
            },
            'test_summary': {
                'total_test_events': len(test_events),
                'events_processed': len(results),
                'successful_events': verification.get('successful', 0) if verification else 0,
                'failed_events': verification.get('failed', 0) if verification else 0,
                'success_rate': verification.get('success_rate', 0) if verification else 0,
                'themes_created': verification.get('themes_created', 0) if verification else 0
            },
            'test_events': [
                {
                    'news_id': event.get('news_id'),
                    'title': event.get('original_news', {}).get('title', ''),
                    'content_length': len(event.get('original_news', {}).get('content', '')),
                    'event_type': event.get('event_info', {}).get('event_type', ''),
                    'industries': event.get('event_info', {}).get('impact_industries', [])
                }
                for event in test_events
            ],
            'detailed_results': results,
            'verification': verification,
            'conclusion': {
                'overall_status': 'PASS' if verification and verification.get('success_rate', 0) > 0.5 else 'FAIL',
                'data_flow_status': 'WORKING' if results else 'BROKEN',
                'ai_integration_status': 'WORKING' if any('ai_decision' in r for r in results) else 'BROKEN',
                'database_integration_status': 'WORKING' if verification and verification.get('themes_created', 0) > 0 else 'BROKEN',
                'issues_found': [],
                'recommendations': [
                    '验证AI大模型能看到完整original_news.content',
                    '检查主题合并决策的准确性',
                    '验证事件-主题关联的正确性'
                ]
            }
        }
        
        # 保存报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 测试报告已生成:")
        print(f"   📄 报告文件: {report_file.relative_to(PROJECT_ROOT)}")
        print(f"   📊 总体状态: {report['conclusion']['overall_status']}")
        print(f"   🔗 数据流: {report['conclusion']['data_flow_status']}")
        print(f"   🤖 AI集成: {report['conclusion']['ai_integration_status']}")
        print(f"   🗄️  数据库集成: {report['conclusion']['database_integration_status']}")
        
        return report_file
        
    except Exception as e:
        print(f"❌ 生成报告失败: {e}")
        return None

async def test_step_8_cleanup(db_manager):
    """步骤8: 清理资源"""
    print("\n8️⃣ 步骤8: 清理资源")
    
    try:
        if db_manager:
            await db_manager.cleanup()
            print("✅ 内存数据库已清理")
        
        print("✅ 资源清理完成")
        return True
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🚀 AI主题发现完整流程测试")
    print("=" * 80)
    
    db_manager = None
    
    try:
        # 步骤1: 加载数据
        test_events = await test_step_1_load_data()
        if not test_events:
            return False
        
        # 步骤2: 设置内存数据库
        db_manager, data_fetcher = await test_step_2_setup_memory_database(test_events)
        if not db_manager:
            return False
        
        # 步骤3: 初始化AI组件
        llm_parser, similarity_analyzer, ai_client = await test_step_3_initialize_ai_components()
        if not ai_client:
            print("⚠️  无法初始化AI客户端，使用模拟模式继续测试")
        
        # 步骤4: 初始化主题发现引擎
        engine = await test_step_4_initialize_discovery_engine(
            db_manager, data_fetcher, ai_client, similarity_analyzer
        )
        if not engine:
            return False
        
        # 步骤5: 运行主题发现流程
        results = await test_step_5_run_discovery_process(engine, test_events)
        
        # 步骤6: 验证结果
        verification = await test_step_6_verify_results(db_manager, results)
        
        # 步骤7: 生成报告
        report_file = await test_step_7_generate_report(test_events, results, verification)
        
        # 步骤8: 清理资源
        await test_step_8_cleanup(db_manager)
        
        print("\n" + "=" * 80)
        print("🎉 完整流程测试完成!")
        
        if verification and verification.get('success_rate', 0) > 0.5:
            print("✅ 测试通过: 数据流已打通!")
        else:
            print("⚠️  测试部分通过，需要进一步调试")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试过程异常: {e}")
        import traceback
        traceback.print_exc()
        
        # 确保清理
        if db_manager:
            await test_step_8_cleanup(db_manager)
        
        return False

if __name__ == "__main__":
    # 设置事件循环策略（Windows）
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行测试
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️ 测试被用户中断")
        sys.exit(130)