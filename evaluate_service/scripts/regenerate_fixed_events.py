# evaluate_service/scripts/regenerate_fixed_events.py
"""
重新生成修复数据结构后的事件数据
使用新的event_extractor处理76条原始数据
"""
import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from model_service.services.event_extractor import AIEventExtractor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'evaluate_service/data/results/logs/fixed_regeneration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

async def process_single_news(news_data: Dict[str, Any], extractor: AIEventExtractor) -> Dict[str, Any]:
    """处理单条新闻"""
    try:
        # 确保有news_id
        if 'news_id' not in news_data and 'test_id' in news_data:
            news_data['news_id'] = news_data['test_id']
        
        # 使用新的event_extractor处理
        event_result = await extractor.extract_event(news_data)
        
        if event_result:
            logger.info(f"✅ 成功处理: {news_data.get('news_id')}")
            return event_result
        else:
            logger.warning(f"❌ 处理失败: {news_data.get('news_id')}")
            return None
            
    except Exception as e:
        logger.error(f"❌ 处理异常 {news_data.get('news_id')}: {e}")
        return None

async def regenerate_fixed_events():
    """重新生成修复后的完整事件数据"""
    start_time = datetime.now()
    
    # 路径配置
    raw_data_path = project_root / "evaluate_service" / "data" / "raw" / "validation_dataset.json"
    output_path = project_root / "evaluate_service" / "data" / "processed" / "validation_events_fixed.json"
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📂 加载原始数据: {raw_data_path}")
    
    # 加载原始数据
    try:
        with open(raw_data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        logger.error(f"❌ 加载原始数据失败: {e}")
        return False
    
    if not isinstance(raw_data, list):
        logger.error("❌ 原始数据不是列表格式")
        return False
    
    total_news = len(raw_data)
    logger.info(f"📊 原始数据数量: {total_news} 条")
    
    # 创建事件提取器
    try:
        extractor = AIEventExtractor()
        logger.info("✅ 事件提取器初始化成功")
    except Exception as e:
        logger.error(f"❌ 事件提取器初始化失败: {e}")
        return False
    
    # 处理所有新闻
    processed_events = []
    successful = 0
    failed = 0
    
    logger.info("⚡ 开始处理新闻...")
    
    for i, news_data in enumerate(raw_data, 1):
        logger.info(f"📝 处理第 {i}/{total_news} 条: {news_data.get('test_id', 'N/A')}")
        
        try:
            event_result = await process_single_news(news_data, extractor)
            
            if event_result:
                processed_events.append(event_result)
                successful += 1
            else:
                failed += 1
                
        except Exception as e:
            logger.error(f"❌ 处理过程中发生异常: {e}")
            failed += 1
        
        # 每10条显示一次进度
        if i % 10 == 0:
            logger.info(f"📈 进度: {i}/{total_news} (成功: {successful}, 失败: {failed})")
    
    # 计算处理时间
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    # 构建完整结果
    final_result = {
        "metadata": {
            "generated_at": end_time.isoformat(),
            "generator": "FixedDataRegenerator_v1.0",
            "description": "使用修复数据结构后的event_extractor重新生成的事件数据",
            "total_news": total_news,
            "total_processed": len(processed_events),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total_news if total_news > 0 else 0,
            "processing_stats": {
                "total_time_seconds": total_time,
                "total_time_minutes": total_time / 60,
                "avg_time_per_event": total_time / len(processed_events) if processed_events else 0,
                "events_per_minute": len(processed_events) / (total_time / 60) if total_time > 0 else 0
            },
            "note": "修复了数据结构冗余问题，移除了summary、data_integrity等冗余字段",
            "data_structure": {
                "event_info": "事件基础信息",
                "theme_discovery_directive": "主题发现决策",
                "original_news": "完整原始数据"
            }
        },
        "events": processed_events
    }
    
    # 保存结果
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 结果保存到: {output_path}")
        logger.info(f"📊 处理统计:")
        logger.info(f"   - 总数: {total_news}")
        logger.info(f"   - 成功: {successful}")
        logger.info(f"   - 失败: {failed}")
        logger.info(f"   - 成功率: {final_result['metadata']['success_rate']:.1%}")
        logger.info(f"   - 总耗时: {total_time/60:.1f} 分钟")
        logger.info(f"   - 平均时间: {final_result['metadata']['processing_stats']['avg_time_per_event']:.1f} 秒/条")
        
        # 显示第一条事件的检查
        if processed_events:
            first_event = processed_events[0]
            logger.info(f"\n📋 第一条事件数据结构检查:")
            logger.info(f"   - news_id: {first_event.get('news_id')}")
            logger.info(f"   - event_type: {first_event.get('event_info', {}).get('event_type')}")
            logger.info(f"   - decision_action: {first_event.get('theme_discovery_directive', {}).get('action')}")
            logger.info(f"   - original_content_length: {len(first_event.get('original_news', {}).get('content', ''))}")
            
            # 检查是否有冗余字段
            redundant_fields = ['summary', 'raw_ai_response', 'ai_response', 'data_integrity', 'extraction_metadata']
            has_redundant = any(field in first_event for field in redundant_fields)
            logger.info(f"   - 是否有冗余字段: {'❌ YES' if has_redundant else '✅ NO'}")
            
            if has_redundant:
                actual_fields = list(first_event.keys())
                logger.info(f"   - 实际字段: {actual_fields}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 保存结果失败: {e}")
        return False
    finally:
        await extractor.close()

def main():
    """主函数"""
    print("🚀 开始重新生成修复数据结构后的事件数据")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    try:
        # 检查API密钥
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ DEEPSEEK_API_KEY 环境变量未设置")
            return 1
        
        if api_key.startswith("sk-test"):
            print("❌ 请使用真实的DeepSeek API密钥")
            return 1
        
        print(f"🔑 API密钥: {api_key[:10]}...")
        print("")
        
        # 检查原始数据文件
        raw_data_path = project_root / "evaluate_service" / "data" / "raw" / "validation_dataset.json"
        if not raw_data_path.exists():
            print(f"❌ 原始数据文件不存在: {raw_data_path}")
            return 1
        
        print(f"📂 原始数据文件: {raw_data_path}")
        
        # 检查文件大小
        file_size = raw_data_path.stat().st_size
        print(f"📊 文件大小: {file_size/1024:.1f} KB")
        
        # 加载并检查数据
        with open(raw_data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        if not isinstance(raw_data, list):
            print("❌ 数据格式不是列表")
            return 1
        
        total_news = len(raw_data)
        print(f"📊 数据条数: {total_news}")
        print("")
        
        # 显示前3条
        print("🔍 前3条数据预览:")
        for i in range(min(3, len(raw_data))):
            news = raw_data[i]
            print(f"  {i+1}. {news.get('test_id', 'N/A')}: {news.get('title', '无标题')[:40]}...")
        print("")
        
        # 确认继续
        confirm = input("⚠️  重新生成可能需要15-30分钟，是否继续？(y/N): ")
        if confirm.lower() != 'y':
            print("操作取消")
            return 0
        
        print("")
        print("⚡ 开始处理...")
        print("")
        
        # 运行异步任务
        success = asyncio.run(regenerate_fixed_events())
        
        if success:
            print("✅ 重新生成完成！")
            
            # 显示生成的文件信息
            output_path = project_root / "evaluate_service" / "data" / "processed" / "validation_events_fixed.json"
            if output_path.exists():
                print(f"📄 生成文件: {output_path}")
                
                # 检查是否覆盖旧的enhanced文件
                old_path = project_root / "evaluate_service" / "data" / "processed" / "validation_events_enhanced.json"
                if old_path.exists():
                    print("")
                    print("⚠️  注意：已存在 validation_events_enhanced.json")
                    print("")
                    print("建议操作：")
                    print(f"1. 备份旧文件: cp {old_path} {old_path}.backup")
                    print(f"2. 使用新文件: cp {output_path} {old_path}")
            
            return 0
        else:
            print("❌ 重新生成失败")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⏹️  操作被用户中断")
        return 130
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())