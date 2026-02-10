# run_real_data_test.py
"""
运行真实数据测试的简易脚本
"""
import asyncio
import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)


async def main():
    """主函数"""
    print("=" * 70)
    print("运行76条真实数据测试")
    print("=" * 70)
    
    try:
        from tests.test_real_data import RealDataTestRunner
        
        # 创建测试运行器
        runner = RealDataTestRunner()
        
        # 设置环境
        print("\n1. 设置测试环境...")
        await runner.setup()
        
        # 运行测试（先测试10条，快速验证）
        print("\n2. 运行测试（先测试10条快速验证）...")
        stats = await runner.run_tests(max_events=10)
        
        # 显示结果
        if stats:
            success_rate = stats.get('success_rate', 0)
            print(f"\n📊 快速测试结果:")
            print(f"  测试事件数: {stats.get('total_events', 0)}")
            print(f"  成功率: {success_rate:.1f}%")
            
            if success_rate >= 80:
                print("\n✅ 快速测试通过!")
                print("建议运行完整76条数据测试。")
                
                run_full = input("\n是否运行完整76条数据测试? (y/n): ").lower() == 'y'
                if run_full:
                    print("\n3. 运行完整76条数据测试...")
                    full_stats = await runner.run_tests(max_events=None)
                    
                    if full_stats:
                        full_success_rate = full_stats.get('success_rate', 0)
                        print(f"\n🎯 完整测试结果:")
                        print(f"  总事件数: {full_stats.get('total_events', 0)}")
                        print(f"  成功率: {full_success_rate:.1f}%")
                        print(f"  创建主题数: {full_stats.get('total_themes_created', 'N/A')}")
            else:
                print("\n⚠️  快速测试失败率较高，建议先调试。")
        
        print("\n🏁 测试完成!")
        
    except ImportError as e:
        print(f"\n❌ 导入失败: {e}")
        print("请确保 test_real_data.py 文件存在。")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())