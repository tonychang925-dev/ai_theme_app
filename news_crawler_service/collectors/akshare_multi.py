# ai_theme_app/news_crawler_service/collectors/akshare_multi.py
import akshare as ak
from .akshare_base import AkshareBaseCollector

class AkshareClsCollector(AkshareBaseCollector):
    """财联社电报（已有，适配新基类）"""
    
    def __init__(self, **kwargs):
        super().__init__(fetch_function=lambda: ak.stock_info_global_cls(symbol="全部"), **kwargs)
    
    @property
    def source_name(self) -> str:
        return "akshare_cls"

class AkshareEastmoneyCollector(AkshareBaseCollector):
    """东方财富新闻"""
    
    def __init__(self, **kwargs):
        super().__init__(fetch_function=ak.news_5562, **kwargs)
    
    @property
    def source_name(self) -> str:
        return "akshare_eastmoney"

class AkshareSinaCollector(AkshareBaseCollector):
    """新浪新闻"""
    
    def __init__(self, **kwargs):
        super().__init__(fetch_function=ak.news_sina, **kwargs)
    
    @property
    def source_name(self) -> str:
        return "akshare_sina"

# 更多采集器可以根据测试结果添加...