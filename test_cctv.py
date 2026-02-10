# ai_theme_app/test_cctv.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.collectors.akshare_cctv import AkshareCctvCollector

async def test_cctv():
    print("测试央视新闻采集器...")
    collector = AkshareCctvCollector()
    
    # 健康检查
    health = await collector.health_check()
    print(f"健康检查: {'✅ 通过' if health else '❌ 失败'}")
    
    # 抓取测试
    news = await collector.fetch()
    print(f"抓取结果: {len(news)} 条新闻")
    
    if news:
        print("前3条新闻:")
        for i, item in enumerate(news[:3], 1):
            print(f"  {i}. [{item.publish_date}] {item.title[:50]}...")

if __name__ == "__main__":
    asyncio.run(test_cctv())