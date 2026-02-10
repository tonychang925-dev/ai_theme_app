#!/usr/bin/env python3
"""
集成评估器 - 最终修复版
完全解决 'ThemeRecord' object has no attribute 'get' 错误
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

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def setup_logging():
    log_dir = project_root / "evaluate_service" / "data" / "results" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"integrated_evaluator_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
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
    """事件准备器"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.events_cache = {}
    
    async def prepare_all_events(self, events_list):
        """保存所有事件到数据库"""
        logger.info(f"💾 准备 {len(events_list)} 个事件数据到数据库...")
        
        saved_count = 0
        for i, event in enumerate(events_list[:3]):  # 🔥 只测试3个事件
            try:
                event_id = event.get('news_id', f'event_{i}')
                
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
                
                saved_id = await self.db_manager.create_or_update_event(db_event)
                if saved_id:
                    saved_count += 1
                    self.events_cache[event_id] = event
                    
            except Exception as e:
                logger.warning(f"  保存事件失败: {e}")
        
        logger.info(f"✅ 成功保存 {saved_count} 个事件到数据库")
        return saved_count
    
    async def get_event_for_analysis(self, event_id):
        """获取用于分析的事件数据"""
        if event_id in self.events_cache:
            return self.events_cache[event_id]
        return None

class ThemeDiscoverySaverFinal:
    """主题发现结果保存器 - 最终修复版"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        logger.debug("✅ ThemeDiscoverySaverFinal 初始化完成")
    
    async def save_discovery_result(self, discovery_result, event_data):
        """保存主题发现结果到数据库 - 安全版"""
        try:
            action = discovery_result.get('action')
            event_id = event_data.get('news_id', 'unknown')
            
            logger.debug(f"  save_discovery_result: action={action}, event_id={event_id}")
            
            if action == 'CREATE_NEW':
                return await self._save_new_theme_final(discovery_result, event_data)
            elif action == 'CLUSTER':
                return await self._handle_cluster_final(discovery_result, event_data)
        except Exception as e:
            logger.error(f"保存主题结果失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return None, None
    
    async def _save_new_theme_final(self, discovery_result, event_data):
        """最终版保存新主题 - 绝对不使用get()"""
        event_id = event_data.get('news_id', 'unknown')
        
        # 提取主题信息
        theme_info = discovery_result.get('theme', {})
        
        # 安全提取主题名
        theme_name = ""
        if isinstance(theme_info, dict):
            # 使用字典的get方法（这是安全的）
            theme_name = theme_info.get('name', '')
        else:
            theme_name = str(theme_info)
        
        if not theme_name or theme_name in ['无主题', '信息不足', '无法提取主题']:
            return None, None
        
        logger.debug(f"  创建主题: {theme_name}")
        
        try:
            # 直接创建主题
            saved_theme = await self.db_manager.create_theme(
                name=theme_name,
                description=f"{theme_name}主题",
                keywords=[theme_name],
                discovery_source='integrated_evaluator',
                discovery_confidence=0.8
            )
            
            if not saved_theme:
                logger.warning(f"   创建主题返回None: {theme_name}")
                return None, None
            
            logger.debug(f"  主题创建成功，类型: {type(saved_theme)}")
            
            # 🔥🔥🔥 关键修复：安全获取主题ID
            theme_id = self._safe_get_theme_id(saved_theme)
            
            if not theme_id:
                logger.error(f"   无法获取主题ID: {saved_theme}")
                return saved_theme, None
            
            logger.debug(f"  获取到主题ID: {theme_id}")
            
            # 创建关联
            relation = await self.db_manager.create_event_theme_relation(
                event_id=event_id,
                theme_id=theme_id,
                confidence=0.8,
                confidence_level='high'
            )
            
            logger.info(f"   主题创建完成: {theme_name} (ID: {theme_id})")
            return saved_theme, relation
            
        except Exception as e:
            logger.error(f"   创建主题失败 {theme_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, None
    
    def _safe_get_theme_id(self, theme_obj):
        """安全获取主题ID - 绝对不使用get()方法"""
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
    
    async def _handle_cluster_final(self, discovery_result, event_data):
        """最终版处理聚类"""
        # 简化处理，暂时返回None
        return None, None

class IntegratedEvaluatorFinal:
    """集成评估器 - 最终修复版"""
    
    def __init__(self):
        self.start_time = None
        self.results = []
        self.metrics = {
            'total_events': 0,
            'processed': 0,
            'themes_created': 0,
            'themes_clustered': 0
        }
        
        self.data_dir = project_root / "evaluate_service" / "data"
        self.results_dir = self.data_dir / "results"
        self.reports_dir = self.results_dir / "reports"
        
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        self.event_preparer = None
        self.theme_saver = None
    
    async def initialize_components(self):
        """初始化组件"""
        logger.info("🔧 初始化组件...")
        
        try:
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 1. 初始化数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            if hasattr(db_manager, 'clear_all_data'):
                await db_manager.clear_all_data()
                logger.info("  ✅ 数据库已清空")
            
            # 2. 初始化其他组件
            data_fetcher = PureDataFetcher(db_manager)
            self.event_preparer = EventPreparer(db_manager)
            self.theme_saver = ThemeDiscoverySaverFinal(db_manager)
            
            # 3. 初始化AI组件
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                raise ValueError("需要DEEPSEEK_API_KEY")
            
            llm_config = {
                'api_key': api_key,
                'model_name': 'deepseek-chat',
                'max_retries': 2,
                'timeout': 30,
                'temperature': 0.1
            }
            
            llm_parser = ReliableDeepSeekParser(config=llm_config)
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            return {
                'db_manager': db_manager,
                'discovery': discovery
            }
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise
    
    async def load_test_data(self):
        """加载测试数据"""
        events_path = self.data_dir / "processed" / "validation_events_fixed.json"
        
        if not events_path.exists():
            raise FileNotFoundError(f"找不到文件: {events_path}")
        
        with open(events_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取事件
        events = []
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict) and 'events' in data:
            events = data['events']
        else:
            events = list(data.values())
        
        # 只取前3个事件
        events = events[:3]
        
        logger.info(f"✅ 加载 {len(events)} 个测试事件")
        return events
    
    async def run_evaluation(self, components, events):
        """运行评估"""
        logger.info(f"🚀 开始评估测试")
        
        self.start_time = datetime.now()
        db_manager = components['db_manager']
        discovery = components['discovery']
        
        # 保存事件
        saved_count = await self.event_preparer.prepare_all_events(events)
        self.metrics['total_events'] = len(events)
        
        # 处理每个事件
        for i, event in enumerate(events):
            event_id = event.get('news_id', f'event_{i}')
            
            logger.info(f"\n[{i+1}/{len(events)}] 处理事件: {event_id}")
            
            try:
                # 获取事件数据
                complete_event = await self.event_preparer.get_event_for_analysis(event_id)
                if not complete_event:
                    complete_event = event
                
                # 调用主题发现
                logger.info("   🤖 调用theme_service...")
                start_time = time.time()
                
                result = await discovery.process_event(complete_event)
                processing_time = time.time() - start_time
                
                self.metrics['processed'] += 1
                
                # 提取结果
                ai_action = result.get('action')
                ai_theme_info = result.get('theme', {})
                
                # 构建结果记录
                result_record = {
                    'event_id': event_id,
                    'processing_time': processing_time,
                    'timestamp': datetime.now().isoformat()
                }
                
                if ai_action == 'CREATE_NEW':
                    # 提取主题名
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
                    
                    # 🔥🔥🔥 关键：安全保存主题
                    try:
                        saved_theme, relation = await self.theme_saver.save_discovery_result(result, complete_event)
                        if saved_theme:
                            self.metrics['themes_created'] += 1
                            result_record['theme_saved'] = True
                            
                            # 🔥 安全获取主题ID
                            theme_id = self.theme_saver._safe_get_theme_id(saved_theme)
                            result_record['theme_id'] = theme_id
                            result_record['theme_name'] = ai_theme
                            
                            logger.info(f"   主题保存成功: {ai_theme} (ID: {theme_id})")
                        else:
                            result_record['theme_saved'] = False
                            result_record['theme_id'] = None
                            logger.warning(f"   主题保存失败: {ai_theme}")
                    except Exception as save_error:
                        logger.error(f"   保存主题时出错: {save_error}")
                        import traceback
                        logger.error(traceback.format_exc())
                        result_record['theme_saved'] = False
                        result_record['theme_id'] = None
                
                elif ai_action == 'CLUSTER':
                    logger.info(f"   AI决策: 🔗 CLUSTER")
                    result_record['ai_action'] = 'CLUSTER'
                    result_record['final_theme'] = '聚类主题'
                
                # 保存结果
                self.results.append(result_record)
                
                logger.info(f"   ✅ 事件处理完成")
                
            except Exception as e:
                logger.error(f"❌ 处理事件失败: {e}")
                logger.error("🔍 完整错误堆栈:")
                import traceback
                error_trace = traceback.format_exc()
                logger.error(error_trace)
                
                # 保存错误信息到文件
                error_file = self.results_dir / f"error_{event_id}.txt"
                with open(error_file, 'w', encoding='utf-8') as f:
                    f.write(f"事件ID: {event_id}\n错误: {str(e)}\n\n堆栈:\n{error_trace}")
                
                self.results.append({
                    'event_id': event_id,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                
                await asyncio.sleep(2)
        
        logger.info(f"✅ 评估完成，处理了 {self.metrics['processed']} 个事件")
    
    async def generate_output(self):
        """生成输出文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = self.results_dir / f"optimized_system_results_{timestamp}.json"
        
        output_data = {
            'metadata': {
                'evaluation_time': datetime.now().isoformat(),
                'total_events': self.metrics['total_events'],
                'processed_events': self.metrics['processed'],
                'themes_created': self.metrics['themes_created']
            },
            'events': self.results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 结果已保存: {output_file}")
        return output_file

async def main():
    """主函数"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ 需要设置DEEPSEEK_API_KEY环境变量")
        return 1
    
    logger.info("🔧 开始集成评估...")
    
    evaluator = IntegratedEvaluatorFinal()
    
    try:
        # 1. 加载数据
        events = await evaluator.load_test_data()
        
        # 2. 初始化组件
        components = await evaluator.initialize_components()
        
        # 3. 运行评估
        await evaluator.run_evaluation(components, events)
        
        # 4. 生成输出
        output_file = await evaluator.generate_output()
        
        print(f"\n✅ 评估完成！")
        print(f"📁 结果文件: {output_file}")
        print(f"📊 统计: {evaluator.metrics['processed']}/{evaluator.metrics['total_events']} 个事件处理完成")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ 评估失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    asyncio.run(main())