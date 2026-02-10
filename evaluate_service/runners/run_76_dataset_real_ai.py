# evaluate_service/runners/run_76_dataset_real_ai.py
"""
76个数据集真实AI评估测试 - 生产级验证
使用真实AI大模型和真实数据库，输出完整评估报告
"""
#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import traceback

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def check_environment():
    """检查环境配置"""
    logger = logging.getLogger(__name__)
    errors = []
    warnings = []
    
    # 检查API密钥
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        errors.append("❌ DEEPSEEK_API_KEY环境变量未设置")
    else:
        logger.info(f"✅ DEEPSEEK_API_KEY已设置（长度: {len(api_key)}）")
    
    # 检查数据库配置
    try:
        from database_service.config import DatabaseConfig
        config = DatabaseConfig()
        config_dict = config.to_dict()
        logger.info(f"✅ 数据库配置: {config_dict['db_type']}")
        
        if config_dict['db_type'] == 'memory':
            warnings.append("⚠️  使用内存数据库（测试模式）")
        
    except ImportError as e:
        errors.append(f"❌ 数据库服务导入失败: {e}")
    except Exception as e:
        errors.append(f"❌ 数据库配置检查错误: {e}")
    
    # 检查测试数据文件
    data_dir = project_root / "evaluate_service" / "data" / "processed"
    events_path = data_dir / "validation_events_fixed.json"
    if not events_path.exists():
        errors.append(f"❌ 测试数据文件不存在: {events_path}")
    else:
        logger.info(f"✅ 找到测试数据文件: {events_path}")
    
    # 显示警告
    for warning in warnings:
        logger.warning(warning)
    
    # 如果有错误，显示并返回False
    if errors:
        for error in errors:
            logger.error(error)
        
        print("\n🔧 环境配置帮助:")
        print("1. 设置API密钥: export DEEPSEEK_API_KEY='your-key-here'")
        print("2. 确保数据文件在: evaluate_service/data/processed/validation_events_fixed.json")
        
        return False
    
    return True


# 配置日志
def setup_logging():
    """设置日志配置"""
    log_dir = project_root / "evaluate_service" / "data" / "results" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"76_dataset_real_ai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()


