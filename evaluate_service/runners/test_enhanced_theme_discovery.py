#!/usr/bin/env python3
"""
增强版主题发现组件集成测试
使用EnhancedThemeDiscovery组件，验证其主题聚合能力
"""
import asyncio
import logging
import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

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
    """增强版主题发现组件测试器"""
    
    def __init__(self):
        self.data_dir = project_root / "evaluate_service" / "data" / "processed"
        self.test_events = []
        self.db_manager = None
        self.theme_discovery = None
        self.ai_parsers = []  # 记录创建的AI解析器，用于最后关闭
    
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
        """加载测试数据"""
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
            
            # 只取AI/AR相关事件
            ai_ar_events = []
            for event in all_events[:30]:
                if not isinstance(event, dict):
                    continue
                
                event_id = event.get('news_id', 'unknown')
                title = event.get('original_news', {}).get('title', '').lower()
                
                # 扩展关键词匹配
                keywords = ['ai', 'ar', '智能', '眼镜', 'meta', 'oakley', 'apple', 'nvidia', '英伟达', '专利']
                is_related = any(keyword in title for keyword in keywords)
                
                if is_related and 'original_news' in event:
                    original_content = event['original_news'].get('content', '')
                    if original_content and len(original_content) >= 76:
                        ai_ar_events.append(event)
                        if len(ai_ar_events) >= 76:
                            break
            
            self.test_events = ai_ar_events
            logger.info(f"✅🔥 加载 {len(self.test_events)} 个相关新闻事件")
            
        except Exception as e:
            logger.error(f"❌ 加载测试数据失败: {e}")
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
            import traceback
            traceback.print_exc()
            raise
    
    async def test_all_events(self):
        """测试所有事件"""
        results = []
        
        for i in range(len(self.test_events)):
            try:
                result = await self.test_single_event(i)
                results.append((i, True, result))
            except Exception as e:
                results.append((i, False, str(e)))
                logger.error(f"❌ 事件 {i+1} 测试失败: {e}")
        
        # 生成测试报告
        await self.generate_test_report(results)
        
        return all(success for _, success, _ in results)
    
    async def test_single_event(self, event_index: int):
        """使用EnhancedThemeDiscovery测试单个事件"""
        event = self.test_events[event_index]
        event_id = event.get('news_id', f'event_{event_index}')
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 测试事件 {event_index+1}: {event_id} (使用EnhancedThemeDiscovery)")
        logger.info(f"{'='*80}")
        
        # 1. 保存事件到数据库
        await self._save_event_to_db(event)
        
        # 2. 使用EnhancedThemeDiscovery处理事件
        logger.info("🤖 开始AI分析 (使用EnhancedThemeDiscovery)...")
        
        try:
            # 调用EnhancedThemeDiscovery的process_event方法
            discovery_result = await self.theme_discovery.process_event(event)
            
            # 3. 处理结果
            action = discovery_result.get('action', '')
            
            if action == 'ERROR':
                raise ValueError(f"EnhancedThemeDiscovery处理失败: {discovery_result.get('error', '未知错误')}")
            
            # 获取主题信息
            theme_info = discovery_result.get('theme', {})
            theme_name = theme_info.get('name', '未知主题')
            
            # 4. 在数据库中创建相应的主题和关联
            if action == 'CREATE_NEW':
                await self._create_new_theme_in_db(theme_name, event_id, discovery_result)
                logger.info(f"✅ EnhancedThemeDiscovery创建新主题: {theme_name}")
            elif action == 'CLUSTER':
                await self._create_theme_relation(event_id, theme_name, discovery_result)
                logger.info(f"✅ EnhancedThemeDiscovery归并到现有主题: {theme_name}")
            
            # 5. 从analysis中提取相似度信息
            analysis = discovery_result.get('analysis', {})
            similarity_score = analysis.get('similarity_analysis', {}).get('similarity_score', 0)
            extracted_name = analysis.get('theme_extraction', {}).get('extracted_name', '')
            
            return {
                'event_id': event_id,
                'action': action,
                'theme_name': theme_name,
                'similarity_score': similarity_score,
                'extracted_name': extracted_name,
                'discovery_result': discovery_result
            }
            
        except Exception as e:
            logger.error(f"❌ EnhancedThemeDiscovery处理失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
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
    
    async def generate_test_report(self, results: List):
        """生成测试报告"""
        logger.info(f"\n{'='*80}")
        logger.info("📊 增强版主题发现组件测试报告")
        logger.info(f"{'='*80}")
        
        total = len(results)
        passed = sum(1 for _, success, _ in results if success)
        failed = total - passed
        
        logger.info(f"📈 总体结果: {passed}/{total} 通过 ({passed/total*100:.1f}%)")
        
        if passed > 0:
            logger.info("\n✅ 通过的事件:")
            for i, success, result in results:
                if success:
                    event_id = result.get('event_id', f'event_{i}')
                    action = result.get('action', '')
                    theme_name = result.get('theme_name', '')
                    similarity = result.get('similarity_score', 0)
                    extracted_name = result.get('extracted_name', '')
                    
                    logger.info(f"  事件 {i+1}: {event_id}")
                    logger.info(f"    操作: {action}, 主题: {theme_name}, 相似度: {similarity:.3f}")
                    logger.info(f"    提取名称: {extracted_name}")
        
        if failed > 0:
            logger.info("\n❌ 失败的事件:")
            for i, success, error in results:
                if not success:
                    logger.info(f"  事件 {i+1}: {error}")
        
        # 数据库最终状态
        if self.db_manager:
            stats = await self.db_manager.get_stats()
            logger.info(f"\n📦 数据库最终状态:")
            logger.info(f"  总事件数: {stats.get('total_events', 0)}")
            logger.info(f"  总主题数: {stats.get('total_themes', 0)}")
            logger.info(f"  总关联数: {stats.get('total_relations', 0)}")
            
            # 显示所有主题
            all_themes = await self.db_manager.get_all_active_themes(limit=20)
            if all_themes:
                logger.info(f"\n🏷️  创建的主题列表:")
                for i, theme in enumerate(all_themes):
                    theme_name = theme.get('name', '')
                    event_count = len(theme.get('related_events', []))
                    logger.info(f"  {i+1}. {theme_name} ({event_count}个事件)")
    
    async def analyze_performance_comparison(self, original_test_log_path: str):
        """分析与原测试的性能对比"""
        try:
            # 读取原测试日志
            with open(original_test_log_path, 'r', encoding='utf-8') as f:
                original_log = f.read()
            
            # 提取关键指标
            import re
            
            # 从原日志提取主题数量
            original_theme_match = re.search(r'总主题数:\s*(\d+)', original_log)
            original_themes = int(original_theme_match.group(1)) if original_theme_match else 0
            
            # 从当前数据库获取主题数量
            stats = await self.db_manager.get_stats()
            current_themes = stats.get('total_themes', 0)
            
            logger.info(f"\n{'='*80}")
            logger.info("🔍 性能对比分析")
            logger.info(f"{'='*80}")
            logger.info(f"原测试 (直接使用AIThemeSimilarityAnalyzer):")
            logger.info(f"  - 主题数量: {original_themes}")
            logger.info(f"新测试 (使用EnhancedThemeDiscovery):")
            logger.info(f"  - 主题数量: {current_themes}")
            
            if current_themes == original_themes:
                logger.info(f"✅ 主题聚合结果一致!")
            elif current_themes < original_themes:
                logger.info(f"📈 EnhancedThemeDiscovery聚合度更高!")
            else:
                logger.info(f"⚠️  EnhancedThemeDiscovery聚合度较低")
                
        except Exception as e:
            logger.warning(f"性能对比分析失败: {e}")

async def main():
    """主函数"""
    # 环境检查
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY环境变量未设置")
        return 1
    
    print(f"✅ 检测到API密钥，开始增强版主题发现组件测试...")
    
    # 使用上下文管理器确保资源释放
    async with EnhancedThemeDiscoveryTester() as tester:
        try:
            await tester.setup()
            
            # 测试所有事件
            success = await tester.test_all_events()
            
            if success:
                print("\n🎉 EnhancedThemeDiscovery组件测试通过！")
                
                # 可选：与原始测试对比
                original_log_path = project_root / "evaluate_service" / "data" / "results" / "logs" / "test_strict_complete_flow.log"
                if original_log_path.exists():
                    await tester.analyze_performance_comparison(str(original_log_path))
                
                return 0
            else:
                print("\n⚠️  EnhancedThemeDiscovery组件部分测试失败")
                return 1
                
        except KeyboardInterrupt:
            print("\n\n⚠️  测试被用户中断")
            return 130
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)