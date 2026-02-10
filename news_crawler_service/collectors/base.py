from abc import ABC, abstractmethod
from typing import List, Optional
from ..models.news_raw import NewsRawItem

class BaseCollector(ABC):
    """新闻采集器抽象基类"""
    
    def __init__(self, request_interval: int = 10, max_retries: int = 3):
        self.request_interval = request_interval
        self.max_retries = max_retries
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """采集器唯一标识"""
        pass
    
    @abstractmethod
    async def fetch(self) -> List[NewsRawItem]:
        """
        执行采集任务
        返回标准化后的新闻列表
        """
        pass
    
    async def health_check(self) -> bool:
        """健康检查，默认返回True"""
        return True