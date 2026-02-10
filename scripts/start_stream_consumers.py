#!/usr/bin/env python3
"""
启动所有Stream消费者
"""
import asyncio
import signal
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """主启动函数"""
    logger.info("🚀 Starting Redis Stream Consumers...")
    
    # TODO: 实现消费者启动逻辑
    
    # 等待信号
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("🛑 Received shutdown signal")
        stop_event.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    await stop_event.wait()
    logger.info("👋 Shutting down...")

if __name__ == "__main__":
    asyncio.run(main())
