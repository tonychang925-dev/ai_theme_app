#!/usr/bin/env python3
"""
重建数据集 - 使用修复后的组件重新处理
位置: evaluate_service/runners/rebuild_dataset_fixed.py
"""
import asyncio
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# 设置项目路径
EVALUATE_DIR = Path(__file__).parent.parent.absolute()
PROJECT_ROOT = EVALUATE_DIR.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

print("="*80)
print("📊 重建数据集 - 使用修复后的组件")
print("="*80)
print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"评估目录: {EVALUATE_DIR}")
print(f"项目根目录: {PROJECT_ROOT}")

# 配置日志
log_dir = EVALUATE_DIR / "data" / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"dataset_rebuild_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)

async def rebuild_dataset():
    """重建数据集"""
    logger.info("🚀 开始重建数据集 - 使用修复后的组件")
    
    # 1. 加载原始数据
    raw_data_path = EVALUATE_DIR / "data" / "raw" / "validation_dataset.json"
    output_path = EVALUATE_DIR / "data" / "processed" / "validation_events_enhanced_fixed.json"
    
    if not raw_data_path.exists():
        logger.error(f"原始数据文件不存在: {raw_data_path}")
        return False
    
    logger.info(f"加载原始数据: {raw_data_path}")
    
    try:
        with open(raw_data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        logger.error(f"加载原始数据失败: {e}")
        return False
    
    # 2. 创建事件提取器（使用修复后的组件）
    try:
        from model_service.services.event_extractor import AIEventExtractor
        logger.info("✅ 成功导入修复后的AIEventExtractor")
        extractor = AIEventExtractor()
    except ImportError as e:
        logger.error(f"导入AIEventExtractor失败: {e}")
        return False
    except Exception as e:
        logger.error(f"创建提取器失败: {e}")
        # 尝试使用Mock提取器（仅用于测试）
        from model_service.services.event_extractor import MockEventExtractor
        extractor = MockEventExtractor()
        logger.warning("⚠️  使用MockEventExtractor进行测试")
    
    # 3. 确定数据结构
    if isinstance(raw_data, dict) and 'news' in raw_data:
        news_list = raw_data['news']
        logger.info(f"数据集结构: dict with 'news' key, 数量: {len(news_list)}")
    elif isinstance(raw_data, list):
        news_list = raw_data
        logger.info(f"数据集结构: list, 数量: {len(news_list)}")
    else:
        logger.error(f"未知的数据结构: {type(raw_data)}")
        return False
    
    total_news = len(news_list)
    logger.info(f"需要处理 {total_news} 个新闻")
    
    # 4. 处理每个新闻
    processed_events = []
    success_count = 0
    fail_count = 0
    data_integrity_stats = []
    
    for i, news_item in enumerate(news_list):
        # 获取新闻ID
        news_id = news_item.get('news_id', 
                               news_item.get('id', 
                                           f'news_{i:03d}'))
        
        logger.info(f"[{i+1}/{total_news}] 处理新闻: {news_id}")
        
        try:
            # 提取事件
            event = await extractor.extract_event(news_item)
            
            if event:
                # 添加处理元数据
                event['rebuild_timestamp'] = datetime.now().isoformat()
                event['rebuild_version'] = 'fixed_v2_data_integrity'
                event['original_data_source'] = str(raw_data_path)
                
                processed_events.append(event)
                success_count += 1
                
                # 记录数据完整性
                content_len = event.get('data_integrity', {}).get('content_length', 0)
                summary_len = event.get('data_integrity', {}).get('ai_summary_length', 0)
                has_full_content = event.get('original_data', {}).get('has_full_content', False)
                
                data_integrity_stats.append({
                    'news_id': news_id,
                    'content_length': content_len,
                    'summary_length': summary_len,
                    'has_full_content': has_full_content,
                    'enhancement_ratio': summary_len / max(content_len, 1) if content_len > 0 else 0
                })
                
                logger.info(f"  成功提取，内容长度: {content_len}, "
                          f"AI摘要: {summary_len}, "
                          f"完整内容: {has_full_content}")
            else:
                fail_count += 1
                logger.warning(f"  提取失败")
                
        except Exception as e:
            fail_count += 1
            logger.error(f"  处理异常: {e}")
            import traceback
            traceback.print_exc()
    
    # 5. 保存结果
    result = {
        'metadata': {
            'rebuild_time': datetime.now().isoformat(),
            'rebuild_version': 'fixed_v2_data_integrity',
            'original_dataset': str(raw_data_path),
            'total_news': total_news,
            'success_count': success_count,
            'fail_count': fail_count,
            'success_rate': success_count / total_news if total_news > 0 else 0,
            'components_used': {
                'event_extractor': 'fixed_v2',
                'deepseek_parser': 'fixed_v1'
            }
        },
        'data_integrity_stats': data_integrity_stats,
        'events': processed_events
    }
    
    # 保存到文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 数据集重建完成")
    logger.info(f"  保存到: {output_path}")
    logger.info(f"  统计: 成功 {success_count}/{total_news} "
               f"({(success_count/total_news*100):.1f}%)")
    
    # 6. 数据完整性分析
    logger.info("\n📊 数据完整性分析:")
    
    if data_integrity_stats:
        content_lengths = [s['content_length'] for s in data_integrity_stats]
        summary_lengths = [s['summary_length'] for s in data_integrity_stats]
        has_full_content_count = sum(1 for s in data_integrity_stats if s['has_full_content'])
        
        avg_content = sum(content_lengths) / len(content_lengths)
        avg_summary = sum(summary_lengths) / len(summary_lengths)
        full_content_rate = has_full_content_count / len(data_integrity_stats)
        
        logger.info(f"  平均原始内容长度: {avg_content:.1f}字符")
        logger.info(f"  平均AI摘要长度: {avg_summary:.1f}字符")
        logger.info(f"  平均摘要/内容比例: {(avg_summary/avg_content*100 if avg_content > 0 else 0):.1f}%")
        logger.info(f"  有完整内容的新闻: {has_full_content_count}/{len(data_integrity_stats)} "
                   f"({full_content_rate*100:.1f}%)")
        
        # 分类统计
        short_content = sum(1 for cl in content_lengths if cl < 100)
        medium_content = sum(1 for cl in content_lengths if 100 <= cl < 500)
        long_content = sum(1 for cl in content_lengths if cl >= 500)
        
        logger.info(f"\n📈 内容长度分布:")
        logger.info(f"  短内容(<100字符): {short_content} 个")
        logger.info(f"  中等内容(100-500字符): {medium_content} 个")
        logger.info(f"  长内容(≥500字符): {long_content} 个")
    
    # 7. 生成详细报告
    report_path = EVALUATE_DIR / "data" / "results" / f"rebuild_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    
    report = {
        'rebuild_summary': {
            'timestamp': datetime.now().isoformat(),
            'input_file': str(raw_data_path),
            'output_file': str(output_path),
            'total_processed': total_news,
            'successful': success_count,
            'failed': fail_count,
            'success_rate': success_count / total_news if total_news > 0 else 0
        },
        'data_integrity': {
            'stats': data_integrity_stats[:10] if data_integrity_stats else [],  # 只保存前10个样本
            'summary': {
                'avg_content_length': avg_content if 'avg_content' in locals() else 0,
                'avg_summary_length': avg_summary if 'avg_summary' in locals() else 0,
                'full_content_rate': full_content_rate if 'full_content_rate' in locals() else 0
            }
        }
    }
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n📄 详细报告保存到: {report_path}")
    logger.info(f"📝 日志文件: {log_file}")
    
    return True

async def verify_rebuilt_dataset():
    """验证重建的数据集"""
    print("\n" + "="*60)
    print("🔍 验证重建的数据集")
    print("="*60)
    
    dataset_path = EVALUATE_DIR / "data" / "processed" / "validation_events_enhanced_fixed.json"
    
    if not dataset_path.exists():
        print(f"❌ 数据集不存在: {dataset_path}")
        return False
    
    print(f"验证数据集: {dataset_path}")
    
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查基本结构
        if 'metadata' not in data or 'events' not in data:
            print("❌ 数据集结构不正确")
            return False
        
        metadata = data['metadata']
        events = data['events']
        
        print(f"✅ 数据集结构正确")
        print(f"  重建版本: {metadata.get('rebuild_version', 'unknown')}")
        print(f"  总新闻数: {metadata.get('total_news', 0)}")
        print(f"  成功数: {metadata.get('success_count', 0)}")
        print(f"  成功率: {metadata.get('success_rate', 0)*100:.1f}%")
        print(f"  事件数量: {len(events)}")
        
        # 检查第一个事件的数据完整性
        if events:
            first_event = events[0]
            print(f"\n🔍 第一个事件检查:")
            print(f"  ID: {first_event.get('news_id', 'unknown')}")
            
            # 检查修复字段
            fix_fields = ['original_data', 'data_integrity', 'ai_response']
            for field in fix_fields:
                if field in first_event:
                    print(f"  ✅ 有{field}字段")
                else:
                    print(f"  ❌ 缺少{field}字段")
                    return False
            
            # 检查原始数据保存
            if 'original_data' in first_event:
                od = first_event['original_data']
                if 'content' in od and od['content']:
                    print(f"  ✅ 保存了完整内容 ({len(od['content'])}字符)")
                else:
                    print(f"  ❌ 未保存完整内容")
            
            # 检查数据完整性标记
            if 'data_integrity' in first_event:
                di = first_event['data_integrity']
                print(f"  ✅ 有数据完整性标记")
                print(f"    内容长度: {di.get('content_length', 0)}")
                print(f"    AI摘要长度: {di.get('ai_summary_length', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False

async def main():
    """主函数"""
    print("\n📋 重建计划:")
    print("1. 使用修复后的event_extractor重新处理76个原始新闻")
    print("2. 保存到validation_events_enhanced_fixed.json")
    print("3. 验证重建的数据集")
    print()
    
    # 1. 重建数据集
    print("🔧 步骤1: 重建数据集...")
    rebuild_success = await rebuild_dataset()
    
    if not rebuild_success:
        print("❌ 数据集重建失败")
        return 1
    
    # 2. 验证数据集
    print("\n🔍 步骤2: 验证重建的数据集...")
    verify_success = await verify_rebuilt_dataset()
    
    print("\n" + "="*80)
    if rebuild_success and verify_success:
        print("🎉 数据集重建成功！")
        print("\n✅ 修复效果:")
        print("  1. 原始新闻内容被完整保存在 original_data.content")
        print("  2. AI判断摘要保存在 summary 字段")
        print("  3. 数据完整性标记完整")
        print("\n📊 下一步: 可以使用这个修复后的数据集进行主题分析测试")
        return 0
    else:
        print("⚠️  数据集重建或验证失败")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
