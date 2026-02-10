# evaluate_service/scripts/interface_content_validator.py
"""
接口内容验证器 - 验证EnhancedThemeDiscovery相关接口的内容完整性
"""
#!/usr/bin/env python3
import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

class InterfaceContentValidator:
    """接口内容验证器"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.results_dir = output_dir / "results" / "interface_validation"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        log_file = self.results_dir / f"interface_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file, encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    async def validate_fetcher_interfaces(self, test_data_path: Path) -> Dict[str, Any]:
        """
        验证主题获取器接口的内容完整性
        
        Args:
            test_data_path: 测试数据路径
            
        Returns:
            验证结果
        """
        self.logger.info("🔍 开始验证主题获取器接口内容完整性")
        
        try:
            # 导入需要的模块
            from database_service.memory_manager import MemoryDatabaseManager
            from database_service.config import DatabaseConfig
            from database_service.pure_data_fetcher import PureDataFetcher
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            
            # 1. 初始化数据库
            db_config = DatabaseConfig()
            db_manager = MemoryDatabaseManager(db_config)
            await db_manager.connect()
            
            if hasattr(db_manager, 'clear_all_data'):
                await db_manager.clear_all_data()
            
            # 2. 加载测试数据
            test_events = self._load_test_data(test_data_path)
            
            # 3. 保存测试数据到数据库
            saved_events = await self._save_test_events(db_manager, test_events)
            
            # 4. 创建主题和关联
            theme_id = await self._create_test_theme_and_relations(db_manager, saved_events)
            
            # 5. 验证各个接口
            validation_results = {
                'timestamp': datetime.now().isoformat(),
                'test_events': len(saved_events),
                'methods': {}
            }
            
            # 创建获取器
            data_fetcher = PureDataFetcher(db_manager)
            theme_fetcher = RelatedThemeFetcher(data_fetcher)
            
            # 使用第一个事件作为测试输入
            test_event = test_events[0]
            
            # 验证方法1: fetch_relevant_themes
            self.logger.info("\n📊 验证方法1: fetch_relevant_themes")
            themes1 = await theme_fetcher.fetch_relevant_themes(test_event, limit=3)
            validation_results['methods']['fetch_relevant_themes'] = self._analyze_theme_data(themes1)
            
            # 验证方法2: fetch_themes_with_complete_news_content
            self.logger.info("\n📊 验证方法2: fetch_themes_with_complete_news_content")
            if hasattr(theme_fetcher, 'fetch_themes_with_complete_news_content'):
                themes2 = await theme_fetcher.fetch_themes_with_complete_news_content(test_event, limit=3)
                validation_results['methods']['fetch_themes_with_complete_news_content'] = self._analyze_theme_data(themes2)
            else:
                self.logger.error("❌ fetch_themes_with_complete_news_content 方法不存在！")
                validation_results['methods']['fetch_themes_with_complete_news_content'] = {
                    'error': 'Method not found',
                    'has_complete_content': False
                }
            
            # 6. 生成报告
            report = self._generate_validation_report(validation_results)
            
            # 保存结果
            await self._save_results(validation_results, report)
            
            await db_manager.disconnect()
            
            return validation_results
            
        except Exception as e:
            self.logger.error(f"❌ 验证失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _load_test_data(self, data_path: Path) -> List[Dict[str, Any]]:
        """加载测试数据"""
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 解析数据结构
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict) and 'events' in data:
            events = data['events']
        else:
            events = []
        
        # 只取AR相关的事件
        ar_events = []
        for event in events[:5]:  # 只取前5个
            if not isinstance(event, dict):
                continue
            
            # 检查是否是AR相关
            title = event.get('original_news', {}).get('title', '').lower()
            if any(kw in title for kw in ['ar', '智能', '眼镜', 'meta', 'oakley']):
                ar_events.append(event)
        
        self.logger.info(f"📂 加载到 {len(ar_events)} 个AR相关测试事件")
        return ar_events
    
    async def _save_test_events(self, db_manager, events: List[Dict]) -> List[Dict]:
        """保存测试事件到数据库"""
        saved_events = []
        
        for event in events:
            event_id = event.get('news_id')
            original_news = event.get('original_news', {})
            
            db_event = {
                'id': event_id,
                'news_id': event_id,
                'title': original_news.get('title', ''),
                'full_content': original_news.get('content', ''),
                'content_length': len(original_news.get('content', '')),
                'has_full_content': bool(original_news.get('content')),
                'original_news': original_news,
                'event_info': event.get('event_info', {})
            }
            
            saved_id = await db_manager.create_or_update_event(db_event)
            if saved_id:
                saved_events.append({
                    'id': saved_id,
                    'original_content_length': len(original_news.get('content', '')),
                    'title': original_news.get('title', '')
                })
        
        self.logger.info(f"💾 保存 {len(saved_events)} 个事件到数据库")
        return saved_events
    
    async def _create_test_theme_and_relations(self, db_manager, events: List[Dict]) -> int:
        """创建测试主题和关联"""
        theme_record = await db_manager.create_theme(
            name="AR智能眼镜接口验证主题",
            description="用于验证接口内容完整性的测试主题",
            keywords=["AR", "智能眼镜", "接口验证", "内容完整性"]
        )
        
        # 关联所有事件到主题
        for event in events:
            await db_manager.create_event_theme_relation(
                event_id=event['id'],
                theme_id=theme_record.id,
                confidence=0.9,
                confidence_level="high"
            )
        
        self.logger.info(f"🏷️ 创建主题 '{theme_record.name}'，关联 {len(events)} 个事件")
        return theme_record.id
    
    def _analyze_theme_data(self, themes: List[Dict]) -> Dict[str, Any]:
        """分析主题数据的内容完整性"""
        if not themes:
            return {
                'theme_count': 0,
                'has_complete_content': False,
                'total_content_length': 0,
                'content_field_analysis': {}
            }
        
        result = {
            'theme_count': len(themes),
            'has_complete_content': False,
            'total_content_length': 0,
            'content_field_analysis': {}
        }
        
        # 检查第一个主题
        first_theme = themes[0]
        
        # 检查关键字段
        for field in ['has_complete_content', 'related_news_full_contents', 'related_event_contents']:
            if field in first_theme:
                result['content_field_analysis'][field] = True
                
                if field == 'has_complete_content':
                    result['has_complete_content'] = first_theme[field]
                elif field in ['related_news_full_contents', 'related_event_contents']:
                    content_list = first_theme[field]
                    if content_list:
                        # 计算总内容长度
                        total_length = 0
                        for item in content_list:
                            if isinstance(item, dict):
                                content = item.get('content', '')
                                if content:
                                    total_length += len(content)
                        
                        result['total_content_length'] = total_length
        
        # 如果没有找到标准字段，检查其他可能的content字段
        if not result['content_field_analysis']:
            for key, value in first_theme.items():
                if 'content' in key.lower():
                    if isinstance(value, str):
                        result['content_field_analysis'][key] = f"string:{len(value)}chars"
                    elif isinstance(value, list):
                        result['content_field_analysis'][key] = f"list:{len(value)}items"
        
        return result
    
    def _generate_validation_report(self, results: Dict) -> str:
        """生成验证报告"""
        report_lines = [
            "=" * 80,
            "接口内容完整性验证报告",
            "=" * 80,
            f"验证时间: {results['timestamp']}",
            f"测试事件数: {results['test_events']}",
            "\n方法验证结果:",
            "-" * 40
        ]
        
        for method_name, method_result in results['methods'].items():
            report_lines.append(f"\n📋 {method_name}:")
            if 'error' in method_result:
                report_lines.append(f"  ❌ 错误: {method_result['error']}")
            else:
                report_lines.append(f"  ✅ 返回主题数: {method_result.get('theme_count', 0)}")
                report_lines.append(f"  有完整内容: {method_result.get('has_complete_content', False)}")
                report_lines.append(f"  总内容长度: {method_result.get('total_content_length', 0)}字符")
                
                if method_result.get('content_field_analysis'):
                    report_lines.append("  内容字段分析:")
                    for field, analysis in method_result['content_field_analysis'].items():
                        report_lines.append(f"    - {field}: {analysis}")
        
        # 结论
        report_lines.extend([
            "\n" + "=" * 80,
            "验证结论:",
            "-" * 40
        ])
        
        # 检查两个方法是否都提供了完整内容
        method1 = results['methods'].get('fetch_relevant_themes', {})
        method2 = results['methods'].get('fetch_themes_with_complete_news_content', {})
        
        if method2.get('has_complete_content', False):
            report_lines.append("✅ fetch_themes_with_complete_news_content 提供了完整内容")
        elif 'error' in method2:
            report_lines.append("❌ fetch_themes_with_complete_news_content 方法不存在或出错")
        else:
            report_lines.append("⚠️  fetch_themes_with_complete_news_content 可能未提供完整内容")
        
        if method1.get('total_content_length', 0) > 100:
            report_lines.append("✅ fetch_relevant_themes 提供了足够的内容供AI分析")
        else:
            report_lines.append("⚠️  fetch_relevant_themes 提供的内容可能不足")
        
        return "\n".join(report_lines)
    
    async def _save_results(self, results: Dict, report: str):
        """保存验证结果"""
        # 保存JSON结果
        json_file = self.results_dir / f"validation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # 保存文本报告
        report_file = self.results_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        self.logger.info(f"💾 结果已保存到: {json_file}")
        self.logger.info(f"📋 报告已保存到: {report_file}")
        
        # 打印报告
        print(report)

# 运行入口
async def main():
    """主函数"""
    import sys
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    # 设置路径
    output_dir = project_root / "evaluate_service"
    test_data_path = output_dir / "data" / "processed" / "validation_events_fixed.json"
    
    if not test_data_path.exists():
        print(f"❌ 测试数据文件不存在: {test_data_path}")
        return 1
    
    # 运行验证
    validator = InterfaceContentValidator(output_dir)
    await validator.validate_fetcher_interfaces(test_data_path)
    
    return 0

if __name__ == "__main__":
    asyncio.run(main())