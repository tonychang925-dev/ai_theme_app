#!/usr/bin/env python3
"""
集成评估器 - IntegratedEvaluator
运行优化后的全套 theme_service 组件，生成详细评估报告。
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import sys

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入集成测试执行器
from runners.integrated_test_runner import IntegratedTestRunner

logger = logging.getLogger(__name__)

class IntegratedEvaluator:
    """集成评估器 - 运行全套优化组件并生成报告"""
    
    def __init__(self):
        self.data_dir = project_root / "evaluate_service" / "data"
        self.results_dir = self.data_dir / "results"
        self.reports_dir = self.results_dir / "reports"
        
        # 确保目录存在
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # 测试结果
        self.test_results = None
        self.final_state = None
        self.evaluation_metrics = {}
    
    async def run_evaluation(self) -> Dict:
        """
        运行完整的集成评估
        
        Returns:
            包含评估结果和指标的字典
        """
        logger.info("🎯 开始集成评估 - 运行优化后的全套 theme_service 组件")
        
        # 1. 准备输入数据
        input_file = self.data_dir / "processed" / "validation_events_fixed.json"
        
        if not input_file.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")
        
        logger.info(f"📥 输入文件: {input_file}")
        
        # 2. 创建并运行测试执行器
        runner = IntegratedTestRunner(input_file)
        
        try:
            await runner.initialize()
            self.test_results = await runner.run()
            self.final_state = runner.get_final_state()
            
            # 3. 计算评估指标
            self.evaluation_metrics = self._calculate_metrics(self.test_results, self.final_state)
            
            # 4. 生成输出文件
            output_files = await self._generate_output_files()
            
            # 5. 生成评估报告
            report_file = await self._generate_evaluation_report()
            
            logger.info(f"✅ 集成评估完成")
            logger.info(f"   结果文件: {output_files['results']}")
            logger.info(f"   状态快照: {output_files['state']}")
            logger.info(f"   评估报告: {report_file}")
            
            return {
                'success': True,
                'metrics': self.evaluation_metrics,
                'output_files': output_files,
                'report_file': report_file
            }
            
        except Exception as e:
            logger.error(f"❌ 集成评估失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _calculate_metrics(self, results: List[Dict], final_state: Dict) -> Dict:
        """计算评估指标"""
        total_events = len(results)
        successful_events = sum(1 for r in results if r.get('final_theme'))
        failed_events = total_events - successful_events
        
        # 提取处理时间
        processing_times = [r.get('processing_time', 0) for r in results if r.get('processing_time')]
        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        # 主题统计
        theme_distribution = final_state.get('theme_distribution', {})
        theme_count = len(theme_distribution)
        
        # 决策分布
        actions = [r.get('action') for r in results if r.get('action')]
        create_new_count = sum(1 for a in actions if a == 'CREATE_NEW')
        cluster_count = sum(1 for a in actions if a == 'CLUSTER')
        
        return {
            'total_events': total_events,
            'successful_events': successful_events,
            'failed_events': failed_events,
            'success_rate': successful_events / total_events if total_events > 0 else 0,
            'avg_processing_time_seconds': avg_time,
            'theme_count': theme_count,
            'theme_distribution': theme_distribution,
            'decisions': {
                'CREATE_NEW': create_new_count,
                'CLUSTER': cluster_count
            },
            'system_efficiency': self._calculate_efficiency_metrics(results)
        }
    
    def _calculate_efficiency_metrics(self, results: List[Dict]) -> Dict:
        """计算系统效率指标"""
        if not results:
            return {}
        
        # 提取置信度
        confidences = [r.get('confidence', 0) for r in results if r.get('confidence')]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # 决策时间分析
        decision_times = [r.get('processing_time', 0) for r in results]
        
        return {
            'average_confidence': avg_confidence,
            'min_processing_time': min(decision_times) if decision_times else 0,
            'max_processing_time': max(decision_times) if decision_times else 0,
            'throughput_events_per_minute': len(results) / (sum(decision_times) / 60) if decision_times else 0
        }
    
    async def _generate_output_files(self) -> Dict:
        """生成输出文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 1. 优化系统结果文件
        results_file = self.results_dir / f"optimized_system_results_{timestamp}.json"
        
        optimized_results = {
            'metadata': {
                'evaluation_type': 'integrated_system_evaluation',
                'evaluation_time': datetime.now().isoformat(),
                'system_version': 'optimized_theme_service_v2',
                'data_source': 'validation_events_fixed.json'
            },
            'events': [],
            'summary': self.evaluation_metrics
        }
        
        # 格式化每个事件的结果
        for result in self.test_results:
            event_result = {
                'event_id': result.get('event_id'),
                'original_title': result.get('original_title'),
                'final_theme': result.get('final_theme', '未匹配'),
                'decision': result.get('action'),
                'confidence': result.get('confidence', 0),
                'processing_time': result.get('processing_time', 0),
                'decision_path': self._extract_decision_path(result),
                'timestamp': result.get('timestamp')
            }
            optimized_results['events'].append(event_result)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(optimized_results, f, ensure_ascii=False, indent=2)
        
        # 2. 虚拟数据库状态快照
        state_file = self.results_dir / f"virtual_db_snapshot_{timestamp}.json"
        
        state_snapshot = {
            'snapshot_time': datetime.now().isoformat(),
            'virtual_database_state': self.final_state,
            'database_stats': await self._get_database_stats() if hasattr(self, 'runner') else {}
        }
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state_snapshot, f, ensure_ascii=False, indent=2)
        
        return {
            'results': str(results_file),
            'state': str(state_file)
        }
    
    def _extract_decision_path(self, result: Dict) -> Dict:
        """从结果中提取决策路径"""
        theme_result = result.get('theme_result', {})
        analysis = theme_result.get('analysis', {})
        
        return {
            'model_service_output': result.get('news_event', {}).get('theme_directive', {}),
            'theme_extraction': analysis.get('theme_extraction', {}),
            'similarity_analysis': analysis.get('similarity_analysis', {}),
            'recommendation': analysis.get('recommendation', {}),
            'final_decision': theme_result.get('action'),
            'matched_theme': theme_result.get('theme', {})
        }
    
    async def _get_database_stats(self) -> Dict:
        """获取数据库统计信息（如果可用）"""
        # 这个方法需要在runner中暴露db_manager
        return {}
    
    async def _generate_evaluation_report(self) -> str:
        """生成详细的评估报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.reports_dir / f"integrated_evaluation_report_{timestamp}.json"
        
        report = {
            'report_metadata': {
                'title': '集成系统评估报告',
                'generated_at': datetime.now().isoformat(),
                'evaluator_version': '1.0'
            },
            'executive_summary': self._generate_executive_summary(),
            'detailed_metrics': self.evaluation_metrics,
            'theme_analysis': self._analyze_themes(),
            'performance_analysis': self._analyze_performance(),
            'recommendations': self._generate_recommendations(),
            'appendix': {
                'test_results_sample': self.test_results[:5] if self.test_results else [],
                'theme_distribution_full': self.evaluation_metrics.get('theme_distribution', {})
            }
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return str(report_file)
    
    def _generate_executive_summary(self) -> Dict:
        """生成执行摘要"""
        metrics = self.evaluation_metrics
        
        return {
            'overall_status': 'PASS' if metrics.get('success_rate', 0) > 0.8 else 'WARNING' if metrics.get('success_rate', 0) > 0.6 else 'FAIL',
            'key_findings': [
                f"成功处理 {metrics.get('successful_events', 0)}/{metrics.get('total_events', 0)} 个事件",
                f"系统识别出 {metrics.get('theme_count', 0)} 个不同主题",
                f"平均处理时间: {metrics.get('avg_processing_time_seconds', 0):.2f}秒",
                f"新主题创建率: {metrics.get('decisions', {}).get('CREATE_NEW', 0)/metrics.get('total_events', 1):.1%}"
            ],
            'system_efficiency_rating': self._rate_system_efficiency()
        }
    
    def _rate_system_efficiency(self) -> str:
        """评估系统效率等级"""
        metrics = self.evaluation_metrics
        success_rate = metrics.get('success_rate', 0)
        avg_time = metrics.get('avg_processing_time_seconds', 0)
        
        if success_rate > 0.85 and avg_time < 5.0:
            return '优秀'
        elif success_rate > 0.7 and avg_time < 10.0:
            return '良好'
        elif success_rate > 0.5:
            return '一般'
        else:
            return '待改进'
    
    def _analyze_themes(self) -> Dict:
        """分析主题发现效果"""
        distribution = self.evaluation_metrics.get('theme_distribution', {})
        
        if not distribution:
            return {'analysis': '无主题数据'}
        
        # 计算主题集中度
        total_events = self.evaluation_metrics.get('total_events', 1)
        theme_counts = list(distribution.values())
        
        # 前3大主题的集中度
        top_3_sum = sum(sorted(theme_counts, reverse=True)[:3])
        concentration = top_3_sum / total_events if total_events > 0 else 0
        
        return {
            'theme_concentration': f"{concentration:.1%}",
            'top_themes': sorted(distribution.items(), key=lambda x: x[1], reverse=True)[:5],
            'theme_quality_assessment': self._assess_theme_quality(distribution)
        }
    
    def _assess_theme_quality(self, distribution: Dict) -> List[str]:
        """评估主题质量"""
        assessments = []
        
        # 检查主题名称质量
        for theme_name in distribution.keys():
            if len(theme_name) < 2:
                assessments.append(f"主题'{theme_name}'名称过短")
            elif len(theme_name) > 20:
                assessments.append(f"主题'{theme_name}'名称过长")
        
        # 检查主题分布
        if len(distribution) > 15:
            assessments.append("主题数量可能过多，考虑提高聚类阈值")
        elif len(distribution) < 5 and self.evaluation_metrics.get('total_events', 0) > 20:
            assessments.append("主题数量偏少，考虑降低聚类阈值")
        
        return assessments if assessments else ["主题命名和分布合理"]
    
    def _analyze_performance(self) -> Dict:
        """分析系统性能"""
        efficiency = self.evaluation_metrics.get('system_efficiency', {})
        
        return {
            'processing_performance': {
                'rating': '优秀' if efficiency.get('avg_processing_time_seconds', 0) < 3.0 else 
                         '良好' if efficiency.get('avg_processing_time_seconds', 0) < 6.0 else 
                         '一般',
                'throughput': f"{efficiency.get('throughput_events_per_minute', 0):.1f} 事件/分钟"
            },
            'decision_quality': {
                'average_confidence': f"{efficiency.get('average_confidence', 0):.1%}",
                'confidence_distribution': self._analyze_confidence_distribution()
            }
        }
    
    def _analyze_confidence_distribution(self) -> Dict:
        """分析置信度分布"""
        confidences = []
        for result in self.test_results:
            if result.get('confidence'):
                confidences.append(result['confidence'])
        
        if not confidences:
            return {}
        
        return {
            'high_confidence(>0.8)': sum(1 for c in confidences if c > 0.8),
            'medium_confidence(0.5-0.8)': sum(1 for c in confidences if 0.5 <= c <= 0.8),
            'low_confidence(<0.5)': sum(1 for c in confidences if c < 0.5)
        }
    
    def _generate_recommendations(self) -> List[Dict]:
        """生成优化建议"""
        metrics = self.evaluation_metrics
        recommendations = []
        
        # 基于成功率的建议
        success_rate = metrics.get('success_rate', 0)
        if success_rate < 0.7:
            recommendations.append({
                'area': '匹配准确性',
                'recommendation': '优化主题相似度算法，考虑增加行业匹配权重',
                'priority': '高'
            })
        
        # 基于处理时间的建议
        avg_time = metrics.get('avg_processing_time_seconds', 0)
        if avg_time > 5.0:
            recommendations.append({
                'area': '系统性能',
                'recommendation': '优化AI调用频率，考虑缓存机制',
                'priority': '中'
            })
        
        # 基于主题分布的建议
        theme_count = metrics.get('theme_count', 0)
        if theme_count > 15:
            recommendations.append({
                'area': '主题聚合',
                'recommendation': '提高新主题创建阈值，减少小题材分裂',
                'priority': '中'
            })
        
        return recommendations


async def main():
    """主函数 - 运行集成评估"""
    import sys
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # 环境检查
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        logger.error("❌ 必须设置 DEEPSEEK_API_KEY 环境变量")
        print("\n🔧 配置说明:")
        print("export DEEPSEEK_API_KEY='your-api-key-here'")
        return 1
    
    logger.info("✅ 环境检查通过，开始集成评估...")
    
    # 创建并运行评估器
    evaluator = IntegratedEvaluator()
    result = await evaluator.run_evaluation()
    
    if result.get('success'):
        print(f"\n{'='*60}")
        print("🎉 集成评估成功完成!")
        print(f"{'='*60}")
        
        metrics = result.get('metrics', {})
        print(f"📊 核心指标:")
        print(f"  成功率: {metrics.get('success_rate', 0):.1%}")
        print(f"  主题数量: {metrics.get('theme_count', 0)}")
        print(f"  平均处理时间: {metrics.get('avg_processing_time_seconds', 0):.2f}秒")
        print(f"  新主题创建: {metrics.get('decisions', {}).get('CREATE_NEW', 0)}次")
        print(f"  事件聚类: {metrics.get('decisions', {}).get('CLUSTER', 0)}次")
        
        print(f"\n📁 输出文件:")
        for name, path in result.get('output_files', {}).items():
            print(f"  {name}: {path}")
        print(f"  详细报告: {result.get('report_file', '')}")
        
        return 0
    else:
        print(f"\n❌ 集成评估失败: {result.get('error', '未知错误')}")
        return 1


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)