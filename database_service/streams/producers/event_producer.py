"""
事件生产者
"""
import logging
from typing import Dict, Optional, List

from ..stream_manager import RedisStreamManager

logger = logging.getLogger(__name__)

class EventProducer:
    """事件生产者"""
    
    def __init__(self, stream_manager: RedisStreamManager):
        self.stream_manager = stream_manager
    
    async def publish(self, event_data: Dict, is_major: bool = False) -> Optional[str]:
        """发布事件"""
        try:
            stream_key = "events:major" if is_major else "events:normal"
            
            message = {
                "event_data": event_data,
                "is_major": is_major,
                "type": "event_extraction",
                "source": "event_producer"
            }
            
            message_id = await self.stream_manager.publish(
                f"stream:{stream_key}",
                message,
                max_len=5000 if is_major else 20000
            )
            
            logger.info(f"发布事件到 stream:{stream_key}: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"发布事件失败: {e}")
            return None
