#!/usr/bin/env python3
"""
76条数据综合评估测试
符合文档要求的完整测试报告生成
"""
import os
import sys
import json
import asyncio
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Comprehensive76DataEvaluator:
    """76条数据综合评估器"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.test_results = []
        self.performance_metrics = {}
        self.ground_truth = None
        
    async def load_test_data(self) -> List[Dict[str, Any]]:
        """加载测试数据"""
        data_path = os.path.join(
            current_dir, 
            "evaluate_service", 
            "data", 
            "processed", 
            "validation_events_enhanced.json"
        )
        
        if not os.path.exists(data_path):
            logger.error(f"数据文件不存在: {data_path}")
            return []
        
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and 'events' in data:
                events = data['events']
            elif isinstance(data, list):
                events = data
            else:
                logger.error(f"数据格式异常: {type(data)}")
                return []
            
            logger.info(f"成功加载 {len(events)} 条测试数据")
            return events[:76]  # 确保最多76条
            
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return []
    
    async def load_ground_truth(self) -> Optional[Dict[str, Any]]:
        """加载ground truth数据"""
        gt_path = os.path.join(
            current_dir,
            "evaluate_service",
            "config",
            "ground_truth_correct.json"
        )
        
        if not os.path.exists(gt_path):
            logger.warning(f"Ground truth文件不存在: {gt_path}")
            return None
        
        try:
            with open(gt_path, 'r', encoding='utf-8') as f:
                ground_truth = json.load(f)
            
            logger.info(f"成功加载ground truth数据")
            return ground_truth
            
        except Exception as e:
            logger.error(f"加载ground truth失败: {e}")
            return None
    
    async def initialize_system(self):
        """初始化系统组件"""
        logger.info("初始化系统组件...")
        
        try:
            # 导入所有需要的组件
            from database_service.config import DatabaseConfig
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.client import DatabaseClient
            
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            
            # 初始化数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            db_client = DatabaseClient(db_manager)
            
            # 初始化AI组件（优化配置）
            ai_parser = ReliableDeepSeekParser(
                config={
                    'max_retries': 3,
                    'timeout': 90,
                    'temperature': 0.1,
                    'enable_cache': True,
                    'max_tokens': 2000
                }
            )
            
            similarity_analyzer = AIThemeSimilarityAnalyzer(ai_parser)
            ai_client = EnhancedAIThemeClient()
            
            # 创建优化后的引擎
            engine = EnhancedThemeDiscoveryEngine(
                ai_client=ai_client,
                database_client=db_client,
                similarity_analyzer=similarity_analyzer,
                config={
                    'fast_track_threshold': 0.85,
                    'review_threshold': 0.60,
                    'ignore_threshold': 0.25,
                    'enable_batch_processing': True
                }
            )
            
            logger.info("✅ 系统组件初始化完成")
            
            return {
                'db_manager': db_manager,
                'db_client': db_client,
                'ai_parser': ai_parser,
                'similarity_analyzer': similarity_analyzer,
                'ai_client': ai_client,
                'engine': engine
            }
            
        except Exception as e:
            logger.error(f"初始化系统组件失败: {e}")
            raise
    
    async def run_comprehensive_evaluation(self, test_events: List[Dict[str, Any]]):
        """运行综合评估"""
        logger.info(f"开始综合评估 {len(test_events)} 条数据")
        
        # 初始化系统
        components = await self.initialize_system()
        engine = components['engine']
        
        # 准备性能追踪
        performance_data = {
            'event_processing_times': [],
            'ai_decision_times': [],
            'similarity_analysis_times': [],
            'total_themes_created': 0,
            'total_themes_merged': 0,
            'total_events_ignored': 0
        }
        
        # 分批处理事件（每批10个）
        batch_size = 10
        results = []
        
        for i in range(0, len(test_events), batch_size):
            batch = test_events[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(test_events) + batch_size - 1) // batch_size
            
            logger.info(f"处理批次 {batch_num}/{total_batches} ({len(batch)} 个事件)")
            
            batch_start = datetime.now()
            batch_results = await engine.batch_process_events(batch, show_progress=False)
            
            # 收集性能数据
            for result in batch_results:
                if 'processing_steps' in result:
                    for step in result['processing_steps']:
                        if step.get('step') == 'ai_decision' and 'duration' in step:
                            performance_data['ai_decision_times'].append(step['duration'])
                        elif step.get('step') == 'fetch_related_themes_ai' and 'duration' in step:
                            performance_data['similarity_analysis_times'].append(step['duration'])
                
                # 统计主题操作
                if result.get('status') == 'created':
                    performance_data['total_themes_created'] += 1
                elif result.get('status') == 'merged':
                    performance_data['total_themes_merged'] += 1
                elif result.get('status') == 'ignored':
                    performance_data['total_events_ignored'] += 1
            
            batch_time = (datetime.now() - batch_start).total_seconds()
            performance_data['event_processing_times'].append(batch_time / len(batch))
            
            results.extend(batch_results)
            
            # 显示进度
            processed = min(i + batch_size, len(test_events))
            percentage = (processed / len(test_events)) * 100
            logger.info(f"进度: {processed}/{len(test_events)} ({percentage:.1f}%)")
        
        # 清理资源
        await components['ai_parser'].close()
        await components['db_manager'].disconnect()
        
        self.test_results = results
        self.performance_metrics = performance_data
        
        return results
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """计算评估指标"""
        if not self.test_results:
            return {}
        
        total_events = len(self.test_results)
        successful = sum(1 for r in self.test_results if r.get('status') != 'failed')
        failed = total_events - successful
        
        # 成功率
        success_rate = successful / total_events if total_events > 0 else 0
        
        # 决策分布
        decision_counts = {}
        for result in self.test_results:
            if 'ai_decision' in result:
                decision = result['ai_decision'].get('decision', 'UNKNOWN')
                decision_counts[decision] = decision_counts.get(decision, 0) + 1
        
        # 相似度统计
        similarity_scores = []
        for result in self.test_results:
            if 'best_match' in result:
                score = result['best_match'].get('similarity_score', 0)
                if score > 0:
                    similarity_scores.append(score)
        
        # 性能指标
        avg_processing_time = sum(self.performance_metrics.get('event_processing_times', [])) / \
                            max(len(self.performance_metrics.get('event_processing_times', [])), 1)
        
        avg_ai_decision_time = sum(self.performance_metrics.get('ai_decision_times', [])) / \
                              max(len(self.performance_metrics.get('ai_decision_times', [])), 1)
        
        avg_similarity_time = sum(self.performance_metrics.get('similarity_analysis_times', [])) / \
                             max(len(self.performance_metrics.get('similarity_analysis_times', [])), 1)
        
        metrics = {
            'total_events': total_events,
            'successful_events': successful,
            'failed_events': failed,
            'success_rate': success_rate,
            'decision_distribution': decision_counts,
            'theme_operations': {
                'created': self.performance_metrics.get('total_themes_created', 0),
                'merged': self.performance_metrics.get('total_themes_merged', 0),
                'ignored': self.performance_metrics.get('total_events_ignored', 0)
            },
            'similarity_analysis': {
                'average_score': sum(similarity_scores) / max(len(similarity_scores), 1) if similarity_scores else 0,
                'max_score': max(similarity_scores) if similarity_scores else 0,
                'min_score': min(similarity_scores) if similarity_scores else 0,
                'samples': len(similarity_scores)
            },
            'performance_metrics': {
                'avg_processing_time_per_event': avg_processing_time,
                'avg_ai_decision_time': avg_ai_decision_time,
                'avg_similarity_analysis_time': avg_similarity_time,
                'events_per_hour': 3600 / avg_processing_time if avg_processing_time > 0 else 0
            }
        }
        
        return metrics
    
    def generate_test_report(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """生成测试报告"""
        total_time = (datetime.now() - self.start_time).total_seconds()
        
        report = {
            'test_id': f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'test_date': datetime.now().isoformat(),
            'test_duration_seconds': total_time,
            'test_configuration': {
                'dataset_size': 76,
                'ai_model': 'DeepSeek-Chat',
                'analysis_method': 'AI相似性分析',
                'engine_version': 'ai_similarity_engine_robust_v1'
            },
            'summary_metrics': {
                'overall_success_rate': metrics.get('success_rate', 0),
                'total_events_processed': metrics.get('total_events', 0),
                'total_time_seconds': total_time
            },
            'detailed_metrics': metrics,
            'clustering_consistency': {
                'description': 'AI相似性分析相比关键词匹配应提供更高的聚类一致性',
                'expected_improvement': '通过AI理解语义相似度，减少误分类'
            },
            'recommendations': self._generate_recommendations(metrics),
            'raw_results_sample': self.test_results[:5] if self.test_results else []
        }
        
        return report
    
    def _generate_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        success_rate = metrics.get('success_rate', 0)
        if success_rate < 0.8:
            recommendations.append("优化错误处理机制，提高成功率")
        
        avg_time = metrics.get('performance_metrics', {}).get('avg_processing_time_per_event', 0)
        if avg_time > 10:
            recommendations.append("优化AI调用性能，考虑批量处理或缓存机制")
        
        similarity_scores = metrics.get('similarity_analysis', {}).get('average_score', 0)
        if similarity_scores < 0.7:
            recommendations.append("调整相似度分析参数，提高匹配准确性")
        
        # 添加基于决策分布的建议
        decision_dist = metrics.get('decision_distribution', {})
        if decision_dist.get('IGNORE', 0) / metrics.get('total_events', 1) > 0.3:
            recommendations.append("调整忽略阈值，减少有效事件的遗漏")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any]):
        """保存测试报告"""
        report_dir = os.path.join(current_dir, "evaluate_service", "data", "results", "ai_similarity_evaluation")
        os.makedirs(report_dir, exist_ok=True)
        
        report_file = os.path.join(report_dir, f"ai_similarity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"测试报告已保存: {report_file}")
        
        # 同时生成简明的CSV报告
        self._generate_csv_summary(report, report_dir)
        
        return report_file
    
    def _generate_csv_summary(self, report: Dict[str, Any], report_dir: str):
        """生成CSV格式的简明报告"""
        csv_file = os.path.join(report_dir, f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        
        summary_data = {
            '测试ID': [report['test_id']],
            '测试日期': [report['test_date']],
            '总耗时(秒)': [report['test_duration_seconds']],
            '处理事件数': [report['detailed_metrics'].get('total_events', 0)],
            '成功率': [f"{report['detailed_metrics'].get('success_rate', 0)*100:.1f}%"],
            '创建主题数': [report['detailed_metrics'].get('theme_operations', {}).get('created', 0)],
            '合并主题数': [report['detailed_metrics'].get('theme_operations', {}).get('merged', 0)],
            '忽略事件数': [report['detailed_metrics'].get('theme_operations', {}).get('ignored', 0)],
            '平均相似度': [f"{report['detailed_metrics'].get('similarity_analysis', {}).get('average_score', 0):.3f}"],
            '平均处理时间(秒)': [f"{report['detailed_metrics'].get('performance_metrics', {}).get('avg_processing_time_per_event', 0):.1f}"],
            '事件处理速度(个/小时)': [f"{report['detailed_metrics'].get('performance_metrics', {}).get('events_per_hour', 0):.1f}"]
        }
        
        df = pd.DataFrame(summary_data)
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
        logger.info(f"CSV摘要报告已保存: {csv_file}")

async def main():
    """主函数"""
    print("="*80)
    print("金融投资AI助理 - 76条数据综合评估测试")
    print("="*80)
    
    # 检查API密钥
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("❌ DEEPSEEK_API_KEY环境变量未设置")
        print("请设置: export DEEPSEEK_API_KEY='your-api-key'")
        return
    
    print(f"🔑 API密钥: {os.getenv('DEEPSEEK_API_KEY')[:8]}...{os.getenv('DEEPSEEK_API_KEY')[-4:]}")
    
    # 创建评估器
    evaluator = Comprehensive76DataEvaluator()
    
    # 加载数据
    print("\n📁 加载测试数据...")
    test_events = await evaluator.load_test_data()
    
    if not test_events:
        print("❌ 无法加载测试数据，测试终止")
        return
    
    print(f"✅ 成功加载 {len(test_events)} 条测试数据")
    
    # 加载ground truth（如果存在）
    ground_truth = await evaluator.load_ground_truth()
    if ground_truth:
        print("✅ 成功加载ground truth数据")
    
    # 询问测试数量
    print(f"\n当前有 {len(test_events)} 条测试数据")
    print("请输入要测试的数量 (输入 '76' 测试全部，或输入其他数字):")
    
    try:
        user_input = input("> ").strip()
        if user_input == '76' or user_input.lower() == 'all':
            test_count = 76
        else:
            test_count = int(user_input)
            test_count = min(test_count, len(test_events))
    except ValueError:
        print("使用默认值: 10")
        test_count = 10
    
    test_events = test_events[:test_count]
    
    print(f"\n{'='*80}")
    print(f"🧪 开始测试 {test_count} 条数据...")
    print(f"   预计时间: {test_count * 15 / 60:.1f} 分钟 (基于15秒/事件)")
    print(f"{'='*80}")
    
    # 运行评估
    results = await evaluator.run_comprehensive_evaluation(test_events)
    
    # 计算指标
    print("\n📊 计算评估指标...")
    metrics = evaluator.calculate_metrics()
    
    # 生成报告
    print("\n📝 生成测试报告...")
    report = evaluator.generate_test_report(metrics)
    
    # 保存报告
    report_file = evaluator.save_report(report)
    
    # 显示关键结果
    print(f"\n{'='*80}")
    print("🎉 评估测试完成!")
    print(f"{'='*80}")
    
    print(f"\n📈 关键指标:")
    print(f"   总事件数: {metrics.get('total_events', 0)}")
    print(f"   成功率: {metrics.get('success_rate', 0)*100:.1f}%")
    print(f"   创建主题: {metrics.get('theme_operations', {}).get('created', 0)}")
    print(f"   合并主题: {metrics.get('theme_operations', {}).get('merged', 0)}")
    print(f"   忽略事件: {metrics.get('theme_operations', {}).get('ignored', 0)}")
    print(f"   平均相似度: {metrics.get('similarity_analysis', {}).get('average_score', 0):.3f}")
    print(f"   平均处理时间: {metrics.get('performance_metrics', {}).get('avg_processing_time_per_event', 0):.1f}秒")
    print(f"   处理速度: {metrics.get('performance_metrics', {}).get('events_per_hour', 0):.1f} 事件/小时")
    
    print(f"\n📋 决策分布:")
    for decision, count in metrics.get('decision_distribution', {}).items():
        percentage = count / metrics.get('total_events', 1) * 100
        print(f"   {decision}: {count} ({percentage:.1f}%)")
    
    print(f"\n💡 优化建议:")
    for i, recommendation in enumerate(report.get('recommendations', []), 1):
        print(f"   {i}. {recommendation}")
    
    print(f"\n📄 详细报告已保存至: {report_file}")
    print(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(main())