"""
全链路打通服务启动脚本

启动所有Stream相关服务，实现从新闻采集到SSE推送的全链路。
"""

import asyncio
import logging
import os
import signal
import sys
import traceback
from typing import List, Dict, Any, Optional
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StreamServicesManager:
    """Stream服务管理器"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.services = []
        self.is_running = False
        self.stream_manager = None
        self.stream_cleanup_scheduler = None
        self.consumer_group_cleanup_task: Optional[asyncio.Task] = None
        self.pending_reclaim_task: Optional[asyncio.Task] = None

        # 清理调度参数（可通过环境变量覆盖）
        self.stream_cleanup_interval_hours = int(os.getenv("STREAM_CLEANUP_INTERVAL_HOURS", "2"))
        self.consumer_group_cleanup_interval_seconds = int(os.getenv("CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS", "1800"))
        self.consumer_group_cleanup_pattern = os.getenv("CONSUMER_GROUP_CLEANUP_PATTERN", "") or None
        self.consumer_group_cleanup_max_age_hours = int(os.getenv("CONSUMER_GROUP_MAX_AGE_HOURS", "12"))

        # pending 回收参数
        self.pending_reclaim_enabled = os.getenv("PENDING_RECLAIM_ENABLED", "true").lower() == "true"
        self.pending_reclaim_interval_seconds = int(os.getenv("PENDING_RECLAIM_INTERVAL_SECONDS", "300"))
        self.pending_reclaim_stream_pattern = os.getenv("PENDING_RECLAIM_STREAM_PATTERN", "stream:*")
        self.pending_reclaim_min_idle_ms = int(os.getenv("PENDING_RECLAIM_MIN_IDLE_MS", "300000"))
        self.pending_reclaim_count = int(os.getenv("PENDING_RECLAIM_COUNT", "50"))
        self.pending_reclaim_max_per_group = int(os.getenv("PENDING_RECLAIM_MAX_PER_GROUP", "200"))

    async def initialize(self):
        """初始化所有服务"""
        logger.info("正在初始化Stream服务...")

        try:
            # 导入服务类
            from .services.real_time_news_collector import RealTimeNewsCollector
            from .services.event_theme_matcher import EventThemeMatcher
            from .services.sse_push_service import SSEPushService
            from .services.event_review_writer import EventReviewWriter
            from .stream_manager import RetryEnhancedRedisStreamManager

            # 尝试导入现有处理器（可选）
            try:
                from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
                HAS_UNIFIED_STREAM_BUS = True
            except ImportError as e:
                HAS_UNIFIED_STREAM_BUS = False
                logger.warning(f"无法导入UnifiedRedisStreamBus: {e}")

            try:
                from database_service.streams.gateway_integration import get_gateway
                HAS_DATABASE_GATEWAY = True
            except ImportError as e:
                HAS_DATABASE_GATEWAY = False
                logger.warning(f"无法导入DatabaseGateway: {e}")

            try:
                from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
                HAS_NEWS_STREAM_HANDLER = True
            except ImportError as e:
                HAS_NEWS_STREAM_HANDLER = False
                logger.warning(f"无法导入NewsStreamHandler: {e}")

            try:
                from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
                from database_service.streams.handlers.theme_processor import ThemeProcessor
                from database_service.streams.handlers.DecisionExecutor import DecisionExecutor  # noqa: F811
                HAS_NEWS_STREAM_PROCESSOR = True
            except ImportError as e:
                HAS_NEWS_STREAM_PROCESSOR = False
                logger.warning(f"无法导入NewsStreamProcessor: {e}")

            # 创建Stream管理器
            stream_manager = RetryEnhancedRedisStreamManager(redis_url=self.redis_url)
            self.stream_manager = stream_manager
            logger.info("Stream管理器创建成功")

            # 初始化Stream清理调度器（可选）
            try:
                from .stream_config import get_stream_config
                from .stream_cleanup_scheduler import StreamCleanupScheduler
                stream_config = get_stream_config()
                self.stream_cleanup_scheduler = StreamCleanupScheduler(stream_manager, stream_config)
                self.stream_cleanup_scheduler.config["cleanup_interval_hours"] = self.stream_cleanup_interval_hours
                logger.info("Stream清理调度器初始化成功")
            except Exception as e:
                self.stream_cleanup_scheduler = None
                logger.warning(f"Stream清理调度器初始化失败，继续运行: {e}")

            # 创建现有处理器所需的依赖
            unified_stream_bus = None
            database_gateway = None
            crawler_client = None

            # 尝试创建爬虫服务客户端
            try:
                from news_crawler_service.services.news_crawler_service import get_news_crawler_service
                crawler_service = get_news_crawler_service()
                # 创建一个简单的适配器，将crawler_service转换为crawler_client接口
                class CrawlerServiceAdapter:
                    def __init__(self, crawler_service):
                        self.crawler_service = crawler_service

                    async def fetch_news(self, sources=None, limit=50, hours=1):
                        # 调用crawler_service的crawl_news_auto方法
                        result = await self.crawler_service.crawl_news_auto(count=limit, prefer_real=True)
                        if result.get("status") == "success":
                            return result.get("response", {}).get("news_list", [])
                        return []

                crawler_client = CrawlerServiceAdapter(crawler_service)
                logger.info("爬虫服务客户端创建成功")
            except Exception as e:
                logger.warning(f"创建爬虫服务客户端失败: {e}")
                crawler_client = None

            if HAS_UNIFIED_STREAM_BUS:
                try:
                    import redis.asyncio as redis
                    from database_service.config import DatabaseConfig
                    redis_client = redis.from_url(self.redis_url)
                    config = DatabaseConfig()  # 使用默认配置
                    unified_stream_bus = UnifiedRedisStreamBus(redis_client=redis_client, config=config)
                    logger.info("UnifiedRedisStreamBus创建成功")
                except Exception as e:
                    logger.error(f"创建UnifiedRedisStreamBus失败: {e}")
                    HAS_UNIFIED_STREAM_BUS = False

            if HAS_DATABASE_GATEWAY:
                try:
                    database_gateway = await get_gateway()
                    logger.info("DatabaseGateway创建成功")
                except Exception as e:
                    logger.error(f"创建DatabaseGateway失败: {e}")
                    HAS_DATABASE_GATEWAY = False

            # 配置服务
            services_config = {
                "news_collector": {
                    "class": RealTimeNewsCollector,
                    "config": {
                        "collection_interval": 300,  # 5分钟
                        "default_mode": "auto",
                        "max_retries": 3,
                        # 采集前预筛选：小事件直接丢弃，不进入stream:news:raw、不触发后续落库
                        "enable_collector_prefilter": True,
                        "collector_drop_on_skip": True,
                        # 为节省资源，collector侧默认仅用规则预筛；如需可切换为True启用Qwen prompt
                        "collector_prefilter_use_prompt": False,
                        "local_qwen_model_path": "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf",
                        "triage_pass_threshold": 0.06,
                        "triage_skip_threshold": -0.02,
                    },
                    "dependencies": ["stream_manager", "crawler_service_client"]
                },
                "event_matcher": {
                    "class": EventThemeMatcher,
                    "config": {
                        "polling_interval": 1,
                        "batch_size": 10,
                        "max_retries": 3
                    },
                    "dependencies": ["stream_manager"]
                },
                "sse_pusher": {
                    "class": SSEPushService,
                    "config": {
                        "input_stream": "stream:event:feed",
                        "polling_interval": 1,
                        "batch_size": 10,
                        "heartbeat_interval": 15
                    },
                    "dependencies": ["stream_manager"]
                },
                "event_review_writer": {
                    "class": EventReviewWriter,
                    "config": {
                        "input_stream": "stream:event:feed",
                        "polling_interval": 1,
                        "batch_size": 10,
                        "max_retries": 3,
                        "min_review_confidence": 0.6,
                        "skip_generic_theme": True,
                    },
                    "dependencies": ["stream_manager", "database_gateway"]
                },
                "theme_processor": {
                    "class": ThemeProcessor,
                    "config": {
                        "consumer_group": "theme_processor_realtime",
                        "stream_structured": "stream:events:structured",
                        "stream_decision": "stream:events:decision",
                        "structured_batch_size": 10,
                        "structured_block_time": 5000,
                    },
                    "dependencies": []
                },
                "decision_executor": {
                    "class": DecisionExecutor,
                    "config": {},
                    "pass_config": False,
                    "param_map": {
                        "redis_client": "stream_manager._client",
                        "db_gateway": "database_gateway",
                    },
                    "dependencies": ["stream_manager", "database_gateway"]
                }
            }

            # 条件添加现有处理器服务
            if HAS_NEWS_STREAM_HANDLER and HAS_UNIFIED_STREAM_BUS and HAS_DATABASE_GATEWAY:
                services_config["news_storage_handler"] = {
                    "class": NewsStreamHandler,
                    "config": {
                        "consumer_group": "news_storage_handlers",
                        "stream_name": "stream:news:raw",
                        "batch_size": 10,
                        "block_time": 5000
                    },
                    "dependencies": ["stream_bus", "database_gateway"]
                }

            if HAS_NEWS_STREAM_PROCESSOR and HAS_UNIFIED_STREAM_BUS and HAS_DATABASE_GATEWAY:
                services_config["news_stream_processor"] = {
                    "class": NewsStreamProcessor,
                    "config": {
                        "database_gateway": database_gateway,
                        "enable_ai_analysis": True,
                        "enable_local_triage": True,
                        "triage_mode": "hybrid",
                        "triage_block_on_skip": False,
                        "triage_pass_threshold": 0.06,
                        "triage_skip_threshold": -0.02,
                        "local_qwen_model_path": "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf",
                        "batch_processing": True,
                        "batch_size": 5
                    },
                    "dependencies": ["event_bus"]
                }

            only_services_raw = os.getenv("STREAM_SERVICES_ONLY", "").strip()
            if only_services_raw:
                only_services = {
                    item.strip()
                    for item in only_services_raw.replace("，", ",").split(",")
                    if item.strip()
                }
                services_config = {
                    name: config
                    for name, config in services_config.items()
                    if name in only_services
                }
                logger.info("STREAM_SERVICES_ONLY 生效，仅启动服务: %s", sorted(services_config.keys()))

            # 创建服务实例
            dependencies = {
                "stream_manager": stream_manager
            }

            # 添加现有处理器的依赖
            if crawler_client:
                dependencies["crawler_service_client"] = crawler_client

            if HAS_UNIFIED_STREAM_BUS and unified_stream_bus:
                dependencies["stream_bus"] = unified_stream_bus
                dependencies["event_bus"] = unified_stream_bus  # 使用相同的bus作为event_bus

            if HAS_DATABASE_GATEWAY and database_gateway:
                dependencies["database_gateway"] = database_gateway

            for service_name, service_config in services_config.items():
                try:
                    service_class = service_config["class"]
                    config = service_config["config"]

                    # 构建依赖参数（支持 pass_config=False 跳过 config 注入）
                    pass_config = service_config.get("pass_config", True)
                    kwargs = {"config": config} if pass_config else {}
                    for dep in service_config.get("dependencies", []):
                        if dep in dependencies:
                            kwargs[dep] = dependencies[dep]
                        elif dep == "stream_manager":
                            kwargs["stream_manager"] = stream_manager

                    # 支持 param_map：将依赖对象映射到构造函数参数名
                    param_map = service_config.get("param_map", {})
                    for param_name, dep_path in param_map.items():
                        parts = dep_path.split(".")
                        obj = dependencies.get(parts[0])
                        if obj is not None:
                            for attr in parts[1:]:
                                obj = getattr(obj, attr, None)
                                if obj is None:
                                    break
                        if obj is not None:
                            kwargs[param_name] = obj

                    # 创建服务实例
                    service_instance = service_class(**kwargs)
                    self.services.append({
                        "name": service_name,
                        "instance": service_instance,
                        "config": config
                    })

                    logger.info(f"服务 '{service_name}' 初始化成功")

                except Exception as e:
                    logger.error(f"服务 '{service_name}' 初始化失败: {e}")
                    raise

            logger.info(f"共初始化 {len(self.services)} 个服务")
            self.is_running = True

        except ImportError as e:
            logger.error(f"导入服务类失败: {e}")
            raise
        except Exception as e:
            logger.error(f"服务管理器初始化失败: {e}")
            raise

    async def start_all(self):
        """启动所有服务"""
        if not self.services:
            await self.initialize()

        logger.info("正在启动所有Stream服务...")

        for service_info in self.services:
            try:
                service_instance = service_info["instance"]
                service_name = service_info["name"]

                # 调用服务的启动方法
                if hasattr(service_instance, 'start'):
                    await service_instance.start()
                    logger.info(f"服务 '{service_name}' 已启动")
                elif hasattr(service_instance, 'start_collection_loop'):
                    await service_instance.start_collection_loop()
                    logger.info(f"服务 '{service_name}' 已启动")
                elif hasattr(service_instance, 'start_matching_loop'):
                    await service_instance.start_matching_loop()
                    logger.info(f"服务 '{service_name}' 已启动")
                elif hasattr(service_instance, 'start_storage_service'):
                    await service_instance.start_storage_service()
                    logger.info(f"服务 '{service_name}' 已启动")
                elif hasattr(service_instance, 'start_business_processing'):
                    await service_instance.start_business_processing()
                    logger.info(f"服务 '{service_name}' 已启动")
                else:
                    logger.warning(f"服务 '{service_name}' 没有启动方法")

            except Exception as e:
                logger.error(f"启动服务 '{service_info['name']}' 失败: {e}")

        # 启动后台清理任务
        if self.stream_cleanup_scheduler:
            try:
                await self.stream_cleanup_scheduler.start()
            except Exception as e:
                logger.warning(f"启动Stream清理调度器失败: {e}")

        if self.stream_manager and self.consumer_group_cleanup_task is None:
            self.consumer_group_cleanup_task = asyncio.create_task(self._consumer_group_cleanup_loop())
            logger.info("消费者组周期清理任务已启动")

        if self.stream_manager and self.pending_reclaim_enabled and self.pending_reclaim_task is None:
            self.pending_reclaim_task = asyncio.create_task(self._pending_reclaim_loop())
            logger.info("pending回收任务已启动")

        logger.info("所有Stream服务启动完成")

    async def stop_all(self):
        """停止所有服务"""
        logger.info("正在停止所有Stream服务...")

        # 先停止后台任务，避免和服务停止并发冲突
        if self.pending_reclaim_task:
            self.pending_reclaim_task.cancel()
            try:
                await self.pending_reclaim_task
            except asyncio.CancelledError:
                pass
            self.pending_reclaim_task = None

        if self.consumer_group_cleanup_task:
            self.consumer_group_cleanup_task.cancel()
            try:
                await self.consumer_group_cleanup_task
            except asyncio.CancelledError:
                pass
            self.consumer_group_cleanup_task = None

        if self.stream_cleanup_scheduler:
            try:
                await self.stream_cleanup_scheduler.stop()
            except Exception as e:
                logger.warning(f"停止Stream清理调度器失败: {e}")

        for service_info in reversed(self.services):
            try:
                service_instance = service_info["instance"]
                service_name = service_info["name"]

                # 调用服务的停止方法
                if hasattr(service_instance, 'stop'):
                    await service_instance.stop()
                elif hasattr(service_instance, 'stop_collection_loop'):
                    await service_instance.stop_collection_loop()
                elif hasattr(service_instance, 'stop_matching_loop'):
                    await service_instance.stop_matching_loop()
                elif hasattr(service_instance, 'stop_storage_service'):
                    await service_instance.stop_storage_service()
                elif hasattr(service_instance, 'stop_business_processing'):
                    await service_instance.stop_business_processing()

                logger.info(f"服务 '{service_name}' 已停止")
            except Exception as e:
                logger.error(f"停止服务 '{service_info['name']}' 失败: {e}")

        self.is_running = False

        # 最后关闭Stream管理器连接
        if self.stream_manager:
            try:
                await self.stream_manager.close()
            except Exception as e:
                logger.warning(f"关闭Stream管理器失败: {e}")

        logger.info("所有Stream服务已停止")

    async def _consumer_group_cleanup_loop(self):
        """周期清理消费者组，避免测试/短生命周期组长期堆积。"""
        logger.info(
            "消费者组清理循环启动: interval=%ss, pattern=%s, max_age_hours=%s",
            self.consumer_group_cleanup_interval_seconds,
            self.consumer_group_cleanup_pattern or "*",
            self.consumer_group_cleanup_max_age_hours,
        )
        while self.is_running and self.stream_manager:
            try:
                await asyncio.sleep(self.consumer_group_cleanup_interval_seconds)
                result = await self.stream_manager.cleanup_consumer_groups(
                    pattern=self.consumer_group_cleanup_pattern,
                    max_age_hours=self.consumer_group_cleanup_max_age_hours,
                )
                if result.get("success", False):
                    logger.info(
                        "消费者组周期清理完成: cleaned=%s, skipped=%s, failed=%s",
                        result.get("cleaned_groups", 0),
                        result.get("skipped_groups", 0),
                        result.get("failed_groups", 0),
                    )
                else:
                    logger.warning(f"消费者组周期清理失败: {result}")
            except asyncio.CancelledError:
                logger.info("消费者组清理循环已取消")
                break
            except Exception as e:
                logger.warning(f"消费者组清理循环异常: {e}")

    async def _pending_reclaim_loop(self):
        """周期执行 stale pending 回收，避免僵尸消息长期滞留。"""
        logger.info(
            "pending回收循环启动: interval=%ss, pattern=%s, min_idle_ms=%s",
            self.pending_reclaim_interval_seconds,
            self.pending_reclaim_stream_pattern,
            self.pending_reclaim_min_idle_ms,
        )
        while self.is_running and self.stream_manager:
            try:
                await asyncio.sleep(self.pending_reclaim_interval_seconds)
                result = await self.stream_manager.reclaim_stale_pending(
                    stream_pattern=self.pending_reclaim_stream_pattern,
                    min_idle_ms=self.pending_reclaim_min_idle_ms,
                    count=self.pending_reclaim_count,
                    max_messages_per_group=self.pending_reclaim_max_per_group,
                    maintenance_consumer="pending_reclaimer",
                    requeue=True,
                )
                if result.get("success", False):
                    claimed = result.get("claimed_messages", 0)
                    requeued = result.get("requeued_messages", 0)
                    acked = result.get("acked_messages", 0)
                    if claimed > 0 or requeued > 0 or acked > 0:
                        logger.info(
                            "pending回收完成: claimed=%s, requeued=%s, acked=%s, errors=%s",
                            claimed,
                            requeued,
                            acked,
                            len(result.get("errors", [])),
                        )
                else:
                    logger.warning(f"pending回收失败: {result}")
            except asyncio.CancelledError:
                logger.info("pending回收循环已取消")
                break
            except Exception as e:
                logger.warning(f"pending回收循环异常: {e}")

    async def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        status = {
            "is_running": self.is_running,
            "services": [],
            "timestamp": time.time()
        }

        for service_info in self.services:
            service_status = {
                "name": service_info["name"],
                "config": service_info["config"]
            }

            # 获取服务特定状态
            service_instance = service_info["instance"]
            if hasattr(service_instance, 'get_stats'):
                try:
                    service_status["stats"] = await service_instance.get_stats()
                except:
                    service_status["stats"] = {"error": "无法获取状态"}
            elif hasattr(service_instance, 'get_matching_stats'):
                try:
                    service_status["stats"] = await service_instance.get_matching_stats()
                except:
                    service_status["stats"] = {"error": "无法获取状态"}
            elif hasattr(service_instance, 'get_collection_stats'):
                try:
                    service_status["stats"] = await service_instance.get_collection_stats()
                except:
                    service_status["stats"] = {"error": "无法获取状态"}

            status["services"].append(service_status)

        return status


async def main():
    """主函数"""
    manager = StreamServicesManager()
    shutdown_reason = "unknown"
    logger.info("Stream服务主进程启动: pid=%s", os.getpid())

    # 设置信号处理
    stop_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}, 正在停止服务...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 启动服务
        await manager.start_all()

        # 保持运行
        logger.info("Stream服务正在运行，按Ctrl+C停止...")

        # 定期报告状态
        while manager.is_running:
            try:
                # 等待停止事件或超时
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=60)
                    # 如果停止事件被触发，跳出循环
                    logger.info("停止事件触发，正在停止服务...")
                    shutdown_reason = "stop_event_signal"
                    break
                except asyncio.TimeoutError:
                    # 超时，检查服务状态
                    pass

                # 报告状态
                status = await manager.get_service_status()
                logger.info(f"服务状态: {len(status['services'])} 个服务运行中")
            except Exception as e:
                logger.error(f"获取服务状态失败: {e}")

    except KeyboardInterrupt:
        shutdown_reason = "keyboard_interrupt"
        logger.info("收到键盘中断，正在停止服务...")
    except Exception as e:
        shutdown_reason = f"runtime_exception:{type(e).__name__}"
        logger.error(f"服务运行出错: {e}")
        logger.error("主循环异常堆栈:\n%s", traceback.format_exc())
    finally:
        if manager.is_running:
            await manager.stop_all()
        logger.info(
            "Stream服务主进程退出: pid=%s, reason=%s, is_running=%s, services=%s",
            os.getpid(),
            shutdown_reason,
            manager.is_running,
            len(manager.services),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except BaseException as e:
        logger.critical(
            "start_services 进程异常退出: %s: %s\n%s",
            type(e).__name__,
            e,
            traceback.format_exc(),
        )
        raise
