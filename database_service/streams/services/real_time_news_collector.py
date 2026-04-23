"""
实时新闻采集服务 (RealTimeNewsCollector)

基于全链路打通方案，定期调用news_crawler_service，将新闻发布到Redis Stream `stream:news:raw`。
实现新闻采集→Stream断点的打通。

功能：
- 配置化采集频率（默认：每5分钟）
- 仅支持真实新闻采集
- 异常处理和重试机制
- 采集统计和监控
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import time

logger = logging.getLogger(__name__)

try:
    from database_service.streams.services.local_qwen_triage_service import LocalQwenNewsTriageService
    HAS_LOCAL_QWEN_TRIAGE = True
except Exception:
    LocalQwenNewsTriageService = None  # type: ignore
    HAS_LOCAL_QWEN_TRIAGE = False


class CollectionMode(Enum):
    """采集模式枚举"""
    REAL = "real"      # 真实新闻采集
    AUTO = "auto"      # 自动选择（仅真实，不再降级到模拟）


class RealTimeNewsCollector:
    """实时新闻采集服务"""

    def __init__(
        self,
        stream_manager,
        crawler_service_client=None,
        news_producer=None,
        config: Optional[Dict] = None
    ):
        """
        初始化实时新闻采集服务

        Args:
            stream_manager: Redis Stream管理器
            crawler_service_client: 爬虫服务客户端（可选）
            news_producer: 新闻生产者（可选）
            config: 配置字典
        """
        self.stream_manager = stream_manager
        self.crawler_client = crawler_service_client
        self.news_producer = news_producer
        self.config = config or {}

        # 配置参数
        self.collection_interval = self.config.get("collection_interval", 300)  # 默认5分钟（秒）
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 10)  # 重试延迟（秒）
        default_mode_value = str(self.config.get("default_mode", "auto")).lower()
        if default_mode_value == "mock":
            logger.warning("检测到 default_mode=mock，核心链路已禁用mock，自动改为auto")
            default_mode_value = "auto"
        self.default_mode = CollectionMode(default_mode_value)
        self.enable_collector_prefilter = bool(self.config.get("enable_collector_prefilter", True))
        self.collector_drop_on_skip = bool(self.config.get("collector_drop_on_skip", True))
        self.collector_prefilter_use_prompt = bool(self.config.get("collector_prefilter_use_prompt", False))
        self.dedup_window_seconds = int(self.config.get("collector_dedup_window_seconds", 1800))
        self._recent_news_ids: Dict[str, float] = {}

        self.local_triage_service = None
        if self.enable_collector_prefilter and HAS_LOCAL_QWEN_TRIAGE:
            triage_cfg = {
                # collector 侧默认走轻量规则预筛，避免重复/高成本调用
                "enable_local_triage": self.collector_prefilter_use_prompt,
                "triage_mode": "prompt",
                "local_qwen_model_path": self.config.get("local_qwen_model_path", ""),
                "triage_pass_threshold": self.config.get("triage_pass_threshold", 0.06),
                "triage_skip_threshold": self.config.get("triage_skip_threshold", -0.02),
            }
            self.local_triage_service = LocalQwenNewsTriageService(triage_cfg)
            logger.info(
                "新闻采集前预筛选已启用: mode=%s, drop_on_skip=%s",
                "prompt" if self.collector_prefilter_use_prompt else "rule",
                self.collector_drop_on_skip,
            )
        elif self.enable_collector_prefilter:
            logger.warning("新闻采集前预筛选启用失败: LocalQwenNewsTriageService 不可用")

        # 运行状态
        self.is_running = False
        self.collection_task: Optional[asyncio.Task] = None
        self.stats = {
            "started_at": None,
            "total_collections": 0,
            "successful_collections": 0,
            "failed_collections": 0,
            "last_collection_time": None,
            "last_collection_result": None,
            "mode_history": [],
            "news_published": 0,
            "news_prefilter_skipped": 0,
            "news_dedup_skipped": 0,
            "errors": []
        }

        logger.info(f"RealTimeNewsCollector 初始化完成")
        logger.info(f"  采集间隔: {self.collection_interval}秒")
        logger.info(f"  默认模式: {self.default_mode.value}")
        logger.info(f"  最大重试: {self.max_retries}")

    async def start_collection_loop(self) -> None:
        """
        启动采集循环

        启动后，服务将按照配置的间隔定期采集新闻并发布到Stream。
        """
        if self.is_running:
            logger.warning("采集循环已经在运行中")
            return

        self.is_running = True
        self.stats["started_at"] = datetime.now().isoformat()

        # 启动采集任务
        self.collection_task = asyncio.create_task(self._collection_loop())

        logger.info(f"新闻采集循环已启动，间隔: {self.collection_interval}秒")

    async def stop_collection_loop(self) -> None:
        """停止采集循环"""
        if not self.is_running:
            logger.warning("采集循环未在运行")
            return

        self.is_running = False

        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                logger.info("采集循环已取消")

        logger.info("新闻采集循环已停止")

    async def _collection_loop(self):
        """采集循环主逻辑"""
        while self.is_running:
            try:
                # 执行单次采集
                result = await self.collect_and_publish()

                # 更新统计
                self.stats["total_collections"] += 1
                if result.get("success"):
                    self.stats["successful_collections"] += 1
                    self.stats["news_published"] += result.get("news_published", 0)
                else:
                    self.stats["failed_collections"] += 1

                self.stats["last_collection_time"] = datetime.now().isoformat()
                self.stats["last_collection_result"] = result

                logger.info(f"新闻采集完成: 成功={result.get('success')}, "
                          f"发布新闻={result.get('news_published', 0)}条, "
                          f"模式={result.get('mode')}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"采集循环发生错误: {e}")
                self.stats["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": str(e)
                })

            # 等待下一次采集
            try:
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break

    async def collect_and_publish(self, mode: str = "auto") -> Dict:
        """
        执行单次新闻采集并发布到Stream

        Args:
            mode: 采集模式 ("real", "auto")

        Returns:
            采集结果字典
        """
        start_time = time.time()
        result = {
            "success": False,
            "mode": mode,
            "news_collected": 0,
            "news_published": 0,
            "error": None,
            "duration": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            # 确定实际采集模式
            actual_mode = self._determine_collection_mode(mode)
            result["mode"] = actual_mode.value
            self.stats["mode_history"].append({
                "time": datetime.now().isoformat(),
                "mode": actual_mode.value
            })

            # 采集新闻
            news_items = await self._collect_news(actual_mode)
            result["news_collected"] = len(news_items)

            if not news_items:
                logger.info(f"采集模式 {actual_mode.value}: 未采集到新闻")
                result["success"] = True  # 无新闻也是成功
                result["duration"] = time.time() - start_time
                return result

            # 采集前预筛选：命中SKIP直接丢弃，不进入stream:news:raw
            news_items, prefilter_skipped = self._prefilter_news(news_items)
            result["news_prefilter_skipped"] = prefilter_skipped
            result["news_after_prefilter"] = len(news_items)
            self.stats["news_prefilter_skipped"] += prefilter_skipped

            # 采集侧短窗口去重：避免同一news_id在短时间内重复下游处理
            news_items, dedup_skipped = self._dedup_news_items(news_items)
            result["news_dedup_skipped"] = dedup_skipped
            result["news_after_dedup"] = len(news_items)
            self.stats["news_dedup_skipped"] += dedup_skipped

            if not news_items:
                logger.info("采集预处理后无可发布新闻（预筛选/去重后全部丢弃）")
                result["success"] = True
                result["duration"] = time.time() - start_time
                return result

            # 发布新闻到Stream
            published_count = await self._publish_news_to_stream(news_items)
            result["news_published"] = published_count
            result["success"] = published_count > 0

            logger.info(f"采集模式 {actual_mode.value}: 采集{len(news_items)}条新闻, "
                        f"发布{published_count}条到stream:news:raw")

        except Exception as e:
            logger.error(f"新闻采集发布失败: {e}")
            result["error"] = str(e)
            result["success"] = False

        result["duration"] = time.time() - start_time
        return result

    def _dedup_news_items(self, news_items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
        """基于news_id做短窗口去重，减少重复事件噪音。"""
        if not news_items:
            return news_items, 0

        now_ts = time.time()
        # 清理过期键
        expired = [
            news_id for news_id, ts in self._recent_news_ids.items()
            if now_ts - ts > self.dedup_window_seconds
        ]
        for news_id in expired:
            self._recent_news_ids.pop(news_id, None)

        filtered: List[Dict[str, Any]] = []
        skipped = 0
        for item in news_items:
            news_id = str(item.get("news_id") or "").strip()
            if not news_id:
                filtered.append(item)
                continue

            if news_id in self._recent_news_ids:
                skipped += 1
                logger.info("🚫 采集侧去重跳过重复新闻: %s", news_id)
                continue

            self._recent_news_ids[news_id] = now_ts
            filtered.append(item)

        return filtered, skipped

    def _determine_collection_mode(self, requested_mode: str) -> CollectionMode:
        """
        确定实际采集模式

        Args:
            requested_mode: 请求的模式 ("real", "auto")

        Returns:
            实际的采集模式
        """
        if requested_mode == "auto":
            # 自动模式：仅真实链路；真实不可用时返回REAL并在采集阶段返回空数据
            if self._is_real_mode_available():
                return CollectionMode.REAL
            else:
                logger.warning("auto模式下真实采集不可用，本轮将不产出新闻（已禁用mock降级）")
                return CollectionMode.REAL
        else:
            try:
                return CollectionMode(requested_mode)
            except ValueError:
                logger.warning(f"无效的采集模式: {requested_mode}，使用默认模式")
                return self.default_mode

    def _is_real_mode_available(self) -> bool:
        """检查真实采集模式是否可用"""
        # 检查爬虫服务客户端是否可用
        if not self.crawler_client:
            logger.debug("真实模式不可用: 缺少爬虫服务客户端")
            return False

        # 可以添加更多检查，如网络连接等
        return True

    async def _collect_news(self, mode: CollectionMode) -> List[Dict]:
        """
        根据指定模式采集新闻

        Args:
            mode: 采集模式

        Returns:
            新闻列表
        """
        if mode == CollectionMode.REAL:
            return await self._collect_real_news()
        else:
            raise ValueError(f"不支持的采集模式: {mode}")

    async def _collect_real_news(self) -> List[Dict]:
        """采集真实新闻"""
        try:
            # 尝试导入并调用news_crawler_service
            try:
                from news_crawler_service.services.news_crawler_service import get_news_crawler_service
                crawler_service = get_news_crawler_service()

                # 使用智能抓取模式
                result = await crawler_service.crawl_news_auto(count=10, prefer_real=True)

                if result.get("status") == "success":
                    news_items = result.get("response", {}).get("news_list", [])

                    # 转换新闻格式为标准化格式
                    standardized_news = []
                    for news in news_items:
                        standardized_news.append({
                            "news_id": news.get("news_id", f"news_{datetime.now().timestamp()}"),
                            "title": news.get("title", ""),
                            "content": news.get("content", news.get("title", "")),  # 如果没有content，使用title
                            "source": news.get("source", "unknown"),
                            "publish_date": news.get("publish_date", datetime.now().strftime("%Y-%m-%d")),
                            "publish_time": news.get("publish_time", datetime.now().strftime("%H:%M:%S")),
                            "url": news.get("url", ""),
                            "keywords": news.get("keywords", []),
                            "collected_at": datetime.now().isoformat()
                        })

                    logger.info(f"通过news_crawler_service采集到 {len(standardized_news)} 条真实新闻")
                    return standardized_news
                else:
                    logger.warning(f"news_crawler_service采集失败: {result.get('error', 'unknown error')}")
                    return []

            except ImportError as e:
                logger.warning(f"无法导入news_crawler_service: {e}")
                # 降级到使用外部客户端（如果提供）
                if self.crawler_client:
                    # 调用爬虫服务客户端获取新闻
                    # 这里需要根据实际的爬虫服务API进行调整
                    news_items = await self.crawler_client.fetch_news(
                        sources=["stock_news_em"],  # 示例：东方财富股票新闻
                        limit=50,
                        hours=1  # 最近1小时的新闻
                    )

                    # 转换新闻格式为标准化格式
                    standardized_news = []
                    for news in news_items:
                        standardized_news.append({
                            "news_id": news.get("id", f"news_{datetime.now().timestamp()}"),
                            "title": news.get("title", ""),
                            "content": news.get("content", ""),
                            "source": news.get("source", "unknown"),
                            "publish_date": news.get("publish_date", datetime.now().strftime("%Y-%m-%d")),
                            "publish_time": news.get("publish_time", datetime.now().strftime("%H:%M:%S")),
                            "url": news.get("url", ""),
                            "keywords": news.get("keywords", []),
                            "collected_at": datetime.now().isoformat()
                        })

                    return standardized_news
                else:
                    logger.warning("无法采集真实新闻: 缺少爬虫服务客户端")
                    return []

        except Exception as e:
            logger.error(f"真实新闻采集失败: {e}")
            return []

    async def _publish_news_to_stream(self, news_items: List[Dict]) -> int:
        """
        发布新闻到Redis Stream

        Args:
            news_items: 新闻列表

        Returns:
            成功发布的新闻数量
        """
        if not news_items:
            return 0

        published_count = 0

        try:
            # 使用新闻生产者（如果提供）
            if self.news_producer:
                message_ids = await self.news_producer.publish_batch(news_items, "raw")
                published_count = sum(1 for mid in message_ids if mid is not None)
            else:
                # 直接使用stream_manager发布
                for news in news_items:
                    try:
                        message_data = {
                            "news_id": news.get("news_id"),
                            "title": news.get("title"),
                            "content": news.get("content"),
                            "source": news.get("source"),
                            "publish_date": news.get("publish_date"),
                            "publish_time": news.get("publish_time"),
                            "collected_at": news.get("collected_at"),
                            "type": "raw_news"
                        }

                        # 发布到stream:news:raw
                        message_id = await self.stream_manager.publish("stream:news:raw", message_data)
                        if message_id:
                            published_count += 1
                            logger.debug(f"新闻发布成功: {news.get('news_id')} -> {message_id}")
                    except Exception as e:
                        logger.error(f"发布单条新闻失败 {news.get('news_id')}: {e}")

        except Exception as e:
            logger.error(f"批量发布新闻失败: {e}")

        return published_count

    def _prefilter_news(self, news_items: List[Dict]) -> (List[Dict], int):
        """在采集侧对新闻做预筛选，命中SKIP时可直接丢弃。"""
        if not self.enable_collector_prefilter or not self.local_triage_service:
            return news_items, 0

        kept: List[Dict] = []
        skipped = 0

        for news in news_items:
            try:
                triage_result = self.local_triage_service.evaluate(news)
                decision = str(triage_result.get("decision") or "PASS").upper()
                news_id = news.get("news_id", "unknown")

                if decision == "SKIP" and self.collector_drop_on_skip:
                    skipped += 1
                    logger.info(
                        "🚫 采集前预筛选丢弃小事件: %s, reason=%s",
                        news_id,
                        triage_result.get("reason"),
                    )
                    continue
            except Exception as e:
                logger.warning(f"采集前预筛选异常，保留该新闻继续流转: {e}")

            kept.append(news)

        return kept, skipped

    async def get_collection_stats(self) -> Dict:
        """获取采集统计信息"""
        stats = self.stats.copy()

        # 计算成功率
        total = stats["total_collections"]
        successful = stats["successful_collections"]
        if total > 0:
            stats["success_rate"] = successful / total * 100
        else:
            stats["success_rate"] = 0

        # 添加运行状态
        stats["is_running"] = self.is_running
        stats["collection_interval"] = self.collection_interval

        # 最近错误（仅保留最近10条）
        if stats["errors"]:
            stats["recent_errors"] = stats["errors"][-10:]
        else:
            stats["recent_errors"] = []

        return stats

    def get_config(self) -> Dict:
        """获取当前配置"""
        return {
            "collection_interval": self.collection_interval,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "default_mode": self.default_mode.value,
            "is_real_mode_available": self._is_real_mode_available()
        }
