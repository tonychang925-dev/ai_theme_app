"""
重新生成完整的76条事件数据
使用真实AI模型处理所有原始新闻数据
"""
import json
import asyncio
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FullDataRegenerator:
    """完整数据重新生成器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(self.project_root))
        
        self.extractor = None
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'processing_times': [],
            'start_time': None
        }
        
        # 文件路径
        self.input_path = self.project_root / "evaluate_service" / "data" / "raw" / "validation_dataset.json"
        self.output_path = self.project_root / "evaluate_service" / "data" / "processed" / "validation_events_complete.json"
        self.log_path = self.project_root / "evaluate_service" / "data" / "results" / "logs" / f"regenerate_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    async def initialize(self):
        """初始化AI提取器"""
        logger.info("初始化AI事件提取器...")
        
        try:
            # 直接导入文件
            import importlib.util
            
            # 导入 event_extractor.py
            spec = importlib.util.spec_from_file_location(
                "event_extractor", 
                self.project_root / "model_service" / "services" / "event_extractor.py"
            )
            event_extractor_module = importlib.util.module_from_spec(spec)
            sys.modules["event_extractor"] = event_extractor_module
            spec.loader.exec_module(event_extractor_module)
            
            from model_service.services.event_extractor import AIEventExtractor
            self.extractor = AIEventExtractor()
            
            logger.info("✅ AI事件提取器初始化成功")
            
            # 健康检查
            health = await self.extractor.health_check()
            logger.info(f"🩺 健康检查: {health}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            return False
    
    async def process_news_batch(self, news_list: List[Dict], batch_size: int = 5) -> List[Dict]:
        """处理新闻批次"""
        all_events = []
        
        total_batches = (len(news_list) + batch_size - 1) // batch_size
        
        for batch_idx in range(0, len(news_list), batch_size):
            batch = news_list[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            
            logger.info(f"\n📦 批次 {batch_num}/{total_batches} ({len(batch)} 条)")
            
            batch_events = []
            batch_tasks = []
            
            for news in batch:
                # 修复news_id：使用test_id
                fixed_news = news.copy()
                test_id = news.get('test_id')
                if test_id:
                    fixed_news['news_id'] = test_id
                else:
                    # 生成一个news_id
                    idx = news_list.index(news)
                    fixed_news['news_id'] = f"news_{idx+1:03d}"
                
                batch_tasks.append(self._process_single_news(fixed_news))
            
            # 并发处理批次
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for i, result in enumerate(batch_results):
                news_idx = batch_idx + i
                if isinstance(result, Exception):
                    logger.error(f"处理失败 [{news_idx+1}]: {result}")
                    self.stats['failed'] += 1
                else:
                    if result['success']:
                        batch_events.append(result['event_data'])
                        self.stats['successful'] += 1
                        self.stats['processing_times'].append(result['processing_time'])
                        
                        # 每10条显示一次进度
                        if (self.stats['successful'] + self.stats['failed']) % 10 == 0:
                            current = self.stats['successful'] + self.stats['failed']
                            success_rate = self.stats['successful'] / max(current, 1)
                            elapsed = time.time() - self.stats['start_time']
                            eta = (elapsed / current) * (len(news_list) - current) if current > 0 else 0
                            
                            logger.info(f"📊 进度: {current}/{len(news_list)} ({current/len(news_list):.1%}) | "
                                       f"成功率: {success_rate:.1%} | "
                                       f"ETA: {eta/60:.1f}分钟")
                    else:
                        self.stats['failed'] += 1
                        logger.warning(f"提取失败 [{news_idx+1}]: {result.get('error', '未知错误')}")
            
            all_events.extend(batch_events)
            self.stats['total_processed'] += len(batch)
            
            # 每批保存中间结果（防止中途失败）
            if batch_num % 5 == 0 or batch_num == total_batches:
                await self._save_intermediate_results(all_events, batch_num)
        
        return all_events
    
    async def _process_single_news(self, news_data: Dict) -> Dict[str, Any]:
        """处理单条新闻"""
        start_time = time.time()
        news_id = news_data.get('news_id', 'unknown')
        
        try:
            event_data = await self.extractor.extract_event(news_data)
            
            if not event_data:
                return {
                    'success': False,
                    'news_id': news_id,
                    'error': '提取器返回None',
                    'processing_time': time.time() - start_time
                }
            
            return {
                'success': True,
                'news_id': news_id,
                'event_data': event_data,
                'processing_time': time.time() - start_time
            }
            
        except Exception as e:
            return {
                'success': False,
                'news_id': news_id,
                'error': str(e),
                'processing_time': time.time() - start_time
            }
    
    async def _save_intermediate_results(self, events: List[Dict], batch_num: int):
        """保存中间结果"""
        temp_path = self.output_path.parent / f"{self.output_path.stem}_batch_{batch_num}.json"
        
        save_data = {
            'metadata': {
                'batch_number': batch_num,
                'saved_at': datetime.now().isoformat(),
                'total_events': len(events),
                'stats': self.stats.copy(),
                'note': f'中间结果 - 批次 {batch_num}'
            },
            'events': events
        }
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"中间结果保存到: {temp_path}")
    
    async def regenerate_all(self):
        """重新生成所有数据"""
        logger.info("=" * 70)
        logger.info("🚀 开始重新生成完整的76条事件数据")
        logger.info("=" * 70)
        
        self.stats['start_time'] = time.time()
        
        # 初始化
        if not await self.initialize():
            return {'error': '初始化失败'}
        
        # 加载数据
        if not self.input_path.exists():
            return {'error': f'输入文件不存在: {self.input_path}'}
        
        logger.info(f"📋 加载原始数据: {self.input_path}")
        with open(self.input_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        if isinstance(raw_data, list):
            news_list = raw_data
            logger.info(f"📊 找到 {len(news_list)} 条新闻数据")
        else:
            return {'error': '数据格式不是列表'}
        
        # 处理所有数据
        logger.info("⚡ 开始处理所有76条数据...")
        logger.info(f"   批次大小: 5")
        logger.info(f"   预计总批次: {(len(news_list) + 4) // 5}")
        
        all_events = await self.process_news_batch(news_list, batch_size=5)
        
        # 保存最终结果
        logger.info("💾 保存最终结果...")
        
        total_time = time.time() - self.stats['start_time']
        avg_time = sum(self.stats['processing_times']) / max(len(self.stats['processing_times']), 1)
        
        result_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'generator': 'FullDataRegenerator_v1.0',
                'total_news': len(news_list),
                'total_processed': self.stats['total_processed'],
                'successful': self.stats['successful'],
                'failed': self.stats['failed'],
                'success_rate': self.stats['successful'] / max(self.stats['total_processed'], 1),
                'processing_stats': {
                    'total_time_seconds': total_time,
                    'total_time_minutes': total_time / 60,
                    'avg_time_per_event': avg_time,
                    'events_per_minute': self.stats['successful'] / (total_time / 60) if total_time > 0 else 0
                },
                'note': '使用真实AI模型重新生成的完整76条事件数据',
                'fix_applied': '使用test_id作为news_id'
            },
            'events': all_events
        }
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        # 清理中间文件
        await self._cleanup_intermediate_files()
        
        # 显示最终结果
        logger.info("=" * 70)
        logger.info("🎉 重新生成完成!")
        logger.info(f"   总新闻数: {len(news_list)}")
        logger.info(f"   成功提取: {self.stats['successful']} ({self.stats['successful']/max(len(news_list),1):.1%})")
        logger.info(f"   失败: {self.stats['failed']}")
        logger.info(f"   总耗时: {total_time/60:.1f} 分钟")
        logger.info(f"   平均处理时间: {avg_time:.1f} 秒/条")
        logger.info(f"   事件生成速度: {self.stats['successful']/(total_time/60):.1f} 条/分钟")
        logger.info(f"   数据已保存到: {self.output_path}")
        logger.info("=" * 70)
        
        # 显示样本数据质量
        if all_events:
            await self._analyze_data_quality(all_events)
        
        return result_data
    
    async def _cleanup_intermediate_files(self):
        """清理中间文件"""
        import glob
        pattern = str(self.output_path.parent / f"{self.output_path.stem}_batch_*.json")
        for file in glob.glob(pattern):
            try:
                os.remove(file)
                logger.debug(f"清理中间文件: {file}")
            except:
                pass
    
    async def _analyze_data_quality(self, events: List[Dict]):
        """分析数据质量"""
        logger.info("\n📊 数据质量分析:")
        
        quality_stats = {
            'has_original_data': 0,
            'has_summary': 0,
            'has_theme_directive': 0,
            'has_impact_industries': 0,
            'valid_news_id': 0,
            'avg_summary_length': 0,
            'avg_confidence': 0
        }
        
        summary_lengths = []
        confidences = []
        
        for event in events:
            # 检查字段存在性
            if 'original_data' in event:
                quality_stats['has_original_data'] += 1
            
            if event.get('summary'):
                quality_stats['has_summary'] += 1
                summary_lengths.append(len(event['summary']))
            
            if 'theme_directive' in event:
                quality_stats['has_theme_directive'] += 1
            
            if event.get('impact_industries'):
                quality_stats['has_impact_industries'] += 1
            
            if event.get('news_id'):
                quality_stats['valid_news_id'] += 1
            
            if 'confidence' in event:
                confidences.append(event['confidence'])
        
        # 计算平均值
        if summary_lengths:
            quality_stats['avg_summary_length'] = sum(summary_lengths) / len(summary_lengths)
        if confidences:
            quality_stats['avg_confidence'] = sum(confidences) / len(confidences)
        
        # 输出质量报告
        total = len(events)
        logger.info(f"   总事件数: {total}")
        logger.info(f"   有原始数据: {quality_stats['has_original_data']}/{total} ({quality_stats['has_original_data']/max(total,1):.1%})")
        logger.info(f"   有摘要: {quality_stats['has_summary']}/{total} ({quality_stats['has_summary']/max(total,1):.1%})")
        logger.info(f"   有主题指令: {quality_stats['has_theme_directive']}/{total} ({quality_stats['has_theme_directive']/max(total,1):.1%})")
        logger.info(f"   有影响行业: {quality_stats['has_impact_industries']}/{total} ({quality_stats['has_impact_industries']/max(total,1):.1%})")
        logger.info(f"   有效news_id: {quality_stats['valid_news_id']}/{total} ({quality_stats['valid_news_id']/max(total,1):.1%})")
        logger.info(f"   平均摘要长度: {quality_stats['avg_summary_length']:.0f} 字符")
        logger.info(f"   平均置信度: {quality_stats['avg_confidence']:.2f}")
        
        # 保存质量报告
        report_path = self.project_root / "evaluate_service" / "data" / "results" / "reports" / "data_quality_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        report = {
            'analysis_time': datetime.now().isoformat(),
            'total_events': total,
            'quality_stats': quality_stats,
            'sample_event': events[0] if events else None
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📄 质量报告已保存到: {report_path}")


async def main():
    """主函数"""
    print("🚀 开始重新生成完整的76条事件数据...")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    regenerator = FullDataRegenerator()
    
    try:
        result = await regenerator.regenerate_all()
        
        if 'error' in result:
            print(f"❌ 重新生成失败: {result['error']}")
            return 1
        
        # 显示简要结果
        metadata = result['metadata']
        print("\n📋 重新生成完成!")
        print(f"   总处理: {metadata['total_news']} 条新闻")
        print(f"   成功: {metadata['successful']} ({metadata['success_rate']:.1%})")
        print(f"   失败: {metadata['failed']}")
        print(f"   总耗时: {metadata['processing_stats']['total_time_minutes']:.1f} 分钟")
        print(f"   生成文件: evaluate_service/data/processed/validation_events_complete.json")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 重新生成异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
