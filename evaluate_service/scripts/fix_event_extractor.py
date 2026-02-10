"""
修复event_extractor以处理test_id
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FixedEventExtractor:
    """修复版事件提取器 - 处理test_id"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(self.project_root))
        
    async def extract_with_fixed_id(self, news_data: dict) -> dict:
        """修复news_id提取"""
        # 优先使用test_id作为news_id
        test_id = news_data.get('test_id')
        news_id = news_data.get('news_id')
        
        if not news_id and test_id:
            # 如果news_id不存在但test_id存在，使用test_id
            news_data = news_data.copy()
            news_data['news_id'] = test_id
            logger.info(f"🔄 使用test_id作为news_id: {test_id}")
        
        return news_data
    
    async def regenerate_with_fixed_ids(self):
        """重新生成数据（修复news_id）"""
        print("🔧 重新生成数据（修复news_id问题）...")
        
        # 导入event_extractor
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "event_extractor", 
                self.project_root / "model_service" / "services" / "event_extractor.py"
            )
            event_extractor_module = importlib.util.module_from_spec(spec)
            sys.modules["event_extractor"] = event_extractor_module
            spec.loader.exec_module(event_extractor_module)
            
            from model_service.services.event_extractor import AIEventExtractor
            extractor = AIEventExtractor()
            print("✅ 创建AI事件提取器成功")
            
        except Exception as e:
            print(f"❌ 导入失败: {e}")
            return False
        
        # 文件路径
        input_path = self.project_root / "evaluate_service" / "data" / "raw" / "validation_dataset.json"
        output_path = self.project_root / "evaluate_service" / "data" / "processed" / "validation_events_fixed_ids.json"
        
        if not input_path.exists():
            print(f"❌ 输入文件不存在: {input_path}")
            return False
        
        # 加载数据
        print(f"📋 加载原始数据...")
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        if isinstance(raw_data, list):
            news_list = raw_data
            print(f"📊 找到 {len(news_list)} 条新闻数据")
        else:
            print("❌ 数据格式不是列表")
            return False
        
        # 修复并处理数据
        print("\n⚡ 开始修复和处理数据...")
        all_events = []
        stats = {
            'total': len(news_list),
            'success': 0,
            'failed': 0
        }
        
        # 处理前10条进行验证
        process_count = min(10, len(news_list))
        print(f"🧪 处理前 {process_count} 条进行验证...")
        
        for i, news in enumerate(news_list[:process_count]):
            test_id = news.get('test_id', f'test_{i+1:03d}')
            title = news.get('title', '无标题')
            
            print(f"\n处理 {i+1}/{process_count}: {test_id} - {title[:30]}...")
            
            try:
                # 修复news_id
                fixed_news = news.copy()
                fixed_news['news_id'] = test_id
                
                # 提取事件
                event_data = await extractor.extract_event(fixed_news)
                
                if event_data:
                    all_events.append(event_data)
                    stats['success'] += 1
                    print(f"  ✅ 成功提取")
                    print(f"    使用的news_id: {event_data.get('news_id')}")
                    print(f"    原始test_id: {test_id}")
                    
                    # 检查数据完整性
                    if 'original_data' in event_data:
                        content = event_data['original_data'].get('content', '')
                        print(f"    原始内容长度: {len(content)} 字符")
                    
                    if 'theme_directive' in event_data:
                        directive = event_data['theme_directive']
                        print(f"    主题指令: {directive.get('action')} (置信度: {directive.get('confidence')})")
                else:
                    stats['failed'] += 1
                    print(f"  ❌ 提取失败")
                    
            except Exception as e:
                stats['failed'] += 1
                print(f"  ❌ 异常: {str(e)[:100]}")
        
        # 保存结果
        print(f"\n💾 保存结果...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        result_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_processed': process_count,
                'successful': stats['success'],
                'failed': stats['failed'],
                'success_rate': stats['success'] / max(process_count, 1),
                'note': '修复news_id问题后生成的事件数据',
                'fix_applied': '使用test_id作为news_id'
            },
            'events': all_events
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        print("="*60)
        print("✅ 修复完成!")
        print(f"   总处理: {process_count}")
        print(f"   成功: {stats['success']} ({stats['success']/max(process_count,1):.1%})")
        print(f"   失败: {stats['failed']}")
        print(f"   数据已保存到: {output_path}")
        print("="*60)
        
        return True

async def main():
    extractor = FixedEventExtractor()
    success = await extractor.regenerate_with_fixed_ids()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
