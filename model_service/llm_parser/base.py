"""
LLM解析器抽象基类定义
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class LLMProvider(Enum):
    """支持的LLM提供商枚举"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    # 未来可扩展：CLAUDE = "claude", GEMINI = "gemini"

@dataclass
class ParsedEvent:
    """标准化的事件解析输出"""
    event_type: str
    impact_industries: List[str]
    direction: str  # 利好/利空/中性
    summary: str
    confidence: float
    raw_response: Optional[Dict] = None  # 保留原始响应供调试

class LLMParser(ABC):
    """LLM解析器抽象基类。所有具体模型解析器必须实现此接口。"""
    
    def __init__(self, provider: LLMProvider):
        self.provider = provider
    
    @abstractmethod
    async def parse_news(self, title: str, content: str) -> Optional[ParsedEvent]:
        """
        核心方法：解析新闻文本，返回结构化事件。
        返回 None 表示解析失败。
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """检查与对应API服务的连接是否健康"""
        pass
    
    @abstractmethod
    async def close(self):
        """清理资源（如HTTP会话）"""
        pass
