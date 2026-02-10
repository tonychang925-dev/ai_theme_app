# ai_theme_app/news_crawler_service/collectors/sina_rss.py
import feedparser
from datetime import datetime
from typing import List
import asyncio
import aiohttp
import chardet  # 需要安装

from .base import BaseCollector
from ..models.news_raw import NewsRawItem

class SinaRssCollector(BaseCollector):
    """新浪财经RSS采集器（修复版）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 尝试更多可靠的RSS源
        self.rss_urls = [
            "https://rss.sina.com.cn/finance/globalnews.xml",  # 国际财经
            "https://rss.sina.com.cn/tech/keji.xml",           # 科技新闻
            "http://finance.sina.com.cn/rss/stock.xml",        # 股票
            "http://finance.sina.com.cn/rss/finance.xml",      # 财经
        ]
        
    @property
    def source_name(self) -> str:
        return "sina_rss"
    
    async def fetch(self) -> List[NewsRawItem]:
        """从RSS抓取新闻"""
        news_items = []
        
        for rss_url in self.rss_urls:
            try:
                print(f"[{self.source_name}] 尝试抓取 {rss_url}")
                
                # 异步获取RSS内容，指定编码
                async with aiohttp.ClientSession() as session:
                    async with session.get(rss_url, timeout=10, 
                                         headers={'User-Agent': 'Mozilla/5.0'}) as response:
                        # 获取原始字节
                        raw_bytes = await response.read()
                        
                        # 自动检测编码
                        detected = chardet.detect(raw_bytes)
                        encoding = detected['encoding'] or 'utf-8'
                        
                        # 解码内容
                        rss_content = raw_bytes.decode(encoding, errors='ignore')
                
                # 解析RSS
                feed = feedparser.parse(rss_content)
                
                if feed.entries:
                    for entry in feed.entries[:10]:  # 每个源取前10条
                        # 跳过无效条目
                        if not entry.get('title'):
                            continue
                            
                        # 解析发布时间
                        publish_date = datetime.now().date()
                        time_keys = ['published_parsed', 'updated_parsed', 'created_parsed']
                        
                        for key in time_keys:
                            if hasattr(entry, key) and getattr(entry, key):
                                pub_time = getattr(entry, key)
                                try:
                                    publish_date = datetime(*pub_time[:6]).date()
                                    break
                                except:
                                    continue
                        
                        # 获取内容
                        content = entry.get('summary', '')
                        if not content or len(content) < 20:
                            content = entry.title
                        
                        # 创建新闻对象
                        news_item = NewsRawItem(
                            title=entry.title[:200].strip(),
                            content=content[:1000].strip(),
                            source=self.source_name,
                            publish_date=publish_date,
                            market="全球" if "global" in rss_url else "A股",
                            url=entry.link if hasattr(entry, 'link') else '',
                        )
                        news_items.append(news_item)
                    
                    print(f"[{self.source_name}] 从 {rss_url} 抓取 {len(feed.entries)} 条，有效 {min(10, len(feed.entries))} 条")
                    
            except Exception as e:
                print(f"[{self.source_name}] {rss_url} 抓取失败: {str(e)[:100]}")
                continue
        
        print(f"[{self.source_name}] 总计抓取 {len(news_items)} 条有效新闻")
        return news_items
    
    async def health_check(self) -> bool:
        """检查RSS源是否可用"""
        try:
            test_url = "https://rss.sina.com.cn/finance/globalnews.xml"
            async with aiohttp.ClientSession() as session:
                async with session.get(test_url, timeout=5, 
                                     headers={'User-Agent': 'Mozilla/5.0'}) as response:
                    return response.status == 200
        except:
            return False