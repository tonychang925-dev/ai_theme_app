#!/usr/bin/env python3
"""
集成评估器 - integrated_evaluator.py
运行优化后的全套theme_service组件，输出每个事件的最终题材归属、决策路径、置信度。
参考 run_76_dataset_real_ai.py 的架构设计。
"""
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

# 配置日志
def setup_logging():
    """设置日志配置"""
    log_dir = project_root / "evaluate_service" / "data" / "results" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"integrated_evaluator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
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

class EventPreparer:
    """事件准备器 - 确保事件数据完整保存到数据库"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.events_cache = {}
    
    async def prepare_all_events(self, events_list):
        """保存所有事件到数据库"""
        logger.info(f"💾 准备 {len(events_list)} 个事件数据到数据库...")
        
        saved_count = 0
        for i, event in enumerate(events_list):
            try:
                event_id = event.get('news_id', f'event_{i}')
                if not event_id:
                    continue
                
                # 构建数据库事件结构
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
                saved_id = await self.db_manager.create_or_update_event(db_event)
                if saved_id:
                    saved_count += 1
                    self.events_cache[event_id] = event
                    
                if (i + 1) % 20 == 0:
                    logger.info(f"  已保存 {i+1}/{len(events_list)} 个事件")
                    
            except Exception as e:
                logger.warning(f"  保存事件 {event.get('news_id', 'unknown')} 失败: {e}")
        
        logger.info(f"✅ 成功保存 {saved_count}/{len(events_list)} 个事件到数据库")
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

class ThemeDiscoverySaver:
    """主题发现结果保存器"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
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
        if not theme_name or theme_name in ['无主题', '信息不足', '无法提取主题']:
            return None, None
        
        # 🔥 修复：检查是否已存在时，安全处理返回的theme对象
        existing_theme = await self.db_manager.get_theme_by_name(theme_name)
        if existing_theme:
            logger.info(f"   主题已存在: {theme_name}")
            # 安全获取主题ID
            theme_id = self._safe_get_theme_id(existing_theme)
            if not theme_id:
                logger.warning(f"   无法获取已存在主题的ID: {theme_name}")
                return None, None
                
            # 建立事件关联
            try:
                relation = await self.db_manager.create_event_theme_relation(
                    event_id=event_id,
                    theme_id=theme_id,
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
                discovery_source='integrated_evaluator',
                discovery_confidence=theme_confidence
            )
            
            if not saved_theme:
                logger.error(f"   创建主题返回None: {theme_name}")
                return None, None
            
            logger.info(f"   💾 创建新主题: {theme_name}")
            
            # 🔥 修复：安全获取新创建主题的ID
            theme_id = self._safe_get_theme_id(saved_theme)
            if not theme_id:
                logger.error(f"   无法获取新主题的ID: {saved_theme}")
                return saved_theme, None
            
            # 建立事件关联
            try:
                relation = await self.db_manager.create_event_theme_relation(
                    event_id=event_id,
                    theme_id=theme_id,
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
    
    def _safe_get_theme_id(self, theme_obj):
        """安全获取主题ID - 不使用get()方法"""
        if theme_obj is None:
            return None
        
        # 方法1：直接访问属性（ThemeRecord对象）
        try:
            return theme_obj.id
        except AttributeError:
            pass
        
        # 方法2：使用getattr
        try:
            return getattr(theme_obj, 'id', None)
        except:
            pass
        
        # 方法3：如果是字典
        if isinstance(theme_obj, dict):
            # 使用字典的get方法（这是安全的）
            return theme_obj.get('id')
        
        # 方法4：尝试其他可能的属性名
        for attr_name in ['id', 'theme_id', '_id']:
            try:
                if hasattr(theme_obj, attr_name):
                    return getattr(theme_obj, attr_name)
            except:
                pass
        
        logger.warning(f"   无法从对象获取ID，类型: {type(theme_obj)}")
        return None
    
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

class IntegratedEvaluator:
    """集成评估器 - 运行优化后的全套theme_service组件"""
    
    def __init__(self):
        self.start_time = None
        self.results = []
        self.metrics = {
            'total_events': 0,
            'processed': 0,
            'themes_created': 0,
            'themes_clustered': 0,
            'processing_times': [],
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
    
    async def initialize_components(self):
        """初始化所有组件"""
        logger.info("🔧 初始化优化后的theme_service组件...")
        
        try:
            # 1. 初始化内存数据库
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.pure_data_fetcher import PureDataFetcher
            
            logger.info("  1. 初始化内存数据库...")
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            # 🔥 关键：清空数据库，确保初始为空
            if hasattr(db_manager, 'clear_all_data'):
                await db_manager.clear_all_data()
                logger.info("  ✅ 数据库已清空（初始状态）")
            
            # 创建数据获取器
            data_fetcher = PureDataFetcher(db_manager)
            
            # 2. 初始化事件准备器和主题保存器
            self.event_preparer = EventPreparer(db_manager)
            self.theme_saver = ThemeDiscoverySaver(db_manager)
            logger.info("  ✅ 事件与主题管理器初始化完成")
            
            # 3. 初始化真实AI分析器
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            logger.info("  2. 创建优化后的主题发现组件...")
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
            
            # 4. 创建优化后的主题发现模块（使用EnhancedThemeDiscovery）
            logger.info("  3. 创建增强版主题发现模块...")
            discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            # 健康检查
            if await discovery.health_check():
                logger.info("  ✅ theme_service组件健康检查通过")
            else:
                logger.warning("  ⚠️ theme_service组件健康检查警告")
            
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
            logger.error(f"❌ 组件初始化失败: {e}")
            traceback.print_exc()
            raise
    
    def _safe_get_theme_id(self, theme_obj):
        """安全获取主题ID"""
        if theme_obj is None:
            return None
        
        try:
            # 方法1：直接访问属性
            return theme_obj.id
        except AttributeError:
            pass
        
        try:
            # 方法2：使用getattr
            return getattr(theme_obj, 'id', None)
        except:
            pass
        
        # 方法3：如果是字典
        if isinstance(theme_obj, dict):
            return theme_obj.get('id')
        
        return None
    
    async def load_test_data(self):
        """加载测试数据"""
        logger.info("📂 加载测试数据集...")
        
        # 使用指定的文件
        events_path = self.data_dir / "processed" / "validation_events_fixed.json"
        
        if not events_path.exists():
            raise FileNotFoundError(f"未找到测试数据文件: {events_path}")
        
        logger.info(f"📄 加载指定数据文件: {events_path}")
        
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取事件 - 支持多种格式
            events = []
            if isinstance(data, list):
                events = data
                logger.info("📊 从列表直接加载数据")
            elif isinstance(data, dict) and 'events' in data:
                events = data['events']
                logger.info("📊 从 'events' 键提取数据")
            elif isinstance(data, dict) and 'processed_events' in data:
                events = data['processed_events']
                logger.info("📊 从 'processed_events' 键提取数据")
            else:
                # 尝试使用所有字典值
                events = list(data.values())
                logger.info(f"📊 使用所有字典值，提取 {len(events)} 条记录")
            
            # 按日期排序（模拟真实时序）
            sorted_events = sorted(
                events,
                key=lambda x: self._parse_event_date(x.get('original_news', {}).get('date', ''))
            )
            
            logger.info(f"✅ 成功加载 {len(sorted_events)} 个测试事件（已按日期排序）")
            
            # 显示示例
            if sorted_events:
                first_event = sorted_events[0]
                logger.info(f"📋 示例事件格式: {list(first_event.keys())}")
                if 'original_news' in first_event:
                    title = first_event['original_news'].get('title', '')
                    if title:
                        logger.info(f"  示例标题: {title[:80]}...")
            
            return sorted_events
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 数据加载失败: {e}")
            raise
    
    def _parse_event_date(self, date_str):
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
    
    async def run_evaluation(self, components, events):
        """运行集成评估"""
        logger.info(f"🚀 开始运行集成评估测试")
        logger.info(f"   使用组件: 优化后的theme_service (EnhancedThemeDiscovery)")
        logger.info(f"   测试事件: {len(events)}个")
        
        self.start_time = datetime.now()
        db_manager = components['db_manager']
        discovery = components['discovery']
        
        # 保存所有事件到数据库
        logger.info("💾 保存所有事件到数据库...")
        saved_count = await self.event_preparer.prepare_all_events(events)
        self.metrics['events_saved'] = saved_count
        
        if saved_count < len(events):
            logger.warning(f"⚠️  仅保存了 {saved_count}/{len(events)} 个事件")
        
        # 检查初始数据库状态
        initial_themes = await self._check_database_themes(db_manager)
        logger.info(f"📊 初始数据库主题数: {initial_themes} (应为0)")
        
        # 按顺序处理每个事件
        for i, event in enumerate(events):
            # 在每次处理前检查数据库状态
            current_theme_count = await self._check_database_themes(db_manager)
            
            # 获取事件ID
            event_id = event.get('news_id', f'event_{i}')
            
            logger.info(f"\n[{i+1}/{len(events)}] 处理事件: {event_id}")
            logger.info(f"   当前数据库主题数: {current_theme_count}")
            
            # 显示事件信息
            title = event.get('original_news', {}).get('title', '')
            if title:
                display_title = title[:60] + "..." if len(title) > 60 else title
                logger.info(f"   标题: {display_title}")
            
            try:
                # 获取完整事件数据
                complete_event = await self.event_preparer.get_event_for_analysis(event_id)
                if not complete_event:
                    logger.warning(f"⚠️  无法获取完整事件数据，使用原始数据: {event_id}")
                    complete_event = event
                
                # 验证事件内容
                if not complete_event.get('original_news', {}).get('content'):
                    logger.warning(f"⚠️  事件 {event_id} 内容为空，可能影响分析")
                
                # 调用优化后的主题发现组件
                logger.info("   🤖 调用优化后的theme_service组件...")
                start_time = time.time()
                
                # 直接使用EnhancedThemeDiscovery的process_event方法
                result = await discovery.process_event(complete_event)
                processing_time = time.time() - start_time
                
                self.metrics['processing_times'].append(processing_time)
                self.metrics['processed'] += 1
                
                # 提取AI结果
                ai_action = result.get('action')
                ai_theme_info = result.get('theme', {})
                
                # 构建详细的结果记录
                result_record = {
                    'event_id': event_id,
                    'original_title': complete_event.get('original_news', {}).get('title', ''),
                    'processing_time': processing_time,
                    'timestamp': datetime.now().isoformat(),
                    'database_state_before': {
                        'theme_count': current_theme_count,
                        'event_count': i  # 已处理的事件数
                    }
                }
                
                if ai_action == 'CREATE_NEW':
                    if isinstance(ai_theme_info, dict):
                        ai_theme = ai_theme_info.get('name', '新主题')
                        confidence = ai_theme_info.get('confidence', 0.8)
                    else:
                        ai_theme = str(ai_theme_info)
                        confidence = 0.8
                    
                    logger.info(f"   AI决策: 📝 CREATE_NEW -> {ai_theme}")
                    result_record['ai_action'] = 'CREATE_NEW'
                    result_record['final_theme'] = ai_theme
                    result_record['confidence'] = confidence
                    
                    # 保存新主题到数据库
                    saved_theme, relation = await self.theme_saver.save_discovery_result(result, complete_event)
                    if saved_theme:
                        self.metrics['themes_created'] += 1
                        result_record['theme_saved'] = True
                        # 🔥 修复：使用安全方法获取ID
                        theme_id = self._safe_get_theme_id(saved_theme)
                        result_record['theme_id'] = theme_id
                    else:
                        result_record['theme_saved'] = False
                    
                elif ai_action == 'CLUSTER':
                    if isinstance(ai_theme_info, dict):
                        ai_theme = ai_theme_info.get('name', '现有主题')
                        theme_id = ai_theme_info.get('id')
                    else:
                        ai_theme = str(ai_theme_info)
                        theme_id = None
                    
                    logger.info(f"   AI决策: 🔗 CLUSTER -> {ai_theme}")
                    result_record['ai_action'] = 'CLUSTER'
                    result_record['final_theme'] = ai_theme
                    result_record['matched_theme_id'] = theme_id
                    
                    # 建立事件-主题关联
                    saved_theme, relation = await self.theme_saver.save_discovery_result(result, complete_event)
                    if saved_theme:
                        self.metrics['themes_clustered'] += 1
                        result_record['relation_created'] = True
                    else:
                        result_record['relation_created'] = False
                
                elif ai_action == 'ERROR':
                    ai_theme = f"错误: {result.get('error', '未知错误')}"
                    logger.error(f"   AI决策: ❌ ERROR -> {result.get('error')}")
                    result_record['ai_action'] = 'ERROR'
                    result_record['final_theme'] = ai_theme
                    result_record['error'] = result.get('error', '未知错误')
                else:
                    ai_theme = f"未知: {ai_action}"
                    logger.warning(f"   AI决策: ⚠️  {ai_action}")
                    result_record['ai_action'] = ai_action
                    result_record['final_theme'] = ai_theme
                
                # 从analysis中提取更多细节
                analysis = result.get('analysis', {})
                if analysis:
                    # 主题提取信息
                    theme_extraction = analysis.get('theme_extraction', {})
                    result_record['theme_extraction'] = {
                        'extracted_name': theme_extraction.get('extracted_name', ''),
                        'naming_reason': theme_extraction.get('naming_reason', ''),
                        'content_based_analysis': theme_extraction.get('content_based_analysis', '')
                    }
                    
                    # 相似性分析信息
                    similarity_analysis = analysis.get('similarity_analysis', {})
                    result_record['similarity_analysis'] = {
                        'best_match_theme': similarity_analysis.get('best_match_theme', ''),
                        'match_score': similarity_analysis.get('match_score', 0),
                        'match_reason': similarity_analysis.get('match_reason', ''),
                        'is_same_domain': similarity_analysis.get('is_same_domain', False)
                    }
                    
                    # 推荐信息
                    recommendation = analysis.get('recommendation', {})
                    result_record['recommendation'] = {
                        'action': recommendation.get('action', ''),
                        'confidence': recommendation.get('confidence', 0),
                        'reason': recommendation.get('reason', '')
                    }
                
                # 检查数据库主题数量变化
                new_theme_count = await self._check_database_themes(db_manager)
                result_record['database_state_after'] = {
                    'theme_count': new_theme_count,
                    'event_count': i + 1
                }
                
                if new_theme_count > current_theme_count:
                    logger.info(f"   🎉 数据库新增主题: 从 {current_theme_count} 增加到 {new_theme_count}")
                
                # 添加到结果列表
                self.results.append(result_record)
                
                # 进度报告
                if (i + 1) % 5 == 0:
                    self._log_progress(i + 1, len(events))
                
                # API限流控制
                if i < len(events) - 1:
                    await asyncio.sleep(1)  # 1秒间隔
                    
            except Exception as e:
                logger.error(f"❌ 处理事件 {event_id} 失败: {e}")
                logger.error("🔍 完整错误堆栈:")
                error_trace = traceback.format_exc()
                logger.error(error_trace)
                
                self.results.append({
                    'event_id': event_id,
                    'error': str(e),
                    'error_trace': error_trace,
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
    
    def _log_progress(self, current, total):
        """记录进度"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        progress = current / total * 100
        
        avg_time = elapsed / current if current > 0 else 0
        
        logger.info(f"📊 进度: {current}/{total} ({progress:.1f}%)")
        logger.info(f"   耗时: {elapsed:.1f}s, 平均: {avg_time:.1f}s/事件")
        logger.info(f"   创建主题: {self.metrics['themes_created']}, 聚类主题: {self.metrics['themes_clustered']}")
        
        # 计算预估剩余时间
        remaining = total - current
        if current > 0 and remaining > 0:
            estimated_remaining = elapsed / current * remaining
            logger.info(f"   预估剩余: {estimated_remaining:.0f}s ({estimated_remaining/60:.1f}分钟)")
    
    async def _calculate_final_metrics(self, db_manager):
        """计算最终指标"""
        # 统计主题分布
        theme_distribution = defaultdict(int)
        for result in self.results:
            if result.get('final_theme'):
                theme = result['final_theme']
                if theme and not theme.startswith(('错误:', '未知:')):
                    theme_distribution[theme] += 1
        
        self.metrics['theme_count'] = len(theme_distribution)
        self.metrics['theme_distribution'] = dict(theme_distribution)
        
        # 获取数据库最终状态
        try:
            final_themes = await db_manager.get_all_active_themes(limit=100)
            self.metrics['database_final_themes'] = len(final_themes)
            logger.info(f"📊 数据库最终主题数: {len(final_themes)}")
            
        except Exception as e:
            self.metrics['database_final_themes'] = 'N/A'
            logger.warning(f"无法获取数据库最终状态: {e}")
    
    async def generate_output_files(self):
        """生成输出文件"""
        logger.info("\n📄 生成输出文件...")
        
        # 生成优化系统结果
        optimized_results = {
            'metadata': {
                'evaluation_name': 'optimized_theme_service_evaluation',
                'evaluation_time': datetime.now().isoformat(),
                'total_events': self.metrics['total_events'],
                'processed_events': self.metrics['processed'],
                'themes_created': self.metrics['themes_created'],
                'themes_clustered': self.metrics['themes_clustered'],
                'final_theme_count': self.metrics['theme_count'],
                'data_source': 'validation_events_fixed.json',
                'component_version': 'EnhancedThemeDiscovery_v1.0'
            },
            'events': []
        }
        
        # 为每个事件构建详细结果
        for result in self.results:
            event_result = {
                'event_id': result.get('event_id'),
                'original_title': result.get('original_title', ''),
                'final_theme': result.get('final_theme', '未匹配'),
                'ai_action': result.get('ai_action', 'UNKNOWN'),
                'processing_time': result.get('processing_time', 0),
                'timestamp': result.get('timestamp'),
                'decision_path': {}
            }
            
            # 添加置信度
            if 'confidence' in result:
                event_result['confidence'] = result['confidence']
            elif 'recommendation' in result:
                event_result['confidence'] = result['recommendation'].get('confidence', 0)
            
            # 构建决策路径
            decision_path = {}
            
            # 主题提取信息
            if 'theme_extraction' in result:
                decision_path['theme_extraction'] = result['theme_extraction']
            
            # 相似性分析信息
            if 'similarity_analysis' in result:
                decision_path['similarity_analysis'] = result['similarity_analysis']
            
            # 推荐信息
            if 'recommendation' in result:
                decision_path['recommendation'] = result['recommendation']
            
            # 数据库状态变化
            if 'database_state_before' in result and 'database_state_after' in result:
                decision_path['database_state_change'] = {
                    'before': result['database_state_before'],
                    'after': result['database_state_after']
                }
            
            event_result['decision_path'] = decision_path
            
            # 其他信息
            if 'theme_saved' in result:
                event_result['theme_saved'] = result['theme_saved']
            if 'relation_created' in result:
                event_result['relation_created'] = result['relation_created']
            if 'error' in result:
                event_result['error'] = result['error']
            
            optimized_results['events'].append(event_result)
        
        # 保存结果
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.results_dir / f"optimized_system_results_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(optimized_results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 优化系统结果已保存: {output_file}")
        
        return output_file
    
    def print_final_summary(self):
        """打印最终总结"""
        if not self.start_time:
            logger.error("评估未正确运行")
            return
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "="*80)
        print("🎯 集成评估测试 - 最终结果")
        print("="*80)
        
        print(f"\n📊 核心指标:")
        print(f"   总事件数: {self.metrics['total_events']}")
        print(f"   已保存事件: {self.metrics['events_saved']}")
        print(f"   已处理事件: {self.metrics['processed']}")
        
        print(f"   创建主题数: {self.metrics['themes_created']}")
        print(f"   聚类主题数: {self.metrics['themes_clustered']}")
        print(f"   AI产生主题数: {self.metrics['theme_count']}")
        
        if self.metrics['processing_times']:
            avg_time = sum(self.metrics['processing_times']) / len(self.metrics['processing_times'])
            print(f"   平均处理时间: {avg_time:.2f}秒/事件")
        
        print(f"   总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")
        
        print(f"\n🏷️  主题分布 (Top 10):")
        sorted_themes = sorted(
            self.metrics.get('theme_distribution', {}).items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        for theme, count in sorted_themes[:10]:
            print(f"   {theme}: {count}个事件")
        
        print(f"\n📈 评估结论:")
        
        # 主题数量评估
        if self.metrics['theme_count'] > 0:
            print(f"   ✅ 系统成功识别出 {self.metrics['theme_count']} 个主题")
        else:
            print(f"   ⚠️  系统未识别出任何主题")
        
        # 处理完整性评估
        if self.metrics['processed'] == self.metrics['total_events']:
            print(f"   ✅ 所有事件处理完成")
        else:
            print(f"   ⚠️  仅处理了 {self.metrics['processed']}/{self.metrics['total_events']} 个事件")
        
        print(f"\n📁 输出文件:")
        print(f"   optimized_system_results_*.json - 包含每个事件的最终题材归属、决策路径、置信度")
        
        print("\n" + "="*80)


async def main():
    """主函数"""
    # 检查环境
    logger.info("🔍 检查环境配置...")
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ DEEPSEEK_API_KEY环境变量未设置")
        print("\n🔧 修复建议:")
        print("   export DEEPSEEK_API_KEY='your-api-key-here'")
        return 1
    
    logger.info(f"✅ DEEPSEEK_API_KEY已设置")
    
    # 检查测试数据文件
    data_dir = project_root / "evaluate_service" / "data" / "processed"
    events_path = data_dir / "validation_events_fixed.json"
    if not events_path.exists():
        print(f"❌ 测试数据文件不存在: {events_path}")
        return 1
    
    logger.info(f"✅ 找到测试数据文件: {events_path}")
    
    # 创建评估器
    evaluator = IntegratedEvaluator()
    
    try:
        # 1. 加载测试数据
        events = await evaluator.load_test_data()
        evaluator.metrics['total_events'] = len(events)
        
        # 2. 初始化组件
        components = await evaluator.initialize_components()
        
        # 3. 运行评估
        await evaluator.run_evaluation(components, events)
        
        # 4. 生成输出文件
        output_file = await evaluator.generate_output_files()
        
        # 5. 打印总结
        evaluator.print_final_summary()
        
        print(f"\n✅ 集成评估完成！")
        print(f"📁 结果文件: {output_file}")
        
        return 0
            
    except KeyboardInterrupt:
        print("\n\n⚠️  评估被用户中断")
        return 130
    except Exception as e:
        logger.error(f"❌ 评估执行失败: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)