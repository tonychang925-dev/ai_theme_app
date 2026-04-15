#!/usr/bin/env python3
"""
全链路Stream集成测试脚本

测试新创建的Stream服务：
1. RealTimeNewsCollector - 新闻采集到 stream:news:raw
2. 现有NewsStreamHandler - 存储新闻到数据库
3. 现有NewsStreamProcessor - AI分析生成结构化事件到 stream:events:structured
4. EventThemeMatcher - 主题匹配到 stream:event:feed
5. SSEPushService - SSE推送服务
"""

import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_stream_services():
    """测试Stream服务集成"""
    logger.info("🚀 开始全链路Stream服务集成测试")

    try:
        # 导入必要的模块
        from database_service.streams.stream_manager import RetryEnhancedRedisStreamManager
        from database_service.streams.services.real_time_news_collector import RealTimeNewsCollector
        from database_service.streams.services.event_theme_matcher import EventThemeMatcher
        from database_service.streams.services.sse_push_service import SSEPushService

        logger.info("✅ 导入服务模块成功")

        # 初始化Redis Stream管理器
        redis_url = "redis://localhost:6379/0"
        stream_manager = RetryEnhancedRedisStreamManager(redis_url=redis_url)
        logger.info("✅ Redis Stream管理器初始化成功")

        # 测试1: RealTimeNewsCollector
        logger.info("\n📰 测试1: RealTimeNewsCollector 新闻采集服务")
        news_collector = RealTimeNewsCollector(
            stream_manager=stream_manager,
            config={
                "collection_interval": 30,  # 30秒间隔用于测试
                "default_mode": "auto",
                "max_retries": 2
            }
        )

        # 单次测试采集
        test_result = await news_collector.collect_and_publish(mode="auto")
        logger.info(f"  采集结果: 成功={test_result['success']}, "
                   f"新闻数={test_result['news_published']}, 模式={test_result['mode']}")

        if not test_result['success']:
            logger.warning("⚠️ 新闻采集测试失败，但继续测试其他服务")

        # 测试2: EventThemeMatcher
        logger.info("\n🎯 测试2: EventThemeMatcher 事件-题材匹配服务")
        event_matcher = EventThemeMatcher(
            stream_manager=stream_manager,
            config={
                "polling_interval": 1,
                "batch_size": 5,
                "max_retries": 2,
                "input_stream": "stream:events:structured",
                "output_stream": "stream:event:feed"
            }
        )

        # 测试一个模拟事件
        test_event = {
            "event_id": f"test_event_{int(time.time())}",
            "news_id": f"test_news_{int(time.time())}",
            "event_type": "policy_change",
            "summary": "测试政策变化事件",
            "title": "央行宣布降准0.5个百分点",
            "content": "中国人民银行决定下调金融机构存款准备金率0.5个百分点，释放长期资金约1万亿元",
            "source": "test",
            "occurred_at": datetime.now().isoformat()
        }

        # 测试匹配功能
        match_result = await event_matcher.match_event_to_themes(test_event)
        logger.info(f"  匹配结果: 决策={match_result.get('decision')}, "
                   f"主题={match_result.get('matched_theme_names', [])}, "
                   f"置信度={match_result.get('confidence')}")

        # 测试发布到feed
        feed_item = event_matcher._create_feed_item(test_event, match_result)
        if feed_item:
            published_id = await event_matcher.publish_matched_event(feed_item)
            if published_id:
                logger.info(f"✅ 成功发布feed项到stream:event:feed, 消息ID: {published_id}")
            else:
                logger.warning("⚠️ 发布feed项失败")
        else:
            logger.warning("⚠️ 创建feed项失败")

        # 测试3: SSEPushService
        logger.info("\n📡 测试3: SSEPushService SSE推送服务")
        sse_service = SSEPushService(
            stream_manager=stream_manager,
            config={
                "input_stream": "stream:event:feed",
                "consumer_group": "sse_testers",
                "batch_size": 5,
                "polling_interval": 1,
                "heartbeat_interval": 10
            }
        )

        # 启动SSE服务
        await sse_service.start()
        logger.info("✅ SSE推送服务已启动")

        # 检查服务状态
        sse_stats = await sse_service.get_service_stats()
        logger.info(f"  SSE服务状态: 运行中={sse_stats.get('is_running')}, "
                   f"输入Stream={sse_stats.get('input_stream')}")

        # 停止SSE服务
        await sse_service.stop()
        logger.info("✅ SSE推送服务已停止")

        # 测试4: 服务管理器集成
        logger.info("\n🔧 测试4: StreamServicesManager 服务管理器")
        from database_service.streams.start_services import StreamServicesManager

        manager = StreamServicesManager(redis_url=redis_url)

        # 初始化服务
        await manager.initialize()
        logger.info(f"✅ 服务管理器初始化成功，共初始化 {len(manager.services)} 个服务")

        # 获取服务状态
        status = await manager.get_service_status()
        logger.info(f"  服务状态: 运行中={status['is_running']}, 服务数={len(status['services'])}")

        for service_info in status['services']:
            logger.info(f"    - {service_info['name']}: 配置已加载")

        # 清理
        await manager.stop_all()
        logger.info("✅ 服务管理器已停止所有服务")

        logger.info("\n🎉 全链路Stream服务集成测试完成！")
        logger.info("下一步: 运行 start_services.py 启动所有服务进行端到端测试")

        return True

    except ImportError as e:
        logger.error(f"❌ 导入模块失败: {e}")
        logger.info("💡 确保在项目根目录运行此脚本")
        return False
    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_sse_endpoint():
    """测试SSE端点"""
    logger.info("\n🌐 测试SSE端点连接")

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # 测试现有的SSE端点
            url = "http://localhost:8000/api/intel/stream/realtime"
            logger.info(f"  连接SSE端点: {url}")

            try:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        logger.info(f"✅ SSE端点连接成功，状态码: {response.status}")
                        # 读取几行响应
                        reader = response.content
                        lines = []
                        for _ in range(3):
                            line = await reader.readline()
                            if not line:
                                break
                            lines.append(line.decode('utf-8').strip())

                        if lines:
                            logger.info(f"  收到SSE响应: {lines[0][:50]}...")
                        return True
                    elif response.status == 503:
                        logger.warning("⚠️ SSE端点服务不可用（可能SSE推送服务未启动）")
                        logger.info("💡 运行 start_services.py 启动SSE推送服务")
                        return False
                    else:
                        logger.warning(f"⚠️ SSE端点返回异常状态码: {response.status}")
                        return False
            except asyncio.TimeoutError:
                logger.warning("⚠️ SSE端点连接超时")
                return False
            except Exception as e:
                logger.warning(f"⚠️ SSE端点连接错误: {e}")
                return False

    except ImportError:
        logger.warning("⚠️ 无法导入aiohttp，跳过SSE端点测试")
        return False


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("全链路Stream服务集成测试")
    logger.info("=" * 60)

    # 测试Stream服务
    stream_services_ok = await test_stream_services()

    # 测试SSE端点
    sse_endpoint_ok = await test_sse_endpoint()

    logger.info("\n" + "=" * 60)
    logger.info("测试结果总结:")
    logger.info(f"  Stream服务集成测试: {'✅ 通过' if stream_services_ok else '❌ 失败'}")
    logger.info(f"  SSE端点连接测试: {'✅ 通过' if sse_endpoint_ok else '⚠️ 警告或跳过'}")

    if stream_services_ok:
        logger.info("\n🎉 全链路打通基础服务搭建完成！")
        logger.info("下一步:")
        logger.info("  1. 启动Redis服务")
        logger.info("  2. 运行 python -m database_service.streams.start_services")
        logger.info("  3. 访问 http://localhost:8000/api/intel/stream/realtime 测试SSE推送")
        logger.info("  4. 使用浏览器或curl测试SSE事件流")
    else:
        logger.info("\n❌ 测试失败，请检查错误信息")

    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())