"""
主题生产者
"""
import logging
from typing import Dict, Optional

from ..stream_manager import RedisStreamManager

logger = logging.getLogger(__name__)

class ThemeProducer:
    """主题生产者"""
    
    def __init__(self, stream_manager: RedisStreamManager):
        self.stream_manager = stream_manager
    
    async def publish(self, theme_data: Dict) -> Optional[str]:
        """发布主题更新"""
        try:
            message = {
                "theme_data": theme_data,
                "type": "theme_update",
                "source": "theme_producer"
            }
            
            message_id = await self.stream_manager.publish(
                "stream:themes:updates",
                message,
                max_len=2000
            )
            
            logger.info(f"发布主题更新到 stream:themes:updates: {message_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"发布主题更新失败: {e}")
            return None
    
    async def publish_heat_change(self, theme_id: int, increment: int = 1) -> Optional[str]:
        """发布主题热度变化"""
        heat_data = {
            "theme_id": theme_id,
            "increment": increment,
            "action": "heat_change"
        }
        
        return await self.publish(heat_data)
