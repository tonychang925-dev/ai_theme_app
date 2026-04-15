"""
事件复核队列写入服务 (EventReviewWriter)

基于全链路打通方案，监听Redis Stream `stream:event:feed`，
将review_required=True的事件写入event_review_queue表。
实现事件匹配→复核队列断点的打通。

功能：
- 监听事件feed Stream
- 过滤review_required=True的事件
- 写入event_review_queue表
- 异常处理和重试机制
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import time

from database_service.streams.utils.retry_manager import RetryManager
from database_service.gateway import DatabaseGateway

logger = logging.getLogger(__name__)


class EventReviewWriter:
    """事件复核队列写入服务"""

    def __init__(
        self,
        stream_manager,
        database_gateway: Optional[DatabaseGateway] = None,
        config: Optional[Dict] = None
    ):
        """
        初始化事件复核队列写入服务

        Args:
            stream_manager: Redis Stream管理器
            database_gateway: 数据库网关（可选）
            config: 配置字典
        """
        self.stream_manager = stream_manager
        self.database_gateway = database_gateway
        self.config = config or {}

        # Stream名称配置
        self.input_stream = self.config.get("input_stream", "stream:event:feed")
        self.consumer_group = self.config.get("consumer_group", "event_review_writers")
        self.consumer_name = self.config.get("consumer_name", f"event_review_writer_{int(time.time())}")
        self.batch_size = self.config.get("batch_size", 10)
        self.polling_interval = self.config.get("polling_interval", 1)
        self.min_review_confidence = float(self.config.get("min_review_confidence", 0.6))
        self.skip_generic_theme = bool(self.config.get("skip_generic_theme", True))

        # 重试管理器
        self.retry_manager = RetryManager(
            max_retries=self.config.get("max_retries", 3),
            base_delay=self.config.get("retry_base_delay", 1.0),
            max_delay=self.config.get("retry_max_delay", 30.0)
        )

        # 统计
        self.stats = {
            "processed": 0,
            "written": 0,
            "skipped": 0,
            "errors": 0,
            "last_processed_at": None
        }
        self.is_running = False
        self._run_task: Optional[asyncio.Task] = None
        self._initialized = False

        logger.info(f"📝 初始化事件复核队列写入服务: input_stream={self.input_stream}")

    async def initialize(self):
        """初始化服务"""
        try:
            if self._initialized:
                return
            # 确保数据库网关可用
            if self.database_gateway is None:
                from database_service.gateway import DatabaseGateway
                self.database_gateway = DatabaseGateway()
                await self.database_gateway.initialize()
                logger.info("✅ 数据库网关初始化成功")

            # 创建消费者组（如果不存在）
            try:
                await self.stream_manager.create_consumer_group(
                    self.input_stream,
                    self.consumer_group
                )
                logger.info(f"✅ 创建消费者组: {self.consumer_group}")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"ℹ️ 消费者组已存在: {self.consumer_group}")
                else:
                    logger.warning(f"⚠️ 创建消费者组失败: {e}")
                    # 继续运行，可能在后续读取时创建
            self._initialized = True

        except Exception as e:
            logger.error(f"❌ 服务初始化失败: {e}")
            raise

    async def process_batch(self, messages: List[Dict]) -> List[Dict]:
        """
        处理一批消息

        Args:
            messages: 消息列表

        Returns:
            成功处理的消息ID列表
        """
        processed_ids = []

        for message in messages:
            try:
                message_id = message.get("id")
                message_data = message.get("data", {})

                # 获取payload字段
                payload_str = message_data.get("payload", "{}")
                logger.debug(f"message_data keys: {list(message_data.keys())}")
                logger.debug(f"原始payload: {payload_str}")

                # 解析payload
                payload = json.loads(payload_str)
                logger.debug(f"解析后payload: {payload}")

                # 检查是否需要复核
                review_required = payload.get("review_required", False)
                logger.info(f"检查复核要求: message_id={message_id}, review_required={review_required}, payload_keys={list(payload.keys())}")
                if not review_required:
                    logger.info(f"跳过事件 (无需复核): {message_id}")
                    self.stats["skipped"] += 1
                    processed_ids.append(message_id)
                    continue

                # 仅接收题材匹配链路产出的待复核事件，避免混入非匹配来源
                source_type = str(payload.get("source_type") or "")
                if source_type != "event_theme_map":
                    logger.info(f"跳过事件 (非题材匹配来源): {message_id}, source_type={source_type or 'unknown'}")
                    self.stats["skipped"] += 1
                    processed_ids.append(message_id)
                    continue

                # 提取事件信息
                event_id = payload.get("original_event_id", "")
                logger.info(f"提取事件ID: message_id={message_id}, original_event_id={event_id}, type={type(event_id)}")
                if not event_id:
                    logger.warning(f"事件ID缺失: {message_id}")
                    self.stats["skipped"] += 1
                    processed_ids.append(message_id)
                    continue

                # 提取主题信息
                theme_names = payload.get("theme_names", [])
                proposed_theme_name = theme_names[0] if theme_names else "其他"
                confidence = payload.get("confidence", 0.5)

                # 过滤“无意义复核”：题材=其他 或 置信度过低
                if self.skip_generic_theme and proposed_theme_name in {"其他", "未匹配", "unknown", "UNKNOWN"}:
                    logger.info(f"跳过事件 (题材过于泛化): {message_id}, theme={proposed_theme_name}")
                    self.stats["skipped"] += 1
                    processed_ids.append(message_id)
                    continue
                if float(confidence or 0.0) < self.min_review_confidence:
                    logger.info(
                        f"跳过事件 (置信度低): {message_id}, confidence={float(confidence or 0.0):.2f}, threshold={self.min_review_confidence:.2f}"
                    )
                    self.stats["skipped"] += 1
                    processed_ids.append(message_id)
                    continue

                # 提取事件摘要
                summary = payload.get("summary", "")
                if not summary:
                    summary = f"事件 {event_id} 需要复核"

                # 构建复核记录
                review_record = {
                    "event_id": self._extract_event_id_number(event_id),
                    "review_status": "waiting",
                    "proposed_theme_name": proposed_theme_name,
                    "proposed_theme_confidence": float(confidence),
                    "reason": summary[:500],  # 限制长度
                    "source_channel": "event_theme_matcher",
                    "created_at": datetime.now()
                }

                # 写入数据库
                success = await self._write_to_review_queue(review_record)

                if success:
                    logger.info(f"✅ 写入复核队列: event_id={review_record['event_id']}, theme={proposed_theme_name}")
                    self.stats["written"] += 1
                else:
                    logger.warning(f"⚠️ 写入复核队列失败: event_id={review_record['event_id']}")
                    self.stats["errors"] += 1

                processed_ids.append(message_id)
                self.stats["processed"] += 1

            except Exception as e:
                logger.error(f"❌ 处理消息失败 {message.get('id', 'unknown')}: {e}")
                self.stats["errors"] += 1

        self.stats["last_processed_at"] = datetime.now()
        return processed_ids

    def _extract_event_id_number(self, event_id) -> int:
        """从事件ID中提取数字ID"""
        try:
            # 如果已经是数字，直接返回
            if isinstance(event_id, (int, float)):
                return int(event_id)

            # 如果是字符串，尝试提取数字
            event_id_str = str(event_id)

            # 尝试从类似 "temp_1775795161_news_1775795098848_" 中提取数字
            parts = event_id_str.split('_')
            for part in parts:
                if part.isdigit() and len(part) > 5:  # 假设ID长度大于5位
                    return int(part)

            # 如果没找到，尝试从末尾提取
            for i in range(len(event_id_str)-1, -1, -1):
                if event_id_str[i].isdigit():
                    j = i
                    while j >= 0 and event_id_str[j].isdigit():
                        j -= 1
                    num_str = event_id_str[j+1:i+1]
                    if num_str:
                        return int(num_str)

            # 最后尝试整个字符串
            digits = ''.join(filter(str.isdigit, event_id_str))
            if digits:
                return int(digits)

            # 如果所有方法都失败，返回0（会触发数据库外键错误）
            logger.warning(f"无法从事件ID提取数字: {event_id} (type: {type(event_id)})")
            return 0
        except Exception as e:
            logger.error(f"提取事件ID失败 {event_id}: {e}")
            return 0

    async def _write_to_review_queue(self, review_record: Dict) -> bool:
        """写入复核队列表"""
        try:
            # 使用重试机制
            async def write_operation():
                # 检查事件是否存在
                event_id = review_record["event_id"]
                if event_id <= 0:
                    logger.warning(f"无效的事件ID: {event_id}")
                    return False

                # 使用DatabaseGateway的enqueue_event_review方法
                # 注意：review_status和created_at在数据库中有默认值
                success = await self.database_gateway.enqueue_event_review(
                    event_id=event_id,
                    reason=review_record["reason"],
                    source_channel=review_record["source_channel"],
                    proposed_theme_name=review_record["proposed_theme_name"],
                    proposed_theme_confidence=review_record["proposed_theme_confidence"]
                )

                return success

            return await self.retry_manager.execute_with_retry(write_operation)

        except Exception as e:
            logger.error(f"❌ 写入复核队列失败: {e}")
            return False

    async def start(self):
        """启动服务（兼容服务管理器）"""
        if self.is_running:
            logger.warning("事件复核队列写入服务已在运行")
            return
        await self.initialize()
        self.is_running = True
        self._run_task = asyncio.create_task(self.run())
        logger.info("🚀 事件复核队列写入服务已启动")

    async def stop(self):
        """停止服务（兼容服务管理器）"""
        if not self.is_running:
            return
        self.is_running = False
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
            self._run_task = None
        logger.info("🛑 事件复核队列写入服务已停止")

    async def run(self):
        """运行服务主循环"""
        logger.info(f"🚀 启动事件复核队列写入服务...")

        while self.is_running:
            try:
                # 从Stream读取消息
                messages = await self.stream_manager.read_group(
                    stream=self.input_stream,
                    group=self.consumer_group,
                    consumer=self.consumer_name,
                    count=self.batch_size,
                    block_ms=1000  # 1秒阻塞
                )

                if messages:
                    logger.info(f"📥 收到 {len(messages)} 条消息")
                    logger.debug(f"消息详情: {messages[:1]}")  # 只记录第一条消息详情

                    # 处理消息
                    processed_ids = await self.process_batch(messages)

                    # 确认消息
                    if processed_ids:
                        for msg_id in processed_ids:
                            await self.stream_manager.ack(
                                stream=self.input_stream,
                                group=self.consumer_group,
                                message_id=msg_id
                            )
                        logger.debug(f"✅ 确认 {len(processed_ids)} 条消息")

                # 定期打印统计
                if self.stats["processed"] % 100 == 0 and self.stats["processed"] > 0:
                    logger.info(f"📊 统计: processed={self.stats['processed']}, "
                               f"written={self.stats['written']}, "
                               f"skipped={self.stats['skipped']}, "
                               f"errors={self.stats['errors']}")

                # 等待下一次轮询
                await asyncio.sleep(self.polling_interval)

            except asyncio.CancelledError:
                logger.info("🛑 服务被取消")
                break
            except Exception as e:
                logger.error(f"❌ 服务运行异常: {e}")
                await asyncio.sleep(5)  # 错误后等待

    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计"""
        return {
            **self.stats,
            "input_stream": self.input_stream,
            "consumer_group": self.consumer_group,
            "consumer_name": self.consumer_name,
            "is_running": self.is_running
        }
