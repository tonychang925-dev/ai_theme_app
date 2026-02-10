"""
消费者基类 - 所有消费者的父类
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseStreamConsumer(ABC):
    """Stream消费者基类"""
    
    def __init__(self, stream_manager, config: Dict):
        self.stream_manager = stream_manager
        self.config = config
        
        self.group_name = config.get("group_name", "default_group")
        self.consumer_name = config.get("consumer_name", "consumer_1")
        self.stream_name = config.get("stream_name")
        self.batch_size = config.get("batch_size", 10)
        
        self.running = False
        self.processed_count = 0
    
    async def start(self):
        """启动消费者"""
        if self.running:
            logger.warning(f"Consumer {self.consumer_name} is already running")
            return
        
        await self.stream_manager.create_consumer_group(self.stream_name, self.group_name)
        self.running = True
        
        while self.running:
            try:
                await self._consume_loop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer {self.consumer_name} error: {e}")
                await asyncio.sleep(1)
    
    async def _consume_loop(self):
        """消费循环"""
        messages = await self.stream_manager.consume(
            group=self.group_name,
            consumer=self.consumer_name,
            stream=self.stream_name,
            count=self.batch_size,
            block_ms=5000
        )
        
        if messages:
            success_ids = []
            for message in messages:
                try:
                    if await self.process_message(message):
                        success_ids.append(message.id)
                        self.processed_count += 1
                except Exception as e:
                    logger.error(f"Error processing message {message.id}: {e}")
            
            if success_ids:
                await self.stream_manager.batch_ack(self.stream_name, self.group_name, success_ids)
    
    @abstractmethod
    async def process_message(self, message) -> bool:
        """处理消息 - 子类必须实现"""
        pass
    
    async def stop(self):
        """停止消费者"""
        self.running = False
