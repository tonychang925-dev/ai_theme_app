# scripts/test_news_workflow.py
"""
快速测试新闻工作流
"""
import asyncio
import sys
import os

def setup_paths():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    database_dir = os.path.dirname(current_dir)
    project_root = os.path.dirname(database_dir)
    
    sys.path.insert(0, project_root)
    sys.path.insert(0, database_dir)

async def test_news_basic():
    """测试新闻基础功能"""
    print("🧪 测试新闻基础功能")
    print("="*50)
    
    try:
        from config import get_config
        from managers.postgres_manager import PostgresDatabaseManager
        from managers.redis_cached_manager import RedisCachedDatabaseManager
        
        # 配置
        config = get_config()
        config.postgres_database = "stock_data_test"
        
        # 连接数据库
        postgres = PostgresDatabaseManager(config)
        await postgres.connect()
        
        cached = RedisCachedDatabaseManager(postgres, config)
        await cached.connect()
        
        # 测试创建新闻
        news_data = {
            "news_id": "quick_test_001",
            "title": "快速测试新闻",
            "content": "测试新闻基础功能",
            "source": "quick_test",
            "publish_date": "2024-01-21",
            "market": "A股",
            "keywords": ["测试", "快速"]
        }
        
        print("1. 创建新闻...")
        news_id = await cached.create_news(news_data)
        print(f"  结果: {'✅ 成功' if news_id else '❌ 失败'}")
        
        if news_id:
            print("\n2. 查询新闻...")
            news = await cached.get_news(news_id)
            print(f"  结果: {'✅ 成功' if news else '❌ 失败'}")
            
            if news:
                print(f"    标题: {news.get('title')}")
                print(f"    来源: {news.get('source')}")
        
        print("\n3. 查询最近新闻...")
        recent = await cached.get_recent_news(3)
        print(f"  结果: 找到 {len(recent)} 条新闻")
        
        # 清理
        await postgres.delete_test_news()
        await postgres.disconnect()
        await cached.disconnect()
        
        print("\n✅ 测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

async def main():
    setup_paths()
    success = await test_news_basic()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)