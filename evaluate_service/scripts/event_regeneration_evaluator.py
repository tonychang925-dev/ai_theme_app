"""
事件重新生成评估器
重新生成76条事件数据，验证AI模型提取能力
"""
import json
import asyncio
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EventRegenerationEvaluator:
    """事件重新生成评估器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(self.project_root))
        
        self.extractor = None
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'processing_times': [],
            'data_integrity_scores': []
        }
        
        # 文件路径
        self.input_path = self.project_root / "evaluate_service" / "data" / "raw" / "validation_dataset.json"
        self.output_path = self.project_root / "evaluate_service" / "data" / "processed" / "validation_events_regenerated.json"
        self.report_path = self.project_root / "evaluate_service" / "data" / "results" / "reports" / "event_regeneration_report.json"
        self.log_path = self.project_root / "evaluate_service" / "data" / "results" / "logs" / f"event_regeneration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    async def initialize(self):
        """初始化AI提取器"""
        logger.info("初始化AI事件提取器...")
        
        try:
            # 直接导入文件
            import importlib.util
            
            # 导入 event_extractor.py
            spec = importlib.util.spec_from_file_location(
                "event_extractor", 
                self.project_root / "model_service" / "services" / "event_extractor.py"
            )
            event_extractor_module = importlib.util.module_from_spec(spec)
            sys.modules["event_extractor"] = event_extractor_module
            spec.loader.exec_module(event_extractor_module)
            
            from model_service.services.event_extractor import AIEventExtractor
            self.extractor = AIEventExtractor()
            
            logger.info("✅ AI事件提取器初始化成功")
            
            # 健康检查
            health = await self.extractor.health_check()
            logger.info(f"🩺 健康检查: {health}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            return False
    
    def _calculate_integrity_score(self, event_data: Dict[str, Any], original_news: Dict[str, Any]) -> float:
        """计算数据完整性分数"""
        score = 0
        max_score = 5
        
        # 1. 原始内容是否保存
        if event_data.get('original_data', {}).get('content'):
            score += 1
        
        # 2. 是否有有意义的摘要
        if len(event_data.get('summary', '')) > 30:
            score += 1
        
        # 3. 是否有主题指令
        if event_data.get('theme_directive'):
            score += 1
        
        # 4. 是否有影响行业
        if event_data.get('impact_industries'):
            score += 1
        
        # 5. 是否有有效事件类型
        if event_data.get('event_type') and event_data['event_type'] != 'unknown':
            score += 1
        
        return score / max_score
    
    async def process_single_news(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理单条新闻"""
        start_time = datetime.now()
        news_id = news_data.get('news_id', 'unknown')
        
        try:
            logger.info(f"处理新闻: {news_id} - {news_data.get('title', '')[:50]}...")
            
            event_data = await self.extractor.extract_event(news_data)
            
            if not event_data:
                return {
                    'success': False,
                    'news_id': news_id,
                    'error': '提取器返回None'
                }
            
            processing_time = (datetime.now() - start_time).total_seconds()
            integrity_score = self._calculate_integrity_score(event_data, news_data)
            
            return {
                'success': True,
                'news_id': news_id,
                'event_data': event_data,
                'processing_time': processing_time,
                'integrity_score': integrity_score
            }
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"处理新闻失败 {news_id}: {e}")
            return {
                'success': False,
                'news_id': news_id,
                'error': str(e),
                'processing_time': processing_time
            }
    
    async def evaluate(self, batch_size: int = 5, test_mode: bool = False):
        """执行评估"""
        logger.info("=" * 60)
        logger.info("🚀 开始事件重新生成评估")
        logger.info("=" * 60)
        
        # 初始化
        if not await self.initialize():
            return {'error': '初始化失败'}
        
        # 加载数据
        if not self.input_path.exists():
            return {'error': f'输入文件不存在: {self.input_path}'}
        
        with open(self.input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict) and 'news_list' in data:
            news_list = data['news_list']
        elif isinstance(data, list):
            news_list = data
        else:
            return {'error': '未知的数据格式'}
        
        logger.info(f"📊 加载到 {len(news_list)} 条新闻数据")
        
        # 确定处理数量
        if test_mode:
            process_count = min(5, len(news_list))
            logger.info(f"🧪 测试模式：只处理前 {process_count} 条")
        else:
            process_count = len(news_list)
            logger.info(f"⚡ 完整模式：处理全部 {process_count} 条")
        
        # 批量处理
        all_events = []
        all_results = []
        
        for i in range(0, process_count, batch_size):
            batch_end = min(i + batch_size, process_count)
            batch = news_list[i:batch_end]
            batch_num = (i // batch_size) + 1
            total_batches = (process_count + batch_size - 1) // batch_size
            
            logger.info(f"\n📦 批次 {batch_num}/{total_batches} ({len(batch)} 条)")
            
            # 处理当前批次
            tasks = [self.process_single_news(news) for news in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"批次处理异常: {result}")
                    all_results.append({
                        'success': False,
                        'error': str(result)
                    })
                else:
                    all_results.append(result)
                    
                    if result['success']:
                        self.stats['successful'] += 1
                        all_events.append(result['event_data'])
                        self.stats['processing_times'].append(result['processing_time'])
                        self.stats['data_integrity_scores'].append(result['integrity_score'])
                    else:
                        self.stats['failed'] += 1
            
            self.stats['total_processed'] += len(batch)
            
            # 显示进度
            progress = min(i + len(batch), process_count)
            logger.info(f"进度: {progress}/{process_count} ({progress/process_count:.1%})")
        
        # 保存生成的事件数据
        logger.info("💾 保存生成的事件数据...")
        output_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'evaluator': 'EventRegenerationEvaluator_v1.0',
                'total_processed': self.stats['total_processed'],
                'successful': self.stats['successful'],
                'failed': self.stats['failed'],
                'success_rate': self.stats['successful'] / max(self.stats['total_processed'], 1),
                'avg_processing_time': sum(self.stats['processing_times']) / max(len(self.stats['processing_times']), 1),
                'avg_integrity_score': sum(self.stats['data_integrity_scores']) / max(len(self.stats['data_integrity_scores']), 1),
                'test_mode': test_mode,
                'note': '使用真实AI模型重新生成的事件数据'
            },
            'events': all_events
        }
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        # 生成评估报告
        logger.info("📊 生成评估报告...")
        report = await self._generate_report(all_results, output_data['metadata'])
        
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 显示结果
        logger.info("=" * 60)
        logger.info("✅ 评估完成!")
        logger.info(f"   总处理: {self.stats['total_processed']}")
        logger.info(f"   成功: {self.stats['successful']} ({self.stats['successful']/max(self.stats['total_processed'],1):.1%})")
        logger.info(f"   失败: {self.stats['failed']}")
        logger.info(f"   平均处理时间: {output_data['metadata']['avg_processing_time']:.2f}s")
        logger.info(f"   平均完整性: {output_data['metadata']['avg_integrity_score']:.2f}")
        logger.info(f"   事件数据: {self.output_path}")
        logger.info(f"   评估报告: {self.report_path}")
        logger.info("=" * 60)
        
        return report
    
    async def _generate_report(self, all_results: List[Dict], metadata: Dict) -> Dict[str, Any]:
        """生成评估报告"""
        successful_results = [r for r in all_results if r['success']]
        failed_results = [r for r in all_results if not r['success']]
        
        # 计算各种指标
        metrics = {
            'extraction_success_rate': len(successful_results) / max(len(all_results), 1),
            'avg_processing_time': sum(r.get('processing_time', 0) for r in successful_results) / max(len(successful_results), 1) if successful_results else 0,
            'avg_integrity_score': sum(r.get('integrity_score', 0) for r in successful_results) / max(len(successful_results), 1) if successful_results else 0,
            'total_events': len(successful_results)
        }
        
        # 数据完整性分析
        integrity_analysis = {
            'events_with_content': sum(1 for r in successful_results if r.get('event_data', {}).get('original_data', {}).get('content')),
            'events_with_summary': sum(1 for r in successful_results if r.get('event_data', {}).get('summary')),
            'events_with_theme_directive': sum(1 for r in successful_results if r.get('event_data', {}).get('theme_directive')),
            'events_with_industries': sum(1 for r in successful_results if r.get('event_data', {}).get('impact_industries')),
            'total_analyzed': len(successful_results)
        }
        
        # 失败分析
        error_analysis = {}
        for result in failed_results:
            error_type = result.get('error', 'unknown')
            error_analysis[error_type] = error_analysis.get(error_type, 0) + 1
        
        return {
            'evaluation_name': '事件重新生成评估',
            'evaluation_time': datetime.now().isoformat(),
            'metadata': metadata,
            'summary_metrics': metrics,
            'integrity_analysis': integrity_analysis,
            'error_analysis': error_analysis,
            'sample_events': [
                {
                    'news_id': r['event_data'].get('news_id'),
                    'event_type': r['event_data'].get('event_type'),
                    'summary_preview': r['event_data'].get('summary', '')[:100] + '...',
                    'theme_directive': r['event_data'].get('theme_directive', {}),
                    'integrity_score': r.get('integrity_score')
                } for r in successful_results[:3]
            ] if successful_results else [],
            'recommendations': self._generate_recommendations(metrics, integrity_analysis)
        }
    
    def _generate_recommendations(self, metrics: Dict, integrity_analysis: Dict) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if metrics['extraction_success_rate'] < 0.9:
            recommendations.append("提高事件提取成功率：优化AI提示词或检查API配置")
        
        if metrics['avg_integrity_score'] < 0.8:
            recommendations.append("提高数据完整性：确保更多字段被正确提取和保存")
        
        total_analyzed = integrity_analysis.get('total_analyzed', 0)
        if total_analyzed > 0:
            if integrity_analysis.get('events_with_content', 0) / total_analyzed < 0.9:
                recommendations.append("确保更多事件的原始内容被完整保存")
            
            if integrity_analysis.get('events_with_theme_directive', 0) / total_analyzed < 0.9:
                recommendations.append("提高主题指令生成质量")
        
        if not recommendations:
            recommendations.append("当前配置良好，继续保持")
        
        return recommendations


async def main():
    """主函数"""
    evaluator = EventRegenerationEvaluator()
    
    # 检查参数
    test_mode = '--test' in sys.argv
    batch_size = 5
    
    report = await evaluator.evaluate(batch_size=batch_size, test_mode=test_mode)
    
    # 打印简要结果
    if 'error' in report:
        print(f"❌ 评估失败: {report['error']}")
        return 1
    
    print("\n📋 评估摘要:")
    metrics = report['summary_metrics']
    print(f"   成功提取率: {metrics['extraction_success_rate']:.1%}")
    print(f"   平均完整性: {metrics['avg_integrity_score']:.2f}")
    print(f"   平均处理时间: {metrics['avg_processing_time']:.2f}s")
    print(f"   生成事件数: {metrics['total_events']}")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
