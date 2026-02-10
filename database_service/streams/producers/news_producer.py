# database_service/streams/producers/news_producer.py
"""
新闻生产者 - 将新闻发布到Redis Stream
"""
import json
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class NewsProducer:
    """新闻生产者"""
    
    def __init__(self, stream_manager):
        """初始化新闻生产者"""
        self.stream_manager = stream_manager
    
    async def publish(self, news_data: Dict, stream_type: str = "news:raw") -> str:
        """发布单条新闻到Stream"""
        try:
            # 构建消息数据
            message_data = {
                "news_data": news_data,
                "type": stream_type,
                "source": "news_producer",
                "published_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            # 确定stream名称
            if ":" in stream_type:
                stream_name = f"stream:{stream_type}"
            else:
                stream_name = f"stream:news:{stream_type}"
            
            # 发布消息
            message_id = await self.stream_manager.publish(stream_name, message_data)
            
            logger.info(f"新闻生产者发布成功: {news_data.get('id', 'unknown')} -> {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"新闻发布失败: {e}")
            raise
    
    async def publish_batch(self, news_items: List[Dict], stream_type: str = "news:raw") -> List[str]:
        """批量发布新闻到Stream"""
        message_ids = []
        
        for news_data in news_items:
            try:
                message_id = await self.publish(news_data, stream_type)
                message_ids.append(message_id)
            except Exception as e:
                logger.error(f"批量发布单条新闻失败: {e}")
                message_ids.append(None)
        
        return message_ids