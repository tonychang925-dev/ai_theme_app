# run_integration_test.py
"""
简易集成测试运行脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent  # 假设在项目根目录
sys.path.insert(0, str(project_root))

async def run_test():
    """运行集成测试"""
    print("🔧 准备运行集成测试...")
    
    try:
        from tests.test_integration import IntegrationTestRunner
        
        runner = IntegrationTestRunner()
        
        # 设置环境
        print("1. 设置测试环境...")
        await runner.setup()
        
        # 运行测试
        print("\n2. 运行集成测试...")
        stats = await runner.run_tests()
        
        # 输出结果
        if stats:
            print(f"\n🎯 测试结果:")
            print(f"   总事件数: {stats.get('total', 0)}")
            print(f"   成功数: {stats.get('success', 0)}")
            print(f"   失败数: {stats.get('failed', 0)}")
            
            success_rate = (stats.get('success', 0) / max(stats.get('total', 1), 1)) * 100
            print(f"   成功率: {success_rate:.1f}%")
            
            if success_rate >= 80:
                print("\n✅ 测试通过! 系统改造基本成功。")
            else:
                print("\n⚠️  测试通过率较低，需要进一步调试。")
        
        # 清理
        print("\n3. 清理测试环境...")
        await runner.cleanup()
        
        print("\n🏁 测试运行完成!")
        
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        print("请确保在项目根目录运行此脚本，并且所有模块已正确安装。")
        print(f"当前Python路径: {sys.path}")
        
    except Exception as e:
        print(f"❌ 测试运行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("金融投资AI助理系统 - 集成测试")
    print("=" * 60)
    
    asyncio.run(run_test())