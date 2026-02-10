# ai_theme_app/news_crawler_service/collectors/akshare_cls.py
import asyncio
import akshare as ak
import pandas as pd
from datetime import datetime, date, time
from typing import List, Dict, Any
import re
import traceback

from ..collectors.base import BaseCollector
from ..models.news_raw import NewsRawItem
from ..config import settings

class AkshareClsCollector(BaseCollector):
    """财联社电报采集器（防护增强版）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.symbol = "全部"  # 可配置化
        self.last_request_time = 0
        
    @property
    def source_name(self) -> str:
        return "akshare_cls"
    
    async def fetch(self) -> List[NewsRawItem]:
        """执行抓取任务，返回标准化新闻列表"""
        news_items = []
        
        try:
            # 1. 遵守请求间隔（防反爬）
            await self._respect_request_interval()
            
            # 2. 在线程池中执行同步的akshare调用
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, 
                self._fetch_akshare_data
            )
            
            if df is not None and not df.empty:
                # 3. 转换为标准化数据模型
                news_items = await self._convert_to_news_items(df)
                
                print(f"[{self.source_name}] 成功抓取 {len(news_items)} 条新闻")
            else:
                print(f"[{self.source_name}] 未抓取到数据")
                
        except Exception as e:
            print(f"[{self.source_name}] 抓取失败: {e}")
            traceback.print_exc()
            # 这里可以触发重试或熔断逻辑
            
        return news_items
    
    def _fetch_akshare_data(self) -> pd.DataFrame:
        """调用akshare获取原始数据（同步方法）"""
        try:
            df = ak.stock_info_global_cls(symbol=self.symbol)
            
            # 调试：输出列名查看数据结构
            print(f"[{self.source_name}] 数据列名: {list(df.columns)}")
            print(f"[{self.source_name}] 数据形状: {df.shape}")
            
            return df
        except Exception as e:
            print(f"[{self.source_name}] akshare调用失败: {e}")
            return pd.DataFrame()
    
    async def _convert_to_news_items(self, df: pd.DataFrame) -> List[NewsRawItem]:
        """将DataFrame转换为NewsRawItem列表"""
        news_items = []
        
        for _, row in df.iterrows():
            try:
                # 解析发布日期
                publish_date = self._parse_publish_date(row)
                
                # 解析发布时间
                publish_time = self._parse_publish_time(row)
                
                # 创建标准化新闻对象
                news_item = NewsRawItem(
                    title=str(row.get('标题', '无标题')).strip(),
                    content=str(row.get('内容', '')).strip(),
                    source=self.source_name,
                    publish_date=publish_date,
                    publish_time=publish_time,
                    market=str(row.get('市场', 'A股')),
                    url=str(row.get('URL', '')),
                )
                
                news_items.append(news_item)
                
            except Exception as e:
                print(f"[{self.source_name}] 解析单条新闻失败: {e}")
                continue
        
        return news_items
    
    def _parse_publish_date(self, row) -> date:
        """解析发布日期"""
        date_str = str(row.get('发布日期', ''))
        
        if not date_str:
            return date.today()
        
        try:
            # 尝试多种日期格式
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            return date.today()
        except Exception:
            return date.today()
    
    def _parse_publish_time(self, row) -> time:
        """解析发布时间"""
        time_str = str(row.get('发布时间', ''))
        
        if not time_str:
            return time(0, 0, 0)
        
        try:
            # 清理时间字符串
            time_str = time_str.strip()
            
            # 处理常见的时间格式
            if ':' in time_str:
                parts = time_str.split(':')
                if len(parts) >= 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    second = int(parts[2]) if len(parts) >= 3 else 0
                    
                    # 验证时间合理性
                    if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
                        return time(hour, minute, second)
            
            return time(0, 0, 0)
        except Exception:
            return time(0, 0, 0)
    
    async def _respect_request_interval(self):
        """遵守请求间隔，防反爬"""
        current_time = datetime.now().timestamp()
        elapsed = current_time - self.last_request_time
        
        if elapsed < settings.REQUEST_INTERVAL_SECONDS:
            sleep_time = settings.REQUEST_INTERVAL_SECONDS - elapsed
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = datetime.now().timestamp()
    
    async def health_check(self) -> bool:
        """健康检查：测试akshare是否可用"""
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, ak.stock_info_global_cls, "全部")
            return df is not None and not df.empty
        except Exception:
            return False

# 方便导入的实例
akshare_collector = AkshareClsCollector(
    request_interval=settings.REQUEST_INTERVAL_SECONDS,
    max_retries=settings.MAX_RETRY_TIMES
)