class RealEventPreparer:
    """真实事件准备器 - 确保事件数据完整保存到数据库"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.events_cache = {}
    
    async def prepare_all_events(self, events_list):
        """修复版事件保存 - 使用小样本测试的成功模式"""
        logger = logging.getLogger(__name__)
        logger.info(f"💾 准备 {len(events_list)} 个事件数据到数据库...")
        
        saved_count = 0
        for i, event in enumerate(events_list):
            try:
                event_id = event.get('news_id', f'event_{i}')
                if not event_id:
                    continue
                
                # 🔥 关键修复：使用与小样本测试完全相同的结构
                from datetime import datetime
                db_event = {
                    'id': event_id,
                    'news_id': event_id,
                    'title': event.get('original_news', {}).get('title', ''),
                    'full_content': event.get('original_news', {}).get('content', ''),
                    'content_length': len(event.get('original_news', {}).get('content', '')),
                    'has_full_content': True,  # 🔥 明确设置
                    'event_info': event.get('event_info', {}),
                    'original_news': event.get('original_news', {}),  # 🔥 保留原始数据
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                
                # 保存到数据库
                saved_id = await self.db_manager.create_or_update_event(db_event)
                if saved_id:
                    saved_count += 1
                    self.events_cache[event_id] = event  # 保存原始事件到缓存
                    
                if (i + 1) % 20 == 0:
                    logger.info(f"  已保存 {i+1}/{len(events_list)} 个事件")
                    
            except Exception as e:
                logger.warning(f"  保存事件 {event.get('news_id', 'unknown')} 失败: {e}")
        
        logger.info(f"✅ 成功保存 {saved_count}/{len(events_list)} 个真实事件到数据库")
        return saved_count
    
    async def get_event_for_analysis(self, event_id):
        """获取用于分析的事件数据"""
        # 优先从缓存获取
        if event_id in self.events_cache:
            return self.events_cache[event_id]
        
        # 从数据库获取
        try:
            event = await self.db_manager.get_event(event_id)
            return event
        except Exception as e:
            logger.warning(f"从数据库获取事件失败 {event_id}: {e}")
            return None


class ThemeSaver:
    """主题保存器 - 负责将AI发现的主题保存到数据库"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.saved_themes = {}
    
    async def save_discovery_result(self, discovery_result, event_data):
        """保存主题发现结果到数据库"""
        action = discovery_result.get('action')
        event_id = event_data.get('news_id', 'unknown')
        
        if action == 'CREATE_NEW':
            return await self._save_new_theme(discovery_result, event_data)
        elif action == 'CLUSTER':
            return await self._handle_cluster(discovery_result, event_data)
        else:
            return None, None
    
    async def _save_new_theme(self, discovery_result, event_data):
        """保存新主题到数据库"""
        event_id = event_data.get('news_id', 'unknown')
        
        # 提取主题信息
        theme_info = discovery_result.get('theme', {})
        if isinstance(theme_info, dict):
            theme_name = theme_info.get('name', '')
            theme_desc = theme_info.get('description', '')
            theme_keywords = theme_info.get('keywords', [])
            theme_confidence = theme_info.get('confidence', 0.8)
        else:
            theme_name = str(theme_info)
            theme_desc = ''
            theme_keywords = []
            theme_confidence = 0.8
        
        # 验证主题名
        if not theme_name or theme_name in ['无主题', '信息不足']:
            return None, None
        
        # 检查是否已存在
        existing_theme = await self.db_manager.get_theme_by_name(theme_name)
        if existing_theme:
            logger.info(f"   主题已存在: {theme_name}")
            # 建立事件关联
            try:
                relation = await self.db_manager.create_event_theme_relation(
                    event_id=event_id,
                    theme_id=existing_theme.id,
                    confidence=theme_confidence,
                    confidence_level='high'
                )
                return existing_theme, relation
            except Exception as e:
                logger.warning(f"   建立事件-主题关联失败: {e}")
                return existing_theme, None
        
        # 生成描述（如果为空）
        if not theme_desc:
            title = event_data.get('original_news', {}).get('title', '')
            industries = event_data.get('event_info', {}).get('impact_industries', [])
            theme_desc = f"{theme_name}主题，基于新闻事件：{title}"
            if industries:
                theme_desc += f"。影响行业：{', '.join(industries)}"
        
        # 创建主题
        try:
            saved_theme = await self.db_manager.create_theme(
                name=theme_name,
                description=theme_desc,
                keywords=theme_keywords,
                discovery_source='enhanced_theme_discovery_test',
                discovery_confidence=theme_confidence
            )
            
            logger.info(f"   💾 创建新主题: {theme_name}")
            
            # 建立事件关联
            try:
                relation = await self.db_manager.create_event_theme_relation(
                    event_id=event_id,
                    theme_id=saved_theme.id,
                    confidence=theme_confidence,
                    confidence_level='high'
                )
                logger.info(f"   已建立事件-主题关联: {event_id} -> {theme_name}")
                return saved_theme, relation
            except Exception as relation_error:
                logger.warning(f"   建立事件-主题关联失败: {relation_error}")
                return saved_theme, None
                
        except Exception as e:
            logger.error(f"   创建主题失败 {theme_name}: {e}")
            return None, None
    
    async def _handle_cluster(self, discovery_result, event_data):
        """处理聚类到现有主题"""
        event_id = event_data.get('news_id', 'unknown')
        theme_info = discovery_result.get('theme', {})
        
        if isinstance(theme_info, dict):
            theme_id = theme_info.get('id')
            theme_name = theme_info.get('name', '未知主题')
            theme_confidence = theme_info.get('confidence', 0.8)
        else:
            theme_name = str(theme_info)
            theme_id = None
            theme_confidence = 0.8
        
        # 尝试建立关联
        if theme_id:
            try:
                relation = await self.db_manager.create_event_theme_relation(
                    event_id=event_id,
                    theme_id=theme_id,
                    confidence=theme_confidence,
                    confidence_level='high'
                )
                logger.info(f"   🔗 事件聚类到主题: {event_id} -> {theme_name}")
                return await self.db_manager.get_theme(theme_id), relation
            except Exception as e:
                logger.warning(f"   建立聚类关联失败: {e}")
        
        return None, None


