"""
事件-题材匹配服务 (EventThemeMatcher)

基于全链路打通方案，监听Redis Stream `stream:events:structured`，
调用主题服务进行事件-题材匹配，将匹配结果发布到Redis Stream `stream:event:feed`。
实现事件结构化→事件-题材匹配断点的打通。

功能：
- 监听结构化事件Stream
- 调用主题服务API进行事件-题材匹配
- 生成事件-主题关联关系
- 发布匹配结果到feed Stream
- 异常处理和重试机制
- 匹配统计和监控
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class EventThemeMatcher:
    """事件-题材匹配服务"""

    def __init__(
        self,
        stream_manager,
        theme_service_client=None,
        event_producer=None,
        config: Optional[Dict] = None
    ):
        """
        初始化事件-题材匹配服务

        Args:
            stream_manager: Redis Stream管理器
            theme_service_client: 主题服务客户端（可选）
            event_producer: 事件生产者（可选）
            config: 配置字典
        """
        self.stream_manager = stream_manager
        self.theme_client = theme_service_client
        self.event_producer = event_producer
        self.config = config or {}

        # 配置参数
        self.polling_interval = self.config.get("polling_interval", 1)  # 默认1秒轮询
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 5)  # 重试延迟（秒）
        self.batch_size = self.config.get("batch_size", 10)  # 批量处理大小
        self.consumer_group = self.config.get("consumer_group", "event_matchers")
        self.consumer_name = self.config.get("consumer_name", f"matcher_{int(time.time())}")

        # Stream名称配置
        self.input_stream = self.config.get("input_stream", "stream:events:structured")
        self.output_stream = self.config.get("output_stream", "stream:event:feed")
        self.output_stream_max_len = int(self.config.get("output_stream_max_len", 5000))
        self.dead_letter_stream = self.config.get("dead_letter_stream", "stream:dead:letter")
        self.theme_service_base_url = self.config.get("theme_service_base_url", "http://localhost:8002")
        self.event_type_filter_mode = str(
            self.config.get("event_type_filter_mode", "whitelist")
        ).strip().lower()
        self.allowed_event_types = {
            str(x).strip() for x in self.config.get(
                "allowed_event_types",
                ["产品发布", "技术突破", "订单合作", "并购重组", "政策利好", "产能扩张"],
            ) if str(x).strip()
        }
        self.low_value_event_types = {
            str(x).strip() for x in self.config.get(
                "low_value_event_types",
                ["其他", "制裁"],
            ) if str(x).strip()
        }
        self._theme_service_client = None
        self._theme_service_disabled_until = 0.0
        self._theme_service_log_at = 0.0
        self._theme_service_failure_streak = 0
        self._theme_service_base_cooldown_seconds = int(
            self.config.get("theme_service_cooldown_seconds", 30)
        )
        self._theme_service_max_cooldown_seconds = int(
            self.config.get("theme_service_max_cooldown_seconds", 300)
        )
        parsed = urlparse(self.theme_service_base_url)
        self._theme_service_host = parsed.hostname or "localhost"
        self._theme_service_port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # 运行状态
        self.is_running = False
        self.matching_task: Optional[asyncio.Task] = None
        self.stats = {
            "started_at": None,
            "total_messages_processed": 0,
            "successful_matches": 0,
            "failed_matches": 0,
            "skipped_low_value": 0,
            "events_published": 0,
            "last_processing_time": None,
            "errors": [],
            "match_decisions": {
                "MATCH": 0,
                "NO_MATCH": 0,
                "REVIEW_REQUIRED": 0
            }
        }

        logger.info(f"EventThemeMatcher 初始化完成")
        logger.info(f"  输入Stream: {self.input_stream}")
        logger.info(f"  输出Stream: {self.output_stream}")
        logger.info(f"  消费者组: {self.consumer_group}")
        logger.info(f"  批量大小: {self.batch_size}")

    async def start_matching_loop(self) -> None:
        """
        启动匹配循环

        启动后，服务将持续监听输入Stream，处理事件并进行主题匹配。
        """
        if self.is_running:
            logger.warning("匹配循环已经在运行中")
            return

        self.is_running = True
        self.stats["started_at"] = datetime.now().isoformat()

        # 确保消费者组存在
        await self._ensure_consumer_group()

        # 启动匹配任务
        self.matching_task = asyncio.create_task(self._matching_loop())

        logger.info(f"事件-题材匹配循环已启动，轮询间隔: {self.polling_interval}秒")

    async def stop_matching_loop(self) -> None:
        """停止匹配循环"""
        if not self.is_running:
            logger.warning("匹配循环未在运行")
            return

        self.is_running = False

        if self.matching_task:
            self.matching_task.cancel()
            try:
                await self.matching_task
            except asyncio.CancelledError:
                logger.info("匹配循环已取消")

        if self._theme_service_client is not None:
            try:
                await self._theme_service_client.close()
            except Exception:
                pass
            self._theme_service_client = None

        # 清理 Redis consumer
        try:
            stream = self.config.get("stream_name", "stream:events:normal")
            if self.stream_manager:
                redis_client = getattr(self.stream_manager, 'redis_client', None)
                if redis_client:
                    await redis_client.xgroup_delconsumer(stream, self.consumer_group, self.consumer_name)
        except Exception:
            pass

        logger.info("事件-题材匹配循环已停止")

    async def _ensure_consumer_group(self) -> None:
        """确保消费者组存在"""
        try:
            await self.stream_manager.create_consumer_group(
                self.input_stream,
                self.consumer_group
            )
            logger.info(f"消费者组 '{self.consumer_group}' 已创建或已存在")
        except Exception as e:
            # 消费者组可能已存在
            logger.debug(f"消费者组创建/检查: {e}")

    async def _matching_loop(self):
        """匹配循环主逻辑"""
        while self.is_running:
            try:
                # 从Stream读取消息
                messages = await self.stream_manager.read_group(
                    stream=self.input_stream,
                    group=self.consumer_group,
                    consumer=self.consumer_name,
                    count=self.batch_size,
                    block_ms=int(self.polling_interval * 1000)
                )

                if messages:
                    # 处理消息批次
                    await self._process_message_batch(messages)

            except asyncio.CancelledError:
                break
            except Exception as e:
                err_text = str(e)
                # Redis在stream被清理/重建后可能抛NOGROUP，自动重建消费者组并继续。
                if "NOGROUP" in err_text:
                    logger.warning("检测到NOGROUP，正在重建事件匹配消费者组后继续运行")
                    try:
                        await self._ensure_consumer_group()
                    except Exception as recreate_err:
                        logger.error(f"NOGROUP后重建消费者组失败: {recreate_err}")
                        await asyncio.sleep(self.retry_delay)
                    continue

                logger.error(f"匹配循环发生错误: {e}")
                self.stats["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": str(e)
                })

                # 短暂等待后继续
                await asyncio.sleep(self.retry_delay)

    async def _process_message_batch(self, messages: List[Dict]) -> None:
        """
        处理消息批次

        Args:
            messages: Stream消息列表
        """
        for message in messages:
            message_id = message.get("id")
            message_data = message.get("data", {})

            try:
                # 处理单条消息
                success = await self._process_single_message(message_id, message_data)

                if success:
                    # 确认消息
                    await self.stream_manager.ack(
                        self.input_stream,
                        self.consumer_group,
                        message_id
                    )
                    self.stats["total_messages_processed"] += 1
                else:
                    # 处理失败，移动到死信队列
                    await self._move_to_dead_letter(message_id, message_data, "匹配失败")
                    self.stats["failed_matches"] += 1

            except Exception as e:
                logger.error(f"处理消息 {message_id} 失败: {e}")
                await self._move_to_dead_letter(message_id, message_data, str(e))
                self.stats["failed_matches"] += 1

    async def _process_single_message(self, message_id: str, message_data: Dict) -> bool:
        """
        处理单条消息

        Args:
            message_id: 消息ID
            message_data: 消息数据

        Returns:
            处理是否成功
        """
        try:
            # 提取事件数据
            logger.debug(f"消息 {message_id}: 原始消息数据: {message_data}")
            event_data = self._extract_event_data(message_data)
            if not event_data:
                logger.warning(f"消息 {message_id}: 无法提取事件数据")
                return False
            logger.debug(f"消息 {message_id}: 提取的事件数据: {event_data}")

            # 执行事件-题材匹配
            if self._should_skip_low_value_event(event_data):
                self.stats["skipped_low_value"] += 1
                logger.info(
                    "消息 %s: 跳过低价值事件匹配, event_type=%s, summary=%s",
                    message_id,
                    event_data.get("event_type", "unknown"),
                    str(event_data.get("summary", ""))[:80],
                )
                return True

            logger.debug(f"消息 {message_id}: 开始匹配...")
            match_result = await self.match_event_to_themes(event_data)
            logger.debug(f"消息 {message_id}: 匹配结果: {match_result}")

            # 更新统计
            decision = match_result.get("decision", "UNKNOWN")
            if decision in self.stats["match_decisions"]:
                self.stats["match_decisions"][decision] += 1

            # 生成feed事件项
            feed_item = self._create_feed_item(event_data, match_result)
            if not feed_item:
                logger.warning(f"消息 {message_id}: 无法生成feed项")
                return False
            logger.debug(f"消息 {message_id}: 生成的feed项: {feed_item}")

            # 发布到feed Stream
            published_id = await self.publish_matched_event(feed_item)
            if published_id:
                self.stats["successful_matches"] += 1
                self.stats["events_published"] += 1
                logger.debug(f"消息 {message_id}: 匹配成功，发布到feed -> {published_id}")
                return True
            else:
                logger.warning(f"消息 {message_id}: 发布到feed失败")
                return False

        except Exception as e:
            logger.error(f"处理消息 {message_id} 时发生错误: {e}")
            return False

    def _extract_event_data(self, message_data: Dict) -> Optional[Dict]:
        """
        从Stream消息中提取事件数据

        Args:
            message_data: Stream消息数据

        Returns:
            事件数据字典，None表示提取失败
        """
        # 支持多种消息格式
        if isinstance(message_data, dict):
            # 直接是事件数据
            if "event_id" in message_data:
                return message_data

            # 嵌套在payload/data中
            for key in ["payload", "data", "event_data"]:
                if key in message_data:
                    value = message_data[key]
                    if isinstance(value, dict):
                        return value
                    elif isinstance(value, str):
                        # 尝试解析JSON字符串
                        try:
                            parsed = json.loads(value)
                            # 递归提取
                            return self._extract_event_data(parsed)
                        except json.JSONDecodeError:
                            pass  # 不是JSON字符串，继续

        # 尝试解析JSON字符串
        if isinstance(message_data, str):
            try:
                data = json.loads(message_data)
                return self._extract_event_data(data)
            except json.JSONDecodeError:
                pass

        return None

    def _should_skip_low_value_event(self, event_data: Dict[str, Any]) -> bool:
        """事件类型过滤：默认白名单放行，避免泛化噪声污染题材主链路。"""
        event_type = str(event_data.get("event_type") or "").strip()
        if not event_type:
            return True

        # 默认策略：白名单放行
        if self.event_type_filter_mode == "whitelist":
            return event_type not in self.allowed_event_types

        # 兼容策略：黑名单拦截
        if event_type in self.low_value_event_types:
            return True
        return False

    async def match_event_to_themes(self, event_data: Dict) -> Dict:
        """
        执行事件-题材匹配

        Args:
            event_data: 事件数据

        Returns:
            匹配结果字典
        """
        # 如果有主题服务客户端，使用客户端
        if self.theme_client:
            try:
                return await self.theme_client.match_event(event_data)
            except Exception as e:
                logger.error(f"主题服务客户端匹配失败: {e}")
                # 降级为默认匹配

        # 尝试使用theme_service_client
        try:
            from database_service.services.theme_service_client import ThemeServiceClient
            now_ts = time.time()
            if now_ts < self._theme_service_disabled_until:
                if now_ts - self._theme_service_log_at > 30:
                    logger.warning(
                        "主题服务暂时不可用，冷却中（%ss 后重试）",
                        int(self._theme_service_disabled_until - now_ts),
                    )
                    self._theme_service_log_at = now_ts
                return self._default_theme_match(event_data)

            # 快速探活：服务端口不可达时直接冷却，避免触发下游HTTP重试风暴
            if not await self._is_theme_service_reachable():
                cooldown = self._next_theme_service_cooldown_seconds()
                self._theme_service_disabled_until = now_ts + cooldown
                if now_ts - self._theme_service_log_at > 30:
                    logger.warning(
                        "主题服务不可达 %s:%s，进入%s秒冷却，降级默认匹配",
                        self._theme_service_host,
                        self._theme_service_port,
                        cooldown,
                    )
                    self._theme_service_log_at = now_ts
                return self._default_theme_match(event_data)

            if self._theme_service_client is None:
                self._theme_service_client = ThemeServiceClient(base_url=self.theme_service_base_url)

            # 构建匹配请求数据
            match_data = {
                "title": event_data.get("title", event_data.get("summary", "")),
                "content": event_data.get("content", event_data.get("summary", "")),
                "keywords": event_data.get("keywords", []),
                "event_type": event_data.get("event_type", "unknown"),
                "source": event_data.get("source", "unknown")
            }

            matched_themes = await self._theme_service_client.match_themes(match_data, limit=3)

            if matched_themes:
                self._theme_service_failure_streak = 0
                # 转换匹配结果为标准格式
                theme_names = []
                subject_keys = []

                for theme in matched_themes:
                    theme_name = theme.get("theme_name", theme.get("name", "未知主题"))
                    theme_names.append(theme_name)
                    # 生成subject_key
                    subject_key = theme_name.lower().replace(" ", "_").replace("-", "_")
                    subject_keys.append(subject_key)

                return {
                    "decision": "MATCH",
                    "confidence": 0.7,
                    "matched_theme_names": theme_names,
                    "matched_subject_keys": subject_keys,
                    "reason_code": "THEME_SERVICE_MATCH",
                    "review_required": False
                }
            else:
                logger.debug("主题服务返回空匹配，降级到默认匹配")
                return self._default_theme_match(event_data)

        except ImportError as e:
            logger.warning(f"无法导入ThemeServiceClient: {e}")
        except Exception as e:
            cooldown = self._next_theme_service_cooldown_seconds()
            self._theme_service_disabled_until = time.time() + cooldown
            logger.warning(f"主题服务调用失败，{cooldown}秒后重试: {e}")

        # 降级方案：基于事件类型的默认匹配
        return self._default_theme_match(event_data)

    def _next_theme_service_cooldown_seconds(self) -> int:
        """连续失败时指数扩展冷却时长，避免持续重试放大资源消耗。"""
        self._theme_service_failure_streak += 1
        exponent = min(3, self._theme_service_failure_streak - 1)
        return min(
            self._theme_service_max_cooldown_seconds,
            self._theme_service_base_cooldown_seconds * (2 ** exponent),
        )

    async def _is_theme_service_reachable(self) -> bool:
        """快速TCP探活，避免对不可达服务频繁发起HTTP重试。"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._theme_service_host, self._theme_service_port),
                timeout=0.3,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _default_theme_match(self, event_data: Dict) -> Dict:
        """
        默认主题匹配（降级方案）

        Args:
            event_data: 事件数据

        Returns:
            默认匹配结果
        """
        event_type = event_data.get("event_type", "unknown")

        # 简单的事件类型到主题映射
        theme_map = {
            "policy_change": ["政策", "监管"],
            "industry_trend": ["行业趋势", "产业"],
            "technology_breakthrough": ["技术突破", "科技创新"],
            "financial_report": ["财报", "业绩"],
            "merger_acquisition": ["并购", "重组"],
        }

        matched_themes = theme_map.get(event_type, ["其他"])

        return {
            "decision": "MATCH",
            "confidence": 0.5,
            "matched_theme_names": matched_themes,
            "matched_subject_keys": [t.lower().replace(" ", "_") for t in matched_themes],
            "reason_code": "DEFAULT_MATCH",
            "review_required": True  # 标记需要人工审核
        }

    def _create_feed_item(self, event_data: Dict, match_result: Dict) -> Optional[Dict]:
        """
        创建feed事件项

        Args:
            event_data: 事件数据
            match_result: 匹配结果

        Returns:
            feed事件项字典，符合 stream:event:feed 格式
        """
        try:
            # 基础字段
            event_id = event_data.get("event_id", f"event_{int(time.time())}")
            news_id = event_data.get("news_id", "")

            # 时间戳
            occurred_at = event_data.get("occurred_at")
            if not occurred_at:
                # 尝试从其他字段提取
                for time_field in ["publish_time", "created_at", "timestamp"]:
                    if time_field in event_data:
                        occurred_at = event_data[time_field]
                        break
                if not occurred_at:
                    occurred_at = datetime.now().isoformat()

            # 主题信息
            theme_names = match_result.get("matched_theme_names", [])
            theme_subject_keys = match_result.get("matched_subject_keys", [])

            # 如果匹配结果使用单数字段，转换为数组
            if not theme_names and match_result.get("matched_theme_name"):
                theme_names = [match_result.get("matched_theme_name")]
            if not theme_subject_keys and match_result.get("matched_subject_key"):
                theme_subject_keys = [match_result.get("matched_subject_key")]

            # 确保至少有一个主题
            if not theme_names:
                theme_names = ["未匹配"]
                theme_subject_keys = ["unmatched"]
                logger.debug(f"事件 {event_id}: 未匹配到主题，使用默认")

            # 构建feed项
            feed_item = {
                "item_id": f"item_{event_id}_{int(time.time())}",
                "event_type": "theme_move",  # 固定类型，符合前端期望
                "occurred_at": occurred_at,
                "summary": event_data.get("summary", event_data.get("title", "")),
                "theme_names": theme_names,
                "theme_subject_keys": theme_subject_keys,
                "confidence": match_result.get("confidence", 0.5),
                "impact_score": event_data.get("severity_score", 50),  # 默认50
                "source_type": "event_theme_map",
                # 原始事件ID用于追踪
                "original_event_id": event_id,
                "original_news_id": news_id,
                "match_decision": match_result.get("decision", "UNKNOWN"),
                "review_required": match_result.get("review_required", False)
            }

            return feed_item

        except Exception as e:
            logger.error(f"创建feed项失败: {e}")
            return None

    async def publish_matched_event(self, feed_item: Dict) -> Optional[str]:
        """
        发布匹配后的事件到feed Stream

        Args:
            feed_item: feed事件项

        Returns:
            发布的消息ID，None表示失败
        """
        try:
            # 使用事件生产者（如果提供）
            if self.event_producer:
                message_ids = await self.event_producer.publish_batch([feed_item], "feed")
                return message_ids[0] if message_ids else None
            else:
                # 直接使用stream_manager发布
                message_id = await self.stream_manager.publish(
                    self.output_stream,
                    feed_item,
                    max_len=self.output_stream_max_len,
                )
                return message_id

        except Exception as e:
            logger.error(f"发布feed项失败: {e}")
            return None

    async def _move_to_dead_letter(self, message_id: str, message_data: Dict, error: str) -> None:
        """
        将消息移动到死信队列

        Args:
            message_id: 消息ID
            message_data: 消息数据
            error: 错误信息
        """
        try:
            dead_letter_item = {
                "original_message_id": message_id,
                "original_stream": self.input_stream,
                "error": error,
                "message_data": message_data,
                "moved_at": datetime.now().isoformat()
            }

            await self.stream_manager.publish(
                self.dead_letter_stream,
                dead_letter_item
            )
            logger.warning(f"消息 {message_id} 已移动到死信队列: {error}")

        except Exception as e:
            logger.error(f"移动消息到死信队列失败: {e}")

    async def get_matching_stats(self) -> Dict:
        """获取匹配统计信息"""
        stats = self.stats.copy()

        # 计算匹配成功率
        total_processed = stats["total_messages_processed"]
        successful = stats["successful_matches"]
        if total_processed > 0:
            stats["success_rate"] = successful / total_processed * 100
        else:
            stats["success_rate"] = 0

        # 添加运行状态
        stats["is_running"] = self.is_running
        stats["input_stream"] = self.input_stream
        stats["output_stream"] = self.output_stream

        # 最近错误（仅保留最近10条）
        if stats["errors"]:
            stats["recent_errors"] = stats["errors"][-10:]
        else:
            stats["recent_errors"] = []

        return stats

    def get_config(self) -> Dict:
        """获取当前配置"""
        return {
            "input_stream": self.input_stream,
            "output_stream": self.output_stream,
            "consumer_group": self.consumer_group,
            "batch_size": self.batch_size,
            "polling_interval": self.polling_interval,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "is_theme_client_available": self.theme_client is not None
        }
