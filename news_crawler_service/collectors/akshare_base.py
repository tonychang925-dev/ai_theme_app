# ai_theme_app/news_crawler_service/collectors/akshare_base.py
from ..collectors.base import BaseCollector
from ..models.news_raw import NewsRawItem
from datetime import datetime, date
from typing import List, Callable
import asyncio

class AkshareBaseCollector(BaseCollector):
    """akshare采集器基类"""
    
    def __init__(self, fetch_function: Callable, **kwargs):
        super().__init__(**kwargs)
        self.fetch_function = fetch_function
        self.source_type = "akshare"
    
    async def fetch(self) -> List[NewsRawItem]:
        """执行抓取任务"""
        news_items = []
        
        try:
            # 在线程池中执行同步的akshare调用
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, self.fetch_function)
            
            if df is not None and not df.empty:
                news_items = await self._convert_dataframe(df)
                print(f"[{self.source_name}] 成功抓取 {len(news_items)} 条新闻")
            else:
                print(f"[{self.source_name}] 未抓取到数据")
                
        except Exception as e:
            print(f"[{self.source_name}] 抓取失败: {e}")
            
        return news_items
    
    async def _convert_dataframe(self, df) -> List[NewsRawItem]:
        """将DataFrame转换为NewsRawItem列表（子类可重写）"""
        news_items = []
        
        # 尝试识别常见的列名
        title_col = self._find_column(df, ['title', '标题', '新闻标题', 'name'])
        content_col = self._find_column(df, ['content', '内容', '新闻内容', '摘要'])
        date_col = self._find_column(df, ['date', '发布日期', '时间', 'pub_date'])
        url_col = self._find_column(df, ['url', '链接', '新闻链接'])
        
        for _, row in df.iterrows():
            try:
                # 获取数据
                title = str(row[title_col]) if title_col else "无标题"
                content = str(row[content_col]) if content_col else title
                url = str(row[url_col]) if url_col else ""
                
                # 解析日期
                publish_date = self._parse_date(row[date_col] if date_col else "")
                
                # 创建新闻对象
                news_item = NewsRawItem(
                    title=title[:300].strip(),
                    content=content[:1000].strip(),
                    source=self.source_name,
                    publish_date=publish_date,
                    market=self._detect_market(title + content),
                    url=url,
                )
                
                news_items.append(news_item)
                
            except Exception as e:
                print(f"[{self.source_name}] 解析数据行失败: {e}")
                continue
        
        return news_items
    
    def _find_column(self, df, possible_names):
        """在DataFrame中查找可能的列名"""
        for name in possible_names:
            if name in df.columns:
                return name
        return df.columns[0] if len(df.columns) > 0 else None
    
    def _parse_date(self, date_str):
        """解析日期字符串"""
        try:
            if isinstance(date_str, (datetime, pd.Timestamp)):
                return date_str.date()
            
            str_date = str(date_str)
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y.%m.%d"):
                try:
                    return datetime.strptime(str_date[:10], fmt).date()
                except:
                    continue
        except:
            pass
        return date.today()
    
    def _detect_market(self, text: str) -> str:
        """从文本中检测市场"""
        text = text.lower()
        if any(word in text for word in ['美股', '纳斯达克', '纽交所', '美国']):
            return "美股"
        elif any(word in text for word in ['港股', '香港', '恒生']):
            return "港股"
        elif any(word in text for word in ['a股', '上证', '深证', '创业板']):
            return "A股"
        return "全球"