class RealAITestRunner:
    """真实AI测试执行器"""
    
    async def create_initial_themes_like_small_test(self, db_manager):
        """创建与小样本测试相同的初始主题"""
        logger = logging.getLogger(__name__)
        
        logger.info("🎯 创建与小样本测试相同的初始主题...")
        
        # 小样本测试中的主题
        test_themes = [
            {
                'name': 'AI智能体企业并购',
                'description': 'AI智能体企业的并购活动，包括技术收购、企业合并等',
                'keywords': ['AI智能体', '并购', '企业收购', '技术收购', 'AI代理', '智能体']
            },
            {
                'name': '智能眼镜新品发布',
                'description': '智能眼镜产品发布相关，包括Meta、Apple等公司的新品发布',
                'keywords': ['智能眼镜', 'AR眼镜', '发布', '新品', '消费电子']
            },
            {
                'name': 'AR眼镜技术突破',
                'description': 'AR眼镜技术研发突破，包括显示技术、交互技术等创新',
                'keywords': ['AR技术', '技术突破', '研发', '创新', '显示技术']
            }
        ]
        
        created_count = 0
        for theme in test_themes:
            try:
                saved_theme = await db_manager.create_theme(
                    name=theme['name'],
                    description=theme['description'],
                    keywords=theme['keywords']
                )
                if saved_theme:
                    created_count += 1
                    logger.info(f"   创建主题: {theme['name']}")
            except Exception as e:
                logger.warning(f"   创建主题失败 {theme['name']}: {e}")
        
        logger.info(f"✅ 创建 {created_count} 个初始主题")
        return created_count

    def __init__(self):
        self.start_time = None
        self.results = []
        self.theme_evolution = []
        self.metrics = {
            'total_events': 0,
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'theme_count': 0,
            'clustering_accuracy': 0.0,
            'severe_mismatches': 0,
            'processing_times': [],
            'themes_created': 0,
            'themes_clustered': 0,
            'events_saved': 0
        }
        
        # 存储路径
        self.data_dir = project_root / "evaluate_service" / "data"
        self.results_dir = self.data_dir / "results"
        self.reports_dir = self.results_dir / "reports"
        
        # 确保目录存在
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # 组件实例
        self.event_preparer = None
        self.theme_saver = None
    
    async def initialize_real_components(self):
        """初始化真实组件"""
        logger.info("🔧 初始化真实AI系统组件...")
        
        try:
            # 1. 初始化真实数据库
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.pure_data_fetcher import PureDataFetcher
            
            logger.info("  1. 初始化真实数据库...")
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            # 创建数据获取器
            data_fetcher = PureDataFetcher(db_manager)
            
            # 检查现有主题
            existing_themes = await db_manager.get_all_active_themes(limit=100)
            logger.info(f"  ✅ 数据库连接成功，现有主题数: {len(existing_themes)}")
            
            # 2. 初始化事件准备器和主题保存器
            self.event_preparer = RealEventPreparer(db_manager)
            self.theme_saver = ThemeSaver(db_manager)
            logger.info("  ✅ 事件与主题管理器初始化完成")
            
            # 3. 初始化真实AI分析器
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            logger.info("  2. 创建真实AI分析器...")
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY环境变量未设置")
            
            llm_config = {
                'api_key': api_key,
                'model_name': 'deepseek-chat',
                'max_retries': 3,
                'timeout': 60,
                'temperature': 0.1
            }
            
            llm_parser = ReliableDeepSeekParser(config=llm_config)
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            # 4. 创建主题发现模块
            logger.info("  3. 创建增强版主题发现模块...")
            discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            # 健康检查
            if await discovery.health_check():
                logger.info("  ✅ AI系统健康检查通过")
            else:
                logger.warning("  ⚠️ AI系统健康检查警告")
            
            return {
                'db_manager': db_manager,
                'data_fetcher': data_fetcher,
                'discovery': discovery,
                'similarity_analyzer': similarity_analyzer
            }
            
        except ImportError as e:
            logger.error(f"❌ 导入失败: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            traceback.print_exc()
            raise
    
    async def load_test_data(self):
        """加载测试数据"""
        logger.info("📂 加载测试数据集...")
        
        # 1. 直接使用指定的文件
        events_path = self.data_dir / "processed" / "validation_events_fixed.json"
        
        if not events_path.exists():
            raise FileNotFoundError(f"未找到76个事件的测试数据文件: {events_path}")
        
        logger.info(f"📄 加载指定数据文件: {events_path}")
        
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取事件 - 支持多种格式
            events = []
            if isinstance(data, dict):
                if 'events' in data:
                    events = data['events']
                    logger.info("📊 从 'events' 键提取数据")
                elif 'processed_events' in data:
                    events = data['processed_events']
                    logger.info("📊 从 'processed_events' 键提取数据")
                elif 'data' in data:
                    events = data['data']
                    logger.info("📊 从 'data' 键提取数据")
                else:
                    # 尝试使用所有字典值
                    events = list(data.values())
                    logger.info(f"📊 使用所有字典值，提取 {len(events)} 条记录")
            elif isinstance(data, list):
                events = data
                logger.info("📊 从列表直接加载数据")
            else:
                raise ValueError(f"数据格式错误: {type(data)}")
            
            logger.info(f"✅ 成功加载 {len(events)} 个测试事件")
            
            # 显示示例
            if events:
                first_event = events[0]
                logger.info(f"📋 示例事件格式: {list(first_event.keys())}")
                if 'original_news' in first_event:
                    title = first_event['original_news'].get('title', '')
                    if title:
                        logger.info(f"  示例标题: {title[:80]}...")
            
            return events, await self._load_ground_truth()
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 数据加载失败: {e}")
            raise
    
    async def _load_ground_truth(self):
        """加载ground truth数据"""
        ground_truth = {}
        
        try:
            # 尝试多个可能的ground truth文件
            gt_files = [
                project_root / "evaluate_service" / "config" / "ground_truth_correct.json",
                project_root / "evaluate_service" / "config" / "ground_truth_mapping.json",
            ]
            
            gt_path = None
            for file_path in gt_files:
                if file_path.exists():
                    gt_path = file_path
                    break
            
            if gt_path:
                logger.info(f"📄 加载ground truth: {gt_path}")
                
                with open(gt_path, 'r', encoding='utf-8') as f:
                    gt_data = json.load(f)
                
                # 转换为事件ID到主题的映射
                if isinstance(gt_data, dict):
                    for theme, event_ids in gt_data.items():
                        if isinstance(event_ids, list):
                            for event_id in event_ids:
                                ground_truth[event_id] = theme
                        else:
                            ground_truth[str(event_ids)] = theme
                
                logger.info(f"✅ 加载 {len(ground_truth)} 个ground truth标注")
            else:
                logger.warning("⚠️  未找到ground truth文件，将跳过准确性检查")
                
        except Exception as e:
            logger.warning(f"⚠️  Ground truth加载失败: {e}")
        
        return ground_truth
    
    async def run_test(self, components, events, ground_truth):
        """运行测试 - 修复版：确保主题获取正确"""
        logger.info(f"🚀 开始运行76个数据集真实AI测试（修复版）")
        logger.info(f"   使用组件: 真实DeepSeek API + 真实数据库")
        logger.info(f"   测试事件: {len(events)}个")
        logger.info(f"   Ground Truth标注: {len(ground_truth)}个")
        
        self.start_time = datetime.now()
        db_manager = components['db_manager']
        discovery = components['discovery']
        
        # 🔥 关键修复1: 首先创建与小样本测试相同的主题
        logger.info("🎯 修复步骤1: 创建与小样本测试相同的初始主题...")
        await self.create_initial_themes_like_small_test(db_manager)
        
        # 🔥 关键修复2: 然后保存所有事件到数据库
        logger.info("💾 修复步骤2: 保存所有事件到数据库...")
        saved_count = await self.event_preparer.prepare_all_events(events)
        self.metrics['events_saved'] = saved_count
        
        if saved_count < len(events):
            logger.warning(f"⚠️  仅保存了 {saved_count}/{len(events)} 个事件")
        
        # 检查当前主题数
        initial_themes = await self._check_database_themes(db_manager)
        logger.info(f"📊 初始数据库主题数: {initial_themes}")
        
        # 按事件ID排序（确保一致性）
        sorted_events = sorted(events, key=lambda x: x.get('news_id', ''))
        
        for i, event in enumerate(sorted_events):
            # 在每次处理前检查数据库状态
            current_theme_count = await self._check_database_themes(db_manager)
            
            # 获取事件ID
            event_id = event.get('news_id', f'event_{i}')
            std_theme = ground_truth.get(event_id)
            
            logger.info(f"\n[{i+1}/{len(events)}] 处理事件: {event_id}")
            logger.info(f"   当前数据库主题数: {current_theme_count}")
            
            # 显示事件信息
            title = event.get('original_news', {}).get('title', '')
            if title:
                display_title = title[:60] + "..." if len(title) > 60 else title
                logger.info(f"   标题: {display_title}")
            
            if std_theme:
                logger.info(f"   Ground Truth: {std_theme}")
            
            try:
                # 🔥 关键修复3: 获取完整事件数据（从数据库或缓存）
                complete_event = await self.event_preparer.get_event_for_analysis(event_id)
                if not complete_event:
                    logger.warning(f"⚠️  无法获取完整事件数据，使用原始数据: {event_id}")
                    complete_event = event
                
                # 🔥 关键修复4: 在AI分析前验证主题获取
                logger.info("   🔍 验证主题获取...")
                from database_service.pure_data_fetcher import PureDataFetcher
                from theme_service.related_theme_fetcher import RelatedThemeFetcher
                
                # 使用与手动测试完全相同的方法获取主题
                data_fetcher = PureDataFetcher(db_manager)
                theme_fetcher = RelatedThemeFetcher(data_fetcher)
                
                relevant_themes = await theme_fetcher.fetch_relevant_themes(complete_event)
                logger.info(f"   手动测试方法获取到 {len(relevant_themes)} 个主题")
                
                if not relevant_themes:
                    logger.error("   ❌ 无法获取相关主题，无法进行AI分析")
                    self.metrics['failed'] += 1
                    self.results.append({
                        'event_id': event_id,
                        'error': '无法获取相关主题',
                        'timestamp': datetime.now().isoformat()
                    })
                    continue
                
                # 显示获取到的主题
                for j, theme in enumerate(relevant_themes[:3]):
                    logger.info(f"      主题 {j+1}: {theme.get('name', '未知')}")
                
                # 🔥 关键修复5: 直接调用AI分析器，确保传递正确的主题数据
                logger.info("   🤖 开始AI分析...")
                start_time = time.time()
                
                # 方法A: 通过 discovery.process_event（可能有问题）
                try:
                    result = await discovery.process_event(complete_event)
                    processing_time = time.time() - start_time
                except Exception as e:
                    logger.warning(f"   ⚠️  discovery.process_event 失败: {e}")
                    logger.info("   🔄 尝试直接调用AI分析器...")
                    
                    # 方法B: 直接调用AI分析器
                    start_time = time.time()
                    analysis_result = await discovery.similarity_analyzer.analyze_with_theme_extraction(
                        complete_event,
                        relevant_themes  # 确保传递正确的主题
                    )
                    
                    # 将AI分析结果转换为discovery的格式
                    result = {
                        'event_id': event_id,
                        'action': 'CREATE_NEW' if analysis_result['metadata']['should_create_new'] else 'CLUSTER',
                        'theme': {
                            'name': analysis_result['theme_extraction']['extracted_name'],
                            'description': '',
                            'confidence': analysis_result['recommendation']['confidence']
                        } if analysis_result['metadata']['should_create_new'] else {
                            'name': analysis_result['similarity_analysis']['best_match_theme'],
                            'id': analysis_result['similarity_analysis']['theme_id']
                        },
                        'analysis': analysis_result,
                        'processing_time': time.time() - start_time
                    }
                    processing_time = time.time() - start_time
                
                self.metrics['processing_times'].append(processing_time)
                self.metrics['processed'] += 1
                
                # 提取AI结果
                ai_theme = None
                ai_action = result.get('action')
                
                if ai_action == 'CREATE_NEW':
                    if isinstance(result.get('theme'), dict):
                        ai_theme = result['theme'].get('name', '新主题')
                    else:
                        ai_theme = result.get('theme', '新主题')
                    logger.info(f"   AI决策: 📝 CREATE_NEW -> {ai_theme}")
                    
                    # 保存新主题到数据库
                    saved_theme, relation = await self.theme_saver.save_discovery_result(result, event)
                    if saved_theme:
                        self.metrics['themes_created'] += 1
                        logger.info(f"   ✅ 主题保存成功: {ai_theme}")
                    else:
                        logger.warning(f"   ⚠️  主题保存失败: {ai_theme}")
                    
                elif ai_action == 'CLUSTER':
                    if isinstance(result.get('theme'), dict):
                        ai_theme = result['theme'].get('name', '未知主题')
                    else:
                        ai_theme = result.get('theme', '未知主题')
                    
                    logger.info(f"   AI决策: 🔗 CLUSTER -> {ai_theme}")
                    
                    # 建立事件-主题关联
                    saved_theme, relation = await self.theme_saver.save_discovery_result(result, event)
                    if saved_theme:
                        self.metrics['themes_clustered'] += 1
                
                elif ai_action == 'ERROR':
                    ai_theme = f"错误: {result.get('error', '未知错误')}"
                    logger.error(f"   AI决策: ❌ ERROR -> {result.get('error')}")
                else:
                    ai_theme = f"未知: {ai_action}"
                    logger.warning(f"   AI决策: ⚠️  {ai_action}")
                
                # 检查数据库主题数量变化
                new_theme_count = await self._check_database_themes(db_manager)
                if new_theme_count > current_theme_count:
                    logger.info(f"   🎉 数据库新增主题: 从 {current_theme_count} 增加到 {new_theme_count}")
                
                # 检查是否正确（如果有ground truth）
                is_correct = False
                is_severe_mismatch = False
                
                if std_theme and ai_theme and not ai_theme.startswith(('错误:', '未知:')):
                    is_correct = self._check_correctness(ai_theme, std_theme)
                    is_severe_mismatch = self._check_severe_mismatch(ai_theme, std_theme)
                    
                    if is_correct:
                        logger.info(f"   ✅ 分类正确")
                        self.metrics['successful'] += 1
                    else:
                        logger.warning(f"   ❌ 分类错误")
                        self.metrics['failed'] += 1
                    
                    if is_severe_mismatch:
                        logger.error(f"   ⚠️  严重错配!")
                        self.metrics['severe_mismatches'] += 1
                
                # 记录结果
                result_record = {
                    'event_id': event_id,
                    'ground_truth': std_theme,
                    'ai_theme': ai_theme,
                    'ai_action': ai_action,
                    'processing_time': processing_time,
                    'is_correct': is_correct,
                    'is_severe_mismatch': is_severe_mismatch,
                    'timestamp': datetime.now().isoformat(),
                    'relevant_themes_count': len(relevant_themes)  # 记录获取到的主题数
                }
                
                self.results.append(result_record)
                
                # 更新主题演化记录
                if ai_theme and not ai_theme.startswith(('错误:', '未知:')):
                    self.theme_evolution.append({
                        'event_id': event_id,
                        'theme': ai_theme,
                        'action': ai_action,
                        'is_correct': is_correct,
                        'timestamp': datetime.now().isoformat()
                    })
                
                # 进度报告
                if (i + 1) % 5 == 0:
                    self._log_progress(i + 1, len(events))
                
                # API限流控制
                if i < len(events) - 1:
                    await asyncio.sleep(1)  # 1秒间隔
                    
            except Exception as e:
                logger.error(f"❌ 处理事件 {event_id} 失败: {e}")
                self.metrics['failed'] += 1
                self.results.append({
                    'event_id': event_id,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                
                # 较长的错误间隔
                await asyncio.sleep(2)
        
        # 计算最终指标
        await self._calculate_final_metrics(db_manager)
    
    async def _check_database_themes(self, db_manager):
        """检查数据库中的主题数量"""
        try:
            themes = await db_manager.get_all_active_themes(limit=1000)
            return len(themes)
        except Exception as e:
            logger.warning(f"无法获取数据库主题数: {e}")
            return 0
    
    def _check_correctness(self, ai_theme, std_theme):
        """检查分类正确性"""
        if not ai_theme or not std_theme:
            return False
        
        ai_lower = str(ai_theme).lower()
        std_lower = str(std_theme).lower()
        
        # 直接字符串匹配
        if std_lower in ai_lower or ai_lower in std_lower:
            return True
        
        # 主题映射
        theme_mapping = {
            'ai/ar眼镜': ['眼镜', 'ar', '智能眼镜', 'ai眼镜'],
            'spacex': ['spacex', '航天', '太空', '火箭'],
            '可控核聚变': ['核聚变', '聚变', '核能'],
            '对日制裁': ['制裁', '日本', '贸易战'],
            '稀土永磁': ['稀土', '永磁', '磁材'],
            '海洋经济': ['海洋', '海工', '海上'],
            '光刻胶': ['光刻', '胶', '半导体材料'],
            '卫星互联': ['卫星', '低轨', '卫星互联网'],
            '液冷数据中心': ['液冷', '数据中心', '服务器'],
            'ai智能体manus': ['manus', '智能体', 'ai智能体']
        }
        
        for std_key, keywords in theme_mapping.items():
            if std_key in std_lower:
                for keyword in keywords:
                    if keyword in ai_lower:
                        return True
        
        return False
    
    def _check_severe_mismatch(self, ai_theme, std_theme):
        """检查严重错配"""
        if not ai_theme or not std_theme:
            return False
        
        ai_lower = str(ai_theme).lower()
        std_lower = str(std_theme).lower()
        
        # 严重错配对
        severe_pairs = [
            ('spacex', 'ai/ar眼镜'),
            ('spacex', '消费电子'),
            ('卫星互联', 'ai/ar眼镜'),
            ('对日制裁', 'ai/ar眼镜'),
            ('可控核聚变', 'ai/ar眼镜'),
            ('光刻胶', 'ai智能体manus')
        ]
        
        for theme1, theme2 in severe_pairs:
            if (theme1 in std_lower and theme2 in ai_lower) or \
               (theme2 in std_lower and theme1 in ai_lower):
                return True
        
        return False
    
    def _log_progress(self, current, total):
        """记录进度"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        progress = current / total * 100
        
        avg_time = elapsed / current if current > 0 else 0
        
        logger.info(f"📊 进度: {current}/{total} ({progress:.1f}%)")
        logger.info(f"   耗时: {elapsed:.1f}s, 平均: {avg_time:.1f}s/事件")
        logger.info(f"   成功: {self.metrics['successful']}, 失败: {self.metrics['failed']}")
        logger.info(f"   创建主题: {self.metrics['themes_created']}, 聚类主题: {self.metrics['themes_clustered']}")
        
        # 计算预估剩余时间
        remaining = total - current
        if current > 0 and remaining > 0:
            estimated_remaining = elapsed / current * remaining
            logger.info(f"   预估剩余: {estimated_remaining:.0f}s ({estimated_remaining/60:.1f}分钟)")
    
    async def _calculate_final_metrics(self, db_manager):
        """计算最终指标"""
        total = self.metrics['processed']
        successful = self.metrics['successful']
        
        if total > 0:
            self.metrics['clustering_accuracy'] = successful / total
        else:
            self.metrics['clustering_accuracy'] = 0.0
        
        # 统计AI产生的主题数量
        ai_themes = set()
        theme_distribution = defaultdict(int)
        
        for result in self.results:
            if result.get('ai_theme'):
                ai_theme = str(result['ai_theme'])
                if not ai_theme.startswith(('错误:', '未知:')):
                    ai_themes.add(ai_theme)
                    theme_distribution[ai_theme] += 1
        
        self.metrics['theme_count'] = len(ai_themes)
        self.metrics['theme_distribution'] = dict(theme_distribution)
        
        # 获取数据库最终状态
        try:
            final_themes = await db_manager.get_all_active_themes(limit=100)
            self.metrics['database_final_themes'] = len(final_themes)
            logger.info(f"📊 数据库最终主题数: {len(final_themes)}")
            
            # 获取数据库统计
            stats = await db_manager.get_stats()
            logger.info(f"📈 数据库统计: {stats}")
            
        except Exception as e:
            self.metrics['database_final_themes'] = 'N/A'
            logger.warning(f"无法获取数据库最终状态: {e}")
    
    def _parse_date(self, date_str):
        """解析日期字符串"""
        if not date_str:
            return datetime.min
        
        try:
            date_str = str(date_str).strip()
            for fmt in ['%Y年%m月%d日', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d']:
                try:
                    return datetime.strptime(date_str, fmt)
                except:
                    continue
            return datetime.min
        except:
            return datetime.min
    
    async def generate_reports(self):
        """生成评估报告"""
        logger.info("\n📄 生成评估报告...")
        
        # 生成详细结果
        detailed_results = {
            'metadata': {
                'test_name': '76_dataset_real_ai_evaluation',
                'test_time': datetime.now().isoformat(),
                'total_events': self.metrics['total_events'],
                'events_saved': self.metrics['events_saved'],
                'processed_events': self.metrics['processed'],
                'elapsed_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
                'database_type': 'memory',
                'data_source': 'validation_events_fixed.json',
                'note': '修复版：确保事件真实保存到数据库'
            },
            'metrics': self.metrics,
            'theme_evolution': self.theme_evolution[:100],
            'results_summary': {
                'total_processed': self.metrics['processed'],
                'successful': self.metrics['successful'],
                'failed': self.metrics['failed'],
                'clustering_accuracy': self.metrics['clustering_accuracy'],
                'theme_count': self.metrics['theme_count'],
                'severe_mismatches': self.metrics['severe_mismatches'],
                'themes_created': self.metrics['themes_created'],
                'themes_clustered': self.metrics['themes_clustered'],
                'avg_processing_time': sum(self.metrics['processing_times']) / len(self.metrics['processing_times']) if self.metrics['processing_times'] else 0,
                'total_processing_time': sum(self.metrics['processing_times'])
            },
            'sample_results': self.results[:20]
        }
        
        # 保存报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 详细结果
        detailed_path = self.reports_dir / f"76_dataset_real_ai_detailed_{timestamp}.json"
        with open(detailed_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        
        # 摘要报告
        summary = {
            'timestamp': timestamp,
            'total_events': self.metrics['total_events'],
            'events_saved': self.metrics['events_saved'],
            'processed_events': self.metrics['processed'],
            'clustering_accuracy': self.metrics['clustering_accuracy'],
            'theme_count': self.metrics['theme_count'],
            'severe_mismatches': self.metrics['severe_mismatches'],
            'themes_created': self.metrics['themes_created'],
            'themes_clustered': self.metrics['themes_clustered'],
            'avg_processing_time': sum(self.metrics['processing_times']) / len(self.metrics['processing_times']) if self.metrics['processing_times'] else 0,
            'success_rate': self.metrics['successful'] / self.metrics['processed'] if self.metrics['processed'] > 0 else 0,
            'performance_rating': self._calculate_performance_rating()
        }
        
        summary_path = self.reports_dir / f"76_dataset_real_ai_summary_{timestamp}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 详细报告已保存: {detailed_path}")
        logger.info(f"✅ 摘要报告已保存: {summary_path}")
        
        return detailed_path, summary_path
    
    def _calculate_performance_rating(self):
        """计算性能评级"""
        accuracy = self.metrics['clustering_accuracy']
        theme_count = self.metrics['theme_count']
        mismatches = self.metrics['severe_mismatches']
        
        score = 0
        
        # 准确率评分
        if accuracy >= 0.8:
            score += 30
        elif accuracy >= 0.6:
            score += 20
        elif accuracy >= 0.4:
            score += 10
        
        # 主题数量评分（目标8-12个）
        if 8 <= theme_count <= 12:
            score += 30
        elif 6 <= theme_count <= 14:
            score += 20
        elif 4 <= theme_count <= 16:
            score += 10
        
        # 严重错配评分
        if mismatches == 0:
            score += 40
        elif mismatches <= 2:
            score += 30
        elif mismatches <= 5:
            score += 20
        elif mismatches <= 10:
            score += 10
        
        # 总体评级
        if score >= 80:
            return "优秀"
        elif score >= 60:
            return "良好"
        elif score >= 40:
            return "一般"
        else:
            return "待改进"
    
    def print_final_summary(self):
        """打印最终总结"""
        if not self.start_time:
            logger.error("测试未正确运行")
            return
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "="*80)
        print("🎯 76个数据集真实AI测试 - 最终结果")
        print("="*80)
        
        print(f"\n📊 核心指标:")
        print(f"   总事件数: {self.metrics['total_events']}")
        print(f"   已保存事件: {self.metrics['events_saved']}")
        print(f"   已处理事件: {self.metrics['processed']}")
        print(f"   成功分类: {self.metrics['successful']}")
        print(f"   失败分类: {self.metrics['failed']}")
        
        if self.metrics['processed'] > 0:
            print(f"   聚类准确率: {self.metrics['clustering_accuracy']:.1%}")
        else:
            print(f"   聚类准确率: N/A")
        
        print(f"   创建主题数: {self.metrics['themes_created']}")
        print(f"   聚类主题数: {self.metrics['themes_clustered']}")
        print(f"   AI产生主题数: {self.metrics['theme_count']}")
        print(f"   严重错配数: {self.metrics['severe_mismatches']}")
        
        if self.metrics['processing_times']:
            avg_time = sum(self.metrics['processing_times']) / len(self.metrics['processing_times'])
            print(f"   平均处理时间: {avg_time:.2f}秒/事件")
        
        print(f"   总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")
        
        print(f"\n🏷️  AI主题分布 (Top 10):")
        sorted_themes = sorted(
            self.metrics.get('theme_distribution', {}).items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        for theme, count in sorted_themes[:10]:
            print(f"   {theme}: {count}个事件")
        
        print(f"\n📈 评估结论:")
        
        # 主题数量评估
        if 8 <= self.metrics['theme_count'] <= 12:
            print(f"   ✅ 主题数量合理 ({self.metrics['theme_count']}个)，接近目标10个")
        elif self.metrics['theme_count'] > 12:
            print(f"   ⚠️  主题数量偏多 ({self.metrics['theme_count']}个)，可能存在过度细分")
        else:
            print(f"   ⚠️  主题数量偏少 ({self.metrics['theme_count']}个)，可能聚类过度")
        
        # 准确率评估
        if self.metrics['clustering_accuracy'] >= 0.8:
            print(f"   ✅ 聚类准确性优秀 ({self.metrics['clustering_accuracy']:.1%})")
        elif self.metrics['clustering_accuracy'] >= 0.6:
            print(f"   ⚠️  聚类准确性一般 ({self.metrics['clustering_accuracy']:.1%})，需要优化")
        elif self.metrics['clustering_accuracy'] > 0:
            print(f"   ❌ 聚类准确性较差 ({self.metrics['clustering_accuracy']:.1%})，需要大幅优化")
        else:
            print(f"   ❌ 聚类准确性无法计算")
        
        # 严重错配评估
        if self.metrics['severe_mismatches'] == 0:
            print(f"   ✅ 严重错配控制良好 (0个)")
        elif self.metrics['severe_mismatches'] <= 2:
            print(f"   ⚠️  严重错配较少 ({self.metrics['severe_mismatches']}个)，可接受")
        elif self.metrics['severe_mismatches'] <= 5:
            print(f"   ⚠️  严重错配中等 ({self.metrics['severe_mismatches']}个)，需要关注")
        else:
            print(f"   ❌ 严重错配较多 ({self.metrics['severe_mismatches']}个)，需要重点关注")
        
        print(f"\n🏆 总体评级: {self._calculate_performance_rating()}")
        
        print("\n" + "="*80)


async def main():
    """主函数"""
    # 检查环境
    if not check_environment():
        print("\n❌ 环境检查失败")
        print("\n🔧 修复建议:")
        print("   1. 设置DEEPSEEK_API_KEY环境变量:")
        print("      export DEEPSEEK_API_KEY='your-api-key-here'")
        print("   2. 确保测试数据文件在:")
        print("      evaluate_service/data/processed/validation_events_fixed.json")
        return 1
    
    runner = RealAITestRunner()
    
    try:
        # 1. 加载测试数据
        events, ground_truth = await runner.load_test_data()
        runner.metrics['total_events'] = len(events)
        
        # 2. 初始化真实组件
        components = await runner.initialize_real_components()
        
        # 3. 运行测试
        await runner.run_test(components, events, ground_truth)
        
        # 4. 生成报告
        await runner.generate_reports()
        
        # 5. 打印总结
        runner.print_final_summary()
        
        # 6. 返回退出码
        if runner.metrics['processed'] > 0 and runner.metrics['successful'] / runner.metrics['processed'] > 0.6:
            print("\n✅ 测试通过！")
            return 0
        else:
            print("\n⚠️  测试未通过，需要优化")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        return 130
    except Exception as e:
        logger.error(f"❌ 测试执行失败: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)