# ai_theme_app/test_dual_source.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.collectors.source_factory import CollectorFactory
from news_crawler_service.database import DatabaseManager, init_database

async def test_dual_source():
    """测试双数据源运行"""
    print("=" * 60)
    print("测试双数据源系统")
    print("=" * 60)
    
    # 初始化
    await init_database()
    
    # 创建采集器
    print("\n1. 创建数据源采集器...")
    collectors = await CollectorFactory.create_collectors()
    print(f"   已创建 {len(collectors)} 个采集器")
    
    # 分别测试每个采集器
    total_news = 0
    
    for collector in collectors:
        print(f"\n2. 测试采集器: {collector.source_name}")
        print("   " + "-" * 40)
        
        # 健康检查
        health = await collector.health_check()
        print(f"   健康检查: {'✅ 通过' if health else '❌ 失败'}")
        
        if health:
            # 抓取数据
            news_items = await collector.fetch()
            print(f"   抓取结果: {len(news_items)} 条新闻")
            
            if news_items:
                # 保存数据
                saved = await DatabaseManager.save_news_batch(news_items)
                print(f"   保存结果: {saved} 条保存成功")
                total_news += saved
                
                # 显示样本
                print(f"   样本标题: {news_items[0].title[:60]}...")
    
    # 显示总体结果
    print("\n" + "=" * 60)
    print("📊 总体测试结果:")
    print(f"   采集器数量: {len(collectors)}")
    print(f"   总计保存新闻: {total_news} 条")
    
    # 显示数据库中的新闻分布
    async with (await DatabaseManager.get_pool()).acquire() as conn:
        dist = await conn.fetch("""
            SELECT source, COUNT(*) as count 
            FROM news_raw 
            GROUP BY source 
            ORDER BY count DESC
        """)
        
        print(f"\n📈 数据库新闻分布:")
        for row in dist:
            print(f"   {row['source']}: {row['count']} 条")
    
    print("\n✅ 双源系统测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_dual_source())