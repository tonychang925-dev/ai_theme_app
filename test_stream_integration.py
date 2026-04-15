#!/usr/bin/env python3
"""
测试StreamServicesManager集成所有服务
"""
import asyncio
import logging
import sys
import time
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_service_integration():
    """测试服务集成"""
    logger.info("测试StreamServicesManager集成")

    try:
        from database_service.streams.start_services import StreamServicesManager

        manager = StreamServicesManager(redis_url="redis://localhost:6379/0")

        # 初始化服务
        await manager.initialize()
        logger.info(f"✅ 服务管理器初始化成功，共 {len(manager.services)} 个服务")

        # 打印服务列表
        for service_info in manager.services:
            service_name = service_info["name"]
            service_class = service_info["instance"].__class__.__name__
            logger.info(f"  - {service_name}: {service_class}")

        # 检查服务依赖
        logger.info("检查服务依赖:")
        for service_info in manager.services:
            service_name = service_info["name"]
            config = service_info["config"]
            logger.info(f"  - {service_name}: 配置 keys = {list(config.keys())}")

        # 启动所有服务
        await manager.start_all()
        logger.info("✅ 所有服务已启动")

        # 等待60秒让服务运行，并检查是否有事件被处理
        logger.info("等待60秒让服务处理数据，并监控事件处理...")

        # 创建Redis客户端来检查streams
        import redis.asyncio as redis
        redis_client = redis.from_url("redis://localhost:6379/0")

        max_wait = 30  # 最大等待30秒
        check_interval = 5  # 每5秒检查一次
        events_processed = False

        for i in range(max_wait // check_interval):
            # 检查stream:events:structured是否有消息
            events_count = await redis_client.xlen("stream:events:structured")
            logger.info(f"检查进度 {i*check_interval}/{max_wait}秒: stream:events:structured 有 {events_count} 条消息")

            if events_count > 0:
                logger.info(f"✅ 检测到事件处理! stream:events:structured 有 {events_count} 条消息")
                events_processed = True
                break

            # 等待下一次检查
            await asyncio.sleep(check_interval)

        if not events_processed:
            logger.warning(f"⚠️  在{max_wait}秒内未检测到事件处理")

        # 继续等待剩余时间以确保稳定运行
        remaining_time = max_wait - (i * check_interval if events_processed else max_wait)
        if remaining_time > 0:
            logger.info(f"等待剩余 {remaining_time} 秒确保稳定运行...")
            await asyncio.sleep(remaining_time)

        await redis_client.close()

        # 获取服务状态
        status = await manager.get_service_status()
        logger.info(f"服务状态: 运行中={status['is_running']}")

        for service_info in status['services']:
            name = service_info['name']
            stats = service_info.get('stats', {})
            logger.info(f"  - {name}: stats = {stats}")

        # 再次检查所有streams的最终状态
        import redis.asyncio as redis
        redis_client = redis.from_url("redis://localhost:6379/0")

        streams = [
            "stream:news:raw",
            "stream:events:structured",
            "stream:event:feed"
        ]

        for stream in streams:
            length = await redis_client.xlen(stream)
            logger.info(f"  {stream}: {length} 条消息")

        await redis_client.close()

        # 停止所有服务
        await manager.stop_all()
        logger.info("✅ 所有服务已停止")

        return True

    except ImportError as e:
        logger.error(f"导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    logger.info("=" * 60)
    logger.info("StreamServicesManager 集成测试")
    logger.info("=" * 60)

    success = await test_service_integration()

    logger.info("\n" + "=" * 60)
    logger.info(f"测试结果: {'✅ 成功' if success else '❌ 失败'}")
    logger.info("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())