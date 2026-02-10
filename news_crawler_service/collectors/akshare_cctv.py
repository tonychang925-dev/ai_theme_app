# ai_theme_app/news_crawler_service/collectors/akshare_cctv.py
import akshare as ak
from datetime import datetime, date, time
from typing import List
import asyncio
import pandas as pd
import time as time_module

from .base import BaseCollector
from ..models.news_raw import NewsRawItem

class AkshareCctvCollector(BaseCollector):
    """央视新闻采集器（修复版）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 央视新闻更新频率较低，可以设置更长的请求间隔
        self.request_interval = max(kwargs.get('request_interval', 300), 300)  # 至少5分钟
        self.last_request_time = 0
        
    @property
    def source_name(self) -> str:
        return "akshare_cctv"
    
    async def fetch(self) -> List[NewsRawItem]:
        """抓取央视新闻"""
        news_items = []
        
        try:
            # 遵守请求间隔
            await self._respect_request_interval()
            
            # 在线程池中执行
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, ak.news_cctv)
            
            if df is not None and not df.empty:
                print(f"[{self.source_name}] 原始数据形状: {df.shape}")
                print(f"[{self.source_name}] 列名: {list(df.columns)}")
                
                news_items = await self._convert_to_news_items(df)
                print(f"[{self.source_name}] 成功转换 {len(news_items)} 条新闻")
            else:
                print(f"[{self.source_name}] 未抓取到数据")
                
        except Exception as e:
            print(f"[{self.source_name}] 抓取失败: {e}")
            import traceback
            traceback.print_exc()
            
        return news_items
    
    async def _respect_request_interval(self):
        """遵守请求间隔，防反爬"""
        current_time = time_module.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.request_interval:
            sleep_time = self.request_interval - elapsed
            print(f"[{self.source_name}] 等待 {sleep_time:.1f} 秒...")
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time_module.time()
    
    async def _convert_to_news_items(self, df: pd.DataFrame) -> List[NewsRawItem]:
        """转换央视新闻数据格式"""
        news_items = []
        
        # 显示前几行数据用于调试
        print(f"[{self.source_name}] 数据前3行:")
        for i in range(min(3, len(df))):
            row = df.iloc[i]
            print(f"  行{i}: date={row.get('date', 'N/A')}, title={str(row.get('title', 'N/A'))[:50]}...")
        
        for _, row in df.iterrows():
            try:
                # 央视新闻的字段：date, title, content
                title = str(row.get('title', '')).strip()
                if not title or title == 'nan':
                    continue  # 跳过空标题
                    
                content = str(row.get('content', '')).strip()
                if not content or content == 'nan':
                    content = title  # 用标题作为内容
                
                date_str = str(row.get('date', ''))
                
                # 解析日期
                publish_date = self._parse_date(date_str)
                
                # 央视新闻主要是政策新闻，市场标记为"政策"
                news_item = NewsRawItem(
                    title=title[:200],
                    content=content[:1000],
                    source=self.source_name,
                    publish_date=publish_date,
                    market="政策",
                    url="",  # 央视新闻没有提供URL
                )
                
                news_items.append(news_item)
                
            except Exception as e:
                print(f"[{self.source_name}] 解析单条新闻失败: {e}")
                continue
        
        return news_items
    
    def _parse_date(self, date_str: str) -> date:
        """解析央视新闻日期格式"""
        if not date_str or date_str.lower() == 'nan':
            return date.today()
        
        try:
            # 尝试多种日期格式
            date_str = str(date_str).strip()
            
            # 央视新闻日期格式如："2024-04-24"
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y.%m.%d"):
                try:
                    return datetime.strptime(date_str[:10], fmt).date()
                except ValueError:
                    continue
            
            # 如果包含时间，如 "2024-04-24 10:30:00"
            if ' ' in date_str:
                date_part = date_str.split(' ')[0]
                return datetime.strptime(date_part, "%Y-%m-%d").date()
                
        except Exception as e:
            print(f"[{self.source_name}] 日期解析失败 '{date_str}': {e}")
        
        return date.today()
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, ak.news_cctv)
            return df is not None and not df.empty
        except Exception as e:
            print(f"[{self.source_name}] 健康检查失败: {e}")
            return False

# 方便导入的实例
cctv_collector = AkshareCctvCollector(request_interval=300)