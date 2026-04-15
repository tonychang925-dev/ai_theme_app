# database_service/streams/utils/consumer_group_manager.py
"""
消费者组管理器 - 提供消费者组生命周期管理功能
优化消费者组泄漏问题，支持自动清理和监控
"""

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class ConsumerGroupManager:
    """消费者组管理器 - 优化消费者组生命周期管理"""

    def __init__(self, redis_client, config: Optional[Dict] = None):
        """
        初始化消费者组管理器

        Args:
            redis_client: Redis异步客户端
            config: 配置字典
        """
        self.redis = redis_client
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "cleanup_enabled": True,
            "max_group_age_hours": 24,
            "cleanup_interval_minutes": 60,
            "fixed_group_prefixes": [
                "news_storage_handlers",
                "theme_processors_v1",
                "major_workers",
                "theme_workers",
                "data_updaters",
                "monitoring"
            ],
            "test_group_patterns": [
                r"theme_processors_real_.*",
                r"test_.*",
                r"temp_.*",
                r"p2_.*"
            ],
            "protected_groups": [
                "news_storage_handlers",
                "monitoring"
            ]
        }

        # 更新配置
        self.default_config.update(self.config)
        self.config = self.default_config

        # 统计信息
        self.stats = {
            "created_groups": 0,
            "cleaned_groups": 0,
            "protected_groups": 0,
            "last_cleanup": None,
            "total_operations": 0,
            "errors": []
        }

        logger.info(f"✅ 初始化消费者组管理器，清理功能: {'启用' if self.config['cleanup_enabled'] else '禁用'}")

    async def ensure_consumer_group(self, stream: str, group: str,
                                   mkstream: bool = True,
                                   is_test_group: bool = False) -> bool:
        """
        确保消费者组存在，提供统一的创建逻辑

        Args:
            stream: Stream名称
            group: 消费者组名称
            mkstream: 是否创建Stream（如果不存在）
            is_test_group: 是否为测试组（用于标记清理）

        Returns:
            bool: 是否成功
        """
        self.stats["total_operations"] += 1

        try:
            # 检查是否为测试组并需要固定名称
            if is_test_group and self._should_use_fixed_group(group):
                fixed_group = self._get_fixed_group_name(stream)
                logger.info(f"🔧 测试组使用固定名称: {group} -> {fixed_group}")
                group = fixed_group

            # 创建消费者组
            result = await self.redis.xgroup_create(
                stream, group, id="0", mkstream=mkstream
            )

            logger.info(f"✅ 创建消费者组成功: {stream}/{group}")
            self.stats["created_groups"] += 1

            # 标记测试组（如果适用）
            if is_test_group:
                await self._mark_test_group(stream, group)

            return True

        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"消费者组已存在: {stream}/{group}")
                return True
            else:
                logger.error(f"创建消费者组失败 {stream}/{group}: {e}")
                self.stats["errors"].append({
                    "operation": "ensure_consumer_group",
                    "stream": stream,
                    "group": group,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                return False

    async def cleanup_old_groups(self, pattern: Optional[str] = None,
                               max_age_hours: Optional[int] = None) -> Dict[str, Any]:
        """
        清理旧的消费者组（特别是测试创建的组）

        Args:
            pattern: 匹配模式，如 "theme_processors_real_*"
            max_age_hours: 最大年龄（小时）

        Returns:
            清理结果统计
        """
        if not self.config["cleanup_enabled"]:
            logger.info("清理功能已禁用")
            return {"enabled": False, "cleaned": 0}

        max_age = max_age_hours or self.config["max_group_age_hours"]
        patterns = [pattern] if pattern else self.config["test_group_patterns"]

        logger.info(f"🧹 开始清理消费者组，最大年龄: {max_age}小时")

        cleanup_stats = {
            "total_groups_found": 0,
            "groups_cleaned": 0,
            "groups_protected": 0,
            "errors": 0,
            "details": []
        }

        try:
            # 获取所有Stream
            streams = await self._get_all_streams()

            for stream in streams:
                try:
                    # 获取Stream的消费者组信息
                    groups_info = await self.redis.xinfo_groups(stream)

                    for group_info in groups_info:
                        group_name = group_info["name"]
                        cleanup_stats["total_groups_found"] += 1

                        # 检查是否应该清理
                        should_clean = await self._should_cleanup_group(
                            stream, group_name, group_info, patterns, max_age
                        )

                        if should_clean:
                            # 执行清理
                            success = await self._cleanup_single_group(stream, group_name)

                            if success:
                                cleanup_stats["groups_cleaned"] += 1
                                cleanup_stats["details"].append({
                                    "stream": stream,
                                    "group": group_name,
                                    "action": "cleaned",
                                    "timestamp": datetime.now().isoformat()
                                })
                                logger.info(f"🧹 清理消费者组: {stream}/{group_name}")
                            else:
                                cleanup_stats["errors"] += 1
                        else:
                            cleanup_stats["groups_protected"] += 1

                except Exception as e:
                    logger.warning(f"处理Stream失败 {stream}: {e}")
                    continue

            # 更新统计
            self.stats["cleaned_groups"] += cleanup_stats["groups_cleaned"]
            self.stats["protected_groups"] += cleanup_stats["groups_protected"]
            self.stats["last_cleanup"] = datetime.now().isoformat()

            logger.info(f"✅ 消费者组清理完成: 找到 {cleanup_stats['total_groups_found']} 个组, "
                       f"清理 {cleanup_stats['groups_cleaned']} 个, "
                       f"保护 {cleanup_stats['groups_protected']} 个")

            return cleanup_stats

        except Exception as e:
            logger.error(f"清理消费者组失败: {e}")
            return {"error": str(e), "cleaned": 0}

    async def get_consumer_group_info(self, stream: Optional[str] = None) -> Dict[str, Any]:
        """
        获取消费者组信息

        Args:
            stream: 可选的Stream名称，为None时获取所有Stream

        Returns:
            消费者组信息
        """
        try:
            if stream:
                # 获取单个Stream的消费者组
                groups_info = await self.redis.xinfo_groups(stream)
                return {
                    "stream": stream,
                    "groups": groups_info,
                    "total_groups": len(groups_info)
                }
            else:
                # 获取所有Stream的消费者组
                streams = await self._get_all_streams()

                all_groups = {}
                for s in streams:
                    try:
                        groups_info = await self.redis.xinfo_groups(s)
                        all_groups[s] = {
                            "groups": groups_info,
                            "count": len(groups_info)
                        }
                    except Exception as e:
                        all_groups[s] = {"error": str(e)}

                return {
                    "streams": all_groups,
                    "total_streams": len(streams)
                }

        except Exception as e:
            logger.error(f"获取消费者组信息失败: {e}")
            return {"error": str(e)}

    async def monitor_consumer_groups(self) -> Dict[str, Any]:
        """
        监控消费者组状态，检测异常

        Returns:
            监控报告
        """
        try:
            streams = await self._get_all_streams()

            report = {
                "timestamp": datetime.now().isoformat(),
                "total_streams": len(streams),
                "stream_details": {},
                "alerts": [],
                "summary": {
                    "total_groups": 0,
                    "groups_with_pending": 0,
                    "groups_with_lag": 0,
                    "inactive_groups": 0
                }
            }

            for stream in streams:
                try:
                    groups_info = await self.redis.xinfo_groups(stream)

                    stream_detail = {
                        "stream": stream,
                        "total_groups": len(groups_info),
                        "groups": []
                    }

                    for group_info in groups_info:
                        group_name = group_info["name"]
                        pending = group_info.get("pending", 0)
                        consumers = group_info.get("consumers", 0)
                        last_delivered = group_info.get("last-delivered-id", "0-0")

                        # 计算lag（简化版）
                        lag = await self._estimate_group_lag(stream, last_delivered)

                        group_detail = {
                            "name": group_name,
                            "pending": pending,
                            "consumers": consumers,
                            "last_delivered": last_delivered,
                            "estimated_lag": lag,
                            "status": "active" if consumers > 0 else "inactive"
                        }

                        stream_detail["groups"].append(group_detail)

                        # 更新摘要
                        report["summary"]["total_groups"] += 1
                        if pending > 0:
                            report["summary"]["groups_with_pending"] += 1
                        if lag > 10:  # 假设lag>10为异常
                            report["summary"]["groups_with_lag"] += 1
                        if consumers == 0:
                            report["summary"]["inactive_groups"] += 1

                        # 检测警报
                        if pending > 100:
                            report["alerts"].append({
                                "level": "warning",
                                "message": f"高pending消息: {stream}/{group_name} ({pending}条)",
                                "stream": stream,
                                "group": group_name,
                                "metric": "pending",
                                "value": pending
                            })

                        if lag > 100:
                            report["alerts"].append({
                                "level": "critical",
                                "message": f"高处理延迟: {stream}/{group_name} (lag={lag})",
                                "stream": stream,
                                "group": group_name,
                                "metric": "lag",
                                "value": lag
                            })

                    report["stream_details"][stream] = stream_detail

                except Exception as e:
                    report["stream_details"][stream] = {"error": str(e)}

            return report

        except Exception as e:
            logger.error(f"监控消费者组失败: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    # ========== 私有方法 ==========

    async def _get_all_streams(self, pattern: str = "stream:*") -> List[str]:
        """获取所有Stream名称"""
        try:
            streams = await self.redis.keys(pattern)
            return [s.decode('utf-8') if isinstance(s, bytes) else s for s in streams]
        except Exception as e:
            logger.warning(f"获取Stream列表失败: {e}")
            return []

    async def _should_cleanup_group(self, stream: str, group: str,
                                  group_info: Dict, patterns: List[str],
                                  max_age_hours: int) -> bool:
        """判断是否应该清理消费者组"""
        # 1. 检查是否为保护组
        if group in self.config["protected_groups"]:
            logger.debug(f"保护组跳过清理: {stream}/{group}")
            return False

        # 2. 检查是否匹配清理模式
        matches_pattern = False
        for pattern in patterns:
            if re.match(pattern, group):
                matches_pattern = True
                break

        if not matches_pattern:
            return False

        # 3. 检查消费者组活动状态
        consumers = group_info.get("consumers", 0)
        if consumers > 0:
            logger.debug(f"活跃组跳过清理: {stream}/{group} (消费者: {consumers})")
            return False

        # 4. 检查年龄（通过最后投递ID估算）
        last_delivered = group_info.get("last-delivered-id", "0-0")
        if last_delivered == "0-0":
            # 从未消费过消息，可能是新创建的测试组
            return True

        # 简单年龄检查：如果pending为0且最近无活动，可清理
        pending = group_info.get("pending", 0)
        if pending == 0:
            # 尝试获取最后消息时间
            try:
                # 获取最后一条消息的时间戳
                last_message = await self.redis.xrevrange(stream, count=1)
                if last_message:
                    # 这里简化处理，实际应该比较消息时间戳
                    return True
            except:
                pass

        return False

    async def _cleanup_single_group(self, stream: str, group: str) -> bool:
        """清理单个消费者组"""
        try:
            await self.redis.xgroup_destroy(stream, group)
            return True
        except Exception as e:
            if "NOGROUP" in str(e):
                # 组已不存在
                return True
            logger.error(f"清理消费者组失败 {stream}/{group}: {e}")
            return False

    async def _estimate_group_lag(self, stream: str, last_delivered_id: str) -> int:
        """估算消费者组lag（简化版）"""
        try:
            if last_delivered_id == "0-0":
                return 0

            # 获取Stream总消息数
            stream_info = await self.redis.xinfo_stream(stream)
            total_messages = stream_info.get("length", 0)

            if total_messages == 0:
                return 0

            # 简单估算：获取最后投递ID之后的消息数
            # 注意：这是简化实现，实际应该使用XPENDING等命令
            return 0  # 暂时返回0，需要更复杂的实现

        except Exception as e:
            logger.debug(f"估算lag失败: {e}")
            return 0

    def _should_use_fixed_group(self, group_name: str) -> bool:
        """检查是否应该使用固定组名（针对测试组）"""
        for pattern in self.config["test_group_patterns"]:
            if re.match(pattern, group_name):
                return True
        return False

    def _get_fixed_group_name(self, stream: str) -> str:
        """根据Stream获取固定组名"""
        stream_to_group = {
            "stream:news:raw": "news_storage_handlers",
            "stream:events:structured": "theme_processors_v1",
            "stream:events:normal": "theme_workers",
            "stream:events:major": "major_workers",
            "stream:themes:updates": "data_updaters",
            "stream:dead:letter": "monitoring"
        }

        return stream_to_group.get(stream, f"fixed_{stream.replace(':', '_')}")

    async def _mark_test_group(self, stream: str, group: str):
        """标记测试组（用于跟踪）"""
        try:
            key = f"test_group:{stream}:{group}"
            await self.redis.setex(key, 3600 * 24, "true")  # 24小时过期
        except Exception as e:
            logger.debug(f"标记测试组失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            "manager_stats": self.stats.copy(),
            "config": {
                "cleanup_enabled": self.config["cleanup_enabled"],
                "max_group_age_hours": self.config["max_group_age_hours"],
                "protected_groups_count": len(self.config["protected_groups"])
            }
        }

    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()

        print("\n📊 消费者组管理器统计")
        print("=" * 60)
        print(f"总操作数: {stats['manager_stats']['total_operations']}")
        print(f"创建组数: {stats['manager_stats']['created_groups']}")
        print(f"清理组数: {stats['manager_stats']['cleaned_groups']}")
        print(f"保护组数: {stats['manager_stats']['protected_groups']}")
        print(f"最后清理: {stats['manager_stats']['last_cleanup'] or '从未清理'}")
        print(f"错误数: {len(stats['manager_stats']['errors'])}")
        print(f"清理功能: {'✅ 启用' if stats['config']['cleanup_enabled'] else '⏸️ 禁用'}")
        print(f"最大组年龄: {stats['config']['max_group_age_hours']}小时")
        print(f"受保护组: {stats['config']['protected_groups_count']}个")
        print("=" * 60)


# 便捷函数
async def create_consumer_group_manager(redis_client, config: Optional[Dict] = None) -> ConsumerGroupManager:
    """创建消费者组管理器的便捷函数"""
    return ConsumerGroupManager(redis_client, config)


async def cleanup_test_consumer_groups(redis_url: str = "redis://localhost:6379/0") -> Dict[str, Any]:
    """清理测试消费者组的便捷函数"""
    import redis.asyncio as redis

    try:
        redis_client = await redis.from_url(redis_url, decode_responses=True)
        manager = ConsumerGroupManager(redis_client)

        result = await manager.cleanup_old_groups()

        await redis_client.close()

        return result

    except Exception as e:
        return {"error": str(e)}


# 测试函数
async def test_consumer_group_manager():
    """测试消费者组管理器"""
    import redis.asyncio as redis

    print("🧪 测试消费者组管理器...")

    try:
        # 创建Redis客户端
        redis_client = await redis.from_url("redis://localhost:6379/0", decode_responses=True)

        # 创建管理器
        manager = await create_consumer_group_manager(redis_client)

        # 测试确保消费者组
        test_stream = "stream:test:manager"
        test_group = "test_manager_group"

        success = await manager.ensure_consumer_group(test_stream, test_group, is_test_group=True)
        print(f"创建消费者组: {success}")

        # 获取消费者组信息
        info = await manager.get_consumer_group_info(test_stream)
        print(f"消费者组信息: {info}")

        # 监控测试
        monitor = await manager.monitor_consumer_groups()
        print(f"监控报告: {len(monitor.get('alerts', []))} 个警报")

        # 清理测试（可选）
        # cleanup = await manager.cleanup_old_groups(pattern="test_.*")
        # print(f"清理结果: {cleanup}")

        # 打印统计
        manager.print_stats()

        # 清理测试Stream
        await redis_client.delete(test_stream)

        await redis_client.close()

        print("✅ 消费者组管理器测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_consumer_group_manager())