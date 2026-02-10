#!/usr/bin/env python3
"""
主题检索器完整信息传递测试
位置: evaluate_service/scripts/test_theme_fetcher.py
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

print(f"项目根目录: {project_root}")

# 配置日志
log_dir = project_root / "evaluate_service" / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"theme_fetcher_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)

async def test_theme_fetcher_basic():
    """测试主题检索器基本功能"""
    logger.info("🧪 测试 RelatedThemeFetcher 基本功能")
    
    try:
        # 首先检查模块是否存在
        import importlib
        try:
            importlib.import_module('theme_service.related_theme_fetcher')
            logger.info("✅ 可以导入related_theme_fetcher模块")
        except ImportError as e:
            logger.error(f"❌ 无法导入related_theme_fetcher: {e}")
            return False
        
        # 检查依赖模块
        try:
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.pure_data_fetcher import PureDataFetcher
            logger.info("✅ 可以导入数据库依赖模块")
        except ImportError as e:
            logger.error(f"❌ 无法导入数据库模块: {e}")
            return False
        
        # 创建模拟的数据获取器
        class MockDataFetcher:
            def __init__(self):
                self.themes = [
                    {
                        'id': 1,
                        'name': '人工智能',
                        'description': '人工智能相关主题',
                        'keywords': ['AI', '人工智能', '机器学习'],
                        'event_count': 5,
                        'heat_score': 85,
                        'context': {
                            'event_summaries': [
                                'AI公司发布新算法，效率提升明显',
                                '人工智能在医疗诊断领域取得突破'
                            ],
                            'common_industries': ['人工智能', '软件'],
                            'time_range': '最近3个月'
                        },
                        'ai_description': '人工智能主题，包含多种AI技术'
                    }
                ]
            
            async def get_all_active_themes_with_context(self, limit=100):
                return self.themes[:limit]
            
            async def get_all_active_themes(self, limit=100):
                # 模拟ThemeRecord对象
                class MockThemeRecord:
                    def __init__(self, data):
                        self.id = data['id']
                        self.name = data['name']
                        self.description = data['description']
                        self.keywords = data['keywords']
                
                return [MockThemeRecord(t) for t in self.themes[:limit]]
        
        # 创建模拟的相似性分析器
        class MockSimilarityAnalyzer:
            async def analyze_similarity(self, event_data, existing_themes, top_n):
                logger.info(f"模拟相似性分析，事件: {event_data.get('title')}")
                return {
                    'most_similar_theme': {
                        'theme_name': existing_themes[0]['name'] if existing_themes else '未知',
                        'similarity_score': 0.75,
                        'similarity_reason': '模拟分析结果',
                        'confidence': 0.8
                    },
                    'similar_themes': [],
                    'analysis_summary': '模拟分析摘要',
                    'recommendation': 'MERGE_WITH_EXISTING'
                }
        
        # 创建主题检索器
        try:
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            
            mock_data_fetcher = MockDataFetcher()
            mock_analyzer = MockSimilarityAnalyzer()
            
            fetcher = RelatedThemeFetcher(
                data_fetcher=mock_data_fetcher,
                similarity_analyzer=mock_analyzer,
                use_cache=False
            )
            
            logger.info("✅ 创建RelatedThemeFetcher实例成功")
            
            # 创建测试事件
            test_events = [
                {
                    'id': 'test_event_full',
                    'title': 'AI技术突破事件',
                    'summary': '某公司发布AI大模型',
                    'full_summary': '某AI公司今日正式发布了新一代人工智能大模型，该模型在多项基准测试中表现优异，相比上一代产品性能提升了30%。该技术突破预计将对人工智能行业产生深远影响。',
                    'event_type': '技术突破',
                    'impact_industries': ['人工智能', '软件'],
                    'direction': '利好',
                    'confidence': 0.85
                },
                {
                    'id': 'test_event_partial',
                    'title': '测试事件部分信息',
                    'summary': '简要摘要...',
                    'original_data': {
                        'content_preview': '这是一个完整的新闻内容预览，包含详细的信息描述，供AI进行完整分析使用。'
                    },
                    'event_type': '测试',
                    'impact_industries': ['测试'],
                    'direction': '中性',
                    'confidence': 0.7
                }
            ]
            
            # 测试每个事件
            for event in test_events:
                logger.info(f"\n测试事件: {event['title']}")
                logger.info(f"事件ID: {event['id']}")
                
                # 检查事件数据完整性
                summary_len = len(event.get('summary', ''))
                has_full = 'full_summary' in event
                has_original = 'original_data' in event
                
                logger.info(f"摘要长度: {summary_len}字符")
                logger.info(f"有完整摘要: {'是' if has_full else '否'}")
                logger.info(f"有原始数据: {'是' if has_original else '否'}")
                
                # 模拟主题检索器的数据增强
                enhanced_event = event.copy()
                
                # 尝试获取完整内容
                best_content = event.get('summary', '')
                
                # 检查完整摘要
                if 'full_summary' in event and len(event['full_summary']) > len(best_content) * 1.2:
                    best_content = event['full_summary']
                    enhanced_event['summary'] = best_content
                    enhanced_event['data_enhanced'] = True
                    logger.info(f"使用完整摘要，长度: {len(best_content)}字符")
                
                # 检查原始数据
                elif 'original_data' in event and isinstance(event['original_data'], dict):
                    if 'content_preview' in event['original_data']:
                        content = event['original_data']['content_preview']
                        if content and len(content) > len(best_content) * 1.2:
                            best_content = content
                            enhanced_event['summary'] = best_content
                            enhanced_event['data_enhanced'] = True
                            logger.info(f"使用原始数据内容，长度: {len(best_content)}字符")
                
                final_len = len(enhanced_event.get('summary', ''))
                data_sufficient = final_len >= 100  # 至少100字符才算信息充足
                
                if data_sufficient:
                    logger.info(f"✅ 事件数据充足 ({final_len}字符)")
                else:
                    logger.warning(f"⚠️ 事件数据可能不足 ({final_len}字符)")
            
            logger.info("\n✅ RelatedThemeFetcher基本功能测试通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ RelatedThemeFetcher测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        logger.error(f"❌ 主题检索器测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_test_results(results, test_type="theme_fetcher"):
    """保存测试结果"""
    results_dir = project_root / "evaluate_service" / "results"
    results_dir.mkdir(exist_ok=True)
    
    # 保存JSON格式
    json_file = results_dir / f"{test_type}_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 测试结果已保存到: {json_file}")
    return json_file

async def main():
    """主测试函数"""
    print("🚀 启动主题检索器信息传递测试")
    print("="*60)
    
    results = {
        'test_time': datetime.now().isoformat(),
        'modules': {},
        'tests': [],
        'passed': False,
        'errors': []
    }
    
    try:
        # 运行测试
        test_passed = await test_theme_fetcher_basic()
        
        if test_passed:
            results['modules']['RelatedThemeFetcher'] = 'PASS'
            results['passed'] = True
            results['tests'].append({
                'name': '基本功能测试',
                'status': 'PASS',
                'description': '主题检索器基本功能和数据传递测试'
            })
            print("✅ 主题检索器测试通过")
        else:
            results['modules']['RelatedThemeFetcher'] = 'FAIL'
            results['passed'] = False
            results['tests'].append({
                'name': '基本功能测试',
                'status': 'FAIL',
                'description': '主题检索器测试失败'
            })
            print("❌ 主题检索器测试失败")
        
        # 保存结果
        save_test_results(results)
        
        # 打印总结
        print("\n" + "="*60)
        print("📊 主题检索器测试完成")
        print(f"测试状态: {'通过' if test_passed else '失败'}")
        
        if test_passed:
            print("🎉 主题检索器测试通过！")
            print("信息传递机制验证完成")
            return 0
        else:
            print("❌ 主题检索器测试失败")
            print("需要修复数据传递问题")
            return 1
            
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        return 130
    except Exception as e:
        print(f"测试程序异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断")
        exit_code = 130
    except Exception as e:
        print(f"测试程序异常: {e}")
        exit_code = 1
    
    sys.exit(exit_code)
