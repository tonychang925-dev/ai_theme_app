# model_service/llm_parser/base_parser.py
"""
基础LLM解析器抽象类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging


class BaseLLMParser(ABC):
    """LLM解析器基类"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def parse_content(self, content: str) -> Optional[Dict[str, Any]]:
        """
        解析内容并返回结构化数据
        
        Args:
            content: 要解析的文本内容
            
        Returns:
            解析后的结构化数据字典
        """
        pass
    
    @abstractmethod
    async def parse_news(self, title: str, content: str) -> Optional[Dict[str, Any]]:
        """
        解析新闻内容
        
        Args:
            title: 新闻标题
            content: 新闻内容
            
        Returns:
            事件信息字典
        """
        pass
    
    @abstractmethod
    async def close(self):
        """关闭资源"""
        pass
    
    def __str__(self):
        return f"{self.__class__.__name__}(model={self.model_name})"
