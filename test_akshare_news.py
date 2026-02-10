# ai_theme_app/test_akshare_news.py
import akshare as ak
import pandas as pd
from datetime import datetime

def test_akshare_news_sources():
    """测试akshare的各种新闻接口"""
    print("测试akshare新闻源...")
    print("=" * 60)
    
    sources = [
        ("news_cctv", "央视新闻", lambda: ak.news_cctv()),
        ("news_163", "网易新闻", lambda: ak.news_163()),
        ("news_sina", "新浪新闻", lambda: ak.news_sina()),
        ("news_sohu", "搜狐新闻", lambda: ak.news_sohu()),
        ("news_qq", "腾讯新闻", lambda: ak.news_qq()),
        ("news_baidu", "百度新闻", lambda: ak.news_baidu()),
        ("news_5562", "东方财富新闻", lambda: ak.news_5562()),
        ("news_stock", "股票新闻", lambda: ak.news_stock()),
    ]
    
    working_sources = []
    
    for func_name, source_name, fetch_func in sources:
        try:
            print(f"\n测试 {source_name} ({func_name})...")
            df = fetch_func()
            
            if df is not None and not df.empty:
                print(f"  ✅ 成功: {len(df)} 条新闻")
                print(f"     列名: {list(df.columns)}")
                print(f"     示例标题: {df.iloc[0]['title' if 'title' in df.columns else df.columns[0]][:60]}...")
                working_sources.append((func_name, source_name, fetch_func))
            else:
                print(f"  ⚠️  无数据或空DataFrame")
                
        except Exception as e:
            print(f"  ❌ 失败: {str(e)[:80]}")
    
    print("\n" + "=" * 60)
    print(f"📊 结果: {len(working_sources)}/{len(sources)} 个源可用")
    
    if working_sources:
        print("\n🎯 可用的akshare新闻源:")
        for func_name, source_name, _ in working_sources:
            print(f"  - {source_name} (函数: {func_name})")
    
    return working_sources

if __name__ == "__main__":
    test_akshare_news_sources()