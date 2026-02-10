# ai_theme_app/test_multiple_rss.py
import asyncio
import feedparser
import aiohttp
from datetime import datetime

# 可靠的财经RSS源列表
RSS_SOURCES = [
    # 新浪（备用）
    ("sina_global", "https://rss.sina.com.cn/finance/globalnews.xml"),
    ("sina_tech", "https://rss.sina.com.cn/tech/keji.xml"),
    
    # 网易财经
    ("163_finance", "http://money.163.com/special/00251G8F/rss.xml"),
    
    # 腾讯财经
    ("qq_finance", "https://finance.qq.com/rss_finance.xml"),
    
    # 搜狐财经
    ("sohu_finance", "http://business.sohu.com/rss/business.xml"),
    
    # 东方财富（尝试）
    ("eastmoney", "http://finance.eastmoney.com/rss/rsscontent.xml"),
    
    # 和讯网
    ("hexun", "http://news.hexun.com/rss/finance.xml"),
    
    # 华尔街见闻（国际）
    ("wallstreetcn", "https://wallstreetcn.com/rss"),
]

async def test_rss_source(name, url):
    """测试单个RSS源"""
    try:
        print(f"\n测试 {name}: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, 
                                 headers={'User-Agent': 'Mozilla/5.0'}) as response:
                if response.status != 200:
                    print(f"  ❌ HTTP {response.status}")
                    return False
                
                content = await response.text(errors='ignore')
                feed = feedparser.parse(content)
                
                if not feed.entries:
                    print(f"  ⚠️  无内容")
                    return False
                
                print(f"  ✅ 成功: {len(feed.entries)} 条新闻")
                print(f"     示例: {feed.entries[0].title[:60]}...")
                return True
                
    except Exception as e:
        print(f"  ❌ 错误: {str(e)[:80]}")
        return False

async def main():
    print("测试财经RSS源可用性...")
    print("=" * 60)
    
    results = []
    for name, url in RSS_SOURCES:
        success = await test_rss_source(name, url)
        results.append((name, url, success))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总:")
    
    working_sources = []
    for name, url, success in results:
        status = "✅ 可用" if success else "❌ 不可用"
        print(f"  {name:15} {status}")
        if success:
            working_sources.append((name, url))
    
    print(f"\n🎯 可用的RSS源: {len(working_sources)}/{len(RSS_SOURCES)}")
    if working_sources:
        print("推荐使用的源:")
        for name, url in working_sources:
            print(f"  - {name}: {url}")

if __name__ == "__main__":
    asyncio.run(main())