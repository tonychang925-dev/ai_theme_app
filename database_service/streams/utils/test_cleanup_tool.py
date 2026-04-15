# database_service/streams/utils/test_cleanup_tool.py
"""
测试环境清理工具 - 解决测试资源清理不完全问题
专门清理测试结束后残留的Stream和消费者组，避免占用Redis内存
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class TestCleanupTool:
    """测试清理工具 - 专门清理测试环境残留资源"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 config: Optional[Dict] = None, **kwargs):
        """
        初始化测试清理工具

        Args:
            redis_url: Redis连接URL
            config: 配置字典
            **kwargs: 额外的配置参数，会合并到config中
        """
        self.redis_url = redis_url
        self.config = config or {}

        # 将kwargs合并到config中
        if kwargs:
            self.config.update(kwargs)

        # 默认配置
        self.default_config = {
            "test_stream_patterns": [
                r"stream:.*test.*",
                r"stream:.*temp.*",
                r"stream:.*optimization.*",
                r"stream:.*cgm.*",
                r"stream:.*error.*handler.*",
                r"^test_.*",
                r"^temp_.*"
            ],
            "test_group_patterns": [
                r"test_.*",
                r"temp_.*",
                r"optimization.*",
                r"cgm.*",
                r"error_handler.*",
                r"theme_processors_real_.*",
                r"p2_.*"
            ],
            "protected_streams": [
                "stream:news:raw",
                "stream:events:structured",
                "stream:events:normal",
                "stream:events:major",
                "stream:themes:updates",
                "stream:dead:letter"
            ],
            "protected_groups": [
                "news_storage_handlers",
                "theme_processors_v1",
                "major_workers",
                "theme_workers",
                "data_updaters",
                "monitoring"
            ],
            "max_cleanup_age_hours": 24,
            "dry_run": False  # 是否仅模拟运行
        }

        # 更新配置
        self.default_config.update(self.config)
        self.config = self.default_config

        # Redis客户端（延迟初始化）
        self.redis: Optional[Redis] = None

        # 统计信息
        self.stats = {
            "total_cleanups": 0,
            "streams_cleaned": 0,
            "streams_protected": 0,
            "groups_cleaned": 0,
            "groups_protected": 0,
            "memory_freed_bytes": 0,
            "last_cleanup": None,
            "errors": []
        }

        logger.info(f"✅ 初始化测试清理工具，干运行模式: {'是' if self.config['dry_run'] else '否'}")

    async def connect(self) -> None:
        """连接Redis"""
        if self.redis is None:
            self.redis = await Redis.from_url(self.redis_url, decode_responses=True)
            logger.info("✅ Redis连接已建立")

    async def disconnect(self) -> None:
        """断开Redis连接"""
        if self.redis:
            await self.redis.aclose()
            self.redis = None
            logger.info("✅ Redis连接已关闭")

    async def cleanup_test_resources(self, force: bool = False) -> Dict[str, Any]:
        """
        清理测试资源（Stream和消费者组）

        Args:
            force: 是否强制清理（忽略保护规则）

        Returns:
            清理结果统计
        """
        await self.connect()

        logger.info(f"🧹 开始清理测试资源 (强制模式: {'是' if force else '否'})")

        cleanup_stats = {
            "timestamp": datetime.now().isoformat(),
            "streams_found": 0,
            "streams_cleaned": 0,
            "streams_protected": 0,
            "stream_errors": 0,
            "groups_found": 0,
            "groups_cleaned": 0,
            "groups_protected": 0,
            "group_errors": 0,
            "memory_freed_bytes": 0,
            "dry_run": self.config["dry_run"],
            "details": {
                "streams_cleaned": [],
                "streams_protected": [],
                "groups_cleaned": [],
                "groups_protected": []
            }
        }

        try:
            # 1. 清理测试Stream
            stream_stats = await self._cleanup_test_streams(force)
            cleanup_stats.update(stream_stats)

            # 2. 清理测试消费者组
            group_stats = await self._cleanup_test_consumer_groups(force)
            cleanup_stats.update(group_stats)

            # 3. 更新统计
            self.stats["total_cleanups"] += 1
            self.stats["streams_cleaned"] += cleanup_stats["streams_cleaned"]
            self.stats["streams_protected"] += cleanup_stats["streams_protected"]
            self.stats["groups_cleaned"] += cleanup_stats["groups_cleaned"]
            self.stats["groups_protected"] += cleanup_stats["groups_protected"]
            self.stats["memory_freed_bytes"] += cleanup_stats["memory_freed_bytes"]
            self.stats["last_cleanup"] = cleanup_stats["timestamp"]

            # 4. 记录总结
            total_freed_mb = cleanup_stats["memory_freed_bytes"] / (1024 * 1024)

            logger.info(f"✅ 测试资源清理完成:")
            logger.info(f"  Stream: 找到 {cleanup_stats['streams_found']} 个, "
                       f"清理 {cleanup_stats['streams_cleaned']} 个, "
                       f"保护 {cleanup_stats['streams_protected']} 个")
            logger.info(f"  消费者组: 找到 {cleanup_stats['groups_found']} 个, "
                       f"清理 {cleanup_stats['groups_cleaned']} 个, "
                       f"保护 {cleanup_stats['groups_protected']} 个")
            logger.info(f"  释放内存: {total_freed_mb:.2f} MB")

            return cleanup_stats

        except Exception as e:
            logger.error(f"❌ 清理测试资源失败: {e}")
            self.stats["errors"].append({
                "operation": "cleanup_test_resources",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    async def _cleanup_test_streams(self, force: bool = False) -> Dict[str, Any]:
        """清理测试Stream"""
        stats = {
            "streams_found": 0,
            "streams_cleaned": 0,
            "streams_protected": 0,
            "stream_errors": 0,
            "memory_freed_bytes": 0
        }

        try:
            # 获取所有Stream
            all_streams = await self._get_all_streams()

            for stream in all_streams:
                stats["streams_found"] += 1

                # 检查是否为测试Stream
                is_test_stream = self._is_test_stream(stream)

                if not is_test_stream:
                    stats["streams_protected"] += 1
                    continue

                # 检查是否为保护Stream
                if not force and stream in self.config["protected_streams"]:
                    stats["streams_protected"] += 1
                    continue

                # 清理Stream
                memory_before = await self._estimate_stream_memory(stream)

                if not self.config["dry_run"]:
                    try:
                        await self.redis.delete(stream)
                        stats["streams_cleaned"] += 1
                        stats["memory_freed_bytes"] += memory_before

                        logger.info(f"🧹 清理Stream: {stream} (释放约 {memory_before} 字节)")
                    except Exception as e:
                        stats["stream_errors"] += 1
                        logger.warning(f"清理Stream失败 {stream}: {e}")
                else:
                    stats["streams_cleaned"] += 1
                    stats["memory_freed_bytes"] += memory_before
                    logger.info(f"🧹 [干运行] 将清理Stream: {stream} (将释放约 {memory_before} 字节)")

        except Exception as e:
            logger.error(f"清理Stream过程中出错: {e}")
            stats["stream_errors"] += 1

        return stats

    async def _cleanup_test_consumer_groups(self, force: bool = False) -> Dict[str, Any]:
        """清理测试消费者组"""
        stats = {
            "groups_found": 0,
            "groups_cleaned": 0,
            "groups_protected": 0,
            "group_errors": 0
        }

        try:
            # 获取所有Stream
            all_streams = await self._get_all_streams()

            for stream in all_streams:
                try:
                    # 获取Stream的消费者组
                    groups_info = await self.redis.xinfo_groups(stream)

                    for group_info in groups_info:
                        stats["groups_found"] += 1
                        group_name = group_info["name"]

                        # 检查是否为测试组
                        is_test_group = self._is_test_group(group_name)

                        if not is_test_group:
                            stats["groups_protected"] += 1
                            continue

                        # 检查是否为保护组
                        if not force and group_name in self.config["protected_groups"]:
                            stats["groups_protected"] += 1
                            continue

                        # 检查消费者组活动状态
                        consumers = group_info.get("consumers", 0)
                        pending = group_info.get("pending", 0)

                        if consumers > 0 and not force:
                            logger.debug(f"跳过活跃消费者组: {stream}/{group_name} (消费者: {consumers})")
                            stats["groups_protected"] += 1
                            continue

                        # 清理消费者组
                        if not self.config["dry_run"]:
                            try:
                                await self.redis.xgroup_destroy(stream, group_name)
                                stats["groups_cleaned"] += 1
                                logger.info(f"🧹 清理消费者组: {stream}/{group_name}")
                            except Exception as e:
                                if "NOGROUP" in str(e):
                                    # 组已不存在
                                    stats["groups_cleaned"] += 1
                                else:
                                    stats["group_errors"] += 1
                                    logger.warning(f"清理消费者组失败 {stream}/{group_name}: {e}")
                        else:
                            stats["groups_cleaned"] += 1
                            logger.info(f"🧹 [干运行] 将清理消费者组: {stream}/{group_name}")

                except Exception as e:
                    logger.warning(f"处理Stream失败 {stream}: {e}")
                    continue

        except Exception as e:
            logger.error(f"清理消费者组过程中出错: {e}")
            stats["group_errors"] += 1

        return stats

    async def _get_all_streams(self, pattern: str = "stream:*") -> List[str]:
        """获取所有Stream名称"""
        try:
            streams = await self.redis.keys(pattern)
            return [s.decode('utf-8') if isinstance(s, bytes) else s for s in streams]
        except Exception as e:
            logger.warning(f"获取Stream列表失败: {e}")
            return []

    async def _estimate_stream_memory(self, stream: str) -> int:
        """估算Stream占用的内存（简化版）"""
        try:
            stream_info = await self.redis.xinfo_stream(stream)
            length = stream_info.get("length", 0)
            # 简单估算：每条消息约1KB
            return length * 1024
        except Exception as e:
            logger.debug(f"估算Stream内存失败 {stream}: {e}")
            return 0

    def _is_test_stream(self, stream_name: str) -> bool:
        """检查是否为测试Stream"""
        for pattern in self.config["test_stream_patterns"]:
            if re.match(pattern, stream_name, re.IGNORECASE):
                return True
        return False

    def _is_test_group(self, group_name: str) -> bool:
        """检查是否为测试消费者组"""
        for pattern in self.config["test_group_patterns"]:
            if re.match(pattern, group_name, re.IGNORECASE):
                return True
        return False

    async def get_test_resources_report(self) -> Dict[str, Any]:
        """获取测试资源报告"""
        await self.connect()

        report = {
            "timestamp": datetime.now().isoformat(),
            "test_streams": [],
            "test_groups": [],
            "summary": {
                "test_streams_count": 0,
                "test_groups_count": 0,
                "estimated_memory_bytes": 0
            }
        }

        try:
            # 查找测试Stream
            all_streams = await self._get_all_streams()

            for stream in all_streams:
                if self._is_test_stream(stream):
                    try:
                        stream_info = await self.redis.xinfo_stream(stream)
                        estimated_memory = await self._estimate_stream_memory(stream)

                        stream_detail = {
                            "name": stream,
                            "length": stream_info.get("length", 0),
                            "estimated_memory_bytes": estimated_memory,
                            "first_entry": stream_info.get("first-entry", {}),
                            "last_entry": stream_info.get("last-entry", {})
                        }

                        report["test_streams"].append(stream_detail)
                        report["summary"]["test_streams_count"] += 1
                        report["summary"]["estimated_memory_bytes"] += estimated_memory

                    except Exception as e:
                        report["test_streams"].append({
                            "name": stream,
                            "error": str(e)
                        })

            # 查找测试消费者组
            for stream in all_streams:
                try:
                    groups_info = await self.redis.xinfo_groups(stream)

                    for group_info in groups_info:
                        group_name = group_info["name"]

                        if self._is_test_group(group_name):
                            group_detail = {
                                "stream": stream,
                                "group": group_name,
                                "consumers": group_info.get("consumers", 0),
                                "pending": group_info.get("pending", 0),
                                "last_delivered": group_info.get("last-delivered-id", "0-0")
                            }

                            report["test_groups"].append(group_detail)
                            report["summary"]["test_groups_count"] += 1

                except Exception as e:
                    continue

        except Exception as e:
            report["error"] = str(e)

        return report

    def get_stats(self) -> Dict[str, Any]:
        """获取工具统计信息"""
        return {
            "cleanup_tool_stats": self.stats.copy(),
            "config": {
                "test_stream_patterns_count": len(self.config["test_stream_patterns"]),
                "test_group_patterns_count": len(self.config["test_group_patterns"]),
                "protected_streams_count": len(self.config["protected_streams"]),
                "protected_groups_count": len(self.config["protected_groups"]),
                "dry_run": self.config["dry_run"]
            }
        }

    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()

        print("\n📊 测试清理工具统计")
        print("=" * 60)
        print(f"总清理次数: {stats['cleanup_tool_stats']['total_cleanups']}")
        print(f"清理Stream数: {stats['cleanup_tool_stats']['streams_cleaned']}")
        print(f"保护Stream数: {stats['cleanup_tool_stats']['streams_protected']}")
        print(f"清理消费者组数: {stats['cleanup_tool_stats']['groups_cleaned']}")
        print(f"保护消费者组数: {stats['cleanup_tool_stats']['groups_protected']}")
        print(f"释放内存: {stats['cleanup_tool_stats']['memory_freed_bytes'] / (1024 * 1024):.2f} MB")
        print(f"最后清理: {stats['cleanup_tool_stats']['last_cleanup'] or '从未清理'}")
        print(f"错误数: {len(stats['cleanup_tool_stats']['errors'])}")
        print(f"干运行模式: {'✅ 是' if stats['config']['dry_run'] else '❌ 否'}")
        print(f"测试Stream模式: {stats['config']['test_stream_patterns_count']} 个")
        print(f"测试组模式: {stats['config']['test_group_patterns_count']} 个")
        print(f"保护Stream: {stats['config']['protected_streams_count']} 个")
        print(f"保护组: {stats['config']['protected_groups_count']} 个")
        print("=" * 60)


# 便捷函数
async def cleanup_test_environment(redis_url: str = "redis://localhost:6379/0",
                                  dry_run: bool = False) -> Dict[str, Any]:
    """清理测试环境的便捷函数"""
    tool = TestCleanupTool(redis_url, {"dry_run": dry_run})

    try:
        result = await tool.cleanup_test_resources()
        await tool.disconnect()
        return result
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


async def get_test_resources_report(redis_url: str = "redis://localhost:6379/0") -> Dict[str, Any]:
    """获取测试资源报告的便捷函数"""
    tool = TestCleanupTool(redis_url)

    try:
        report = await tool.get_test_resources_report()
        await tool.disconnect()
        return report
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# 测试函数
async def test_cleanup_tool():
    """测试清理工具"""
    print("🧪 测试清理工具...")

    try:
        # 创建清理工具（干运行模式）
        tool = TestCleanupTool(config={"dry_run": True})

        # 获取测试资源报告
        report = await tool.get_test_resources_report()
        print(f"📋 测试资源报告:")
        print(f"  测试Stream数: {report['summary']['test_streams_count']}")
        print(f"  测试消费者组数: {report['summary']['test_groups_count']}")
        print(f"  估计占用内存: {report['summary']['estimated_memory_bytes'] / 1024:.2f} KB")

        # 模拟清理
        cleanup_result = await tool.cleanup_test_resources()
        print(f"🧹 模拟清理结果:")
        print(f"  Stream: 找到 {cleanup_result.get('streams_found', 0)} 个, "
              f"清理 {cleanup_result.get('streams_cleaned', 0)} 个")
        print(f"  消费者组: 找到 {cleanup_result.get('groups_found', 0)} 个, "
              f"清理 {cleanup_result.get('groups_cleaned', 0)} 个")

        # 打印统计
        tool.print_stats()

        await tool.disconnect()

        print("✅ 清理工具测试完成")

        # 提示真实清理
        print("\n💡 提示: 要执行真实清理，请运行:")
        print("  await cleanup_test_environment(dry_run=False)")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_cleanup_tool())