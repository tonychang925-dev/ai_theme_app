# evaluate_service/runners/test_data_integrity.py
"""
数据完整性测试 - 验证AI获取的数据是否完整
"""
#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def setup_logging():
    """设置日志配置"""
    log_dir = project_root / "evaluate_service" / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"data_integrity_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.DEBUG,  # 🔥 DEBUG级别，查看所有细节
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()


class DataIntegrityTester:
    """数据完整性测试器"""
    
    def __init__(self):
        self.data_dir = project_root / "evaluate_service" / "data" / "processed"
        self.test_events = []
        
    async def load_test_events(self, count=10):
        """加载测试事件"""
        events_path = self.data_dir / "validation_events_fixed.json"
        
        logger.info(f"📂 加载测试数据: {events_path}")
        
        with open(events_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取前10个AI/AR眼镜相关事件
        all_events = data if isinstance(data, list) else data.get('events', [])
        
        # 过滤出AI/AR眼镜相关的事件
        ai_ar_events = []
        for event in all_events:
            event_id = event.get('news_id', '')
            if 'AI_AR眼镜' in event_id or '眼镜' in str(event.get('original_news', {}).get('title', '')):
                ai_ar_events.append(event)
                if len(ai_ar_events) >= count:
                    break
        
        self.test_events = ai_ar_events
        logger.info(f"✅ 加载 {len(self.test_events)} 个AI/AR眼镜测试事件")
        
        # 打印每个事件的详细信息
        for i, event in enumerate(self.test_events):
            event_id = event.get('news_id', f'event_{i}')
            title = event.get('original_news', {}).get('title', '')
            content = event.get('original_news', {}).get('content', '')
            content_length = len(content) if content else 0
            
            logger.info(f"\n📋 事件 {i+1}: {event_id}")
            logger.info(f"   标题: {title[:60]}...")
            logger.info(f"   内容长度: {content_length} 字符")
            logger.info(f"   行业: {event.get('event_info', {}).get('impact_industries', [])}")
            
            # 检查关键字段
            missing_fields = []
            for field in ['news_id', 'original_news', 'event_info']:
                if field not in event:
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"   ⚠️  缺少字段: {missing_fields}")
            else:
                logger.info(f"   ✅ 字段完整")
    
    async def test_memory_database(self):
        """测试内存数据库"""
        logger.info("\n" + "="*80)
        logger.info("🧪 测试内存数据库")
        logger.info("="*80)
        
        try:
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            
            # 初始化数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            logger.info("✅ 内存数据库连接成功")
            
            # 🔥 修改：不再清空数据库，直接保存测试数据
            logger.info(f"\n💾 保存 {len(self.test_events)} 个事件到数据库...")
            
            saved_count = 0
            saved_event_ids = []
            for i, event in enumerate(self.test_events):
                event_id = event.get('news_id', f'event_{i}')
                
                # 🔥 关键：检查事件是否已存在
                existing_event = await db_manager.get_event(event_id)
                if existing_event:
                    logger.debug(f"  事件 {i+1} 已存在: {event_id}")
                    saved_count += 1
                    saved_event_ids.append(event_id)
                    continue
                
                # 构建数据库事件
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
                
                # 保存到数据库
                saved_id = await db_manager.create_or_update_event(db_event)
                if saved_id:
                    saved_count += 1
                    saved_event_ids.append(event_id)
                    logger.debug(f"  事件 {i+1} 保存成功: {event_id}")
                else:
                    logger.error(f"  事件 {i+1} 保存失败: {event_id}")
            
            logger.info(f"✅ 成功保存 {saved_count}/{len(self.test_events)} 个事件")
            
            # 3. 验证数据库中的事件
            logger.info("\n🔍 验证数据库中的事件数据...")
            
            for i, event_id in enumerate(saved_event_ids[:3]):  # 只验证前3个
                
                # 从数据库获取
                db_event = await db_manager.get_event(event_id)
                
                if not db_event:
                    logger.error(f"❌ 无法从数据库获取事件: {event_id}")
                    continue
                
                logger.info(f"\n📊 数据库事件 {i+1}: {event_id}")
                logger.info(f"   数据库标题: {db_event.get('title', '')[:60]}...")
                logger.info(f"   数据库内容长度: {len(db_event.get('full_content', ''))} 字符")
                logger.info(f"   has_full_content: {db_event.get('has_full_content', False)}")
                
                # 🔥 重要：检查原始事件对象
                original_event = next((e for e in self.test_events if e.get('news_id') == event_id), None)
                if original_event:
                    original_content = original_event.get('original_news', {}).get('content', '')
                    db_content = db_event.get('full_content', '')
                    
                    if original_content == db_content:
                        logger.info(f"   ✅ 内容一致")
                        logger.info(f"       内容预览: {db_content[:50]}...")
                    else:
                        logger.error(f"   ❌ 内容不一致!")
                        logger.error(f"       原始长度: {len(original_content)}")
                        logger.error(f"       数据库长度: {len(db_content)}")
                        
                        # 检查是否是因为None vs 空字符串
                        if (original_content or '') == (db_content or ''):
                            logger.info(f"   🔄 实际内容相同（None/空字符串处理差异）")
                else:
                    logger.warning(f"   ⚠️  找不到原始事件: {event_id}")
            
            # 4. 测试主题查询
            logger.info("\n🔍 测试主题查询功能...")
            
            # 先检查现有主题数量
            all_themes = await db_manager.get_all_active_themes(limit=100)
            logger.info(f"📊 数据库现有主题数: {len(all_themes)}")
            
            if len(all_themes) < 2:  # 如果主题太少，创建测试主题
                # 创建一些测试主题
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
                    if saved_theme:
                        logger.info(f"✅ 创建主题: {theme['name']}")
                    else:
                        logger.error(f"❌ 创建主题失败: {theme['name']}")
            
            # 再次查询所有主题
            all_themes = await db_manager.get_all_active_themes(limit=100)
            logger.info(f"📊 数据库中共有 {len(all_themes)} 个主题")
            
            for i, theme in enumerate(all_themes[:3]):  # 只显示前3个
                logger.info(f"   主题 {i+1}: {theme.get('name', '未知')}")
                logger.info(f"       描述: {theme.get('description', '')[:50]}...")
                logger.info(f"       关键词: {theme.get('keywords', [])}")
                logger.info(f"       相关事件数: {len(theme.get('related_events', []))}")
                
                # 🔥 检查主题上下文是否完整
                has_description = bool(theme.get('description'))
                has_keywords = bool(theme.get('keywords'))
                
                if not has_description:
                    logger.warning(f"        ⚠️ 主题缺少描述!")
                if not has_keywords:
                    logger.warning(f"        ⚠️ 主题缺少关键词!")
            
            return db_manager
            
        except Exception as e:
            logger.error(f"❌ 内存数据库测试失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def test_ai_analyzer_data_access(self, db_manager):
        """测试AI分析器的数据访问"""
        logger.info("\n" + "="*80)
        logger.info("🤖 测试AI分析器数据访问")
        logger.info("="*80)
        
        try:
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            from database_service.pure_data_fetcher import PureDataFetcher
            
            # 创建数据获取器
            data_fetcher = PureDataFetcher(db_manager)
            
            # 创建主题获取器
            theme_fetcher = RelatedThemeFetcher(data_fetcher)
            
            # 测试第一个事件
            test_event = self.test_events[0] if self.test_events else {}
            event_id = test_event.get('news_id', 'test_event')
            
            logger.info(f"\n🔍 测试事件: {event_id}")
            logger.info(f"   标题: {test_event.get('original_news', {}).get('title', '')[:60]}...")
            
            # 1. 测试主题获取器能否获取到相关主题
            logger.info("\n1. 测试RelatedThemeFetcher...")
            relevant_themes = await theme_fetcher.fetch_relevant_themes(test_event)
            
            logger.info(f"   获取到 {len(relevant_themes)} 个相关主题")
            
            if relevant_themes:
                for i, theme in enumerate(relevant_themes[:3]):  # 只显示前3个
                    logger.info(f"   主题 {i+1}: {theme.get('name', '未知')}")
                    logger.info(f"       描述: {theme.get('description', '')[:50]}...")
                    logger.info(f"       关键词: {theme.get('keywords', [])}")
            else:
                logger.warning("   ⚠️  未获取到相关主题")
            
            # 2. 测试数据获取器能否获取所有主题
            logger.info("\n2. 测试PureDataFetcher获取所有主题...")
            all_themes = await data_fetcher.get_all_active_themes()
            
            logger.info(f"   获取到 {len(all_themes)} 个活动主题")
            
            # 检查主题数据完整性
            if all_themes:
                for i, theme in enumerate(all_themes[:3]):  # 只检查前3个
                    logger.info(f"\n   主题 {i+1} 数据完整性检查:")
                    logger.info(f"       名称: {theme.get('name', 'N/A')}")
                    logger.info(f"       描述: {'✅' if theme.get('description') else '❌'}")
                    logger.info(f"       关键词: {'✅' if theme.get('keywords') else '❌'}")
                    logger.info(f"       事件数量: {len(theme.get('related_events', []))}")
                    
                    # 检查是否有完整的上下文
                    if 'description' not in theme or not theme['description']:
                        logger.error(f"       ❌ 主题缺少描述!")
                    if 'keywords' not in theme or not theme['keywords']:
                        logger.error(f"       ❌ 主题缺少关键词!")
            
            # 3. 测试增强主题获取
            logger.info("\n3. 测试增强主题获取...")
            enhanced_themes = await data_fetcher.get_all_active_themes_with_context()
            
            logger.info(f"   获取到 {len(enhanced_themes)} 个增强主题")
            
            if enhanced_themes:
                sample_theme = enhanced_themes[0]
                logger.info(f"\n   增强主题示例:")
                logger.info(f"       名称: {sample_theme.get('name', 'N/A')}")
                logger.info(f"       描述长度: {len(sample_theme.get('description', ''))}")
                logger.info(f"       关键词数量: {len(sample_theme.get('keywords', []))}")
                logger.info(f"       相关事件: {len(sample_theme.get('related_events', []))}")
                
                # 检查上下文是否完整
                has_full_context = sample_theme.get('has_full_context', False)
                logger.info(f"       has_full_context: {'✅' if has_full_context else '❌'}")
                
                if not has_full_context:
                    logger.error(f"       ⚠️  主题缺少完整上下文!")
            
            # 4. 模拟AI分析器的数据访问流程
            logger.info("\n4. 模拟AI分析器数据访问流程...")
            
            # 获取事件完整数据
            full_event = await db_manager.get_event(event_id)
            if full_event:
                logger.info(f"   ✅ 获取到事件完整数据")
                logger.info(f"       标题: {full_event.get('title', '')[:50]}...")
                logger.info(f"       内容长度: {len(full_event.get('full_content', ''))}")
                logger.info(f"       has_full_content: {full_event.get('has_full_content', False)}")
            else:
                logger.error(f"   ❌ 无法获取事件完整数据")
            
            # 获取主题完整数据
            if all_themes:
                for theme in all_themes[:2]:
                    theme_id = theme.get('id')
                    if theme_id:
                        full_theme = await db_manager.get_theme(theme_id)
                        if full_theme:
                            logger.info(f"   ✅ 获取到主题完整数据: {full_theme.get('name', '')}")
                        else:
                            logger.warning(f"   ⚠️  无法获取主题完整数据: {theme_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ AI分析器数据访问测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_full_ai_analysis_pipeline(self, db_manager):
        """测试完整AI分析流程"""
        logger.info("\n" + "="*80)
        logger.info("🚀 测试完整AI分析流程")
        logger.info("="*80)
        
        try:
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 创建AI分析器
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                logger.error("❌ DEEPSEEK_API_KEY未设置")
                return False
            
            llm_config = {
                'api_key': api_key,
                'model_name': 'deepseek-chat',
                'max_retries': 1,  # 测试时减少重试
                'timeout': 30,
                'temperature': 0.1
            }
            
            llm_parser = ReliableDeepSeekParser(config=llm_config)
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            # 创建主题发现模块
            from database_service.pure_data_fetcher import PureDataFetcher
            data_fetcher = PureDataFetcher(db_manager)
            
            discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            # 测试前3个事件
            test_count = min(3, len(self.test_events))
            
            for i in range(test_count):
                event = self.test_events[i]
                event_id = event.get('news_id', f'test_{i}')
                
                logger.info(f"\n🔍 测试AI分析 - 事件 {i+1}: {event_id}")
                logger.info(f"   标题: {event.get('original_news', {}).get('title', '')[:60]}...")
                
                try:
                    # 🔥 关键：记录分析前的事件数据状态
                    logger.info("   分析前事件数据检查:")
                    logger.info(f"       原始内容长度: {len(event.get('original_news', {}).get('content', ''))}")
                    
                    # 从数据库获取完整事件
                    db_event = await db_manager.get_event(event_id)
                    if db_event:
                        logger.info(f"       数据库内容长度: {len(db_event.get('full_content', ''))}")
                        logger.info(f"       has_full_content: {db_event.get('has_full_content', False)}")
                    
                    # 获取现有主题
                    relevant_themes = await discovery.related_theme_fetcher.fetch_relevant_themes(event)
                    logger.info(f"       现有主题数: {len(relevant_themes)}")
                    
                    for theme in relevant_themes[:2]:
                        logger.info(f"       主题: {theme.get('name', '')}")
                        logger.info(f"           描述: {theme.get('description', '')[:30]}...")
                    
                    # 执行AI分析
                    logger.info("   🤖 开始AI分析...")
                    result = await discovery.process_event(event)
                    
                    action = result.get('action', 'ERROR')
                    theme_info = result.get('theme', {})
                    theme_name = theme_info.get('name', '') if isinstance(theme_info, dict) else str(theme_info)
                    
                    logger.info(f"   📊 AI分析结果:")
                    logger.info(f"       决策: {action}")
                    logger.info(f"       主题: {theme_name}")
                    
                    if 'analysis' in result:
                        analysis = result['analysis']
                        if 'theme_extraction' in analysis:
                            extracted = analysis['theme_extraction'].get('extracted_name', '')
                            logger.info(f"       提取名称: {extracted}")
                        
                        if 'similarity_analysis' in analysis:
                            best_match = analysis['similarity_analysis'].get('best_match_theme', '')
                            score = analysis['similarity_analysis'].get('similarity_score', 0)
                            logger.info(f"       最佳匹配: {best_match} (分数: {score})")
                    
                except Exception as e:
                    logger.error(f"   ❌ AI分析失败: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 完整AI分析流程测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def generate_summary_report(self):
        """生成总结报告"""
        logger.info("\n" + "="*80)
        logger.info("📊 数据完整性测试总结")
        logger.info("="*80)
        
        # 这里可以添加更多统计信息
        logger.info(f"✅ 测试完成")
        logger.info(f"   测试事件数: {len(self.test_events)}")
        logger.info(f"   建议重点关注:")
        logger.info(f"   1. 数据库内容是否与原始内容一致")
        logger.info(f"   2. 主题数据是否包含完整上下文")
        logger.info(f"   3. AI是否能获取到完整的事件和主题数据")


async def main():
    """主函数"""
    # 检查环境
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ DEEPSEEK_API_KEY环境变量未设置")
        print("   export DEEPSEEK_API_KEY='your-api-key-here'")
        return 1
    
    tester = DataIntegrityTester()
    
    try:
        # 1. 加载测试事件
        await tester.load_test_events(count=10)
        
        if not tester.test_events:
            logger.error("❌ 没有找到测试事件")
            return 1
        
        # 2. 测试内存数据库
        db_manager = await tester.test_memory_database()
        if not db_manager:
            return 1
        
        # 3. 测试AI分析器数据访问
        data_access_ok = await tester.test_ai_analyzer_data_access(db_manager)
        if not data_access_ok:
            logger.error("❌ AI分析器数据访问测试失败")
        
        # 4. 测试完整AI分析流程
        ai_pipeline_ok = await tester.test_full_ai_analysis_pipeline(db_manager)
        if not ai_pipeline_ok:
            logger.error("❌ 完整AI分析流程测试失败")
        
        # 5. 生成报告
        tester.generate_summary_report()
        
        if data_access_ok and ai_pipeline_ok:
            print("\n✅ 所有测试通过!")
            return 0
        else:
            print("\n⚠️  测试未完全通过，请查看日志")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        return 130
    except Exception as e:
        logger.error(f"❌ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)