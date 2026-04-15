#!/usr/bin/env python3
"""
紧急消费者启动脚本 - 临时增加处理能力
用于解决高pending消息问题
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.managers.redis_event_bus import RedisEventBus
from database_service.gateway import DatabaseGateway

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def start_emergency_consumer(consumer_id: int):
    """启动紧急消费者"""
    logger.info(f"🚀 启动紧急消费者 #{consumer_id}")
    
    try:
        # 创建事件总线
        event_bus = RedisEventBus()
        
        # 创建数据库网关
        gateway = DatabaseGateway()
        
        # 配置 - 优化处理速度
        config = {
            "database_gateway": gateway,
            "processor_group": "news_business_processors",
            "processor_name": f"emergency_consumer_{consumer_id:03d}",
            "enable_ai_analysis": True,
            "enable_local_triage": True,
            "triage_mode": "fast",  # 快速模式
            "triage_pass_threshold": 0.03,  # 降低阈值，更多消息通过
            "triage_skip_threshold": -0.05,  # 提高跳过阈值
            "triage_block_on_skip": False,  # 不阻塞，继续处理
            "batch_processing": True,
            "batch_size": 3,  # 小批量处理
            "max_processing_time": 30,  # 最大处理时间30秒
        }
        
        # 创建处理器
        processor = NewsStreamProcessor(event_bus, config)
        
        # 启动处理
        await processor.start_business_processing()
        
        logger.info(f"✅ 紧急消费者 #{consumer_id} 启动成功")
        
        # 保持运行
        while True:
            await asyncio.sleep(60)
            logger.info(f"🔄 紧急消费者 #{consumer_id} 运行中...")
            
    except Exception as e:
        logger.error(f"❌ 紧急消费者 #{consumer_id} 启动失败: {e}")
        raise

async def main():
    """主函数"""
    print("=" * 60)
    print("🚨 紧急消费者启动程序")
    print("=" * 60)
    
    # 启动多个消费者
    num_consumers = 10  # 启动10个紧急消费者
    tasks = []
    
    print(f"📈 计划启动 {num_consumers} 个紧急消费者")
    print("这将临时增加处理能力，加速pending消息处理")
    print()
    
    for i in range(num_consumers):
        task = asyncio.create_task(start_emergency_consumer(i + 1))
        tasks.append(task)
        await asyncio.sleep(1)  # 间隔1秒启动
    
    print(f"✅ 已启动 {num_consumers} 个紧急消费者")
    print("📊 监控pending消息变化:")
    print("  redis-cli XPENDING stream:events:normal news_business_processors")
    print()
    
    # 等待所有任务
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\n🛑 收到中断信号，停止紧急消费者...")
    except Exception as e:
        print(f"❌ 运行出错: {e}")
    finally:
        print("👋 紧急消费者程序结束")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户中断")
    except Exception as e:
        print(f"❌ 程序异常: {e}")
        sys.exit(1)
