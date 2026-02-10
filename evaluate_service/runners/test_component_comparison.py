#!/usr/bin/env python3
"""
组件对比测试
对比EnhancedThemeDiscovery与直接使用AIThemeSimilarityAnalyzer的结果差异
"""
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

class ComponentComparisonTester:
    """组件对比测试器"""
    
    def __init__(self):
        self.results_dir = project_root / "evaluate_service" / "data" / "results" / "reports"
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    async def run_comparison(self):
        """运行对比测试"""
        print("🔍 组件对比测试: EnhancedThemeDiscovery vs AIThemeSimilarityAnalyzer")
        print("=" * 80)
        
        # 1. 创建测试事件样本
        test_events = self._create_test_events()
        
        # 2. 分别运行两种方法
        print("\n🔧 方法1: 直接使用AIThemeSimilarityAnalyzer...")
        direct_results = await self._test_direct_analyzer(test_events)
        
        print("\n🔧 方法2: 使用EnhancedThemeDiscovery...")
        enhanced_results = await self._test_enhanced_discovery(test_events)
        
        # 3. 对比结果
        print("\n📊 结果对比分析")
        print("=" * 80)
        
        comparison = self._compare_results(direct_results, enhanced_results)
        
        # 4. 生成报告
        await self._generate_comparison_report(comparison)
        
        print(f"\n{'='*80}")
        if comparison['are_equivalent']:
            print("✅ 两种方法结果完全等价！")
        else:
            print("⚠️  两种方法结果存在差异")
            print(f"   主要差异: {comparison['main_differences']}")
        
        print(f"📄 详细报告已保存至: {self.results_dir / 'component_comparison.json'}")
    
    def _create_test_events(self) -> List[Dict]:
        """创建测试事件样本"""
        # 简化的测试数据，基于我们的10个AI/AR眼镜事件
        return [
            {
                'news_id': 'test_event_1',
                'original_news': {
                    'title': 'Meta与Oakley合作推出智能眼镜',
                    'content': 'Meta与Oakley合作推出的智能眼镜专为运动场景设计，内置摄像头可以拍摄第一人称视角的运动视频。'
                },
                'event_info': {
                    'event_type': '产品发布',
                    'impact_industries': ['消费电子', '人工智能']
                }
            },
            {
                'news_id': 'test_event_2',
                'original_news': {
                    'title': '英伟达公开AR眼镜专利技术',
                    'content': '英伟达公开了一项AR眼镜专利，名为"无背光增强现实数字全息技术"，该技术可显著降低AR眼镜功耗。'
                },
                'event_info': {
                    'event_type': '技术突破',
                    'impact_industries': ['半导体', '消费电子']
                }
            }
        ]
    
    async def _test_direct_analyzer(self, events: List[Dict]) -> List[Dict]:
        """测试直接使用AIThemeSimilarityAnalyzer"""
        results = []
        
        try:
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            llm_parser = ReliableDeepSeekParser(config={'max_retries': 3, 'timeout': 60})
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            for event in events:
                # 模拟空主题列表（第一次创建）
                result = await similarity_analyzer.analyze_with_theme_extraction(event, [])
                
                results.append({
                    'event_id': event['news_id'],
                    'extracted_name': result['theme_extraction']['extracted_name'],
                    'confidence': result['theme_extraction']['confidence'],
                    'naming_reason': result['theme_extraction']['naming_reason']
                })
            
            logger.info(f"✅ 直接分析器测试完成: {len(results)} 个事件")
            
        except Exception as e:
            logger.error(f"❌ 直接分析器测试失败: {e}")
        
        return results
    
    async def _test_enhanced_discovery(self, events: List[Dict]) -> List[Dict]:
        """测试使用EnhancedThemeDiscovery"""
        results = []
        
        try:
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.config import DatabaseConfig
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
            
            # 创建内存数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            # 创建数据获取器
            data_fetcher = PureDataFetcher(db_manager)
            
            # 创建EnhancedThemeDiscovery
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            llm_parser = ReliableDeepSeekParser(config={'max_retries': 3, 'timeout': 60})
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            theme_discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            for event in events:
                # 使用EnhancedThemeDiscovery处理
                result = await theme_discovery.process_event(event)
                
                if result['action'] != 'ERROR':
                    theme_info = result.get('theme', {})
                    analysis = result.get('analysis', {})
                    
                    results.append({
                        'event_id': event['news_id'],
                        'extracted_name': theme_info.get('name', '未知'),
                        'confidence': theme_info.get('confidence', 0),
                        'naming_reason': theme_info.get('naming_reason', ''),
                        'action': result['action']
                    })
            
            logger.info(f"✅ 增强发现组件测试完成: {len(results)} 个事件")
            
            # 清理
            if hasattr(db_manager, 'disconnect'):
                await db_manager.disconnect()
            
        except Exception as e:
            logger.error(f"❌ 增强发现组件测试失败: {e}")
        
        return results
    
    def _compare_results(self, direct_results: List[Dict], enhanced_results: List[Dict]) -> Dict:
        """对比两种方法的结果"""
        comparison = {
            'comparison_time': datetime.now().isoformat(),
            'direct_method_count': len(direct_results),
            'enhanced_method_count': len(enhanced_results),
            'matching_events': [],
            'different_events': [],
            'are_equivalent': True,
            'main_differences': []
        }
        
        # 按事件ID匹配结果
        direct_by_id = {r['event_id']: r for r in direct_results}
        enhanced_by_id = {r['event_id']: r for r in enhanced_results}
        
        all_event_ids = set(direct_by_id.keys()) | set(enhanced_by_id.keys())
        
        for event_id in all_event_ids:
            direct_result = direct_by_id.get(event_id)
            enhanced_result = enhanced_by_id.get(event_id)
            
            if direct_result and enhanced_result:
                # 比较关键字段
                is_same_name = direct_result['extracted_name'] == enhanced_result['extracted_name']
                confidence_diff = abs(direct_result['confidence'] - enhanced_result['confidence'])
                
                if is_same_name and confidence_diff < 0.1:
                    comparison['matching_events'].append({
                        'event_id': event_id,
                        'direct_name': direct_result['extracted_name'],
                        'enhanced_name': enhanced_result['extracted_name'],
                        'confidence_diff': confidence_diff
                    })
                else:
                    comparison['different_events'].append({
                        'event_id': event_id,
                        'direct_name': direct_result['extracted_name'],
                        'enhanced_name': enhanced_result['extracted_name'],
                        'confidence_diff': confidence_diff,
                        'action': enhanced_result.get('action', 'N/A')
                    })
                    comparison['are_equivalent'] = False
            else:
                # 某个方法缺少结果
                comparison['different_events'].append({
                    'event_id': event_id,
                    'direct_result': '存在' if direct_result else '缺失',
                    'enhanced_result': '存在' if enhanced_result else '缺失'
                })
                comparison['are_equivalent'] = False
        
        # 总结主要差异
        if comparison['different_events']:
            comparison['main_differences'] = [
                f"事件 {diff['event_id']}: 直接方法='{diff.get('direct_name', 'N/A')}', 增强方法='{diff.get('enhanced_name', 'N/A')}'"
                for diff in comparison['different_events'][:3]
            ]
        
        return comparison
    
    async def _generate_comparison_report(self, comparison: Dict):
        """生成对比报告"""
        report_path = self.results_dir / "component_comparison.json"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)
        
        # 生成摘要
        print(f"\n📋 对比摘要:")
        print(f"  测试时间: {comparison['comparison_time']}")
        print(f"  直接方法结果数: {comparison['direct_method_count']}")
        print(f"  增强方法结果数: {comparison['enhanced_method_count']}")
        print(f"  匹配事件数: {len(comparison['matching_events'])}")
        print(f"  差异事件数: {len(comparison['different_events'])}")
        
        if comparison['different_events']:
            print(f"\n⚠️  发现差异的事件:")
            for diff in comparison['different_events'][:5]:  # 只显示前5个
                print(f"  - 事件 {diff['event_id']}: 直接='{diff.get('direct_name', 'N/A')}', 增强='{diff.get('enhanced_name', 'N/A')}'")

async def main():
    """主函数"""
    # 检查API密钥
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ 错误: DEEPSEEK_API_KEY环境变量未设置")
        return 1
    
    tester = ComponentComparisonTester()
    
    try:
        await tester.run_comparison()
        return 0
    except KeyboardInterrupt:
        print("\n\n⚠️  对比测试被用户中断")
        return 130
    except Exception as e:
        print(f"❌ 对比测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import asyncio
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)