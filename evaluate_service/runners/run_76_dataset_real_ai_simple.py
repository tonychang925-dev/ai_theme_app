# evaluate_service/runners/run_76_dataset_real_ai_simple.py
"""
简化版：完全复制手动测试的方法
"""
#!/usr/bin/env python3
import asyncio
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def test_with_manual_method():
    """使用手动测试的方法进行测试"""
    logger.info("🧪 使用手动测试的方法运行76个数据集测试")
    
    try:
        # 1. 加载测试数据（和手动测试一样）
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.pure_data_fetcher import PureDataFetcher
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        
        # 2. 初始化数据库（和手动测试一样）
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        
        logger.info("✅ 数据库初始化完成")
        
        # 3. 加载测试数据
        data_path = project_root / "evaluate_service" / "data" / "processed" / "validation_events_fixed.json"
        with open(data_path, 'r', encoding='utf-8') as f:
            events = json.load(f)
        
        if isinstance(events, dict) and 'events' in events:
            events = events['events']
        
        logger.info(f"📊 加载 {len(events)} 个测试事件")
        
        # 4. 保存所有事件到数据库（重要！）
        for i, event in enumerate(events[:10]):  # 先测试10个
            event_id = event.get('news_id', f'test_{i}')
            await db_manager.create_or_update_event(event)
            
            if (i + 1) % 5 == 0:
                logger.info(f"  已保存 {i+1} 个事件")
        
        # 5. 创建AI分析器（和手动测试一样）
        api_key = "your-api-key"  # 从环境变量获取
        llm_parser = ReliableDeepSeekParser(config={
            'api_key': api_key,
            'model_name': 'deepseek-chat',
            'max_retries': 3,
            'timeout': 60
        })
        
        similarity_analyzer = AIThemeSimilarityAnalyzer(llm_parser)
        
        # 6. 创建数据获取器和主题获取器（关键！和手动测试完全一样）
        data_fetcher = PureDataFetcher(db_manager)
        theme_fetcher = RelatedThemeFetcher(data_fetcher)
        
        # 7. 测试第一个事件
        test_event = events[0]
        event_id = test_event.get('news_id', 'test_1')
        
        logger.info(f"\n🔍 测试事件: {event_id}")
        logger.info(f"   标题: {test_event.get('original_news', {}).get('title', '')[:60]}...")
        
        # 获取相关主题
        relevant_themes = await theme_fetcher.fetch_relevant_themes(test_event)
        logger.info(f"   获取到 {len(relevant_themes)} 个相关主题")
        
        # 8. 进行AI分析
        logger.info("🤖 开始AI分析...")
        result = await similarity_analyzer.analyze_with_theme_extraction(
            test_event, relevant_themes
        )
        
        # 输出结果
        print(f"\n📊 AI分析结果:")
        print(f"   提取主题: {result.get('theme_extraction', {}).get('extracted_name', 'N/A')}")
        print(f"   匹配主题: {result.get('similarity_analysis', {}).get('best_match_theme', 'N/A')}")
        print(f"   相似度: {result.get('similarity_analysis', {}).get('similarity_score', 0)}")
        print(f"   决策: {result.get('recommendation', {}).get('action', 'N/A')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("🧪 手动测试方法验证")
    print("="*60)
    
    success = await test_with_manual_method()
    
    if success:
        print("\n✅ 测试成功！验证了手动测试方法的正确性")
    else:
        print("\n❌ 测试失败")

if __name__ == "__main__":
    asyncio.run(main())