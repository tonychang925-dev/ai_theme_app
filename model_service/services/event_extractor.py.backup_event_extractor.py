"""
事件提取器 - 基于LLM解析器的新实现
"""
import logging
from typing import Dict, Optional

from ..llm_parser.factory import LLMParserFactory
from ..llm_parser.base import LLMParser

logger = logging.getLogger(__name__)

class AIEventExtractor:
    """基于抽象LLMParser的事件提取器"""
    
    def __init__(self, llm_parser: Optional[LLMParser] = None):
        """
        可以传入一个已有的解析器，如果为None则从工厂创建默认解析器。
        """
        self.llm_parser = llm_parser or LLMParserFactory.create_parser_from_env()
        logger.info(f"AI事件提取器已初始化，使用 {self.llm_parser.provider.value} 提供商")
    
    async def extract_event(self, news_data: Dict) -> Optional[Dict]:
        """
        从新闻数据中提取结构化事件。
        保持与原有MockEventExtractor完全相同的接口。
        """
        title = news_data.get('title', '')
        content = news_data.get('content', '')
        news_id = news_data.get('news_id')
        
        if not title or not content:
            logger.warning(f"新闻数据不完整，跳过处理。news_id: {news_id}")
            return None
        
        # 调用抽象的LLM解析器
        parsed_event = await self.llm_parser.parse_news(title, content)
        
        if not parsed_event:
            logger.warning(f"LLM解析失败，未提取到事件。news_id: {news_id}")
            return None
        
        logger.info(f"成功提取事件: news_id={news_id}, type={parsed_event.event_type}")
        
        # 转换为news_event表所需的格式
        return {
            'news_id': news_id,
            'event_type': parsed_event.event_type,
            'impact_industries': parsed_event.impact_industries,
            'direction': parsed_event.direction,
            'confidence': parsed_event.confidence,
            'summary': parsed_event.summary,
            'raw_ai_response': parsed_event.raw_response
        }
    
    async def health_check(self) -> bool:
        """检查提取器健康状态"""
        if not self.llm_parser:
            return False
        return await self.llm_parser.health_check()
    
    async def close(self):
        """清理资源"""
        if self.llm_parser:
            await self.llm_parser.close()
            logger.info("AI事件提取器资源已释放")

# 保持向后兼容的Mock提取器（供测试使用）
class MockEventExtractor:
    """模拟事件提取器，用于测试"""
    
    async def extract_event(self, news_data: Dict) -> Optional[Dict]:
        import random
        from datetime import datetime
        
        event_types = ["政策", "技术", "财报", "产业", "资本", "其他"]
        industries = ["人工智能", "新能源汽车", "芯片半导体", "医药生物", "金融"]
        directions = ["利好", "利空", "中性"]
        
        return {
            'news_id': news_data.get('news_id', 'mock_001'),
            'event_type': random.choice(event_types),
            'impact_industries': random.sample(industries, k=random.randint(1, 3)),
            'direction': random.choice(directions),
            'confidence': round(random.uniform(0.7, 0.95), 2),
            'summary': f"模拟事件摘要 - {datetime.now().strftime('%H:%M:%S')}",
            'raw_ai_response': {"mock": True}
        }
    
    async def health_check(self) -> bool:
        return True
    
    async def close(self):
        pass
