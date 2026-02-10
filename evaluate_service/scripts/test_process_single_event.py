# evaluate_service/scripts/test_process_single_event.py
"""
单事件处理集成测试框架 - 修复版
🔥 修复了空主题处理和错误检查
"""
import asyncio
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockDataFetcher:
    """改进版模拟数据获取器 - 包含更多行业关键词"""
    
    def __init__(self):
        # 包含国防航天和消费电子相关关键词的主题
        self.themes = [
            {
                'id': 1,
                'name': '消费电子',
                'description': '消费电子产品和技术发展',
                'keywords': ['消费电子', '智能手机', '智能家居', '可穿戴设备', '电子产品'],
                'event_count': 15,
                'confidence': 0.85
            },
            {
                'id': 2,
                'name': '人工智能技术',
                'description': '人工智能算法和应用',
                'keywords': ['AI', '人工智能', '机器学习', '深度学习', '大模型'],
                'event_count': 20,
                'confidence': 0.90
            },
            {
                'id': 3,
                'name': '半导体',
                'description': '半导体芯片设计和制造',
                'keywords': ['半导体', '芯片', '集成电路', '晶圆代工', '制造工艺'],
                'event_count': 12,
                'confidence': 0.88
            },
            {
                'id': 4,
                'name': '国防航天',
                'description': '国防和航天技术',
                'keywords': ['国防', '航天', '军事', '卫星', '导弹', '安全'],
                'event_count': 8,
                'confidence': 0.82
            },
            {
                'id': 5,
                'name': '智能穿戴设备',
                'description': '可穿戴智能设备',
                'keywords': ['可穿戴', '智能穿戴', '智能手表', '智能眼镜', 'AR眼镜'],
                'event_count': 10,
                'confidence': 0.80
            }
        ]
    
    async def get_all_active_themes(self, limit=100):
        """模拟获取所有主题"""
        return self.themes[:limit]
    
    async def get_all_active_themes_with_context(self, limit=100):
        """模拟获取带上下文的主题"""
        return self.themes[:limit]


