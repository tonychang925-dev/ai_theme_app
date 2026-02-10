"""
消费者管理器
统一管理所有消费者实例
"""
import asyncio
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class ConsumerManager:
    """消费者管理器"""
    
    def __init__(self):
        self.consumers = {}
        self.consumer_tasks = {}
        self.running = False
    
    def register_consumer(self, name: str, consumer):
        """注册消费者"""
        self.consumers[name] = consumer
        logger.info(f"注册消费者: {name}")
    
    async def start_all(self):
        """启动所有消费者"""
        if self.running:
            logger.warning("消费者管理器已在运行")
            return
        
        self.running = True
        logger.info(f"启动 {len(self.consumers)} 个消费者")
        
        for name, consumer in self.consumers.items():
            task = asyncio.create_task(consumer.start())
            self.consumer_tasks[name] = task
            logger.info(f"启动消费者: {name}")
    
    async def stop_all(self):
        """停止所有消费者"""
        if not self.running:
            return
        
        self.running = False
        logger.info("停止所有消费者...")
        
        for name, consumer in self.consumers.items():
            try:
                await consumer.stop()
                logger.info(f"停止消费者: {name}")
            except Exception as e:
                logger.error(f"停止消费者失败 {name}: {e}")
        
        for name, task in self.consumer_tasks.items():
            task.cancel()
        
        await asyncio.gather(*self.consumer_tasks.values(), return_exceptions=True)
        self.consumer_tasks.clear()
        
        logger.info("所有消费者已停止")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {
            "running": self.running,
            "total_consumers": len(self.consumers),
            "running_consumers": len(self.consumer_tasks),
            "consumers": {}
        }
        
        for name, consumer in self.consumers.items():
            if hasattr(consumer, 'get_stats'):
                stats["consumers"][name] = consumer.get_stats()
        
        return stats
