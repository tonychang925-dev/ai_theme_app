#!/usr/bin/env python3
"""
启动所有Stream消费者
"""
import asyncio
import signal
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database_service.config import DatabaseConfig
from database_service.streams.stream_config import get_enhanced_config
from database_service.streams.stream_manager import RedisStreamManager
from database_service.streams.consumers.news_consumer import NewsStreamConsumer
from database_service.streams.consumers.event_consumer import EventStreamConsumer
from database_service.streams.consumers.theme_consumer import ThemeStreamConsumer
from database_service.streams.consumers.consumer_manager import ConsumerManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('stream_consumers.log')
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """主启动函数"""
    logger.info("=" * 60)
    logger.info("🚀 启动Redis Stream消费者")
    logger.info("=" * 60)
    
    # 加载配置
    config = get_enhanced_config()
    
    if not config.redis_stream.enabled:
        logger.warning("Redis Stream处理在配置中被禁用")
        return
    
    if not config.redis.enabled:
        logger.error("Redis未启用，无法启动Stream消费者")
        return
    
    # 创建Stream管理器
    redis_url = f"redis://{config.redis.host}:{config.redis.port}/{config.redis.db}"
    if config.redis.password:
        redis_url = f"redis://:{config.redis.password}@{config.redis.host}:{config.redis.port}/{config.redis.db}"
    
    stream_manager = RedisStreamManager(redis_url)
    await stream_manager.connect()
    
    # 创建消费者管理器
    consumer_manager = ConsumerManager()
    
    # 创建并注册消费者
    consumers = []
    
    # 新闻消费者
    news_consumer = NewsStreamConsumer(stream_manager, {
        "group_name": "news_processors",
        "consumer_name": "news_processor_1",
        "stream_name": "stream:news:raw",
        "batch_size": 10,
        "model_service_url": config.external_services.model_service["url"]
    })
    consumers.append(news_consumer)
    consumer_manager.register_consumer("news_consumer", news_consumer)
    
    # 事件消费者（重大事件）
    major_event_consumer = EventStreamConsumer(stream_manager, {
        "group_name": "major_workers",
        "consumer_name": "major_worker_1",
        "stream_name": "stream:events:major",
        "batch_size": 5,
        "block_time_ms": 10000
    })
    consumers.append(major_event_consumer)
    consumer_manager.register_consumer("major_event_consumer", major_event_consumer)
    
    # 主题消费者
    theme_consumer = ThemeStreamConsumer(stream_manager, {
        "group_name": "theme_workers",
        "consumer_name": "theme_worker_1",
        "stream_name": "stream:events:normal",
        "batch_size": 20,
        "theme_service_url": config.external_services.theme_service["url"]
    })
    consumers.append(theme_consumer)
    consumer_manager.register_consumer("theme_consumer", theme_consumer)
    
    # 启动所有消费者
    logger.info("正在启动消费者...")
    await consumer_manager.start_all()
    
    logger.info("✅ 所有消费者已启动")
    logger.info("=" * 60)
    
    # 设置信号处理
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("\n🛑 收到关闭信号")
        stop_event.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # 等待停止信号
    logger.info("📡 等待消息中... (Ctrl+C 停止)")
    await stop_event.wait()
    
    # 优雅关闭
    logger.info("正在关闭...")
    await consumer_manager.stop_all()
    await stream_manager.redis.close()
    
    logger.info("👋 所有服务已优雅关闭")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 手动中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"致命错误: {e}")
        sys.exit(1)