class ProcessSingleEventTester:
    """单事件处理器测试器 - 修复版"""
    
    def __init__(self):
        self.data_fetcher = MockDataFetcher()
        self.theme_fetcher = None
        self.similarity_analyzer = None
        
    async def initialize(self) -> bool:
        """初始化所有组件"""
        try:
            # 导入相关模块
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzerFactory
            
            # 1. 初始化主题获取器
            self.theme_fetcher = RelatedThemeFetcher(self.data_fetcher, use_cache=False)
            logger.info("✅ RelatedThemeFetcher 初始化完成")
            
            # 2. 初始化AI相似性分析器（增强版）
            self.similarity_analyzer = await AIThemeSimilarityAnalyzerFactory.create()
            logger.info("✅ AI相似性分析器（增强版） 初始化完成")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔥 单事件处理流程 - 修复版
        
        流程：
        1. 从数据层获取相关主题（改进过滤）
        2. 进行AI相似性分析（增强版）
        3. 返回处理结果
        """
        event_id = event.get('news_id', 'unknown')
        logger.info(f"\n🚀 开始处理事件: {event_id}")
        
        try:
            # 步骤1: 获取相关主题（数据层）
            logger.info("📋 步骤1: 获取相关主题...")
            
            # 先尝试按行业过滤
            industries = event.get('event_info', {}).get('impact_industries', [])
            existing_themes = []
            
            if industries:
                existing_themes = await self.theme_fetcher.fetch_themes_by_industries(
                    industries, 
                    limit=10
                )
            
            # 如果按行业过滤失败，获取所有主题
            if not existing_themes:
                logger.warning(f"⚠️  按行业 '{industries}' 未找到主题，获取所有主题")
                existing_themes = await self.theme_fetcher.fetch_all_active_themes(limit=10)
            
            logger.info(f"📊 获取到 {len(existing_themes)} 个相关主题")
            
            if not existing_themes:
                return {
                    'event_id': event_id,
                    'status': 'NO_THEMES',
                    'message': '数据库中没有相关主题',
                    'similarity_analysis': None,
                    'recommendation': None
                }
            
            # 步骤2: AI相似性分析（AI层）- 使用增强版
            logger.info("🤖 步骤2: AI相似性分析（增强版）...")
            
            try:
                similarity_result = await self.similarity_analyzer.analyze_with_theme_extraction(
                    event, 
                    existing_themes
                )
            except Exception as ai_error:
                logger.error(f"❌ AI分析失败: {ai_error}")
                # 降级到基础版
                logger.info("🔄 降级到基础相似性分析...")
                similarity_result = await self.similarity_analyzer.analyze_similarity(
                    event, 
                    existing_themes
                )
            
            # 步骤3: 构建最终结果
            result = {
                'event_id': event_id,
                'upstream_action': event.get('theme_discovery_directive', {}).get('action', 'UNKNOWN'),
                'existing_themes_count': len(existing_themes),
                'similarity_analysis': similarity_result.get('similarity_analysis'),
                'theme_extraction': similarity_result.get('theme_extraction'),
                'recommendation': similarity_result.get('recommendation'),
                'processing_metadata': {
                    'theme_fetcher_used': 'RelatedThemeFetcher',
                    'analyzer_used': 'AIThemeSimilarityAnalyzer(增强版)',
                    'analysis_success': True
                }
            }
            
            logger.info(f"✅ 事件处理完成: {event_id}")
            
            # 安全地输出结果
            if similarity_result.get('similarity_analysis'):
                analysis = similarity_result['similarity_analysis']
                logger.info(f"   最佳匹配: {analysis.get('best_match_theme', 'N/A')}")
                logger.info(f"   相似度: {analysis.get('similarity_score', 0):.3f}")
            
            if similarity_result.get('recommendation'):
                recommendation = similarity_result['recommendation']
                logger.info(f"   推荐操作: {recommendation.get('action', 'N/A')}")
                logger.info(f"   建议主题: {recommendation.get('suggested_theme_name', 'N/A')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 处理事件失败 {event_id}: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'event_id': event_id,
                'status': 'ERROR',
                'error': str(e),
                'similarity_analysis': None,
                'recommendation': None
            }
    
    async def run_test_cases(self, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """运行测试用例"""
        results = []
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"\n{'='*60}")
            logger.info(f"测试用例 {i+1}/{len(test_cases)}: {test_case.get('test_name', '未命名')}")
            
            result = await self.process_single_event(test_case['event'])
            results.append({
                'test_case': test_case['test_name'],
                'result': result
            })
            
            # 添加延迟避免API限流
            if i < len(test_cases) - 1:
                await asyncio.sleep(3)  # 稍微延长等待时间
        
        return results


def create_test_cases() -> List[Dict[str, Any]]:
    """创建测试用例"""
    return [
        {
            'test_id': 'INTEGRATION_001',
            'test_name': '国防航天事件',
            'test_description': '测试国防航天事件的完整处理流程',
            'event': {
                'news_id': 'spacex_missile_defense_integration',
                'event_info': {
                    'event_type': '国防采购',
                    'impact_industries': ['航天', '军工', '国防科技'],
                    'direction': '利好',
                    'event_confidence': 0.95
                },
                'theme_discovery_directive': {
                    'action': 'CREATE_NEW',
                    'decision_confidence': 0.9,
                    'reason': '重大国防航天采购'
                },
                'original_news': {
                    'title': '美国太空军采购72颗导弹预警卫星',
                    'content': '美国太空军与SpaceX签署合同采购72颗先进导弹预警卫星，增强导弹防御能力。',
                    'content_length': 45,
                    'date': '2025-01-15'
                }
            }
        },
        {
            'test_id': 'INTEGRATION_002',
            'test_name': '消费电子事件',
            'test_description': '测试消费电子事件的完整处理流程',
            'event': {
                'news_id': 'meta_smart_glasses_integration',
                'event_info': {
                    'event_type': '产品发布',
                    'impact_industries': ['消费电子', '可穿戴设备'],
                    'direction': '利好',
                    'event_confidence': 0.88
                },
                'theme_discovery_directive': {
                    'action': 'CLUSTER',
                    'decision_confidence': 0.8,
                    'reason': '常规消费电子产品发布'
                },
                'original_news': {
                    'title': 'Meta发布智能眼镜新品',
                    'content': 'Meta发布集成AR和AI技术的智能眼镜，具备实时翻译功能。',
                    'content_length': 35,
                    'date': '2025-01-17'
                }
            }
        }
    ]


async def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("🚀 单事件处理集成测试框架（修复版）")
    print("测试目标：验证 related_theme_fetcher + ai_similarity_analyzer 完整流程")
    print("="*80)
    
    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ 错误: DEEPSEEK_API_KEY 环境变量未设置")
        print("请设置: export DEEPSEEK_API_KEY='your-api-key'")
        return
    
    # 创建测试器
    tester = ProcessSingleEventTester()
    
    # 初始化组件
    print("\n🔧 初始化组件...")
    if not await tester.initialize():
        print("❌ 初始化失败")
        return
    
    print("✅ 所有组件初始化成功")
    
    # 创建测试用例
    test_cases = create_test_cases()
    
    # 运行测试
    print(f"\n🔍 开始运行 {len(test_cases)} 个集成测试...")
    results = await tester.run_test_cases(test_cases)
    
    # 输出总结
    print("\n" + "="*80)
    print("📈 集成测试总结")
    print("="*80)
    
    for i, result in enumerate(results):
        test_name = result['test_case']
        result_data = result['result']
        
        print(f"\n{i+1}. {test_name}:")
        print(f"   状态: {result_data.get('status', 'COMPLETE')}")
        
        # 🔥 安全地访问分析结果
        analysis = result_data.get('similarity_analysis')
        recommendation = result_data.get('recommendation')
        
        if analysis:
            print(f"   匹配主题: {analysis.get('best_match_theme', 'N/A')}")
            print(f"   相似度: {analysis.get('similarity_score', 0):.3f}")
        else:
            print(f"   匹配主题: N/A (无分析结果)")
        
        if recommendation:
            print(f"   推荐操作: {recommendation.get('action', 'N/A')}")
            print(f"   建议主题: {recommendation.get('suggested_theme_name', 'N/A')}")
            print(f"   推荐置信度: {recommendation.get('confidence', 0):.2f}")
        else:
            print(f"   推荐操作: N/A (无推荐结果)")
        
        # 检查是否符合预期
        if "国防航天" in test_name:
            if recommendation and recommendation.get('action') == 'CREATE_NEW':
                print(f"   ✅ 符合预期: 国防航天应建议创建新主题")
            else:
                print(f"   ❌ 不符合预期: 期望 CREATE_NEW")
        
        elif "消费电子" in test_name:
            if recommendation and recommendation.get('action') == 'CLUSTER':
                print(f"   ✅ 符合预期: 消费电子应归并到现有主题")
            else:
                print(f"   ❌ 不符合预期: 期望 CLUSTER")
    
    print("\n" + "="*80)
    print("✅ 集成测试框架修复完成！")
    print("下一步：可以基于此框架测试 enhanced_theme_discovery 模块")


if __name__ == "__main__":
    # 设置事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行测试
    asyncio.run(main())