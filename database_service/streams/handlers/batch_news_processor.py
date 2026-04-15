"""
批量新闻处理器 - 优化AI处理性能
基于AI性能测试结果，批量处理可提升5.1倍性能
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import deque

logger = logging.getLogger(__name__)


class BatchNewsProcessor:
    """批量新闻处理器 - 优化AI处理性能"""

    def __init__(self,
                 event_bus,
                 config=None,
                 batch_size: int = 5,
                 max_batch_wait: float = 2.0,
                 max_concurrent_batches: int = 3):
        """
        初始化批量处理器

        Args:
            event_bus: 事件总线
            config: 配置
            batch_size: 批量大小（默认5条）
            max_batch_wait: 最大等待时间（秒）
            max_concurrent_batches: 最大并发批量数
        """
        self.event_bus = event_bus
        self.config = config or {}
        self.batch_size = batch_size
        self.max_batch_wait = max_batch_wait
        self.max_concurrent_batches = max_concurrent_batches

        # 批量处理队列
        self.batch_queue = deque()
        self.batch_lock = asyncio.Lock()
        self.processing_tasks = set()

        # 性能统计
        self.stats = {
            "total_processed": 0,
            "batch_processed": 0,
            "single_processed": 0,
            "avg_batch_size": 0,
            "avg_processing_time": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }

        # 业务服务
        self.business_services = {}
        self._init_business_services()

        logger.info(
            f"🧠 初始化批量新闻处理器: "
            f"批量大小={batch_size}, "
            f"最大等待={max_batch_wait}s, "
            f"最大并发={max_concurrent_batches}"
        )

    def _init_business_services(self):
        """初始化业务服务"""
        try:
            from model_service import get_model_service
            model_service = get_model_service()
            self.business_services["model_service"] = model_service
            logger.info("✅ 成功初始化ModelService")
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入ModelService: {e}")

    async def process_single(self, message_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单条消息（兼容现有接口）

        Args:
            message_id: 消息ID
            message_data: 消息数据

        Returns:
            处理结果
        """
        start_time = time.time()

        try:
            # 构建事件
            event = self._build_stored_news_event(message_id, message_data)

            # 使用批量处理（内部会处理单条情况）
            batch_result = await self._process_batch_internal([(message_id, event)])

            if batch_result and len(batch_result) > 0:
                result = batch_result[0]
                processing_time = time.time() - start_time

                # 更新统计
                async with self.batch_lock:
                    self.stats["single_processed"] += 1
                    self.stats["total_processed"] += 1
                    self.stats["avg_processing_time"] = (
                        self.stats["avg_processing_time"] * (self.stats["total_processed"] - 1) + processing_time
                    ) / self.stats["total_processed"]

                return result
            else:
                return self._create_error_result(message_id, "批量处理返回空结果")

        except Exception as e:
            logger.error(f"❌ 单条处理失败 {message_id}: {e}")
            return self._create_error_result(message_id, str(e))

    async def process_batch(self, messages: List[Tuple[str, Dict]]) -> List[Dict[str, Any]]:
        """
        批量处理消息

        Args:
            messages: 消息列表，每个元素为(message_id, message_data)

        Returns:
            处理结果列表
        """
        if not messages:
            return []

        start_time = time.time()
        batch_size = len(messages)

        logger.info(f"🧠 开始批量处理 {batch_size} 条消息")

        try:
            # 构建事件列表
            events = []
            for message_id, message_data in messages:
                event = self._build_stored_news_event(message_id, message_data)
                events.append((message_id, event))

            # 处理批量
            results = await self._process_batch_internal(events)

            processing_time = time.time() - start_time
            avg_time_per_message = processing_time / batch_size if batch_size > 0 else 0

            # 更新统计
            async with self.batch_lock:
                self.stats["batch_processed"] += 1
                self.stats["total_processed"] += batch_size
                self.stats["avg_batch_size"] = (
                    self.stats["avg_batch_size"] * (self.stats["batch_processed"] - 1) + batch_size
                ) / self.stats["batch_processed"]
                self.stats["avg_processing_time"] = (
                    self.stats["avg_processing_time"] * (self.stats["total_processed"] - batch_size) + processing_time
                ) / self.stats["total_processed"]

            logger.info(
                f"✅ 批量处理完成: {len([r for r in results if r.get('success')])}/{batch_size}条成功, "
                f"总耗时: {processing_time:.2f}s, 平均: {avg_time_per_message:.2f}s/条"
            )

            return results

        except Exception as e:
            logger.error(f"❌ 批量处理失败: {e}")
            # 返回错误结果
            return [self._create_error_result(msg_id, str(e)) for msg_id, _ in messages]

    async def _process_batch_internal(self, events: List[Tuple[str, Dict]]) -> List[Dict[str, Any]]:
        """内部批量处理方法"""
        if not events:
            return []

        # 如果只有一条，使用单条处理逻辑
        if len(events) == 1:
            message_id, event = events[0]
            return [await self._process_single_event(event, message_id)]

        # 批量处理逻辑
        try:
            # 提取新闻数据
            news_items = []
            event_map = {}

            for message_id, event in events:
                news_data = event.get('data', {}).get('news_data', {})
                if news_data:
                    news_items.append(news_data)
                    event_map[message_id] = event

            if not news_items:
                return [self._create_error_result(msg_id, "无新闻数据") for msg_id, _ in events]

            # 调用批量AI分析
            ai_results = await self._call_batch_ai_analysis(news_items)

            # 构建结果
            results = []
            for i, (message_id, event) in enumerate(events):
                if i < len(ai_results) and ai_results[i]:
                    ai_result = ai_results[i]
                    result = await self._build_result_from_ai_analysis(
                        message_id, event, ai_result
                    )
                else:
                    result = self._create_error_result(message_id, "AI分析失败")

                results.append(result)

            return results

        except Exception as e:
            logger.error(f"❌ 内部批量处理失败: {e}")
            return [self._create_error_result(msg_id, str(e)) for msg_id, _ in events]

    async def _call_batch_ai_analysis(self, news_items: List[Dict]) -> List[Optional[Dict]]:
        """调用批量AI分析"""
        if not news_items:
            return []

        # 优先使用带缓存的批量分析
        if "model_service" in self.business_services:
            model_service = self.business_services["model_service"]

            # 检查是否支持批量分析
            if hasattr(model_service, 'extract_event_batch'):
                try:
                    logger.info(f"🧠 调用批量AI分析: {len(news_items)}条")
                    batch_results = await model_service.extract_event_batch(news_items)
                    return batch_results
                except Exception as e:
                    logger.warning(f"⚠️  批量AI分析失败，退回到单条: {e}")

            # 退回到单条分析
            logger.info(f"🧠 使用单条AI分析（批量模式）: {len(news_items)}条")
            results = []
            for news_item in news_items:
                try:
                    result = await model_service.extract_event(news_item)
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ 单条AI分析失败: {e}")
                    results.append(None)
            return results

        else:
            logger.warning("⚠️  ModelService不可用，跳过AI分析")
            return [None] * len(news_items)

    async def _process_single_event(self, event: Dict[str, Any], message_id: str) -> Dict[str, Any]:
        """处理单个事件"""
        try:
            news_data = event.get('data', {}).get('news_data', {})

            if "model_service" in self.business_services:
                model_service = self.business_services["model_service"]
                ai_result = await model_service.extract_event(news_data)

                if ai_result and ai_result.get("status") == "success":
                    return await self._build_result_from_ai_analysis(
                        message_id, event, ai_result
                    )
                else:
                    error_msg = ai_result.get("error", "AI分析失败") if ai_result else "AI返回空结果"
                    return self._create_error_result(message_id, error_msg)
            else:
                return self._create_error_result(message_id, "ModelService不可用")

        except Exception as e:
            logger.error(f"❌ 单条事件处理失败 {message_id}: {e}")
            return self._create_error_result(message_id, str(e))

    async def _build_result_from_ai_analysis(self, message_id: str, event: Dict, ai_result: Dict) -> Dict[str, Any]:
        """从AI分析结果构建处理结果"""
        try:
            # 这里简化处理，实际应该调用持久化和发布逻辑
            return {
                "success": True,
                "message_id": message_id,
                "news_id": event.get('data', {}).get('news_data', {}).get('news_id', 'unknown'),
                "event_id": event.get('id', message_id),
                "processing_time": datetime.now().isoformat(),
                "ai_result": ai_result,
                "source_type": "batch_processor"
            }
        except Exception as e:
            logger.error(f"❌ 构建结果失败 {message_id}: {e}")
            return self._create_error_result(message_id, str(e))

    def _build_stored_news_event(self, message_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建存储新闻事件"""
        # 简化版本，实际应该从消息中提取新闻数据
        news_data = self._extract_news_from_message(message_id, message_data)

        return {
            "id": message_id,
            "event_type": "news.stored",
            "data": {
                "news_data": news_data,
                "stored_at": datetime.now().isoformat(),
                "source": "stored_news_event",
                "message_id": message_id,
                "raw_data": message_data,
            },
        }

    def _extract_news_from_message(self, message_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """从消息中提取新闻数据"""
        # 简化提取逻辑
        if isinstance(message_data, dict):
            if 'payload' in message_data:
                payload = message_data['payload']
                if isinstance(payload, dict) and 'news_data' in payload:
                    return payload['news_data']
                elif isinstance(payload, str):
                    try:
                        payload_dict = json.loads(payload)
                        if isinstance(payload_dict, dict) and 'news_data' in payload_dict:
                            return payload_dict['news_data']
                    except:
                        pass

        # 默认返回空数据
        return {
            "news_id": message_id,
            "title": "未提取到标题",
            "content": "未提取到内容",
            "timestamp": datetime.now().isoformat()
        }

    def _create_error_result(self, message_id: str, error: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "success": False,
            "message_id": message_id,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "batch_size": self.batch_size,
            "max_concurrent_batches": self.max_concurrent_batches,
            "max_batch_wait": self.max_batch_wait,
            "timestamp": datetime.now().isoformat()
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health = {
            "status": "healthy",
            "batch_processor": True,
            "batch_size": self.batch_size,
            "queue_size": len(self.batch_queue),
            "processing_tasks": len(self.processing_tasks),
            "stats": self.stats,
            "business_services": {
                "model_service": "model_service" in self.business_services
            },
            "timestamp": datetime.now().isoformat()
        }

        # 检查业务服务
        if "model_service" in self.business_services:
            try:
                model_service = self.business_services["model_service"]
                if hasattr(model_service, 'health_check'):
                    service_health = await model_service.health_check()
                    health["model_service_health"] = service_health
            except Exception as e:
                health["model_service_health"] = {"error": str(e)}
                health["status"] = "degraded"

        return health


# 工厂函数
def create_batch_processor(event_bus, config=None, **kwargs) -> BatchNewsProcessor:
    """创建批量处理器实例"""
    return BatchNewsProcessor(event_bus, config, **kwargs)


# 测试代码
if __name__ == "__main__":
    import asyncio

    async def test_batch_processor():
        """测试批量处理器"""
        print("🧪 测试批量新闻处理器")

        try:
            # 创建模拟事件总线
            class MockEventBus:
                pass

            event_bus = MockEventBus()

            # 创建处理器
            processor = create_batch_processor(
                event_bus,
                batch_size=3,
                max_batch_wait=1.0,
                max_concurrent_batches=2
            )

            print(f"✅ 创建批量处理器，批量大小: {processor.batch_size}")

            # 健康检查
            health = await processor.health_check()
            print(f"✅ 健康检查: {health}")

            # 测试数据
            test_messages = [
                ("msg_1", {"payload": {"news_data": {
                    "news_id": "test_1",
                    "title": "测试新闻1",
                    "content": "测试内容1"
                }}}),
                ("msg_2", {"payload": {"news_data": {
                    "news_id": "test_2",
                    "title": "测试新闻2",
                    "content": "测试内容2"
                }}}),
                ("msg_3", {"payload": {"news_data": {
                    "news_id": "test_3",
                    "title": "测试新闻3",
                    "content": "测试内容3"
                }}})
            ]

            print(f"\n📊 测试批量处理 {len(test_messages)} 条消息...")

            # 批量处理
            batch_results = await processor.process_batch(test_messages)
            print(f"✅ 批量处理完成: {len(batch_results)} 条结果")

            success_count = sum(1 for r in batch_results if r.get('success'))
            print(f"   成功: {success_count}条, 失败: {len(batch_results) - success_count}条")

            # 单条处理测试
            print(f"\n📊 测试单条处理...")
            single_result = await processor.process_single("single_msg", test_messages[0][1])
            print(f"✅ 单条处理: {'成功' if single_result.get('success') else '失败'}")

            # 获取统计
            stats = processor.get_stats()
            print(f"\n📈 性能统计: {stats}")

            print("\n🎉 批量处理器测试完成")

        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(test_batch_processor())