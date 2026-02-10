# tests/test_integration.py
"""
集成测试脚本 - 验证整个系统改造
测试EnhancedAIThemeClient + EnhancedThemeDiscoveryEngine + DatabaseClient的集成
"""
import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # 假设项目根目录在tests的上级的上级
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntegrationTestRunner:
    """集成测试运行器"""
    
    def __init__(self, test_data_path: str = None):
        """
        初始化测试运行器
        
        Args:
            test_data_path: 测试数据路径
        """
        self.test_data_path = test_data_path or os.path.join(
            project_root, "evaluate_service", "data", "processed", "validation_events_enhanced.json"
        )
        
        # 测试数据
        self.test_events = []
        self.test_results = []
        
        # 组件实例
        self.ai_client = None
        self.db_client = None
        self.engine = None
        self.dedup_engine = None
        
        logger.info(f"集成测试初始化，测试数据路径: {self.test_data_path}")
    
    async def setup(self):
        """设置测试环境"""
        logger.info("开始设置测试环境...")
        
        try:
            # 1. 加载测试数据
            await self._load_test_data()
            
            # 2. 创建EnhancedAIThemeClient
            await self._create_ai_client()
            
            # 3. 创建DatabaseClient（使用内存数据库）
            await self._create_database_client()
            
            # 4. 创建判重引擎（可选）
            await self._create_dedup_engine()
            
            # 5. 创建业务引擎
            await self._create_business_engine()
            
            logger.info("✅ 测试环境设置完成")
            
        except Exception as e:
            logger.error(f"❌ 设置测试环境失败: {e}")
            raise
    
    async def _load_test_data(self):
        """加载测试数据"""
        logger.info(f"加载测试数据: {self.test_data_path}")
        
        if not os.path.exists(self.test_data_path):
            logger.warning(f"测试数据文件不存在: {self.test_data_path}")
            # 创建模拟数据
            self.test_events = self._create_mock_test_data()
            logger.info(f"创建了 {len(self.test_events)} 条模拟测试数据")
            return
        
        try:
            with open(self.test_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 转换数据格式
            self.test_events = []
            for item in data[:20]:  # 只测试前20条，加快测试速度
                event = {
                    'id': item.get('news_id') or item.get('id') or f"test_{len(self.test_events)}",
                    'title': item.get('title', ''),
                    'summary': item.get('summary', ''),
                    'event_type': item.get('event_type', 'unknown'),
                    'impact_industries': item.get('impact_industries', []),
                    'theme_directive': item.get('theme_directive', {
                        'action': 'CREATE_NEW',
                        'confidence': 0.75,
                        'reason': '测试数据'
                    })
                }
                self.test_events.append(event)
            
            logger.info(f"✅ 成功加载 {len(self.test_events)} 条测试数据")
            
        except Exception as e:
            logger.error(f"❌ 加载测试数据失败: {e}")
            self.test_events = self._create_mock_test_data()
    
    def _create_mock_test_data(self) -> List[Dict[str, Any]]:
        """创建模拟测试数据"""
        mock_events = []
        
        test_cases = [
            {
                'id': 'test_ai_duplicate',
                'title': '人工智能技术新突破，AI芯片性能提升50%',
                'summary': '某公司发布新一代AI芯片，性能提升50%',
                'event_type': '技术突破',
                'impact_industries': ['人工智能', '半导体'],
                'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.8, 'reason': 'AI芯片技术突破'}
            },
            {
                'id': 'test_new_energy',
                'title': '固态电池量产在即，新能源汽车迎来革命',
                'summary': '固态电池技术突破，即将实现量产',
                'event_type': '技术突破',
                'impact_industries': ['新能源汽车', '锂电池'],
                'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.85, 'reason': '固态电池技术革命'}
            },
            {
                'id': 'test_semiconductor',
                'title': '国产半导体设备取得重大进展',
                'summary': '国内半导体设备技术取得突破',
                'event_type': '技术突破',
                'impact_industries': ['半导体', '高端制造'],
                'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.78, 'reason': '国产半导体突破'}
            },
            {
                'id': 'test_biotech',
                'title': '基因编辑技术新应用',
                'summary': '基因编辑技术在医疗领域的新应用',
                'event_type': '技术突破',
                'impact_industries': ['生物医药', '基因技术'],
                'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.82, 'reason': '基因编辑新应用'}
            }
        ]
        
        return test_cases
    
    async def _create_ai_client(self):
        """创建EnhancedAIThemeClient"""
        logger.info("创建EnhancedAIThemeClient...")
        
        try:
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            
            # 使用简洁配置
            settings = {
                'USE_ENHANCED_MODE': True,
                'AI_TIMEOUT': 30,
                'AI_MAX_RETRIES': 3
            }
            
            self.ai_client = EnhancedAIThemeClient(settings)
            logger.info("✅ EnhancedAIThemeClient创建成功")
            
        except Exception as e:
            logger.error(f"❌ 创建EnhancedAIThemeClient失败: {e}")
            # 创建模拟客户端
            self.ai_client = self._create_mock_ai_client()
    
    def _create_mock_ai_client(self):
        """创建模拟AI客户端"""
        logger.warning("创建模拟AI客户端（降级模式）")
        
        class MockEnhancedAIThemeClient:
            async def analyze_event_with_context(self, event_data, related_themes):
                event_id = event_data.get('id', '')
                event_title = event_data.get('title', '').lower()
                
                # 简单模拟逻辑
                if '人工智能' in event_title or 'AI' in event_title:
                    return {
                        "decision": "MERGE_INTO",
                        "target_theme_name": "人工智能",
                        "confidence": 0.75,
                        "reason": "模拟：与人工智能相关",
                        "comparison_analysis": "关键词匹配",
                        "source": "mock_ai_client"
                    }
                elif '新能源' in event_title or '电池' in event_title:
                    return {
                        "decision": "CREATE_NEW",
                        "target_theme_name": "固态电池",
                        "confidence": 0.8,
                        "reason": "模拟：新能源技术突破",
                        "comparison_analysis": "新技术方向",
                        "source": "mock_ai_client"
                    }
                else:
                    return {
                        "decision": "CREATE_NEW",
                        "target_theme_name": "新技术题材",
                        "confidence": 0.7,
                        "reason": "模拟：新题材创建",
                        "comparison_analysis": "新领域",
                        "source": "mock_ai_client"
                    }
            
            async def analyze_event_for_themes(self, event_data):
                return {
                    "potential_themes": ["模拟题材"],
                    "certainty": 0.6,
                    "source": "mock_ai_client"
                }
        
        return MockEnhancedAIThemeClient()
    
    async def _create_database_client(self):
        """创建DatabaseClient"""
        logger.info("创建DatabaseClient...")
        
        try:
            # 首先确保database_service模块可用
            from database_service.client import DatabaseClient
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.config import DatabaseConfig
            
            # 创建内存数据库配置
            config = DatabaseConfig()
            config.db_type = "memory"
            
            # 创建内存数据库管理器
            db_manager = MemoryDatabaseManager(config)
            await db_manager.connect()
            
            # 创建数据库客户端
            self.db_client = DatabaseClient(db_manager)
            logger.info("✅ DatabaseClient创建成功（使用内存数据库）")
            
            # 预先创建一些测试主题
            await self._create_test_themes()
            
        except Exception as e:
            logger.error(f"❌ 创建DatabaseClient失败: {e}")
            # 创建模拟客户端
            self.db_client = self._create_mock_database_client()
    
    async def _create_test_themes(self):
        """创建测试主题"""
        if not self.db_client:
            return
        
        test_themes = [
            {
                'name': '人工智能',
                'keywords': ['AI', '人工智能', '机器学习', '深度学习'],
                'description': '人工智能相关主题',
                'discovery_source': 'test',
                'discovery_confidence': 0.8
            },
            {
                'name': '新能源汽车',
                'keywords': ['新能源', '电动车', '电动汽车', '锂电池'],
                'description': '新能源汽车相关主题',
                'discovery_source': 'test',
                'discovery_confidence': 0.75
            },
            {
                'name': '半导体',
                'keywords': ['半导体', '芯片', '集成电路', 'IC'],
                'description': '半导体芯片相关主题',
                'discovery_source': 'test',
                'discovery_confidence': 0.7
            }
        ]
        
        for theme_data in test_themes:
            try:
                await self.db_client.create_theme(**theme_data)
                logger.debug(f"创建测试主题: {theme_data['name']}")
            except Exception as e:
                logger.debug(f"主题可能已存在: {theme_data['name']}")
    
    def _create_mock_database_client(self):
        """创建模拟数据库客户端"""
        logger.warning("创建模拟DatabaseClient（降级模式）")
        
        class MockDatabaseClient:
            def __init__(self):
                self.themes = {}
                self.relations = []
                self._next_theme_id = 1
                self._next_relation_id = 1
            
            async def find_related_themes(self, event_data, limit=5):
                event_title = event_data.get('title', '').lower()
                related = []
                
                # 模拟匹配逻辑
                for theme in self.themes.values():
                    theme_name = theme['name'].lower()
                    theme_keywords = ' '.join(theme.get('keywords', [])).lower()
                    
                    if (theme_name in event_title or 
                        any(kw in event_title for kw in theme.get('keywords', []))):
                        related.append(theme)
                    
                    if len(related) >= limit:
                        break
                
                return related
            
            async def create_theme(self, **kwargs):
                theme_id = self._next_theme_id
                theme = {'id': theme_id, **kwargs}
                self.themes[theme_id] = theme
                self._next_theme_id += 1
                return theme
            
            async def get_theme_by_name(self, name):
                for theme in self.themes.values():
                    if theme['name'] == name:
                        return theme
                return None
            
            async def create_event_theme_relation(self, event_id, theme_id, **kwargs):
                relation_id = self._next_relation_id
                relation = {'id': relation_id, 'event_id': event_id, 'theme_id': theme_id, **kwargs}
                self.relations.append(relation)
                self._next_relation_id += 1
                return relation
            
            async def mark_event_processed(self, event_id):
                pass  # 模拟实现
            
            def transaction(self):
                # 模拟事务
                class MockTransaction:
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass
                return MockTransaction()
            
            async def get_stats(self):
                return {
                    'total_themes': len(self.themes),
                    'total_relations': len(self.relations)
                }
        
        return MockDatabaseClient()
    
    async def _create_dedup_engine(self):
        """创建判重引擎（可选）"""
        logger.info("创建判重引擎...")
        
        try:
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            
            self.dedup_engine = ThemeDeduplicationEngine()
            logger.info("✅ 判重引擎创建成功")
            
        except Exception as e:
            logger.warning(f"创建判重引擎失败: {e}，继续无判重引擎测试")
            self.dedup_engine = None
    
    async def _create_business_engine(self):
        """创建业务引擎"""
        logger.info("创建EnhancedThemeDiscoveryEngine...")
        
        try:
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            
            self.engine = EnhancedThemeDiscoveryEngine(
                ai_client=self.ai_client,
                database_client=self.db_client,
                dedup_engine=self.dedup_engine,
                config={
                    'fast_track_threshold': 0.85,
                    'review_threshold': 0.65,
                    'ignore_threshold': 0.3
                }
            )
            logger.info("✅ EnhancedThemeDiscoveryEngine创建成功")
            
        except Exception as e:
            logger.error(f"❌ 创建业务引擎失败: {e}")
            raise
    
    async def run_tests(self):
        """运行集成测试"""
        logger.info("=" * 60)
        logger.info("开始运行集成测试")
        logger.info("=" * 60)
        
        if not self.engine:
            logger.error("业务引擎未初始化，无法运行测试")
            return
        
        # 记录开始时间
        start_time = datetime.now()
        
        # 运行测试
        self.test_results = await self.engine.batch_process_events(self.test_events)
        
        # 计算统计
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 分析结果
        stats = self._analyze_results()
        
        # 输出报告
        self._generate_report(stats, duration)
        
        return stats
    
    def _analyze_results(self) -> Dict[str, Any]:
        """分析测试结果"""
        if not self.test_results:
            return {}
        
        stats = {
            'total': len(self.test_results),
            'success': 0,
            'failed': 0,
            'created': 0,
            'merged': 0,
            'ignored': 0,
            'decision_types': {},
            'error_types': {}
        }
        
        for result in self.test_results:
            status = result.get('status', 'unknown')
            
            if status in ['created', 'merged', 'ignored']:
                stats['success'] += 1
                stats[status] += 1
            elif status == 'failed':
                stats['failed'] += 1
                error = result.get('error_type', 'unknown')
                stats['error_types'][error] = stats['error_types'].get(error, 0) + 1
            
            # 记录决策类型
            if 'ai_decision' in result:
                decision = result['ai_decision'].get('decision', 'unknown')
                stats['decision_types'][decision] = stats['decision_types'].get(decision, 0) + 1
        
        return stats
    
    def _generate_report(self, stats: Dict[str, Any], duration: float):
        """生成测试报告"""
        logger.info("=" * 60)
        logger.info("集成测试报告")
        logger.info("=" * 60)
        
        logger.info(f"📊 测试概况:")
        logger.info(f"  总测试事件: {stats.get('total', 0)}")
        logger.info(f"  成功处理: {stats.get('success', 0)}")
        logger.info(f"  失败处理: {stats.get('failed', 0)}")
        logger.info(f"  总耗时: {duration:.2f}秒")
        logger.info(f"  平均每个事件: {duration/max(stats.get('total', 1), 1):.2f}秒")
        
        logger.info(f"📈 处理结果分布:")
        logger.info(f"  创建新主题: {stats.get('created', 0)}")
        logger.info(f"  合并到现有主题: {stats.get('merged', 0)}")
        logger.info(f"  忽略事件: {stats.get('ignored', 0)}")
        
        logger.info(f"🤖 AI决策分布:")
        for decision_type, count in stats.get('decision_types', {}).items():
            logger.info(f"  {decision_type}: {count}")
        
        if stats.get('error_types'):
            logger.info(f"❌ 错误类型分布:")
            for error_type, count in stats.get('error_types', {}).items():
                logger.info(f"  {error_type}: {count}")
        
        # 数据库统计
        if self.db_client and hasattr(self.db_client, 'get_stats'):
            try:
                db_stats = asyncio.run(self.db_client.get_stats())
                logger.info(f"🗄️ 数据库统计:")
                for key, value in db_stats.items():
                    if isinstance(value, (int, float)):
                        logger.info(f"  {key}: {value}")
            except:
                pass
        
        # 引擎统计
        if self.engine:
            engine_stats = self.engine.get_stats()
            logger.info(f"⚙️ 引擎统计:")
            for key, value in engine_stats.items():
                if isinstance(value, (int, float)):
                    logger.info(f"  {key}: {value}")
        
        logger.info("=" * 60)
        
        # 保存详细结果
        self._save_detailed_results()
    
    def _save_detailed_results(self):
        """保存详细结果到文件"""
        if not self.test_results:
            return
        
        output_dir = os.path.join(project_root, "tests", "results")
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_dir, f"integration_test_results_{timestamp}.json")
        
        try:
            # 转换结果为可序列化格式
            serializable_results = []
            for result in self.test_results:
                serializable_result = {}
                for key, value in result.items():
                    if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        serializable_result[key] = value
                    else:
                        serializable_result[key] = str(value)
                serializable_results.append(serializable_result)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"📁 详细结果已保存到: {output_file}")
            
        except Exception as e:
            logger.error(f"保存详细结果失败: {e}")
    
    async def cleanup(self):
        """清理测试环境"""
        logger.info("清理测试环境...")
        
        # 关闭数据库连接等资源
        if self.db_client and hasattr(self.db_client, '_db'):
            try:
                if hasattr(self.db_client._db, 'disconnect'):
                    await self.db_client._db.disconnect()
            except:
                pass
        
        logger.info("✅ 测试环境清理完成")


