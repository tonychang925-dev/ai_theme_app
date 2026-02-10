# evaluate_service/scripts/run_integrated_test_quick.py
#!/usr/bin/env python3
"""
快速集成测试脚本 - 用于快速验证核心功能
"""
import sys
import asyncio
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

async def quick_test():
    """快速测试"""
    print("🧪 快速集成测试开始...")
    
    try:
        # 导入必要的模块
        from evaluate_service.core.virtual_theme_database import VirtualThemeDatabase
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        from evaluate_service.runners.integrated_test_runner import IntegratedTestRunner
        
        # 初始化组件
        virtual_db = VirtualThemeDatabase()
        theme_fetcher = RelatedThemeFetcher(virtual_db=virtual_db)
        ai_client = EnhancedAIThemeClient(virtual_db=virtual_db)
        dedup_engine = ThemeDeduplicationEngine()
        
        enhanced_engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            theme_fetcher=theme_fetcher,
            dedup_engine=dedup_engine
        )
        
        # 创建测试执行器
        test_runner = IntegratedTestRunner(
            virtual_db=virtual_db,
            enhanced_engine=enhanced_engine,
            output_dir="evaluate_service/results/quick_test"
        )
        
        # 创建少量测试数据
        test_events = [
            {
                'id': 'test_ai_001',
                'title': '人工智能技术新突破',
                'summary': 'AI在图像识别领域取得进展',
                'impact_industries': ['人工智能'],
                'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.8, 'reason': '测试'}
            },
            {
                'id': 'test_ai_002',
                'title': 'AI应用场景扩大',
                'summary': '人工智能在各行业应用增加',
                'impact_industries': ['人工智能', '信息技术'],
                'theme_directive': {'action': 'CREATE_NEW', 'confidence': 0.7, 'reason': '测试'}
            }
        ]
        
        # 运行测试
        print("处理测试事件...")
        report = await test_runner.run_full_test(test_events, max_events=2)
        
        if report:
            print(f"✅ 快速测试完成!")
            print(f"  生成题材数: {report['virtual_database_final_state']['theme_count']}")
            print(f"  事件映射: {report['event_theme_mapping']}")
            return True
        else:
            print("❌ 快速测试失败")
            return False
            
    except Exception as e:
        print(f"❌ 快速测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(quick_test())
    sys.exit(0 if success else 1)