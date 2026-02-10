# test_enhanced_theme_final.py
"""
最终版增强主题发现测试 - 修复所有问题
"""
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockDataFetcher:
    """模拟数据获取器 - 精简版"""
    
    def __init__(self):
        self.themes = [
            {
                'id': 1,
                'name': '消费电子',
                'description': '消费电子产品和技术发展',
                'keywords': ['消费电子', '智能设备'],
                'status': 'active'
            },
            {
                'id': 2,
                'name': '半导体',
                'description': '半导体制造与芯片技术主题',
                'keywords': ['半导体', '芯片', '集成电路'],
                'status': 'active'
            },
            {
                'id': 3,
                'name': '智能穿戴设备',
                'description': '可穿戴智能设备主题',
                'keywords': ['可穿戴', '智能穿戴', '智能设备'],
                'status': 'active'
            }
        ]
    
    async def get_all_active_themes(self, limit=100):
        return [t for t in self.themes if t.get('status') == 'active'][:limit]
    
    async def get_all_active_themes_with_context(self, limit=100):
        return [t for t in self.themes if t.get('status') == 'active'][:limit]


async def test_production_scenarios():
    """生产环境场景测试"""
    print("🚀 生产环境场景测试")
    print("="*60)
    
    # 检查API密钥
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY 环境变量未设置")
        return
    
    print(f"✅ API密钥已设置: {api_key[:10]}...")
    
    try:
        # 1. 创建数据获取器
        data_fetcher = MockDataFetcher()
        
        # 2. 使用简化创建方法
        print("\n🔧 使用简化方法创建增强主题发现模块...")
        
        from theme_service.enhanced_theme_discovery import create_enhanced_theme_discovery
        
        discovery = await create_enhanced_theme_discovery(data_fetcher, api_key)
        print("✅ 增强主题发现模块创建成功")
        
        # 3. 关键场景测试
        scenarios = [
            {
                'id': 1,
                'name': '国防航天 - 应该创建新主题',
                'event': {
                    'news_id': 'prod_defense_001',
                    'event_info': {
                        'event_type': '国防采购',
                        'impact_industries': ['航天', '军工'],
                        'direction': '利好'
                    },
                    'original_news': {
                        'title': '导弹预警卫星采购',
                        'content': '美国太空军采购导弹预警卫星增强防御能力'
                    }
                },
                'expected_action': 'CREATE_NEW',
                'expected_theme': '导弹预警卫星'
            },
            {
                'id': 2,
                'name': '半导体技术 - 应该归并',
                'event': {
                    'news_id': 'prod_semiconductor_001',
                    'event_info': {
                        'event_type': '技术突破',
                        'impact_industries': ['半导体'],
                        'direction': '利好'
                    },
                    'original_news': {
                        'title': '3nm芯片量产',
                        'content': '台积电3nm芯片开始大规模量产'
                    }
                },
                'expected_action': 'CLUSTER',
                'expected_theme': '半导体'
            },
            {
                'id': 3,
                'name': 'AR眼镜 - 应该归并到智能穿戴',
                'event': {
                    'news_id': 'prod_ar_001',
                    'event_info': {
                        'event_type': '产品发布',
                        'impact_industries': ['消费电子'],
                        'direction': '利好'
                    },
                    'original_news': {
                        'title': '苹果AR眼镜发布',
                        'content': '苹果发布新一代AR智能眼镜'
                    }
                },
                'expected_action': 'CLUSTER',
                'expected_theme': '智能穿戴设备'
            }
        ]
        
        # 4. 运行测试
        print(f"\n🧪 开始运行 {len(scenarios)} 个关键场景测试...")
        print("-" * 60)
        
        results = []
        for scenario in scenarios:
            print(f"\n📋 场景{scenario['id']}: {scenario['name']}")
            print(f"   事件: {scenario['event']['original_news']['title']}")
            print(f"   预期: {scenario['expected_action']} -> {scenario['expected_theme']}")
            
            try:
                # 处理事件
                result = await discovery.process_event(scenario['event'])
                
                # 提取结果
                action = result.get('action', 'UNKNOWN')
                
                # 获取主题名称
                if action == 'CREATE_NEW':
                    theme_name = result.get('theme', {}).get('name', 'N/A')
                elif action == 'CLUSTER':
                    theme_name = result.get('theme', {}).get('name', 'N/A')
                else:
                    theme_name = 'N/A'
                
                # 显示结果
                print(f"   实际: {action} -> {theme_name}")
                
                # 显示分析详情
                if 'analysis' in result:
                    analysis = result['analysis']
                    
                    # 主题提取
                    if 'theme_extraction' in analysis:
                        extracted = analysis['theme_extraction'].get('extracted_name', 'N/A')
                        print(f"   提取主题: {extracted}")
                    
                    # 相似性分析
                    if 'similarity_analysis' in analysis:
                        sim = analysis['similarity_analysis']
                        match = sim.get('best_match_theme', 'N/A')
                        score = sim.get('similarity_score', 0)
                        print(f"   匹配主题: {match} (分数: {score:.3f})")
                
                # 判断结果
                action_match = action == scenario['expected_action']
                
                # 对于CREATE_NEW场景，只检查action
                # 对于CLUSTER场景，检查action和主题匹配
                if scenario['expected_action'] == 'CREATE_NEW':
                    passed = action_match
                    check_msg = "动作匹配" if action_match else "动作不匹配"
                else:
                    theme_match = theme_name == scenario['expected_theme']
                    passed = action_match and theme_match
                    check_msg = f"动作{'匹配' if action_match else '不匹配'}, 主题{'匹配' if theme_match else '不匹配'}"
                
                status = "✅ 通过" if passed else "❌ 失败"
                print(f"   测试结果: {status} ({check_msg})")
                
                results.append({
                    'scenario': scenario['name'],
                    'expected_action': scenario['expected_action'],
                    'expected_theme': scenario['expected_theme'],
                    'actual_action': action,
                    'actual_theme': theme_name,
                    'passed': passed
                })
                
            except Exception as e:
                print(f"   ❌ 处理失败: {e}")
                results.append({
                    'scenario': scenario['name'],
                    'error': str(e),
                    'passed': False
                })
            
            # 添加延迟
            if scenario['id'] < len(scenarios):
                await asyncio.sleep(2)  # 2秒延迟
        
        # 5. 输出总结
        print("\n" + "="*60)
        print("📊 生产环境测试总结")
        print("="*60)
        
        total = len(results)
        passed = sum(1 for r in results if r.get('passed', False))
        
        print(f"总场景数: {total}")
        print(f"通过数: {passed}")
        print(f"失败数: {total - passed}")
        print(f"通过率: {passed/total*100:.1f}%" if total > 0 else "0%")
        
        # 详细结果
        print("\n🔍 详细结果:")
        for i, result in enumerate(results):
            print(f"\n{i+1}. {result['scenario']}:")
            if 'error' in result:
                print(f"   ❌ 错误: {result['error']}")
            else:
                print(f"   预期: {result['expected_action']} -> {result['expected_theme']}")
                print(f"   实际: {result['actual_action']} -> {result['actual_theme']}")
                print(f"   结果: {'✅ 通过' if result['passed'] else '❌ 失败'}")
        
        if passed == total:
            print("\n🎉 所有生产场景测试通过！系统准备就绪！")
            print("\n📋 下一步行动:")
            print("1. ✅ 将修复后的代码集成到主分支")
            print("2. ✅ 部署到测试环境")
            print("3. ✅ 运行完整的端到端测试")
            print("4. ✅ 监控生产环境性能")
        else:
            print(f"\n⚠️  有 {total-passed} 个场景失败，需要调试")
        
    except Exception as e:
        print(f"❌ 测试过程出现错误: {e}")
        import traceback
        traceback.print_exc()


