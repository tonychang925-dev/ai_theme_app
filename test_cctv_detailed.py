# ai_theme_app/test_cctv_detailed.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.collectors.akshare_cctv import AkshareCctvCollector
from news_crawler_service.database import DatabaseManager, init_database

async def test_cctv_detailed():
    """详细测试央视新闻采集器"""
    print("=" * 60)
    print("详细测试央视新闻采集器")
    print("=" * 60)
    
    # 1. 初始化数据库
    print("\n1. 初始化数据库...")
    await init_database()
    
    # 2. 创建采集器
    print("\n2. 创建央视新闻采集器...")
    collector = AkshareCctvCollector(request_interval=1)  # 测试用短间隔
    
    # 3. 健康检查
    print("\n3. 健康检查...")
    health = await collector.health_check()
    print(f"   结果: {'✅ 通过' if health else '❌ 失败'}")
    
    if not health:
        print("   健康检查失败，结束测试")
        return
    
    # 4. 抓取测试
    print("\n4. 执行抓取...")
    news_items = await collector.fetch()
    
    if not news_items:
        print("   ❌ 抓取失败，无数据")
        return
    
    print(f"   ✅ 成功抓取 {len(news_items)} 条新闻")
    
    # 5. 显示样本数据
    print("\n5. 样本数据:")
    for i, item in enumerate(news_items[:3], 1):
        print(f"   [{i}] {item.title[:60]}...")
        print(f"       日期: {item.publish_date}")
        print(f"       来源: {item.source}")
        print(f"       ID: {item.news_id[:20]}...")
    
    # 6. 保存到数据库测试
    print("\n6. 保存到数据库测试...")
    saved_count = await DatabaseManager.save_news_batch(news_items)
    print(f"   尝试保存 {len(news_items)} 条，实际保存 {saved_count} 条")
    
    if saved_count > 0:
        # 7. 验证数据
        print("\n7. 验证数据库中的新闻...")
        recent = await DatabaseManager.get_recent_news(3)
        print("   最新保存的新闻:")
        for i, news in enumerate(recent, 1):
            if news['source'] == 'akshare_cctv':
                print(f"   [{i}] [{news['source']}] {news['title'][:50]}...")
    
    # 8. 测试防重复机制
    print("\n8. 测试防重复机制...")
    print("   再次抓取相同数据...")
    news_items2 = await collector.fetch()
    saved_count2 = await DatabaseManager.save_news_batch(news_items2)
    
    if saved_count2 == 0:
        print(f"   ✅ 防重复有效: 第二次保存0条（预期）")
    else:
        print(f"   ⚠️  防重复可能有问题: 第二次保存{saved_count2}条")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_cctv_detailed())