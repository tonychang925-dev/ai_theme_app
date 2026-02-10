#!/usr/bin/env python3
"""
带进度显示的AI架构测试
详细显示每个步骤的进展和结果
"""
import os
import sys
import asyncio
import logging
import time
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.steps_completed = 0
        self.total_steps = 0
        self.results = {}
    
    def start_step(self, step_name, message):
        """开始一个步骤"""
        elapsed = time.time() - self.start_time
        print(f"\n[{elapsed:.1f}s] 🔄 {step_name}: {message}")
        return step_name
    
    def complete_step(self, step_name, success=True, details=None):
        """完成一个步骤"""
        self.steps_completed += 1
        elapsed = time.time() - self.start_time
        
        icon = "✅" if success else "❌"
        status = "完成" if success else "失败"
        
        print(f"[{elapsed:.1f}s] {icon} {step_name}: {status}")
        
        if details:
            for key, value in details.items():
                if isinstance(value, list) and len(value) > 3:
                    print(f"      {key}: {len(value)} 项")
                elif isinstance(value, dict):
                    print(f"      {key}: {len(value)} 个键值对")
                else:
                    print(f"      {key}: {value}")
        
        self.results[step_name] = {
            'success': success,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        
        return success
    
    def get_summary(self):
        """获取测试摘要"""
        elapsed = time.time() - self.start_time
        success_count = sum(1 for r in self.results.values() if r['success'])
        total_count = len(self.results)
        
        return {
            'total_time': elapsed,
            'steps_total': total_count,
            'steps_success': success_count,
            'success_rate': success_count / total_count if total_count > 0 else 0,
            'results': self.results
        }
    
    def print_summary(self):
        """打印测试摘要"""
        summary = self.get_summary()
        
        print("\n" + "="*70)
        print("测试摘要")
        print("="*70)
        
        print(f"📊 总体统计:")
        print(f"   总耗时: {summary['total_time']:.1f} 秒")
        print(f"   步骤总数: {summary['steps_total']}")
        print(f"   成功步骤: {summary['steps_success']}")
        print(f"   成功率: {summary['success_rate']*100:.1f}%")
        
        print(f"\n📋 详细结果:")
        for step_name, result in summary['results'].items():
            icon = "✅" if result['success'] else "❌"
            print(f"   {icon} {step_name}")
            
            if result['details']:
                for key, value in result['details'].items():
                    if isinstance(value, (int, float, str)):
                        print(f"      {key}: {value}")

async def test_with_detailed_progress():
    """带详细进度显示的测试"""
    tracker = ProgressTracker()
    
    print("="*70)
    print("AI相似性分析架构 - 详细进度测试")
    print("="*70)
    
    # 检查API密钥
    step = tracker.start_step("环境检查", "检查DEEPSEEK_API_KEY")
    if not os.getenv('DEEPSEEK_API_KEY'):
        tracker.complete_step(step, False, {'error': 'DEEPSEEK_API_KEY未设置'})
        print("\n❌ 请设置环境变量: export DEEPSEEK_API_KEY='your-api-key'")
        return False
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    tracker.complete_step(step, True, {'api_key': f"{api_key[:8]}...{api_key[-4:]}"})
    
    try:
        # 1. 导入组件
        step = tracker.start_step("导入组件", "导入所有必要的Python模块")
        
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.client import DatabaseClient
        
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        tracker.complete_step(step, True, {
            'modules_imported': 8,
            'components': ['DatabaseManager', 'AI Parser', '相似性分析器', 'AI客户端', '主题发现引擎']
        })
        
        # 2. 初始化数据库
        step = tracker.start_step("初始化数据库", "创建内存数据库并连接")
        
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        # 添加测试主题
        test_themes = [
            ("人工智能芯片", ["AI", "芯片", "半导体", "英伟达", "GPU"], "AI专用芯片技术"),
            ("新能源汽车", ["电动车", "电池", "特斯拉", "比亚迪", "充电桩"], "新能源汽车及相关技术"),
            ("AR/VR设备", ["AR", "VR", "眼镜", "头显", "元宇宙"], "增强现实和虚拟现实设备"),
            ("生物医药", ["医药", "生物", "创新药", "疫苗", "基因"], "生物医药技术")
        ]
        
        for name, keywords, desc in test_themes:
            await db_manager.create_theme(
                name=name,
                keywords=keywords,
                description=desc
            )
        
        stats = await db_manager.get_stats()
        
        tracker.complete_step(step, True, {
            'database_type': '内存数据库',
            'themes_created': len(test_themes),
            'total_themes': stats['total_themes'],
            'theme_names': [name for name, _, _ in test_themes]
        })
        
        # 3. 创建DatabaseClient
        step = tracker.start_step("创建DatabaseClient", "包装数据库管理器")
        db_client = DatabaseClient(db_manager)
        
        # 验证DatabaseClient方法
        methods = [m for m in dir(db_client) if 'theme' in m.lower() and not m.startswith('_')]
        
        tracker.complete_step(step, True, {
            'client_type': type(db_client).__name__,
            'theme_methods': len(methods),
            'available_methods': methods[:5] + ['...'] if len(methods) > 5 else methods
        })
        
        # 4. 初始化AI解析器
        step = tracker.start_step("初始化AI解析器", "创建DeepSeek解析器")
        
        ai_parser = ReliableDeepSeekParser(
            config={
                'max_retries': 3,
                'timeout': 60,
                'temperature': 0.1,
                'model_name': 'deepseek-chat'
            }
        )
        
        # 测试AI解析器健康状态
        health = await ai_parser.health_check()
        
        tracker.complete_step(step, health.get('is_healthy', False), {
            'parser_type': 'ReliableDeepSeekParser',
            'health_check': health.get('is_healthy', False),
            'model': health.get('model_name', 'unknown'),
            'max_tokens': health.get('max_tokens', 0)
        })
        
        if not health.get('is_healthy', False):
            print("⚠️  AI解析器健康检查失败，但继续测试...")
        
        # 5. 初始化相似性分析器
        step = tracker.start_step("初始化相似性分析器", "创建AIThemeSimilarityAnalyzer")
        
        similarity_analyzer = AIThemeSimilarityAnalyzer(ai_parser)
        
        # 测试相似性分析
        test_event = {
            "id": "progress_test_001",
            "title": "AI芯片技术测试",
            "summary": "测试AI芯片相似性分析",
            "impact_industries": ["人工智能", "半导体"]
        }
        
        test_themes_for_analysis = [{"name": name, "description": desc, "keywords": kw} 
                                   for name, kw, desc in test_themes[:2]]
        
        similarity_result = await similarity_analyzer.analyze_similarity(
            test_event, 
            test_themes_for_analysis
        )
        
        most_similar = similarity_result.get('most_similar_theme', {})
        
        tracker.complete_step(step, True, {
            'analyzer_type': 'AIThemeSimilarityAnalyzer',
            'test_event': test_event['title'],
            'themes_analyzed': len(test_themes_for_analysis),
            'most_similar_theme': most_similar.get('theme_name', '无'),
            'similarity_score': most_similar.get('similarity_score', 0)
        })
        
        # 6. 初始化AI客户端
        step = tracker.start_step("初始化AI客户端", "创建EnhancedAIThemeClient")
        
        ai_client = EnhancedAIThemeClient()
        
        tracker.complete_step(step, True, {
            'client_type': 'EnhancedAIThemeClient',
            'version': '1.0'
        })
        
        # 7. 创建主题发现引擎
        step = tracker.start_step("创建主题发现引擎", "集成所有组件")
        
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            database_client=db_client,
            similarity_analyzer=similarity_analyzer,
            config={
                'fast_track_threshold': 0.85,
                'review_threshold': 0.65,
                'ignore_threshold': 0.3
            }
        )
        
        engine_info = engine.get_engine_info()
        
        tracker.complete_step(step, True, {
            'engine_version': engine_info['engine_version'],
            'analysis_method': engine_info['analysis_method'],
            'components_available': sum(engine_info['components_available'].values()),
            'total_components': len(engine_info['components_available'])
        })
        
        # 8. 处理测试事件
        print(f"\n{'='*70}")
        print("处理测试事件")
        print(f"{'='*70}")
        
        test_events = [
            {
                "id": "progress_001",
                "title": "英伟达发布新一代AI芯片H200",
                "summary": "英伟达发布H200 AI芯片，性能比H100提升40%，采用更先进制程",
                "event_type": "产品发布",
                "impact_industries": ["人工智能", "半导体", "芯片", "高性能计算"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.9, "reason": "重大技术突破"}
            },
            {
                "id": "progress_002", 
                "title": "特斯拉4680电池量产突破",
                "summary": "特斯拉实现4680电池大规模量产，续航里程提升16%",
                "event_type": "技术突破",
                "impact_industries": ["新能源汽车", "电池", "储能"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.8, "reason": "电池技术进展"}
            },
            {
                "id": "progress_003",
                "title": "苹果Vision Pro销量超预期",
                "summary": "苹果Vision Pro AR头显销量超过市场预期，推动AR产业发展",
                "event_type": "市场表现",
                "impact_industries": ["AR/VR", "消费电子", "元宇宙"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.75, "reason": "市场表现良好"}
            }
        ]
        
        event_results = []
        for i, event in enumerate(test_events):
            step_name = f"处理事件 {i+1}"
            step = tracker.start_step(step_name, f"{event['title']}")
            
            try:
                result = await engine.process_single_event(event)
                event_results.append(result)
                
                details = {
                    'event_id': result['event_id'],
                    'status': result['status'],
                    'related_themes': result.get('related_themes_count', 0)
                }
                
                if 'ai_decision' in result:
                    details['decision'] = result['ai_decision'].get('decision')
                    details['confidence'] = result['ai_decision'].get('confidence', 0)
                
                if 'best_match' in result:
                    details['best_match'] = result['best_match']['theme_name']
                    details['similarity'] = result['best_match']['similarity_score']
                
                tracker.complete_step(step_name, result['status'] != 'failed', details)
                
            except Exception as e:
                tracker.complete_step(step_name, False, {
                    'error': str(e),
                    'event_id': event.get('id', 'unknown')
                })
                event_results.append({'status': 'failed', 'error': str(e)})
        
        # 9. 分析结果
        step = tracker.start_step("结果分析", "分析所有事件处理结果")
        
        success_events = [r for r in event_results if r.get('status') != 'failed']
        failed_events = [r for r in event_results if r.get('status') == 'failed']
        
        decisions = {}
        for result in success_events:
            if 'ai_decision' in result:
                decision = result['ai_decision'].get('decision', 'unknown')
                decisions[decision] = decisions.get(decision, 0) + 1
        
        tracker.complete_step(step, len(success_events) > 0, {
            'total_events': len(test_events),
            'successful': len(success_events),
            'failed': len(failed_events),
            'success_rate': len(success_events) / len(test_events),
            'decisions_made': decisions,
            'avg_related_themes': sum(r.get('related_themes_count', 0) for r in success_events) / max(len(success_events), 1)
        })
        
        # 10. 获取引擎统计
        step = tracker.start_step("引擎统计", "获取处理统计信息")
        
        engine_stats = engine.get_stats()
        
        tracker.complete_step(step, True, {
            'total_processed': engine_stats.get('total_processed', 0),
            'created': engine_stats.get('created', 0),
            'merged': engine_stats.get('merged', 0),
            'ignored': engine_stats.get('ignored', 0),
            'ai_similarity_calls': engine_stats.get('ai_similarity_calls', 0),
            'success_rate': engine_stats.get('success_rate', 0)
        })
        
        # 11. 清理资源
        step = tracker.start_step("清理资源", "关闭数据库和AI解析器")
        
        try:
            await ai_parser.close()
            await db_manager.disconnect()
            tracker.complete_step(step, True, {
                'resources_closed': ['AI解析器', '数据库连接']
            })
        except Exception as e:
            tracker.complete_step(step, False, {
                'error': str(e),
                'resources_closed': '部分'
            })
        
        # 打印最终摘要
        tracker.print_summary()
        
        summary = tracker.get_summary()
        overall_success = summary['success_rate'] > 0.7
        
        print("\n" + "="*70)
        if overall_success:
            print("🎉 AI相似性分析架构测试通过！")
            print("所有关键组件正常工作，可以处理实际事件。")
        else:
            print("⚠️  测试部分成功，建议检查失败步骤")
        print("="*70)
        
        return overall_success
        
    except Exception as e:
        print(f"\n❌ 测试过程异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    success = asyncio.run(test_with_detailed_progress())
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    exit(0 if success else 1)