async def main():
    """主函数"""
    print("🚀 开始运行金融投资AI助理系统集成测试")
    print("=" * 60)
    
    runner = IntegrationTestRunner()
    
    try:
        # 设置测试环境
        await runner.setup()
        
        # 运行测试
        print("\n🧪 开始运行集成测试...")
        stats = await runner.run_tests()
        
        # 总结
        print("\n" + "=" * 60)
        print("🎉 集成测试完成!")
        
        success_rate = (stats.get('success', 0) / max(stats.get('total', 1), 1)) * 100
        print(f"✅ 成功率: {success_rate:.1f}%")
        
        if stats.get('failed', 0) > 0:
            print(f"❌ 失败数: {stats.get('failed', 0)}")
        
        print("=" * 60)
        
        # 询问是否显示详细结果
        show_details = input("\n是否显示详细结果? (y/n): ").lower() == 'y'
        if show_details and runner.test_results:
            print("\n📋 详细结果:")
            for i, result in enumerate(runner.test_results[:5]):  # 只显示前5个
                print(f"\n事件 {i+1}: {result.get('event_id')}")
                print(f"  状态: {result.get('status')}")
                if 'ai_decision' in result:
                    decision = result['ai_decision']
                    print(f"  决策: {decision.get('decision')}")
                    print(f"  目标主题: {decision.get('target_theme_name')}")
                    print(f"  置信度: {decision.get('confidence', 0):.2f}")
        
        return stats
        
    except Exception as e:
        print(f"\n❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        # 清理
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())