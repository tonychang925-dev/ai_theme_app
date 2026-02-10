#!/usr/bin/env python3
# evaluate_service/runners/minimal_test.py
"""
最小测试：复现数据库读取问题
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def test_theme_fetching():
    """测试主题获取"""
    from database_service.config import DatabaseConfig
    from database_service.memory_manager import MemoryDatabaseManager
    from database_service.pure_data_fetcher import PureDataFetcher
    from theme_service.related_theme_fetcher import RelatedThemeFetcher
    
    # 1. 初始化
    db_config = DatabaseConfig()
    db_manager = MemoryDatabaseManager(db_config)
    await db_manager.connect()
    
    # 2. 创建测试主题
    await db_manager.create_theme(
        name="智能眼镜新品发布",
        description="测试主题",
        keywords=[]
    )
    
    # 3. 创建测试事件
    test_event = {
        'news_id': 'test_event_1',
        'original_news': {
            'title': 'Meta智能眼镜发布会',
            'content': 'Meta发布智能眼镜'
        },
        'event_info': {
            'impact_industries': ['消费电子', '可穿戴设备']
        }
    }
    
    # 4. 测试主题获取器
    data_fetcher = PureDataFetcher(db_manager)
    theme_fetcher = RelatedThemeFetcher(data_fetcher)
    
    themes = await theme_fetcher.fetch_relevant_themes(test_event)
    
    print(f"📊 获取到 {len(themes)} 个主题")
    if themes:
        print(f"   主题: {themes[0].get('name', '未知')}")
    else:
        print("   ⚠️  未获取到主题")
    
    return len(themes) > 0

if __name__ == "__main__":
    success = asyncio.run(test_theme_fetching())
    if success:
        print("✅ 测试成功")
    else:
        print("❌ 测试失败")
