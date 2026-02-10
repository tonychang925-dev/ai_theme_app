# evaluate_service/scripts/component_comparison_test.py
"""
组件对比测试 - 对比原版和新版主题发现的处理流程
"""
#!/usr/bin/env python3
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

class ComponentComparisonTester:
    """组件对比测试器"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.results_dir = output_dir / "results" / "component_comparison"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        log_file = self.results_dir / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    async def compare_processing_flows(self, test_data_path: Path) -> Dict[str, Any]:
        """
        对比两种处理流程
        
        Args:
            test_data_path: 测试数据路径
            
        Returns:
            对比结果
        """
        self.logger.info("🔍 开始对比原版和新版处理流程")
        
        try:
            # 加载测试数据
            test_events = self._load_test_data(test_data_path, count=3)
            
            # 对比结果存储
            comparison_results = {
                'timestamp': datetime.now().isoformat(),
                'test_events': len(test_events),
                'original_flow': {},
                'enhanced_flow': {},
                'differences': []
            }
            
            # 测试原版流程（AIThemeSimilarityAnalyzer）
            self.logger.info("\n📊 测试原版流程 (AIThemeSimilarityAnalyzer)")
            original_results = await self._test_original_flow(test_events[0])
            comparison_results['original_flow'] = original_results
            
            # 测试新版流程（EnhancedThemeDiscovery）
            self.logger.info("\n📊 测试新版流程 (EnhancedThemeDiscovery)")
            enhanced_results = await self._test_enhanced_flow(test_events[0])
            comparison_results['enhanced_flow'] = enhanced_results
            
            # 分析差异
            comparison_results['differences'] = self._analyze_differences(
                original_results, 
                enhanced_results
            )
            
            # 生成报告
            report = self._generate_comparison_report(comparison_results)
            
            # 保存结果
            await self._save_comparison_results(comparison_results, report)
            
            return comparison_results
            
        except Exception as e:
            self.logger.error(f"❌ 对比测试失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _load_test_data(self, data_path: Path, count: int = 3) -> List[Dict[str, Any]]:
        """加载测试数据"""
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict) and 'events' in data:
            events = data['events']
        else:
            events = []
        
        # 过滤AR相关事件
        ar_events = []
        for event in events[:10]:  # 检查前10个
            if not isinstance(event, dict):
                continue
            
            title = event.get('original_news', {}).get('title', '').lower()
            if any(kw in title for kw in ['ar', '智能', '眼镜']):
                ar_events.append(event)
                
                if len(ar_events) >= count:
                    break
        
        self.logger.info(f"📂 加载到 {len(ar_events)} 个AR相关测试事件")
        return ar_events
    
    async def _test_original_flow(self, test_event: Dict) -> Dict[str, Any]:
        """测试原版流程"""
        try:
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.config import DatabaseConfig
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 初始化数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            if hasattr(db_manager, 'clear_all_data'):
                await db_manager.clear_all_data()
            
            # 保存测试事件
            event_id = test_event.get('news_id')
            original_news = test_event.get('original_news', {})
            
            db_event = {
                'id': event_id,
                'news_id': event_id,
                'title': original_news.get('title', ''),
                'full_content': original_news.get('content', ''),
                'content_length': len(original_news.get('content', '')),
                'has_full_content': True,
                'original_news': original_news,
                'event_info': test_event.get('event_info', {})
            }
            
            saved_id = await db_manager.create_or_update_event(db_event)
            
            # 获取主题
            data_fetcher = PureDataFetcher(db_manager)
            theme_fetcher = RelatedThemeFetcher(data_fetcher)
            
            themes = await theme_fetcher.fetch_relevant_themes(test_event, limit=5)
            
            # 分析主题数据的内容
            theme_analysis = self._analyze_theme_content(themes)
            
            # 记录AI分析器会看到的内容
            llm_parser = ReliableDeepSeekParser(config={'max_retries': 1, 'timeout': 10})
            analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            # 模拟构建提示词（不实际调用API）
            prompt_content = ""
            if hasattr(analyzer, '_build_enhanced_prompt'):
                try:
                    prompt_content = analyzer._build_enhanced_prompt(test_event, themes)
                    theme_analysis['prompt_length'] = len(prompt_content)
                    theme_analysis['prompt_contains_content'] = '完整内容' in prompt_content
                except:
                    pass
            
            await db_manager.disconnect()
            
            return {
                'event_id': event_id,
                'theme_count': len(themes),
                'theme_analysis': theme_analysis,
                'prompt_analysis': {
                    'length': len(prompt_content),
                    'contains_full_content': '完整内容' in prompt_content
                }
            }
            
        except Exception as e:
            self.logger.error(f"原版流程测试失败: {e}")
            return {'error': str(e)}
    
    async def _test_enhanced_flow(self, test_event: Dict) -> Dict[str, Any]:
        """测试新版流程"""
        try:
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.config import DatabaseConfig
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.enhanced_theme_discovery import EnhancedThemeDiscovery
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 初始化数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            if hasattr(db_manager, 'clear_all_data'):
                await db_manager.clear_all_data()
            
            # 保存测试事件
            event_id = test_event.get('news_id')
            original_news = test_event.get('original_news', {})
            
            db_event = {
                'id': event_id,
                'news_id': event_id,
                'title': original_news.get('title', ''),
                'full_content': original_news.get('content', ''),
                'content_length': len(original_news.get('content', '')),
                'has_full_content': True,
                'original_news': original_news,
                'event_info': test_event.get('event_info', {})
            }
            
            saved_id = await db_manager.create_or_update_event(db_event)
            
            # 创建EnhancedThemeDiscovery
            data_fetcher = PureDataFetcher(db_manager)
            llm_parser = ReliableDeepSeekParser(config={'max_retries': 1, 'timeout': 10})
            similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
            
            enhanced_discovery = EnhancedThemeDiscovery(
                data_fetcher=data_fetcher,
                similarity_analyzer=similarity_analyzer,
                new_theme_threshold=0.3
            )
            
            # 模拟process_event内部调用（不实际调用AI）
            # 我们只关心它获取的主题数据
            if hasattr(enhanced_discovery, '_fetch_existing_themes'):
                themes = await enhanced_discovery._fetch_existing_themes(test_event)
                theme_analysis = self._analyze_theme_content(themes)
            else:
                theme_analysis = {'error': '无法获取主题'}
            
            await db_manager.disconnect()
            
            return {
                'event_id': event_id,
                'theme_count': len(themes) if 'themes' in locals() else 0,
                'theme_analysis': theme_analysis,
                'discovery_method': 'EnhancedThemeDiscovery'
            }
            
        except Exception as e:
            self.logger.error(f"新版流程测试失败: {e}")
            return {'error': str(e)}
    
    def _analyze_theme_content(self, themes: List[Dict]) -> Dict[str, Any]:
        """分析主题内容"""
        if not themes:
            return {
                'has_content': False,
                'content_length': 0,
                'content_fields': []
            }
        
        # 检查第一个主题
        first_theme = themes[0]
        
        result = {
            'has_content': False,
            'content_length': 0,
            'content_fields': [],
            'has_complete_content_flag': False
        }
        
        # 检查是否有完整内容标记
        if 'has_complete_content' in first_theme:
            result['has_complete_content_flag'] = first_theme['has_complete_content']
        
        # 检查内容相关字段
        for key, value in first_theme.items():
            if 'content' in key.lower():
                result['content_fields'].append(key)
                
                if isinstance(value, str):
                    result['has_content'] = True
                    result['content_length'] += len(value)
                elif isinstance(value, list) and value:
                    # 可能是related_news_full_contents
                    for item in value[:2]:  # 检查前两个
                        if isinstance(item, dict) and 'content' in item:
                            content = item.get('content', '')
                            if content:
                                result['has_content'] = True
                                result['content_length'] += len(content)
        
        return result
    
    def _analyze_differences(self, original: Dict, enhanced: Dict) -> List[str]:
        """分析差异"""
        differences = []
        
        # 比较主题数量
        orig_count = original.get('theme_count', 0)
        enh_count = enhanced.get('theme_count', 0)
        
        if orig_count != enh_count:
            differences.append(f"主题数量不同: 原版={orig_count}, 新版={enh_count}")
        
        # 比较内容完整性
        orig_analysis = original.get('theme_analysis', {})
        enh_analysis = enhanced.get('theme_analysis', {})
        
        if orig_analysis.get('has_content') != enh_analysis.get('has_content'):
            differences.append(f"内容存在性不同: 原版={orig_analysis.get('has_content')}, 新版={enh_analysis.get('has_content')}")
        
        if orig_analysis.get('content_length', 0) != enh_analysis.get('content_length', 0):
            orig_len = orig_analysis.get('content_length', 0)
            enh_len = enh_analysis.get('content_length', 0)
            differences.append(f"内容长度不同: 原版={orig_len}字符, 新版={enh_len}字符")
            
            if enh_len < orig_len:
                differences.append(f"⚠️  新版内容比原版少 {orig_len - enh_len} 字符")
        
        # 检查完整内容标记
        if 'has_complete_content_flag' in enh_analysis:
            if not enh_analysis['has_complete_content_flag']:
                differences.append("⚠️  新版主题缺少完整内容标记 (has_complete_content=False)")
        
        return differences
    
    def _generate_comparison_report(self, results: Dict) -> str:
        """生成对比报告"""
        report = [
            "=" * 80,
            "组件处理流程对比报告",
            "=" * 80,
            f"对比时间: {results['timestamp']}",
            f"测试事件数: {results['test_events']}",
            "\n" + "=" * 80,
            "📊 原版流程 (AIThemeSimilarityAnalyzer)",
            "=" * 80
        ]
        
        original = results.get('original_flow', {})
        if 'error' in original:
            report.append(f"❌ 错误: {original['error']}")
        else:
            report.extend([
                f"事件ID: {original.get('event_id', 'N/A')}",
                f"获取主题数: {original.get('theme_count', 0)}",
                f"主题分析: {original.get('theme_analysis', {})}",
                f"提示词分析: {original.get('prompt_analysis', {})}"
            ])
        
        report.extend([
            "\n" + "=" * 80,
            "📊 新版流程 (EnhancedThemeDiscovery)",
            "=" * 80
        ])
        
        enhanced = results.get('enhanced_flow', {})
        if 'error' in enhanced:
            report.append(f"❌ 错误: {enhanced['error']}")
        else:
            report.extend([
                f"事件ID: {enhanced.get('event_id', 'N/A')}",
                f"获取主题数: {enhanced.get('theme_count', 0)}",
                f"主题分析: {enhanced.get('theme_analysis', {})}",
                f"使用的方法: {enhanced.get('discovery_method', 'N/A')}"
            ])
        
        # 差异分析
        report.extend([
            "\n" + "=" * 80,
            "🔍 关键差异分析",
            "=" * 80
        ])
        
        differences = results.get('differences', [])
        if differences:
            for i, diff in enumerate(differences, 1):
                report.append(f"{i}. {diff}")
        else:
            report.append("✅ 未发现显著差异")
        
        # 结论
        report.extend([
            "\n" + "=" * 80,
            "🎯 测试结论",
            "=" * 80
        ])
        
        if differences:
            report.append("⚠️  发现处理流程差异，可能需要调整接口实现")
            report.append("\n🔧 建议检查:")
            report.append("1. EnhancedThemeDiscovery._fetch_existing_themes 方法")
            report.append("2. fetch_themes_with_complete_news_content 接口实现")
            report.append("3. 主题数据的内容完整性")
        else:
            report.append("✅ 两种处理流程表现一致")
        
        return "\n".join(report)
    
    async def _save_comparison_results(self, results: Dict, report: str):
        """保存对比结果"""
        # 保存JSON结果
        json_file = self.results_dir / f"comparison_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # 保存文本报告
        report_file = self.results_dir / f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        self.logger.info(f"💾 对比结果已保存到: {json_file}")
        self.logger.info(f"📋 对比报告已保存到: {report_file}")
        
        # 打印报告
        print(report)

# 运行入口
async def main():
    """主函数"""
    import sys
    
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    output_dir = project_root / "evaluate_service"
    test_data_path = output_dir / "data" / "processed" / "validation_events_fixed.json"
    
    if not test_data_path.exists():
        print(f"❌ 测试数据文件不存在: {test_data_path}")
        return 1
    
    tester = ComponentComparisonTester(output_dir)
    await tester.compare_processing_flows(test_data_path)
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())