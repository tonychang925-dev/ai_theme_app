# evaluate_service/runners/run_enhanced_discovery_validation.py
"""
运行EnhancedThemeDiscovery组件验证 - 命令行入口
"""
#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def run_validation():
    """运行验证"""
    print("🚀 开始EnhancedThemeDiscovery组件验证")
    print("=" * 80)
    
    try:
        # 导入验证器
        from evaluate_service.scripts.interface_content_validator import InterfaceContentValidator
        
        # 设置路径
        output_dir = project_root / "evaluate_service"
        test_data_path = output_dir / "data" / "processed" / "validation_events_fixed.json"
        
        if not test_data_path.exists():
            print(f"❌ 测试数据文件不存在: {test_data_path}")
            print(f"   请确保文件存在或提供正确的路径")
            return 1
        
        print(f"📂 使用测试数据: {test_data_path}")
        
        # 运行验证
        validator = InterfaceContentValidator(output_dir)
        await validator.validate_fetcher_interfaces(test_data_path)
        
        print("\n✅ 验证完成！")
        print("📋 详细报告保存在: evaluate_service/results/interface_validation/")
        
        return 0
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

def main():
    """主函数"""
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    return asyncio.run(run_validation())

if __name__ == "__main__":
    sys.exit(main())