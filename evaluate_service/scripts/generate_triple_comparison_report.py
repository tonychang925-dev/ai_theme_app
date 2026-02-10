# evaluate_service/scripts/generate_triple_comparison_report.py
#!/usr/bin/env python3
"""
生成三方对比报告主脚本
"""
import json
import sys
import logging
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

def main():
    """生成三方对比报告"""
    print("📊 开始生成三方对比评估报告")
    print("=" * 60)
    
    try:
        # 1. 加载数据
        print("📂 步骤1: 加载三方结果数据...")
        
        # 加载优化系统结果
        optimized_path = "evaluate_service/results/integrated_test/optimized_system_results.json"
        if not Path(optimized_path).exists():
            print(f"❌ 优化系统结果不存在: {optimized_path}")
            return
        
        with open(optimized_path, 'r', encoding='utf-8') as f:
            optimized_data = json.load(f)
        
        # 加载基线系统结果
        baseline_path = "evaluate_service/results/baseline_system_results.json"
        if not Path(baseline_path).exists():
            print(f"❌ 基线系统结果不存在: {baseline_path}")
            return
        
        with open(baseline_path, 'r', encoding='utf-8') as f:
            baseline_data = json.load(f)
        
        # 2. 提取事件-题材映射
        optimized_mapping = optimized_data.get('event_theme_mapping', {})
        baseline_mapping = baseline_data.get('event_theme_mapping', {})
        
        print(f"  优化系统: {len(optimized_mapping)} 个事件映射")
        print(f"  基线系统: {len(baseline_mapping)} 个事件映射")
        
        # 3. 执行对比分析
        print("🔍 步骤2: 执行三方对比分析...")
        from evaluate_service.core.comparison_analyzer import TripleComparisonAnalyzer
        
        analyzer = TripleComparisonAnalyzer()
        comparison_results = analyzer.analyze(optimized_mapping, baseline_mapping)
        
        # 4. 生成报告
        print("📝 步骤3: 生成评估报告...")
        
        # 创建报告目录
        report_dir = "evaluate_service/results/triple_comparison"
        Path(report_dir).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON报告
        json_report_path = Path(report_dir) / f"triple_comparison_report_{timestamp}.json"
        with open(json_report_path, 'w', encoding='utf-8') as f:
            json.dump(comparison_results, f, ensure_ascii=False, indent=2)
        
        # HTML报告
        html_report_path = Path(report_dir) / f"triple_comparison_report_{timestamp}.html"
        analyzer.generate_html_report(comparison_results, str(html_report_path))
        
        # 5. 显示关键结果
        print("\n✅ 三方对比报告生成完成!")
        print(f"  JSON报告: {json_report_path}")
        print(f"  HTML报告: {html_report_path}")
        
        self._print_summary_results(comparison_results)
        
        # 6. 给出决策建议
        self._provide_recommendation(comparison_results)
        
        return comparison_results
        
    except Exception as e:
        logger.error(f"生成报告失败: {e}", exc_info=True)
        print(f"❌ 报告生成失败: {e}")
        return None
    
    def _print_summary_results(self, results):
        """打印摘要结果"""
        print("\n📈 核心指标对比:")
        print("-" * 80)
        
        # 题材数量
        theme_counts = results['theme_count_comparison']
        print(f"题材数量:")
        print(f"  优化后系统: {theme_counts['optimized']}个")
        print(f"  基线系统: {theme_counts['baseline']}个")
        print(f"  久赢恒丰标准: {theme_counts['ground_truth']}个")
        
        # 聚类准确率
        accuracy = results['clustering_accuracy_comparison']
        improvement = results['improvement_summary']['accuracy_improvement']
        print(f"\n聚类一致性准确率:")
        print(f"  优化后系统: {accuracy['optimized']:.1%}")
        print(f"  基线系统: {accuracy['baseline']:.1%}")
        print(f"  提升: {improvement['percentage']:.1f}%")
        
        # 严重错配
        severe_mismatches = results['severe_mismatch_comparison']
        reduction = results['improvement_summary']['severe_mismatch_reduction']
        print(f"\n严重错配数:")
        print(f"  优化后系统: {len(severe_mismatches['optimized'])}例")
        print(f"  基线系统: {len(severe_mismatches['baseline'])}例")
        print(f"  减少: {reduction['percentage']:.1f}%")
        
        # 总体评估
        overall = results['overall_assessment']
        print(f"\n🎯 总体评估: {overall['overall_status']}")
        print(f"📋 建议: {overall['recommendation']}")
    
    def _provide_recommendation(self, results):
        """提供决策建议"""
        overall = results['overall_assessment']
        
        print("\n" + "=" * 80)
        
        if overall['overall_status'] == '通过':
            print("🎉 优化目标达成情况:")
            for assessment in overall['domain_assessments']:
                status_icon = "✅" if assessment['status'] == '达标' else "⚠️ "
                print(f"  {status_icon} {assessment['dimension']}: {assessment['comment']}")
            
            print("\n🚀 决策建议: 所有关键指标均已达标，可以推进至下一阶段（连接真实数据库）")
        else:
            print("⚠️  优化目标未完全达成:")
            for assessment in overall['domain_assessments']:
                if assessment['status'] == '未达标':
                    print(f"  ❌ {assessment['dimension']}: {assessment['comment']}")
            
            print("\n🔧 下一步行动建议:")
            print("  1. 分析详细错配案例（见报告中的detailed_mismatch_analysis）")
            print("  2. 优化主题相似度计算算法")
            print("  3. 调整AI决策阈值")
            print("  4. 重新运行测试验证改进效果")

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    results = main()
    
    if results:
        # 根据评估结果返回适当的退出代码
        overall_status = results['overall_assessment']['overall_status']
        if overall_status == '通过':
            print("\n✅ 测试验证通过，可以进入下一阶段")
            sys.exit(0)
        else:
            print("\n❌ 测试验证未完全通过，需要进一步优化")
            sys.exit(1)
    else:
        print("\n❌ 报告生成失败")
        sys.exit(1)