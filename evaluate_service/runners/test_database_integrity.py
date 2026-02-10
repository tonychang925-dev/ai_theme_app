#!/usr/bin/env python3
"""
增强版主题发现组件集成测试 - 强化版
使用真实数据验证数据库完整性和主题聚合能力
"""
import asyncio
import logging
import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import traceback

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class EnhancedThemeDiscoveryTester:
    """增强版主题发现组件测试器 - 强化版"""
    
    def __init__(self):
        self.data_dir = project_root / "evaluate_service" / "data" / "processed"
        self.test_events = []
        self.db_manager = None
        self.theme_discovery = None
        self.ai_parsers = []
        self.test_results = []
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """确保关闭所有资源"""
        await self._close_all_resources()
    
    async def _close_all_resources(self):
        """关闭所有AI解析器资源"""
        for llm_parser in self.ai_parsers:
            if hasattr(llm_parser, 'close'):
                try:
                    await llm_parser.close()
                    logger.debug("✅ 关闭AI解析器")
                except Exception as e:
                    logger.warning(f"关闭AI解析器失败: {e}")
        
        if self.db_manager and hasattr(self.db_manager, 'disconnect'):
            try:
                await self.db_manager.disconnect()
                logger.debug("✅ 断开数据库连接")
            except Exception as e:
                logger.warning(f"断开数据库连接失败: {e}")
    
    async def setup(self):
        """严格初始化"""
        # 检查API密钥
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("❌🔥 必须设置真实的DEEPSEEK_API_KEY环境变量")
        
        if api_key.startswith('sk-test'):
            raise ValueError("❌🔥 请使用真实的DeepSeek API密钥，而不是测试密钥")
        
        logger.info("✅ API密钥验证通过")
        
        # 清空之前的数据
        await self._clean_database()
        
        # 加载测试数据
        await self._load_test_data()
        
        # 创建EnhancedThemeDiscovery实例
        await self._create_theme_discovery()
    
    async def _clean_database(self):
        """清空数据库"""
        try:
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.config import DatabaseConfig
            
            db_config = DatabaseConfig()
            self.db_manager = MemoryDatabaseManager(db_config)
            await self.db_manager.connect()
            
            # 清空所有数据
            if hasattr(self.db_manager, 'clear_all_data'):
                await self.db_manager.clear_all_data()
            
            logger.info("🔥 数据库已清空，开始严格测试")
        except Exception as e:
            logger.error(f"❌ 初始化数据库失败: {e}")
            raise
    
    async def _load_test_data(self):
        """加载测试数据 - 强化版：加载更多数据"""
        events_path = self.data_dir / "validation_events_fixed.json"
        
        if not events_path.exists():
            # 尝试从raw目录加载
            raw_path = project_root / "evaluate_service" / "data" / "raw" / "validation_dataset.json"
            if raw_path.exists():
                events_path = raw_path
                logger.info(f"📂 使用原始数据文件: {raw_path}")
            else:
                raise FileNotFoundError(f"找不到测试数据文件: {events_path}")
        
        logger.info(f"📂 加载测试数据: {events_path}")
        
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 解析数据结构
            if isinstance(data, list):
                all_events = data
            elif isinstance(data, dict) and 'events' in data:
                all_events = data['events']
            else:
                all_events = []
            
            logger.info(f"📊 原始数据中共有 {len(all_events)} 个事件")
            
            # 🔥 强化：加载前30个事件进行测试
            loaded_events = []
            for i, event in enumerate(all_events[:76]):  # 取前30个
                if not isinstance(event, dict):
                    continue
                
                event_id = event.get('news_id', f'event_{i}')
                
                # 验证事件数据结构
                if 'original_news' not in event:
                    logger.warning(f"事件 {event_id} 缺少 original_news 字段")
                    continue
                
                original_news = event['original_news']
                if 'content' not in original_news or not original_news['content']:
                    logger.warning(f"事件 {event_id} 内容为空")
                    continue
                
                loaded_events.append(event)
            
            self.test_events = loaded_events
            logger.info(f"✅🔥 加载 {len(self.test_events)} 个有效新闻事件进行强化测试")
            
            # 显示事件统计
            event_types = {}
            for event in self.test_events:
                event_type = event.get('event_info', {}).get('event_type', '未知')
                event_types[event_type] = event_types.get(event_type, 0) + 1
            
            logger.info(f"📊 事件类型分布: {event_types}")
            
        except Exception as e:
            logger.error(f"❌ 加载测试数据失败: {e}")
            traceback.print_exc()
            raise
    
    async def _create_theme_discovery(self):
        """创建EnhancedThemeDiscovery实例"""
        try:
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscoveryFactory
            
            # 创建数据获取器
            data_fetcher = PureDataFetcher(self.db_manager)
            
            # 使用工厂创建EnhancedThemeDiscovery
            logger.info("🔧 创建EnhancedThemeDiscovery实例...")
            
            try:
                # 尝试使用工厂类创建
                self.theme_discovery = await EnhancedThemeDiscoveryFactory.create(
                    data_fetcher=data_fetcher,
                    similarity_analyzer_config={'max_retries': 3, 'timeout': 60}
                )
                logger.info("✅ 使用工厂类创建成功")
            except Exception as factory_error:
                logger.warning(f"工厂类创建失败: {factory_error}")
                logger.info("🔄 尝试直接创建分析器并组装...")
                
                # 直接创建组件并组装
                from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
                from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
                
                llm_parser = ReliableDeepSeekParser(config={'max_retries': 3, 'timeout': 60})
                self.ai_parsers.append(llm_parser)
                
                # 创建AI分析器
                similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
                
                # 创建EnhancedThemeDiscovery
                from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
                self.theme_discovery = EnhancedThemeDiscovery(
                    data_fetcher=data_fetcher,
                    similarity_analyzer=similarity_analyzer,
                    new_theme_threshold=0.4
                )
                logger.info("✅ 直接组装创建成功")
            
            # 健康检查
            if await self.theme_discovery.health_check():
                logger.info("✅ EnhancedThemeDiscovery健康检查通过")
            else:
                raise ValueError("EnhancedThemeDiscovery健康检查失败")
                
        except Exception as e:
            logger.error(f"❌ 创建EnhancedThemeDiscovery失败: {e}")
            traceback.print_exc()
            raise

    # 🔥 新增：数据库完整性验证测试
    async def test_database_integrity(self):
        """测试数据库完整性 - 强化版"""
        logger.info("\n🧪" + "="*80)
        logger.info("🧪 开始数据库完整性强化测试")
        logger.info("="*80)
        
        test_results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'details': []
        }
        
        try:
            # 测试1：检查数据库是否为空
            test_results['total_tests'] += 1
            stats = await self.db_manager.get_stats()
            if stats['total_events'] == 0:
                logger.info("✅ 测试1通过：数据库初始为空")
                test_results['passed_tests'] += 1
            else:
                logger.error("❌ 测试1失败：数据库初始不为空")
                test_results['failed_tests'] += 1
            
            # 测试2：保存事件到数据库
            test_results['total_tests'] += 1
            test_event = {
                'news_id': 'TEST_EVENT_001',
                'original_news': {
                    'title': '测试新闻标题',
                    'content': '这是一个测试新闻内容，用于验证数据库完整性。',
                    'content_length': 30,
                    'date': '2025-01-01'
                },
                'event_info': {
                    'event_type': '测试类型',
                    'impact_industries': ['测试行业'],
                    'direction': '利好',
                    'event_confidence': 0.9
                }
            }
            
            saved_id = await self._save_event_to_db(test_event)
            if saved_id:
                logger.info(f"✅ 测试2通过：事件保存成功，ID: {saved_id}")
                test_results['passed_tests'] += 1
            else:
                logger.error("❌ 测试2失败：事件保存失败")
                test_results['failed_tests'] += 1
            
            # 测试3：验证事件在数据库中
            test_results['total_tests'] += 1
            event_data = await self.db_manager.get_event('TEST_EVENT_001')
            if event_data and event_data.get('original_news', {}).get('content'):
                logger.info(f"✅ 测试3通过：事件内容正确存储，内容长度: {len(event_data['original_news']['content'])}")
                test_results['passed_tests'] += 1
            else:
                logger.error("❌ 测试3失败：事件内容未正确存储")
                test_results['failed_tests'] += 1
            
            # 测试4：创建主题
            test_results['total_tests'] += 1
            theme_record = await self.db_manager.create_theme(
                name='测试主题',
                description='测试主题描述',
                keywords=['测试', '验证'],
                discovery_source='integrity_test',
                discovery_confidence=0.95
            )
            
            if theme_record:
                logger.info(f"✅ 测试4通过：主题创建成功，ID: {theme_record.id}")
                test_results['passed_tests'] += 1
                
                # 测试5：创建事件-主题关联
                test_results['total_tests'] += 1
                relation = await self.db_manager.create_event_theme_relation(
                    event_id='TEST_EVENT_001',
                    theme_id=theme_record.id,
                    confidence=0.8,
                    confidence_level='high'
                )
                
                if relation:
                    logger.info("✅ 测试5通过：事件-主题关联创建成功")
                    test_results['passed_tests'] += 1
                    
                    # 测试6：验证主题的related_events字段
                    test_results['total_tests'] += 1
                    theme_data = await self.db_manager.get_theme(theme_record.id)
                    if theme_data and 'related_events' in theme_data and 'TEST_EVENT_001' in theme_data['related_events']:
                        logger.info(f"✅ 测试6通过：主题的related_events字段正确更新，包含事件: TEST_EVENT_001")
                        test_results['passed_tests'] += 1
                    else:
                        logger.error(f"❌ 测试6失败：主题的related_events字段未正确更新")
                        if theme_data:
                            logger.error(f"   当前related_events: {theme_data.get('related_events', [])}")
                        test_results['failed_tests'] += 1
                else:
                    logger.error("❌ 测试5失败：事件-主题关联创建失败")
                    test_results['failed_tests'] += 1
            else:
                logger.error("❌ 测试4失败：主题创建失败")
                test_results['failed_tests'] += 1
            
            # 测试7：验证get_all_active_themes返回正确的字段
            test_results['total_tests'] += 1
            all_themes = await self.db_manager.get_all_active_themes(limit=10)
            if all_themes:
                first_theme = all_themes[0]
                required_fields = ['id', 'name', 'description', 'keywords', 'related_events']
                missing_fields = [field for field in required_fields if field not in first_theme]
                
                if not missing_fields:
                    logger.info("✅ 测试7通过：get_all_active_themes返回所有必需字段")
                    test_results['passed_tests'] += 1
                else:
                    logger.error(f"❌ 测试7失败：缺少字段: {missing_fields}")
                    logger.error(f"   现有字段: {list(first_theme.keys())}")
                    test_results['failed_tests'] += 1
            else:
                logger.error("❌ 测试7失败：get_all_active_themes返回空列表")
                test_results['failed_tests'] += 1
            
            # 最终统计
            logger.info("\n📊 数据库完整性测试结果:")
            logger.info(f"   总测试数: {test_results['total_tests']}")
            logger.info(f"   通过测试: {test_results['passed_tests']}")
            logger.info(f"   失败测试: {test_results['failed_tests']}")
            
            return test_results['failed_tests'] == 0
            
        except Exception as e:
            logger.error(f"❌ 数据库完整性测试异常: {e}")
            traceback.print_exc()
            return False

    # 🔥 新增：运行30个事件的强化测试
    async def run_enhanced_test(self):
        """运行增强测试：处理30个事件并验证结果"""
        logger.info("\n🚀" + "="*80)
        logger.info("🚀 开始30个事件的增强测试")
        logger.info("="*80)
        
        results = []
        theme_evolution = []  # 记录主题演变过程
        
        for i, event in enumerate(self.test_events):
            event_id = event.get('news_id', f'event_{i}')
            
            logger.info(f"\n📌 处理事件 {i+1}/{len(self.test_events)}: {event_id}")
            
            try:
                # 1. 保存事件到数据库
                await self._save_event_to_db(event)
                
                # 2. 记录处理前的主题状态
                themes_before = await self.db_manager.get_all_active_themes(limit=100)
                theme_count_before = len(themes_before)
                theme_names_before = [t.get('name', '') for t in themes_before]
                
                logger.info(f"   处理前主题数: {theme_count_before}")
                if theme_count_before > 0:
                    logger.info(f"   处理前主题列表: {theme_names_before}")
                
                # 3. 使用EnhancedThemeDiscovery处理事件
                discovery_result = await self.theme_discovery.process_event(event)
                
                # 4. 处理结果
                action = discovery_result.get('action', '')
                theme_info = discovery_result.get('theme', {})
                theme_name = theme_info.get('name', '未知主题') if isinstance(theme_info, dict) else str(theme_info)
                
                if action == 'CREATE_NEW':
                    await self._create_new_theme_in_db(theme_name, event_id, discovery_result)
                    logger.info(f"   ✅ 创建新主题: {theme_name}")
                elif action == 'CLUSTER':
                    await self._create_theme_relation(event_id, theme_name, discovery_result)
                    logger.info(f"   🔗 归并到主题: {theme_name}")
                
                # 5. 记录处理后的主题状态
                themes_after = await self.db_manager.get_all_active_themes(limit=100)
                theme_count_after = len(themes_after)
                theme_names_after = [t.get('name', '') for t in themes_after]
                
                # 6. 验证主题数据完整性
                validation_ok = await self._validate_theme_data(theme_name if action == 'CREATE_NEW' else theme_name)
                
                # 7. 记录结果
                result = {
                    'event_id': event_id,
                    'action': action,
                    'theme_name': theme_name,
                    'theme_count_before': theme_count_before,
                    'theme_count_after': theme_count_after,
                    'new_theme_created': action == 'CREATE_NEW',
                    'validation_passed': validation_ok,
                    'processing_time': discovery_result.get('metadata', {}).get('processing_time', 'N/A')
                }
                
                results.append(result)
                
                # 记录主题演变
                theme_evolution.append({
                    'event_index': i,
                    'event_id': event_id,
                    'themes_before': theme_names_before,
                    'themes_after': theme_names_after,
                    'action': action,
                    'theme_name': theme_name
                })
                
                # 进度报告
                if (i + 1) % 5 == 0:
                    self._log_progress(i + 1, len(self.test_events), results)
                
                # API限流
                if i < len(self.test_events) - 1:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"❌ 处理事件 {event_id} 失败: {e}")
                traceback.print_exc()
                results.append({
                    'event_id': event_id,
                    'error': str(e),
                    'success': False
                })
                
                await asyncio.sleep(2)
        
        # 生成详细报告
        await self._generate_enhanced_report(results, theme_evolution)
        
        return results
    
    async def _validate_theme_data(self, theme_name: str) -> bool:
        """验证主题数据完整性"""
        try:
            # 获取主题
            theme = await self.db_manager.get_theme_by_name(theme_name)
            if not theme:
                logger.warning(f"⚠️  主题 '{theme_name}' 不存在于数据库中")
                return False
            
            # 检查相关字段
            required_fields = ['id', 'name', 'related_events']
            missing_fields = [field for field in required_fields if field not in theme]
            
            if missing_fields:
                logger.warning(f"⚠️  主题 '{theme_name}' 缺少字段: {missing_fields}")
                return False
            
            # 检查 related_events 是否列表
            related_events = theme.get('related_events', [])
            if not isinstance(related_events, list):
                logger.warning(f"⚠️  主题 '{theme_name}' 的 related_events 不是列表类型")
                return False
            
            # 如果有关联事件，检查事件是否存在
            for event_id in related_events[:3]:  # 只检查前3个
                event_data = await self.db_manager.get_event(event_id)
                if not event_data:
                    logger.warning(f"⚠️  主题 '{theme_name}' 的关联事件 {event_id} 不存在")
                    return False
            
            logger.debug(f"✅ 主题 '{theme_name}' 数据完整性验证通过")
            return True
            
        except Exception as e:
            logger.warning(f"主题验证异常: {e}")
            return False

    def _log_progress(self, current, total, results):
        """记录进度"""
        created_count = sum(1 for r in results if r.get('new_theme_created'))
        clustered_count = sum(1 for r in results if r.get('action') == 'CLUSTER')
        
        logger.info(f"📊 进度: {current}/{total} ({current/total*100:.1f}%)")
        logger.info(f"   创建主题: {created_count}, 归并主题: {clustered_count}")

    async def _generate_enhanced_report(self, results, theme_evolution):
        """生成增强版测试报告"""
        logger.info("\n📈" + "="*80)
        logger.info("📈 30事件增强测试详细报告")
        logger.info("="*80)
        
        # 基本统计
        total_events = len(results)
        successful_events = sum(1 for r in results if not r.get('error'))
        created_themes = sum(1 for r in results if r.get('new_theme_created'))
        clustered_themes = sum(1 for r in results if r.get('action') == 'CLUSTER')
        
        logger.info(f"📊 基本统计:")
        logger.info(f"   总事件数: {total_events}")
        logger.info(f"   成功处理: {successful_events}")
        logger.info(f"   创建主题: {created_themes}")
        logger.info(f"   归并主题: {clustered_themes}")
        
        # 主题演变分析
        logger.info(f"\n🎯 主题演变过程:")
        for evolution in theme_evolution[-10:]:  # 显示最后10个事件的演变
            if evolution['action'] == 'CREATE_NEW':
                logger.info(f"   事件 {evolution['event_index']+1}: {evolution['event_id']}")
                logger.info(f"     🆕 创建新主题: {evolution['theme_name']}")
                logger.info(f"     主题数变化: {len(evolution['themes_before'])} → {len(evolution['themes_after'])}")
        
        # 最终主题统计
        final_themes = await self.db_manager.get_all_active_themes(limit=100)
        logger.info(f"\n🏷️  最终主题列表 (共{len(final_themes)}个):")
        
        for i, theme in enumerate(final_themes[:20]):  # 显示前20个主题
            theme_name = theme.get('name', '')
            related_events = theme.get('related_events', [])
            event_count = len(related_events)
            
            logger.info(f"   {i+1}. {theme_name} ({event_count}个事件)")
            if event_count > 0:
                # 显示前3个事件ID
                logger.info(f"      关联事件: {related_events[:3]}")
        
        # 数据库最终状态
        stats = await self.db_manager.get_stats()
        logger.info(f"\n📦 数据库最终状态:")
        logger.info(f"   总事件数: {stats.get('total_events', 0)}")
        logger.info(f"   总主题数: {stats.get('total_themes', 0)}")
        logger.info(f"   总关联数: {stats.get('total_relations', 0)}")

    # 原有方法保持不变（但我会保持它们完整）
    async def _save_event_to_db(self, event: Dict):
        """保存事件到数据库"""
        event_id = event.get('news_id')
        
        db_event = {
            'id': event_id,
            'news_id': event_id,
            'title': event.get('original_news', {}).get('title', ''),
            'full_content': event.get('original_news', {}).get('content', ''),
            'content_length': len(event.get('original_news', {}).get('content', '')),
            'has_full_content': True,
            'original_news': event.get('original_news', {}),
            'event_info': event.get('event_info', {}),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        saved_id = await self.db_manager.create_or_update_event(db_event)
        if not saved_id:
            raise ValueError(f"保存事件失败: {event_id}")
        
        return saved_id
    
    async def _create_new_theme_in_db(self, theme_name: str, event_id: str, discovery_result: Dict):
        """根据EnhancedThemeDiscovery结果创建新主题"""
        theme_info = discovery_result.get('theme', {})
        analysis = discovery_result.get('analysis', {})
        
        theme_record = await self.db_manager.create_theme(
            name=theme_name,
            description=theme_info.get('description', '基于EnhancedThemeDiscovery创建的主题'),
            keywords=theme_info.get('keywords', self._extract_keywords_from_discovery(discovery_result)),
            discovery_source="enhanced_discovery_test",
            discovery_confidence=theme_info.get('confidence', 0.8)
        )
        
        if not theme_record:
            raise ValueError(f"创建主题失败: {theme_name}")
        
        # 创建关联
        await self.db_manager.create_event_theme_relation(
            event_id=event_id,
            theme_id=theme_record.id,
            confidence=theme_info.get('confidence', 0.8),
            confidence_level="high"
        )
    
    async def _create_theme_relation(self, event_id: str, theme_name: str, discovery_result: Dict):
        """根据EnhancedThemeDiscovery结果创建事件-主题关联"""
        # 查找主题ID
        all_themes = await self.db_manager.get_all_active_themes(limit=100)
        theme_id = None
        
        for theme in all_themes:
            if theme.get('name') == theme_name:
                theme_id = theme.get('id')
                break
        
        if not theme_id:
            raise ValueError(f"找不到主题: {theme_name}")
        
        # 创建关联
        confidence = discovery_result.get('analysis', {}).get('recommendation', {}).get('confidence', 0.8)
        
        await self.db_manager.create_event_theme_relation(
            event_id=event_id,
            theme_id=theme_id,
            confidence=confidence,
            confidence_level="high"
        )
    
    def _extract_keywords_from_discovery(self, discovery_result: Dict) -> List[str]:
        """从EnhancedThemeDiscovery结果提取关键词"""
        keywords = ['AI', 'AR']
        
        theme_info = discovery_result.get('theme', {})
        theme_name = theme_info.get('name', '')
        
        if '眼镜' in theme_name:
            keywords.append('智能眼镜')
        if '技术' in theme_name:
            keywords.append('技术突破')
        if '发布' in theme_name:
            keywords.append('产品发布')
        
        # 从主题信息中获取额外的关键词
        additional_keywords = theme_info.get('keywords', [])
        if isinstance(additional_keywords, list):
            keywords.extend(additional_keywords)
        
        # 去重并限制数量
        return list(set(keywords))[:10]

async def main():
    """主函数 - 强化版"""
    # 环境检查
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY环境变量未设置")
        return 1
    
    print(f"✅ 检测到API密钥，开始增强版主题发现组件强化测试...")
    print(f"📊 将测试30个事件的数据完整性和主题聚合能力")
    
    # 使用上下文管理器确保资源释放
    async with EnhancedThemeDiscoveryTester() as tester:
        try:
            # 1. 初始化
            await tester.setup()
            
            # 2. 🔥 运行数据库完整性测试
            print("\n🧪 运行数据库完整性测试...")
            db_integrity_ok = await tester.test_database_integrity()
            
            if not db_integrity_ok:
                print("❌ 数据库完整性测试失败，停止测试")
                return 1
            
            print("✅ 数据库完整性测试通过")
            
            # 3. 🔥 运行30个事件的增强测试
            print("\n🚀 运行30个事件的增强测试...")
            results = await tester.run_enhanced_test()
            
            # 4. 最终统计
            successful_events = sum(1 for r in results if not r.get('error'))
            total_events = len(results)
            
            print(f"\n🎉 增强测试完成!")
            print(f"📊 结果: {successful_events}/{total_events} 个事件成功处理")
            
            if successful_events == total_events:
                return 0
            else:
                print(f"⚠️  部分测试失败，请查看日志")
                return 1
                
        except KeyboardInterrupt:
            print("\n\n⚠️  测试被用户中断")
            return 130
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            traceback.print_exc()
            return 1

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)