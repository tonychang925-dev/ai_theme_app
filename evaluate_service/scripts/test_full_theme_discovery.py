# evaluate_service/scripts/test_full_theme_discovery.py
#!/usr/bin/env python3
"""
完整主题发现流程测试 - 使用真实AI大模型
🚀 验证EnhancedThemeDiscoveryEngine在新数据结构下的功能
📊 生成详细的测试报告
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
import logging

# 设置项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "evaluate_service" / "data" / "results" / "logs" / "theme_discovery_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def print_header(title):
    """打印测试标题"""
    print(f"\n{'='*80}")
    print(f"🧪 {title}")
    print(f"{'='*80}")

async def test_1_setup_environment():
    """测试1：环境设置和数据准备"""
    print_header("测试1: 环境设置和数据准备")
    
    try:
        # 1. 检查数据文件
        data_file = PROJECT_ROOT / "evaluate_service" / "data" / "processed" / "validation_events_fixed.json"
        if not data_file.exists():
            logger.error(f"❌ 数据文件不存在: {data_file}")
            return None, None
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 使用前3条数据进行测试
        test_events = data.get('events', [])[:3]
        logger.info(f"✅ 加载 {len(test_events)} 条测试事件")
        
        # 显示事件信息
        for i, event in enumerate(test_events):
            logger.info(f"  事件{i+1}: {event.get('news_id')} - {event.get('original_news', {}).get('title', '')[:50]}...")
            logger.info(f"     内容长度: {event.get('original_news', {}).get('content_length', 0)} 字符")
        
        return data_file, test_events
        
    except Exception as e:
        logger.error(f"❌ 环境设置失败: {e}")
        return None, None

async def test_2_initialize_components():
    """测试2：初始化所有组件"""
    print_header("测试2: 初始化组件")
    
    try:
        # 1. 初始化内存数据库
        from database_service.memory_manager import MemoryDatabaseManager
        db_manager = MemoryDatabaseManager()
        await db_manager.connect()
        logger.info("✅ 内存数据库初始化完成")
        
        # 2. 初始化数据获取器
        from database_service.pure_data_fetcher import PureDataFetcher
        data_fetcher = PureDataFetcher(db_manager)
        logger.info("✅ 纯数据获取器初始化完成")
        
        # 3. 初始化AI解析器（真实DeepSeek API）
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
            logger.info("✅ 真实DeepSeek解析器初始化完成")
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入真实DeepSeek解析器: {e}")
            # 使用模拟解析器作为后备
            from model_service.llm_parser.mock_parser import MockLLMParser
            llm_parser = MockLLMParser()
            logger.info("⚠️ 使用Mock解析器（后备方案）")
        
        # 4. 初始化AI相似性分析器
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
        logger.info("✅ AI相似性分析器初始化完成")
        
        # 5. 初始化主题检索器
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        theme_fetcher = RelatedThemeFetcher(
            data_fetcher=data_fetcher,
            similarity_analyzer=similarity_analyzer,
            use_cache=True
        )
        logger.info("✅ 主题检索器初始化完成")
        
        # 6. 初始化AI客户端
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        ai_client = EnhancedAIThemeClient(llm_parser)
        
        # 测试AI健康状态
        ai_health = await ai_client.health_check()
        logger.info(f"✅ AI客户端初始化完成，健康状态: {ai_health}")
        
        # 7. 初始化数据库客户端
        from database_service.client import DatabaseClient
        db_client = DatabaseClient(db_manager)
        logger.info("✅ 数据库客户端初始化完成")
        
        # 8. 初始化主题发现引擎
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            database_client=db_client,
            similarity_analyzer=similarity_analyzer,
            data_fetcher=data_fetcher,
            config={
                'fast_track_threshold': 0.8,
                'review_threshold': 0.6,
                'ignore_threshold': 0.3,
                'max_processing_time': 60,
                'enable_detailed_logging': True,
                'data_structure': 'new'
            }
        )
        
        engine_info = engine.get_engine_info()
        logger.info(f"✅ 主题发现引擎初始化完成")
        logger.info(f"   引擎版本: {engine_info.get('engine_version')}")
        logger.info(f"   分析方法: {engine_info.get('analysis_method')}")
        
        return {
            'db_manager': db_manager,
            'data_fetcher': data_fetcher,
            'llm_parser': llm_parser,
            'similarity_analyzer': similarity_analyzer,
            'theme_fetcher': theme_fetcher,
            'ai_client': ai_client,
            'db_client': db_client,
            'engine': engine
        }
        
    except Exception as e:
        logger.error(f"❌ 组件初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_3_load_and_process_events(components, test_events):
    """测试3：加载并处理事件"""
    print_header("测试3: 事件处理流程")
    
    results = []
    total_events = len(test_events)
    
    logger.info(f"🚀 开始处理 {total_events} 个事件...")
    
    for i, event_data in enumerate(test_events):
        event_id = event_data.get('news_id', f'event_{i+1}')
        logger.info(f"\n📋 处理事件 {i+1}/{total_events}: {event_id}")
        
        try:
            start_time = datetime.now()
            
            # 1. 将事件存储到数据库
            stored_id = await components['db_manager'].create_or_update_event(event_data)
            logger.info(f"   ✅ 事件存储完成: {stored_id}")
            
            # 2. 处理事件
            result = await components['engine'].process_single_event(event_data)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # 记录结果
            result_summary = {
                'event_id': event_id,
                'stored_id': stored_id,
                'processing_time': processing_time,
                'status': result.get('status', 'unknown'),
                'ai_decision': result.get('ai_decision', {}),
                'related_themes_count': result.get('related_themes_count', 0),
                'success': result.get('status') in ['created', 'merged']
            }
            
            results.append(result_summary)
            
            # 输出详细信息
            logger.info(f"   ⏱️  处理时间: {processing_time:.2f}秒")
            logger.info(f"   📊 状态: {result.get('status')}")
            
            if 'ai_decision' in result:
                ai_decision = result['ai_decision']
                logger.info(f"   🤖 AI决策: {ai_decision.get('decision')}")
                logger.info(f"   🔍 置信度: {ai_decision.get('confidence', 0):.2f}")
                logger.info(f"   💡 理由: {ai_decision.get('reason', '')[:100]}...")
            
            if result.get('theme_name'):
                logger.info(f"   🏷️  主题: {result.get('theme_name')}")
            
        except Exception as e:
            logger.error(f"❌ 事件处理失败: {event_id}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            results.append({
                'event_id': event_id,
                'error': str(e),
                'success': False
            })
    
    return results

async def test_4_validate_results(components, results):
    """测试4：验证结果"""
    print_header("测试4: 结果验证")
    
    try:
        # 1. 统计信息
        total = len(results)
        successful = sum(1 for r in results if r.get('success', False))
        failed = total - successful
        
        logger.info(f"📊 处理统计:")
        logger.info(f"   总计: {total} 个事件")
        logger.info(f"   成功: {successful} 个")
        logger.info(f"   失败: {failed} 个")
        logger.info(f"   成功率: {successful/total*100:.1f}%" if total > 0 else "成功率: N/A")
        
        # 2. 处理时间分析
        if successful > 0:
            avg_time = sum(r.get('processing_time', 0) for r in results if r.get('success')) / successful
            logger.info(f"   ⏱️  平均处理时间: {avg_time:.2f}秒")
        
        # 3. 获取数据库状态
        db_stats = await components['db_manager'].get_stats()
        logger.info(f"📊 数据库状态:")
        logger.info(f"   主题数量: {db_stats.get('total_themes', 0)}")
        logger.info(f"   关联数量: {db_stats.get('total_relations', 0)}")
        logger.info(f"   事件数量: {db_stats.get('total_events', 0)}")
        
        # 4. 获取引擎统计
        engine_stats = await components['engine'].get_processing_stats()
        logger.info(f"📊 引擎统计:")
        logger.info(f"   总处理事件: {engine_stats.get('total_events', 0)}")
        logger.info(f"   成功: {engine_stats.get('successful', 0)}")
        logger.info(f"   失败: {engine_stats.get('failed', 0)}")
        logger.info(f"   创建主题: {engine_stats.get('created_themes', 0)}")
        logger.info(f"   合并主题: {engine_stats.get('merged_themes', 0)}")
        
        # 5. 验证主题是否被正确创建
        themes = await components['db_manager'].get_all_active_themes(limit=10)
        if themes:
            logger.info(f"📋 已创建的主题:")
            for theme in themes:
                # 获取主题关联的事件数量
                event_ids = await components['db_manager'].get_theme_events(theme.id, limit=5)
                logger.info(f"   • {theme.name} (ID: {theme.id}, 热度: {theme.heat_score}, 事件数: {len(event_ids)})")
        
        return {
            'total_events': total,
            'successful': successful,
            'failed': failed,
            'success_rate': successful/total if total > 0 else 0,
            'avg_processing_time': avg_time if successful > 0 else 0,
            'database_stats': db_stats,
            'engine_stats': engine_stats,
            'themes_created': len(themes) if themes else 0
        }
        
    except Exception as e:
        logger.error(f"❌ 结果验证失败: {e}")
        return None

async def test_5_generate_report(test_events, components, results, validation):
    """测试5：生成测试报告"""
    print_header("测试5: 生成测试报告")
    
    try:
        # 创建报告目录
        report_dir = PROJECT_ROOT / "evaluate_service" / "data" / "results" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"theme_discovery_report_{timestamp}.json"
        
        # 收集AI客户端信息
        ai_info = {}
        if components and 'ai_client' in components:
            try:
                ai_info = await components['ai_client'].get_client_info()
            except:
                ai_info = {'error': '无法获取AI客户端信息'}
        
        # 构建报告
        report = {
            'metadata': {
                'report_id': f"theme_discovery_{timestamp}",
                'generated_at': datetime.now().isoformat(),
                'test_type': 'full_theme_discovery',
                'data_structure': 'new',
                'test_version': '1.0.0'
            },
            'test_summary': {
                'total_test_events': len(test_events),
                'events_processed': len(results),
                'successful_events': validation.get('successful', 0) if validation else 0,
                'failed_events': validation.get('failed', 0) if validation else 0,
                'success_rate': validation.get('success_rate', 0) if validation else 0,
                'avg_processing_time': validation.get('avg_processing_time', 0) if validation else 0
            },
            'ai_system_info': ai_info,
            'database_stats': validation.get('database_stats', {}) if validation else {},
            'engine_stats': validation.get('engine_stats', {}) if validation else {},
            'test_events': [
                {
                    'news_id': event.get('news_id'),
                    'title': event.get('original_news', {}).get('title', ''),
                    'content_length': event.get('original_news', {}).get('content_length', 0),
                    'event_type': event.get('event_info', {}).get('event_type', ''),
                    'industries': event.get('event_info', {}).get('impact_industries', [])
                }
                for event in test_events
            ],
            'detailed_results': results,
            'validation': validation,
            'conclusion': {
                'overall_status': 'PASS' if validation and validation.get('success_rate', 0) > 0.7 else 'FAIL',
                'issues_found': [],
                'recommendations': [
                    '验证AI大模型能够看到完整原始内容',
                    '检查主题合并决策的准确性',
                    '验证数据结构适配性'
                ]
            }
        }
        
        # 保存报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 测试报告已生成: {report_file}")
        
        # 打印总结
        print_header("测试总结")
        print(f"📊 总体结果: {'✅ 通过' if report['conclusion']['overall_status'] == 'PASS' else '❌ 失败'}")
        print(f"📈 成功率: {report['test_summary']['success_rate']*100:.1f}%")
        print(f"⏱️  平均处理时间: {report['test_summary']['avg_processing_time']:.2f}秒")
        print(f"🏷️  创建主题: {validation.get('themes_created', 0) if validation else 0} 个")
        print(f"📁 报告文件: {report_file.relative_to(PROJECT_ROOT)}")
        
        return report_file
        
    except Exception as e:
        logger.error(f"❌ 报告生成失败: {e}")
        return None

async def test_6_cleanup(components):
    """测试6：清理资源"""
    print_header("测试6: 清理资源")
    
    try:
        if components and 'db_manager' in components:
            await components['db_manager'].cleanup()
            logger.info("✅ 内存数据库已清理")
        
        logger.info("✅ 资源清理完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 清理失败: {e}")
        return False

async def main():
    """主测试函数"""
    print_header("完整主题发现流程测试")
    print("🚀 目标: 验证EnhancedThemeDiscoveryEngine在新数据结构下的功能")
    print("📊 使用真实AI大模型进行测试")
    print(f"📅 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    all_passed = True
    test_results = {}
    
    try:
        # 测试1: 环境设置
        data_file, test_events = await test_1_setup_environment()
        if not data_file or not test_events:
            logger.error("❌ 测试1失败")
            return False
        test_results['test1'] = True
        
        # 测试2: 初始化组件
        components = await test_2_initialize_components()
        if not components:
            logger.error("❌ 测试2失败")
            return False
        test_results['test2'] = True
        
        # 测试3: 处理事件
        results = await test_3_load_and_process_events(components, test_events)
        if not results:
            logger.error("❌ 测试3失败")
            all_passed = False
        test_results['test3'] = bool(results)
        
        # 测试4: 验证结果
        validation = await test_4_validate_results(components, results)
        if not validation:
            logger.error("❌ 测试4失败")
            all_passed = False
        test_results['test4'] = bool(validation)
        
        # 测试5: 生成报告
        report_file = await test_5_generate_report(test_events, components, results, validation)
        if not report_file:
            logger.error("❌ 测试5失败")
            all_passed = False
        test_results['test5'] = bool(report_file)
        
        # 测试6: 清理资源
        cleanup_ok = await test_6_cleanup(components)
        test_results['test6'] = cleanup_ok
        
        # 最终统计
        passed_tests = sum(1 for v in test_results.values() if v)
        total_tests = len(test_results)
        
        print_header("最终测试结果")
        print(f"📊 测试通过率: {passed_tests}/{total_tests}")
        print(f"🎯 总体状态: {'✅ 所有测试通过' if all_passed else '⚠️  部分测试失败'}")
        
        if report_file:
            print(f"📄 详细报告: {report_file}")
        
        return all_passed
        
    except Exception as e:
        logger.error(f"❌ 测试过程异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 创建必要的目录
    log_dir = PROJECT_ROOT / "evaluate_service" / "data" / "results" / "logs"
    report_dir = PROJECT_ROOT / "evaluate_service" / "data" / "results" / "reports"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    # 运行测试
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️ 测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)