async def quick_health_check():
    """快速健康检查"""
    print("🧪 快速健康检查")
    print("="*60)
    
    try:
        # 创建基本组件
        data_fetcher = MockDataFetcher()
        
        # 直接导入并创建
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
        
        # 使用环境变量中的API密钥
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("⚠️  警告: 未设置DEEPSEEK_API_KEY，使用默认配置")
        
        # 创建LLM解析器
        llm_parser = ReliableDeepSeekParser(config={'api_key': api_key} if api_key else {})
        
        # 创建分析器
        analyzer = AIThemeSimilarityAnalyzer(llm_parser)
        
        # 创建主题发现模块
        discovery = EnhancedThemeDiscovery(data_fetcher, analyzer)
        
        # 健康检查
        health = await discovery.health_check()
        print(f"✅ 健康检查: {'通过' if health else '失败'}")
        
        if health:
            print("🎉 所有组件健康，系统可以投入生产！")
        else:
            print("⚠️  健康检查失败，需要调试")
            
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    print("选择测试类型:")
    print("1. 生产环境场景测试（完整）")
    print("2. 快速健康检查")
    choice = input("请输入选择 (1 或 2): ").strip()
    
    if choice == "1":
        asyncio.run(test_production_scenarios())
    else:
        asyncio.run(quick_health_check())