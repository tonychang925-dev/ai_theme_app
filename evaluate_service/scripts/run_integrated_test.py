#!/usr/bin/env python3
"""
运行集成测试的简易脚本 - 聚类一致性评估版
"""
import asyncio
import os
import sys

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)


async def main():
    """主函数"""
    print("=" * 70)
    print("运行聚类一致性集成测试")
    print("=" * 70)
    print("评估重点：聚类一致性，而非名称匹配")
    print("-" * 70)
    
    try:
        from evaluate_service.runners.integrated_test_runner import IntegratedTestRunner
        
        # 创建测试运行器
        runner = IntegratedTestRunner()
        
        # 设置环境
        print("\n1. 设置测试环境...")
        await runner.setup()
        
        # 运行快速测试
        print("\n2. 运行快速测试（10条数据，验证聚类一致性）...")
        quick_stats = await runner.run_tests(max_events=10)
        
        if quick_stats:
            print(f"\n📊 快速测试结果:")
            print(f"  测试事件数: {quick_stats.get('total_events', 0)}")
            print(f"  成功率: {quick_stats.get('success_rate', 0):.1f}%")
            
            if 'clustering_analysis' in quick_stats:
                clustering = quick_stats['clustering_analysis']
                print(f"  聚类一致性: {clustering.get('overall_consistency_percentage', 0):.1f}%")
                print(f"  严重错误数: {clustering.get('serious_error_count', 0)}")
                print(f"  AI主题数: {clustering.get('ai_theme_groups', 0)} (标准: {clustering.get('ground_truth_groups', 0)})")
            
            # 评估是否通过快速测试
            success_rate = quick_stats.get('success_rate', 0)
            consistency = quick_stats.get('clustering_analysis', {}).get('overall_consistency_percentage', 0)
            
            if success_rate >= 80 and consistency >= 70:
                print("\n✅ 快速测试通过! 聚类一致性良好")
                
                # 询问是否运行完整测试
                print("\n是否运行完整76条数据测试? (y/n): ", end='')
                run_full = input().strip().lower() == 'y'
                
                if run_full:
                    print("\n3. 运行完整76条数据测试...")
                    full_stats = await runner.run_tests(max_events=None)
                    
                    if full_stats:
                        print(f"\n🎯 完整测试结果:")
                        print(f"  总事件数: {full_stats.get('total_events', 0)}")
                        print(f"  成功率: {full_stats.get('success_rate', 0):.1f}%")
                        
                        if 'clustering_analysis' in full_stats:
                            full_clustering = full_stats['clustering_analysis']
                            print(f"  聚类一致性: {full_clustering.get('overall_consistency_percentage', 0):.1f}%")
                            print(f"  严重错误数: {full_clustering.get('serious_error_count', 0)}")
                            print(f"  AI主题数: {full_clustering.get('ai_theme_groups', 0)} (标准: {full_clustering.get('ground_truth_groups', 0)})")
            else:
                print("\n⚠️  快速测试结果不理想，建议先调试系统。")
                print("  建议检查：")
                print("  1. API密钥是否正确")
                print("  2. 网络连接是否正常")
                print("  3. EnhancedThemeAnalyzer的Prompt是否需要优化")
        
        print("\n🏁 测试完成!")
        
    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("请确保 integrated_test_runner.py 文件存在。")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())