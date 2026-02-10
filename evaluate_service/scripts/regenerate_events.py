# evaluate_service/scripts/regenerate_events.py
"""
重新生成完整事件数据脚本
使用真实AI模型处理原始新闻数据，生成结构化事件数据
"""
import json
import logging
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

from model_service.service.event_extractor import AIEventExtractor
from model_service.llm_parser.factory import LLMParserFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventDataRegenerator:
    """事件数据重新生成器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化重新生成器
        
        Args:
            config_path: 配置文件路径
        """
        self.llm_parser = None
        self.event_extractor = None
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'processing_times': []
        }
        
    async def initialize(self):
        """初始化AI组件"""
        logger.info("正在初始化AI事件提取器...")
        
        try:
            # 使用真实AI解析器（DeepSeek）
            self.llm_parser = LLMParserFactory.create_parser_from_env()
            logger.info(f"AI解析器创建成功: {type(self.llm_parser).__name__}")
            
            # 创建事件提取器
            self.event_extractor = AIEventExtractor(self.llm_parser)
            logger.info("事件提取器创建成功")
            
            # 健康检查
            health = await self.event_extractor.health_check()
            if not health:
                raise Exception("AI事件提取器健康检查失败")
                
            logger.info("✅ AI事件提取器初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            return False
    
    async def process_single_news(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单条新闻数据
        
        Args:
            news_data: 新闻数据
            
        Returns:
            处理结果
        """
        start_time = datetime.now()
        news_id = news_data.get('news_id', 'unknown')
        
        try:
            logger.info(f"处理新闻: {news_id} - {news_data.get('title', '')[:50]}...")
            
            # 提取事件
            event_result = await self.event_extractor.extract_event(news_data)
            
            if not event_result:
                raise Exception("事件提取器返回空结果")
            
            # 验证数据完整性
            self._validate_event_integrity(event_result, news_data)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            self.stats['successful'] += 1
            self.stats['processing_times'].append(processing_time)
            
            logger.info(f"✅ 成功处理新闻 {news_id} (耗时: {processing_time:.2f}s)")
            
            return {
                'success': True,
                'news_id': news_id,
                'event_data': event_result,
                'processing_time': processing_time,
                'original_data_preserved': self._check_data_preservation(event_result, news_data)
            }
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self.stats['failed'] += 1
            
            logger.error(f"❌ 处理新闻失败 {news_id}: {e}")
            
            return {
                'success': False,
                'news_id': news_id,
                'error': str(e),
                'processing_time': processing_time,
                'original_data': {
                    'title': news_data.get('title', ''),
                    'content_length': len(news_data.get('content', ''))
                }
            }
    
    def _validate_event_integrity(self, event_data: Dict[str, Any], original_news: Dict[str, Any]):
        """验证事件数据的完整性"""
        required_fields = [
            'news_id', 'event_type', 'impact_industries', 'direction',
            'confidence', 'summary', 'theme_directive', 'original_data'
        ]
        
        missing_fields = [field for field in required_fields if field not in event_data]
        if missing_fields:
            logger.warning(f"事件数据缺少字段: {missing_fields}")
        
        # 检查原始数据是否完整保存
        original_data = event_data.get('original_data', {})
        if not original_data.get('content'):
            logger.warning(f"原始内容未保存，新闻ID: {event_data.get('news_id')}")
        
        # 检查摘要长度是否合理
        ai_summary = event_data.get('summary', '')
        original_content = original_news.get('content', '')
        
        if original_content and ai_summary:
            summary_ratio = len(ai_summary) / len(original_content)
            if summary_ratio < 0.1:
                logger.info(f"摘要压缩率: {summary_ratio:.2%} - 高度概括")
            elif summary_ratio > 0.5:
                logger.info(f"摘要压缩率: {summary_ratio:.2%} - 保留较多细节")
    
    def _check_data_preservation(self, event_data: Dict[str, Any], original_news: Dict[str, Any]) -> Dict[str, Any]:
        """检查数据保留情况"""
        original_content = original_news.get('content', '')
        event_original_data = event_data.get('original_data', {})
        saved_content = event_original_data.get('content', '')
        
        return {
            'original_content_length': len(original_content),
            'saved_content_length': len(saved_content),
            'content_fully_preserved': original_content == saved_content,
            'has_full_content': bool(saved_content),
            'ai_summary_length': len(event_data.get('summary', '')),
            'has_theme_directive': 'theme_directive' in event_data
        }
    
    async def process_batch(self, news_list: List[Dict[str, Any]], 
                          output_path: str,
                          batch_size: int = 10) -> Dict[str, Any]:
        """
        批量处理新闻数据
        
        Args:
            news_list: 新闻列表
            output_path: 输出文件路径
            batch_size: 批次大小
            
        Returns:
            处理统计
        """
        logger.info(f"开始批量处理 {len(news_list)} 条新闻，批次大小: {batch_size}")
        
        total_news = len(news_list)
        results = []
        
        for i in range(0, total_news, batch_size):
            batch = news_list[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_news + batch_size - 1) // batch_size
            
            logger.info(f"\n📦 处理批次 {batch_num}/{total_batches} ({len(batch)} 条新闻)")
            
            # 处理批次
            batch_tasks = [self.process_single_news(news) for news in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"批次处理异常: {result}")
                    results.append({
                        'success': False,
                        'error': str(result)
                    })
                else:
                    results.append(result)
                    if result['success']:
                        self.stats['successful'] += 1
                    else:
                        self.stats['failed'] += 1
            
            self.stats['total_processed'] += len(batch)
            
            # 显示进度
            progress = min(i + len(batch), total_news)
            logger.info(f"进度: {progress}/{total_news} ({progress/total_news:.1%})")
            
            # 每批保存中间结果
            if i + batch_size >= total_news or batch_num % 3 == 0:
                await self._save_intermediate_results(results, output_path, batch_num)
        
        # 计算统计数据
        await self._calculate_final_stats()
        
        # 保存最终结果
        final_output = await self._save_final_results(results, output_path)
        
        return final_output
    
    async def _save_intermediate_results(self, results: List[Dict], 
                                        output_path: str,
                                        batch_num: int):
        """保存中间结果"""
        temp_path = output_path.replace('.json', f'_batch_{batch_num}.json')
        
        # 提取成功的事件数据
        successful_events = [
            r['event_data'] for r in results 
            if r.get('success') and 'event_data' in r
        ]
        
        save_data = {
            'metadata': {
                'batch_number': batch_num,
                'saved_at': datetime.now().isoformat(),
                'total_events': len(successful_events),
                'stats': self.stats.copy()
            },
            'events': successful_events
        }
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"中间结果保存到: {temp_path}")
    
    async def _calculate_final_stats(self):
        """计算最终统计数据"""
        if self.stats['processing_times']:
            avg_time = sum(self.stats['processing_times']) / len(self.stats['processing_times'])
            max_time = max(self.stats['processing_times'])
            min_time = min(self.stats['processing_times'])
            
            self.stats['avg_processing_time'] = avg_time
            self.stats['max_processing_time'] = max_time
            self.stats['min_processing_time'] = min_time
            self.stats['total_time'] = sum(self.stats['processing_times'])
        
        self.stats['success_rate'] = (
            self.stats['successful'] / max(self.stats['total_processed'], 1)
        )
    
    async def _save_final_results(self, results: List[Dict], output_path: str) -> Dict[str, Any]:
        """保存最终结果"""
        # 提取所有成功的事件数据
        all_events = []
        data_integrity_report = []
        
        for result in results:
            if result.get('success') and 'event_data' in result:
                all_events.append(result['event_data'])
                if 'original_data_preserved' in result:
                    data_integrity_report.append(result['original_data_preserved'])
        
        # 创建完整的输出数据
        output_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_events': len(all_events),
                'total_processed': self.stats['total_processed'],
                'successful': self.stats['successful'],
                'failed': self.stats['failed'],
                'success_rate': self.stats.get('success_rate', 0),
                'processing_stats': {
                    'avg_time': self.stats.get('avg_processing_time', 0),
                    'max_time': self.stats.get('max_processing_time', 0),
                    'min_time': self.stats.get('min_processing_time', 0),
                    'total_time': self.stats.get('total_time', 0)
                },
                'generator': 'EventDataRegenerator_v1.0',
                'ai_model': 'DeepSeek'
            },
            'data_integrity_report': {
                'total_checked': len(data_integrity_report),
                'content_fully_preserved': sum(1 for r in data_integrity_report if r.get('content_fully_preserved', False)),
                'has_full_content': sum(1 for r in data_integrity_report if r.get('has_full_content', False)),
                'avg_ai_summary_length': sum(r.get('ai_summary_length', 0) for r in data_integrity_report) / max(len(data_integrity_report), 1),
                'all_have_theme_directive': all(r.get('has_theme_directive', False) for r in data_integrity_report)
            },
            'events': all_events
        }
        
        # 保存到文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 处理完成！")
        logger.info(f"   总处理: {self.stats['total_processed']}")
        logger.info(f"   成功: {self.stats['successful']} ({self.stats.get('success_rate', 0):.1%})")
        logger.info(f"   失败: {self.stats['failed']}")
        logger.info(f"   平均处理时间: {self.stats.get('avg_processing_time', 0):.2f}s")
        logger.info(f"   数据已保存到: {output_path}")
        logger.info(f"{'='*60}")
        
        return output_data
    
    async def cleanup(self):
        """清理资源"""
        if self.event_extractor:
            await self.event_extractor.close()
            logger.info("AI事件提取器资源已释放")


async def main():
    """主函数"""
    # 文件路径
    project_root = Path(__file__).parent.parent.parent
    input_path = project_root / 'evaluate_service' / 'data' / 'raw' / 'validation_dataset.json'
    output_path = project_root / 'evaluate_service' / 'data' / 'processed' / 'validation_events_regenerated.json'
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 加载原始数据
    logger.info(f"加载原始数据: {input_path}")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # 检查数据格式
        if isinstance(raw_data, dict) and 'news_list' in raw_data:
            news_list = raw_data['news_list']
        elif isinstance(raw_data, list):
            news_list = raw_data
        else:
            logger.error(f"未知的数据格式: {type(raw_data)}")
            return
        
        logger.info(f"加载到 {len(news_list)} 条新闻数据")
        
    except Exception as e:
        logger.error(f"加载数据失败: {e}")
        return
    
    # 创建并运行重新生成器
    regenerator = EventDataRegenerator()
    
    try:
        # 初始化
        initialized = await regenerator.initialize()
        if not initialized:
            logger.error("初始化失败，退出")
            return
        
        # 批量处理
        await regenerator.process_batch(
            news_list=news_list,
            output_path=str(output_path),
            batch_size=5  # 小批量以避免API限制
        )
        
    finally:
        # 清理资源
        await regenerator.cleanup()


if __name__ == '__main__':
    asyncio.run(main())