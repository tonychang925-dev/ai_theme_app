"""
Redis Stream 定时清理调度器
基于配置自动执行Stream清理，防止数据长期堆积
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta

# 尝试导入RedisStreamConfig（可选依赖）
try:
    from .stream_config import RedisStreamConfig
    REDIS_STREAM_CONFIG_AVAILABLE = True
except ImportError:
    REDIS_STREAM_CONFIG_AVAILABLE = False
    # 定义占位符类以便类型提示
    class RedisStreamConfig:
        pass

logger = logging.getLogger(__name__)


class StreamCleanupScheduler:
    """Stream清理调度器 - 定时执行基于时间和长度的Stream清理"""

    def __init__(self, stream_manager, config: Optional[Union[Dict[str, Any], RedisStreamConfig]] = None):
        """
        初始化清理调度器

        Args:
            stream_manager: RedisStreamManager实例
            config: 清理配置，可以是字典或RedisStreamConfig对象
        """
        self.stream_manager = stream_manager

        # 处理不同类型的配置
        config_dict = self._process_config(config)

        # 默认配置
        self.default_config = {
            "enabled": True,
            "cleanup_interval_hours": 24,  # 清理间隔（小时）
            "default_max_age_days": 30,    # 默认最大保留天数
            "default_max_length": 10000,   # 默认最大长度
            "dry_run": False,              # 是否仅模拟运行
            "enable_age_based_cleanup": True,   # 启用基于时间的清理
            "enable_length_based_cleanup": True, # 启用基于长度的清理
            "stream_specific_config": {},  # Stream特定配置
            "protected_streams": [         # 受保护的Stream（不自动清理）
                "stream:dead:letter",
                "stream:themes:updates"    # 主题更新可能需长期保留
            ],
            "max_streams_per_batch": 10,   # 每批处理的Stream最大数
            "health_check_before_cleanup": True,  # 清理前先检查健康状态
            "report_after_cleanup": True   # 清理后生成报告
        }

        # 更新配置
        self.default_config.update(config_dict)
        self.config = self.default_config

        # 统计信息
        self.stats = {
            "total_cleanups": 0,
            "streams_processed": 0,
            "messages_trimmed_by_age": 0,
            "messages_trimmed_by_length": 0,
            "protected_streams_skipped": 0,
            "errors": [],
            "last_cleanup": None,
            "last_successful_cleanup": None
        }

        # 任务句柄
        self._cleanup_task = None
        self._running = False

        logger.info(f"✅ 初始化Stream清理调度器，启用: {self.config['enabled']}")
        logger.info(f"  清理间隔: {self.config['cleanup_interval_hours']}小时")
        logger.info(f"  默认保留: {self.config['default_max_age_days']}天")
        logger.info(f"  模拟模式: {self.config['dry_run']}")

    def _process_config(self, config: Optional[Union[Dict[str, Any], RedisStreamConfig]]) -> Dict[str, Any]:
        """
        处理不同类型的配置，转换为统一的字典格式

        Args:
            config: 配置对象，可以是字典或RedisStreamConfig

        Returns:
            统一格式的配置字典
        """
        if config is None:
            return {}

        # 如果是字典类型，直接返回
        if isinstance(config, dict):
            return config.copy()

        # 如果是RedisStreamConfig类型
        if REDIS_STREAM_CONFIG_AVAILABLE and isinstance(config, RedisStreamConfig):
            config_dict = {}

            # 映射字段
            if hasattr(config, 'auto_cleanup'):
                config_dict['enabled'] = config.auto_cleanup

            if hasattr(config, 'cleanup_interval_hours'):
                config_dict['cleanup_interval_hours'] = config.cleanup_interval_hours

            if hasattr(config, 'max_stream_age_days'):
                config_dict['default_max_age_days'] = config.max_stream_age_days

            # 从Stream定义中提取默认最大长度
            if hasattr(config, 'streams') and config.streams:
                # 使用第一个Stream的max_length作为默认值
                first_stream = next(iter(config.streams.values()))
                if hasattr(first_stream, 'max_length'):
                    config_dict['default_max_length'] = first_stream.max_length

            # 从Stream定义中提取受保护的Stream（auto_trim=False的Stream）
            protected_streams = []
            if hasattr(config, 'streams') and config.streams:
                for stream_def in config.streams.values():
                    if hasattr(stream_def, 'auto_trim') and not stream_def.auto_trim:
                        protected_streams.append(stream_def.name)

            if protected_streams:
                config_dict['protected_streams'] = protected_streams

            # 保留原有的protected_streams（如果有的话）
            if hasattr(config, 'protected_streams'):
                existing_protected = config_dict.get('protected_streams', [])
                if isinstance(config.protected_streams, list):
                    config_dict['protected_streams'] = existing_protected + config.protected_streams

            return config_dict

        # 未知类型，返回空字典
        logger.warning(f"未知配置类型: {type(config)}，使用默认配置")
        return {}

    async def start(self) -> bool:
        """启动定时清理任务"""
        if not self.config["enabled"]:
            logger.info("清理调度器已禁用，不启动定时任务")
            return False

        if self._running:
            logger.warning("清理调度器已在运行")
            return True

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("✅ Stream清理调度器已启动")
        return True

    async def stop(self) -> bool:
        """停止定时清理任务"""
        if not self._running:
            logger.info("清理调度器未运行")
            return True

        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        logger.info("✅ Stream清理调度器已停止")
        return True

    async def _cleanup_loop(self):
        """清理循环 - 定期执行清理"""
        cleanup_interval = self.config["cleanup_interval_hours"] * 3600  # 转换为秒

        logger.info(f"🔧 清理循环启动，间隔: {cleanup_interval/3600:.1f}小时")

        while self._running:
            try:
                # 等待下一个清理周期
                await asyncio.sleep(cleanup_interval)

                # 执行清理
                await self.perform_scheduled_cleanup()

            except asyncio.CancelledError:
                logger.info("清理循环被取消")
                break
            except Exception as e:
                logger.error(f"清理循环出错: {e}")
                self.stats["errors"].append({
                    "operation": "cleanup_loop",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                # 出错后等待较短时间再重试
                await asyncio.sleep(300)  # 5分钟

    async def perform_scheduled_cleanup(self) -> Dict[str, Any]:
        """
        执行计划的清理任务

        Returns:
            清理结果统计
        """
        cleanup_start = datetime.now()
        logger.info(f"🧹 开始计划清理任务: {cleanup_start.isoformat()}")

        result = {
            "timestamp": cleanup_start.isoformat(),
            "success": False,
            "dry_run": self.config["dry_run"],
            "streams_processed": 0,
            "streams_cleaned": 0,
            "streams_protected": 0,
            "streams_failed": 0,
            "total_messages_trimmed": 0,
            "age_based_trimmed": 0,
            "length_based_trimmed": 0,
            "details": []
        }

        try:
            # 步骤1: 获取所有Stream
            metrics = await self.stream_manager.get_stream_metrics("stream:*")
            streams_found = metrics.get("streams_found", 0)

            if streams_found == 0:
                result.update({
                    "success": True,
                    "message": "未找到Stream，跳过清理"
                })
                return result

            # 步骤2: 处理每个Stream
            streams = metrics.get("streams", {})
            processed_count = 0

            for stream_name, stream_info in streams.items():
                if processed_count >= self.config["max_streams_per_batch"]:
                    logger.info(f"达到批次限制 ({self.config['max_streams_per_batch']})，停止处理更多Stream")
                    break

                stream_result = await self._cleanup_single_stream(stream_name, stream_info)
                result["details"].append(stream_result)
                result["streams_processed"] += 1
                processed_count += 1

                if stream_result.get("protected", False):
                    result["streams_protected"] += 1
                elif stream_result.get("cleaned", False):
                    result["streams_cleaned"] += 1
                    result["total_messages_trimmed"] += stream_result.get("messages_trimmed", 0)
                    result["age_based_trimmed"] += stream_result.get("age_based_trimmed", 0)
                    result["length_based_trimmed"] += stream_result.get("length_based_trimmed", 0)
                elif stream_result.get("error"):
                    result["streams_failed"] += 1

            # 步骤3: 更新统计和结果
            self.stats["total_cleanups"] += 1
            self.stats["streams_processed"] += result["streams_processed"]
            self.stats["messages_trimmed_by_age"] += result["age_based_trimmed"]
            self.stats["messages_trimmed_by_length"] += result["length_based_trimmed"]
            self.stats["last_cleanup"] = cleanup_start.isoformat()

            if result["streams_failed"] == 0:
                self.stats["last_successful_cleanup"] = cleanup_start.isoformat()
                result["success"] = True
            else:
                result["success"] = False
                result["message"] = f"清理完成，但有 {result['streams_failed']} 个Stream失败"

            cleanup_duration = (datetime.now() - cleanup_start).total_seconds()
            result["duration_seconds"] = cleanup_duration

            logger.info(f"✅ 计划清理完成: 处理 {result['streams_processed']} 个Stream, "
                       f"清理 {result['streams_cleaned']} 个, "
                       f"保护 {result['streams_protected']} 个, "
                       f"耗时 {cleanup_duration:.1f}秒")

            if not self.config["dry_run"] and result["total_messages_trimmed"] > 0:
                logger.info(f"  清理消息数: {result['total_messages_trimmed']} 条 "
                           f"(时间: {result['age_based_trimmed']}, 长度: {result['length_based_trimmed']})")

            return result

        except Exception as e:
            logger.error(f"计划清理失败: {e}")
            self.stats["errors"].append({
                "operation": "perform_scheduled_cleanup",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })

            result.update({
                "success": False,
                "error": str(e),
                "duration_seconds": (datetime.now() - cleanup_start).total_seconds()
            })
            return result

    async def _cleanup_single_stream(self, stream_name: str, stream_info: Dict[str, Any]) -> Dict[str, Any]:
        """清理单个Stream"""
        stream_result = {
            "stream": stream_name,
            "timestamp": datetime.now().isoformat(),
            "protected": False,
            "cleaned": False,
            "messages_trimmed": 0,
            "age_based_trimmed": 0,
            "length_based_trimmed": 0,
            "before_length": stream_info.get("length", 0)
        }

        try:
            # 检查是否为保护Stream
            if stream_name in self.config["protected_streams"]:
                stream_result["protected"] = True
                stream_result["reason"] = "protected_stream"
                self.stats["protected_streams_skipped"] += 1
                logger.debug(f"跳过保护Stream: {stream_name}")
                return stream_result

            # 获取Stream特定配置
            stream_config = self.config["stream_specific_config"].get(stream_name, {})
            max_age_days = stream_config.get("max_age_days", self.config["default_max_age_days"])
            max_length = stream_config.get("max_length", self.config["default_max_length"])

            # 执行安全清理
            if self.config["health_check_before_cleanup"]:
                health_report = await self.stream_manager.analyze_stream_health(stream_name)
                stream_result["health_report"] = health_report

            cleanup_result = await self.stream_manager.safe_stream_cleanup(
                stream=stream_name,
                max_age_days=max_age_days if self.config["enable_age_based_cleanup"] else None,
                max_length=max_length if self.config["enable_length_based_cleanup"] else None,
                dry_run=self.config["dry_run"]
            )

            stream_result["cleanup_result"] = cleanup_result

            if cleanup_result.get("success", False):
                stream_result["cleaned"] = True

                # 提取清理的消息数
                cleanup_results = cleanup_result.get("cleanup_results", {})
                age_result = cleanup_results.get("age_based_cleanup", {})
                length_result = cleanup_results.get("length_based_cleanup", {})

                if age_result.get("success", False):
                    trimmed = age_result.get("trimmed_count", 0)
                    if isinstance(trimmed, int):
                        stream_result["age_based_trimmed"] = trimmed
                        stream_result["messages_trimmed"] += trimmed

                if length_result.get("success", False):
                    trimmed = length_result.get("trimmed_count", 0)
                    if isinstance(trimmed, int):
                        stream_result["length_based_trimmed"] = trimmed
                        stream_result["messages_trimmed"] += trimmed

                logger.info(f"✅ Stream清理完成: {stream_name}, "
                           f"清理消息: {stream_result['messages_trimmed']} 条")
            else:
                stream_result["error"] = cleanup_result.get("error", "unknown_error")
                logger.warning(f"Stream清理失败: {stream_name}, 错误: {stream_result['error']}")

        except Exception as e:
            stream_result["error"] = str(e)
            logger.error(f"清理Stream失败 {stream_name}: {e}")

        return stream_result

    async def perform_immediate_cleanup(self, stream_pattern: str = "stream:*",
                                      max_age_days: Optional[int] = None,
                                      max_length: Optional[int] = None) -> Dict[str, Any]:
        """
        立即执行清理（手动触发）

        Args:
            stream_pattern: Stream模式
            max_age_days: 最大保留天数（覆盖配置）
            max_length: 最大长度（覆盖配置）

        Returns:
            清理结果
        """
        logger.info(f"🚀 立即执行清理: 模式={stream_pattern}, "
                   f"保留天数={max_age_days or '使用配置'}, 最大长度={max_length or '使用配置'}")

        # 临时覆盖配置
        original_dry_run = self.config["dry_run"]
        self.config["dry_run"] = False  # 立即清理总是实际执行

        try:
            # 使用指定的参数
            if max_age_days is not None:
                original_age = self.config["default_max_age_days"]
                self.config["default_max_age_days"] = max_age_days

            if max_length is not None:
                original_length = self.config["default_max_length"]
                self.config["default_max_length"] = max_length

            # 执行清理
            result = await self.perform_scheduled_cleanup()

            # 恢复配置
            if max_age_days is not None:
                self.config["default_max_age_days"] = original_age

            if max_length is not None:
                self.config["default_max_length"] = original_length

            return result

        finally:
            # 恢复模拟模式设置
            self.config["dry_run"] = original_dry_run

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "scheduler_stats": self.stats.copy(),
            "config": {
                "enabled": self.config["enabled"],
                "cleanup_interval_hours": self.config["cleanup_interval_hours"],
                "default_max_age_days": self.config["default_max_age_days"],
                "default_max_length": self.config["default_max_length"],
                "dry_run": self.config["dry_run"],
                "protected_streams_count": len(self.config["protected_streams"]),
                "stream_specific_config_count": len(self.config["stream_specific_config"])
            }
        }

    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()

        print("\n📊 Stream清理调度器统计")
        print("=" * 60)
        print(f"总清理次数: {stats['scheduler_stats']['total_cleanups']}")
        print(f"处理Stream数: {stats['scheduler_stats']['streams_processed']}")
        print(f"按时间清理消息: {stats['scheduler_stats']['messages_trimmed_by_age']}")
        print(f"按长度清理消息: {stats['scheduler_stats']['messages_trimmed_by_length']}")
        print(f"保护Stream跳过: {stats['scheduler_stats']['protected_streams_skipped']}")
        print(f"错误数: {len(stats['scheduler_stats']['errors'])}")
        print(f"最后清理: {stats['scheduler_stats']['last_cleanup'] or '从未清理'}")
        print(f"最后成功清理: {stats['scheduler_stats']['last_successful_cleanup'] or '从未成功'}")
        print(f"启用状态: {'✅ 启用' if stats['config']['enabled'] else '❌ 禁用'}")
        print(f"清理间隔: {stats['config']['cleanup_interval_hours']} 小时")
        print(f"默认保留: {stats['config']['default_max_age_days']} 天")
        print(f"默认最大长度: {stats['config']['default_max_length']} 条")
        print(f"模拟模式: {'✅ 是' if stats['config']['dry_run'] else '❌ 否'}")
        print(f"保护Stream: {stats['config']['protected_streams_count']} 个")
        print(f"Stream特定配置: {stats['config']['stream_specific_config_count']} 个")
        print("=" * 60)


# 便捷函数
async def create_and_start_cleanup_scheduler(stream_manager, config: Optional[Dict] = None) -> StreamCleanupScheduler:
    """创建并启动清理调度器的便捷函数"""
    scheduler = StreamCleanupScheduler(stream_manager, config)

    try:
        started = await scheduler.start()
        if started:
            logger.info("✅ Stream清理调度器创建并启动成功")
        else:
            logger.info("ℹ️ Stream清理调度器创建但未启动（已禁用）")
    except Exception as e:
        logger.error(f"❌ 启动清理调度器失败: {e}")

    return scheduler


async def perform_one_time_cleanup(redis_url: str = "redis://localhost:6379/0",
                                 max_age_days: int = 30,
                                 max_length: int = 10000,
                                 dry_run: bool = True) -> Dict[str, Any]:
    """执行一次性清理的便捷函数"""
    try:
        from .stream_manager import RetryEnhancedRedisStreamManager

        # 创建管理器
        manager = RetryEnhancedRedisStreamManager(redis_url)
        await manager.connect()

        # 执行安全清理（针对所有Stream）
        all_streams_result = await manager.get_stream_metrics("stream:*")
        streams_found = all_streams_result.get("streams_found", 0)

        if streams_found == 0:
            await manager.close()
            return {
                "success": True,
                "message": "未找到Stream，无需清理",
                "dry_run": dry_run
            }

        # 对每个Stream执行清理
        results = []
        streams = all_streams_result.get("streams", {})

        for stream_name, stream_info in streams.items():
            cleanup_result = await manager.safe_stream_cleanup(
                stream=stream_name,
                max_age_days=max_age_days,
                max_length=max_length,
                dry_run=dry_run
            )
            results.append(cleanup_result)

        await manager.close()

        # 汇总结果
        success_count = sum(1 for r in results if r.get("success", False))
        total_trimmed = 0

        for r in results:
            cleanup_results = r.get("cleanup_results", {})
            age_result = cleanup_results.get("age_based_cleanup", {})
            length_result = cleanup_results.get("length_based_cleanup", {})

            if age_result.get("success", False):
                trimmed = age_result.get("trimmed_count", 0)
                if isinstance(trimmed, int):
                    total_trimmed += trimmed

            if length_result.get("success", False):
                trimmed = length_result.get("trimmed_count", 0)
                if isinstance(trimmed, int):
                    total_trimmed += trimmed

        return {
            "success": success_count == len(results),
            "dry_run": dry_run,
            "streams_processed": len(results),
            "streams_successful": success_count,
            "total_messages_trimmed": total_trimmed,
            "details": results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat()
        }


# 测试函数
async def test_cleanup_scheduler():
    """测试清理调度器"""
    print("🧪 测试Stream清理调度器...")

    try:
        from .stream_manager import RetryEnhancedRedisStreamManager

        # 创建管理器
        manager = RetryEnhancedRedisStreamManager()
        await manager.connect()

        # 创建调度器（模拟模式）
        scheduler = StreamCleanupScheduler(
            manager,
            config={
                "dry_run": True,
                "cleanup_interval_hours": 1,  # 测试用短间隔
                "max_streams_per_batch": 3    # 测试限制
            }
        )

        # 打印配置
        print(f"✅ 清理调度器创建成功")
        scheduler.print_stats()

        # 测试单次清理
        print("\n🔍 测试单次清理...")
        result = await scheduler.perform_scheduled_cleanup()

        print(f"清理结果: {'成功' if result.get('success') else '失败'}")
        print(f"处理Stream: {result.get('streams_processed', 0)} 个")
        print(f"清理消息: {result.get('total_messages_trimmed', 0)} 条")

        # 打印更新后的统计
        print("\n📊 清理后统计:")
        scheduler.print_stats()

        # 测试立即清理
        print("\n🚀 测试立即清理（手动触发）...")
        immediate_result = await scheduler.perform_immediate_cleanup(
            stream_pattern="stream:*test*",
            max_age_days=7
        )

        print(f"立即清理结果: {'成功' if immediate_result.get('success') else '失败'}")

        await manager.close()
        print("✅ 清理调度器测试完成")

        # 提示真实清理
        print("\n💡 提示: 要执行真实清理，请运行:")
        print("  scheduler = StreamCleanupScheduler(manager, config={'dry_run': False})")
        print("  await scheduler.perform_scheduled_cleanup()")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 直接运行测试
    import asyncio
    asyncio.run(test_cleanup_scheduler())