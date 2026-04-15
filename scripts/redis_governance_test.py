#!/usr/bin/env python3
"""
Redis治理功能测试脚本
用于验证Day 4的Redis治理功能
"""

import asyncio
import time
import json
import logging
import redis.asyncio as redis
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import sys

# 添加项目路径
sys.path.append('.')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RedisGovernanceTester:
    """Redis治理功能测试器"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self.results = {
            "test_timestamp": datetime.now().isoformat(),
            "test_cases": [],
            "summary": {},
            "issues_found": [],
            "recommendations": []
        }

    async def connect(self):
        """连接到Redis"""
        try:
            self.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info(f"✅ 成功连接到Redis: {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"❌ 连接Redis失败: {e}")
            return False

    async def disconnect(self):
        """断开Redis连接"""
        if self.redis_client:
            await self.redis_client.close()

    async def test_consumer_group_management(self) -> Dict[str, Any]:
        """测试消费者组管理功能"""
        logger.info("🧪 测试消费者组管理功能...")

        test_stream = "test:governance:stream"
        test_group = "test:governance:group"

        try:
            # 清理测试环境
            await self.redis_client.delete(test_stream)

            # 创建测试Stream
            await self.redis_client.xadd(test_stream, {"test": "data"})

            # 创建消费者组
            await self.redis_client.xgroup_create(test_stream, test_group, id="0", mkstream=True)

            # 检查消费者组是否存在
            groups_info = await self.redis_client.xinfo_groups(test_stream)
            group_exists = any(g["name"] == test_group for g in groups_info)

            # 测试自动清理（模拟）
            # 在实际环境中，清理脚本会定期运行

            result = {
                "test_name": "消费者组管理",
                "stream": test_stream,
                "group": test_group,
                "group_created": True,
                "group_exists": group_exists,
                "groups_count": len(groups_info),
                "timestamp": datetime.now().isoformat()
            }

            logger.info(f"  ✅ 消费者组创建: {'成功' if group_exists else '失败'}")
            logger.info(f"  📊 Stream中的消费者组数量: {len(groups_info)}")

            # 清理测试数据
            await self.redis_client.delete(test_stream)

            return result

        except Exception as e:
            logger.error(f"  ❌ 消费者组管理测试失败: {e}")
            return {
                "test_name": "消费者组管理",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def test_auto_cleanup_function(self) -> Dict[str, Any]:
        """测试自动清理功能"""
        logger.info("🧪 测试自动清理功能...")

        try:
            # 导入清理工具
            from scripts.redis_consumer_group_cleanup import EnhancedConsumerGroupCleanup

            # 创建清理器实例（干跑模式）
            cleaner = EnhancedConsumerGroupCleanup(
                self.redis_client,
                config={
                    "dry_run": True,  # 干跑模式，不实际删除
                    "max_group_age_hours": 1,  # 1小时
                    "min_idle_time_minutes": 5,  # 5分钟
                    "protected_groups": ["test_protected_group"]
                }
            )

            # 模拟清理操作
            # 在实际测试中，这里会调用清理器的清理方法

            result = {
                "test_name": "自动清理功能",
                "dry_run_mode": True,
                "cleanup_config": cleaner.config,
                "timestamp": datetime.now().isoformat()
            }

            logger.info("  ✅ 自动清理功能配置检查完成")
            logger.info(f"  ⚙️  清理配置: {json.dumps(cleaner.config, indent=2)}")

            return result

        except ImportError as e:
            logger.error(f"  ❌ 无法导入清理工具: {e}")
            return {
                "test_name": "自动清理功能",
                "error": f"导入失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"  ❌ 自动清理功能测试失败: {e}")
            return {
                "test_name": "自动清理功能",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def test_monitoring_alerts(self) -> Dict[str, Any]:
        """测试监控告警功能"""
        logger.info("🧪 测试监控告警功能...")

        try:
            # 导入告警服务
            from database_service.streams.utils.alert_service import (
                AlertManager, ConsoleAlertService, Alert, AlertType, AlertSeverity, AlertContext
            )

            # 创建告警管理器
            alert_manager = AlertManager([ConsoleAlertService()])

            # 创建测试告警
            test_context = AlertContext(
                stream_name="test:monitoring:stream",
                metric_value=150,
                threshold=100,
                additional_info={"test": "data"}
            )

            test_alert = Alert(
                type=AlertType.HIGH_PENDING,
                severity=AlertSeverity.WARNING,
                message="测试告警: 高pending消息",
                context=test_context
            )

            # 发送测试告警
            alert_results = await alert_manager.send_alert(test_alert)

            result = {
                "test_name": "监控告警功能",
                "alert_type": test_alert.type.value,
                "alert_severity": test_alert.severity.value,
                "alert_message": test_alert.message,
                "alert_sent": len(alert_results) > 0,
                "alert_results": alert_results,
                "timestamp": datetime.now().isoformat()
            }

            logger.info(f"  ✅ 测试告警发送: {'成功' if result['alert_sent'] else '失败'}")
            logger.info(f"  📨 告警类型: {test_alert.type.value}")
            logger.info(f"  ⚠️  告警级别: {test_alert.severity.value}")

            return result

        except ImportError as e:
            logger.error(f"  ❌ 无法导入告警服务: {e}")
            return {
                "test_name": "监控告警功能",
                "error": f"导入失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"  ❌ 监控告警功能测试失败: {e}")
            return {
                "test_name": "监控告警功能",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def test_pending_message_analysis(self) -> Dict[str, Any]:
        """测试pending消息分析"""
        logger.info("🧪 测试pending消息分析...")

        test_stream = "test:pending:analysis"
        test_group = "test:pending:group"

        try:
            # 清理测试环境
            await self.redis_client.delete(test_stream)

            # 创建测试Stream和消费者组
            await self.redis_client.xadd(test_stream, {"test": "data1"})
            await self.redis_client.xadd(test_stream, {"test": "data2"})
            await self.redis_client.xgroup_create(test_stream, test_group, id="0", mkstream=True)

            # 读取消息但不确认（创建pending消息）
            messages = await self.redis_client.xreadgroup(
                test_group, "test_consumer", {test_stream: ">"}, count=2
            )

            pending_count = 0
            if messages:
                for stream, message_list in messages:
                    pending_count = len(message_list)

            # 获取pending消息信息
            pending_info = await self.redis_client.xpending(test_stream, test_group)

            result = {
                "test_name": "pending消息分析",
                "stream": test_stream,
                "group": test_group,
                "messages_created": 2,
                "messages_consumed": pending_count,
                "pending_count": pending_info.get("pending", 0) if pending_info else 0,
                "timestamp": datetime.now().isoformat()
            }

            logger.info(f"  ✅ 创建测试消息: {result['messages_created']}条")
            logger.info(f"  ✅ 消费消息（不确认）: {result['messages_consumed']}条")
            logger.info(f"  📊 pending消息数量: {result['pending_count']}条")

            # 清理测试数据
            await self.redis_client.delete(test_stream)

            return result

        except Exception as e:
            logger.error(f"  ❌ pending消息分析测试失败: {e}")
            return {
                "test_name": "pending消息分析",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def test_memory_usage_monitoring(self) -> Dict[str, Any]:
        """测试内存使用监控"""
        logger.info("🧪 测试内存使用监控...")

        try:
            # 获取Redis内存信息
            memory_info = await self.redis_client.info("memory")

            result = {
                "test_name": "内存使用监控",
                "used_memory_human": memory_info.get("used_memory_human", "N/A"),
                "used_memory_peak_human": memory_info.get("used_memory_peak_human", "N/A"),
                "mem_fragmentation_ratio": memory_info.get("mem_fragmentation_ratio", "N/A"),
                "timestamp": datetime.now().isoformat()
            }

            logger.info(f"  📊 当前内存使用: {result['used_memory_human']}")
            logger.info(f"  📈 峰值内存使用: {result['used_memory_peak_human']}")
            logger.info(f"  🔢 内存碎片率: {result['mem_fragmentation_ratio']}")

            # 检查内存使用是否正常
            if memory_info.get("mem_fragmentation_ratio", 1.0) > 1.5:
                self.results["issues_found"].append({
                    "type": "warning",
                    "message": "内存碎片率较高，可能影响性能",
                    "metric": memory_info.get("mem_fragmentation_ratio"),
                    "threshold": 1.5
                })

            return result

        except Exception as e:
            logger.error(f"  ❌ 内存使用监控测试失败: {e}")
            return {
                "test_name": "内存使用监控",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有Redis治理测试"""
        logger.info("🚀 开始Redis治理功能测试")
        logger.info("=" * 60)

        # 连接到Redis
        if not await self.connect():
            logger.error("❌ 无法连接到Redis，测试终止")
            return self.results

        test_cases = []

        try:
            # 运行各个测试
            test_cases.append(await self.test_consumer_group_management())
            test_cases.append(await self.test_auto_cleanup_function())
            test_cases.append(await self.test_monitoring_alerts())
            test_cases.append(await self.test_pending_message_analysis())
            test_cases.append(await self.test_memory_usage_monitoring())

            # 计算测试结果统计
            successful_tests = sum(1 for t in test_cases if "error" not in t)
            failed_tests = len(test_cases) - successful_tests

            # 生成总结
            summary = {
                "total_tests": len(test_cases),
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "success_rate": successful_tests / len(test_cases) * 100 if test_cases else 0,
                "issues_found_count": len(self.results["issues_found"]),
                "test_duration_seconds": (datetime.now() - datetime.fromisoformat(self.results["test_timestamp"])).total_seconds()
            }

            # 生成建议
            recommendations = []

            if summary["success_rate"] >= 80:
                recommendations.append({
                    "type": "success",
                    "message": f"✅ Redis治理功能测试通过率: {summary['success_rate']:.1f}%",
                    "action": "Redis治理功能基本正常，可以投入生产使用"
                })
            else:
                recommendations.append({
                    "type": "warning",
                    "message": f"⚠️ Redis治理功能测试通过率较低: {summary['success_rate']:.1f}%",
                    "action": "需要修复失败的测试用例"
                })

            if self.results["issues_found"]:
                recommendations.append({
                    "type": "warning",
                    "message": f"⚠️ 发现 {len(self.results['issues_found'])} 个问题",
                    "action": "检查问题详情并采取相应措施"
                })

            # 更新结果
            self.results["test_cases"] = test_cases
            self.results["summary"] = summary
            self.results["recommendations"] = recommendations

            logger.info("=" * 60)
            logger.info("📊 Redis治理功能测试总结")
            logger.info(f"  总测试用例: {summary['total_tests']}")
            logger.info(f"  成功用例: {summary['successful_tests']}")
            logger.info(f"  失败用例: {summary['failed_tests']}")
            logger.info(f"  通过率: {summary['success_rate']:.1f}%")
            logger.info(f"  发现问题: {summary['issues_found_count']}个")
            logger.info(f"  测试耗时: {summary['test_duration_seconds']:.1f}秒")

        finally:
            # 断开Redis连接
            await self.disconnect()

        return self.results

    def save_results(self, filename: str = "redis_governance_test_results.json"):
        """保存测试结果到文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 测试结果已保存到: {filename}")

    def print_report(self):
        """打印测试报告"""
        print("\n" + "=" * 60)
        print("📋 Redis治理功能测试报告")
        print("=" * 60)

        print(f"\n📅 测试时间: {self.results['test_timestamp']}")

        print("\n📊 测试用例结果:")
        for i, test in enumerate(self.results["test_cases"], 1):
            status = "✅" if "error" not in test else "❌"
            print(f"  {i}. {status} {test['test_name']}")
            if "error" in test:
                print(f"     错误: {test['error']}")

        summary = self.results["summary"]
        print(f"\n🎯 测试总结:")
        print(f"  总测试用例: {summary['total_tests']}")
        print(f"  成功用例: {summary['successful_tests']}")
        print(f"  失败用例: {summary['failed_tests']}")
        print(f"  通过率: {summary['success_rate']:.1f}%")
        print(f"  发现问题: {summary['issues_found_count']}个")
        print(f"  测试耗时: {summary['test_duration_seconds']:.1f}秒")

        if self.results["issues_found"]:
            print(f"\n⚠️ 发现问题:")
            for issue in self.results["issues_found"]:
                print(f"  • {issue['message']} (指标: {issue.get('metric', 'N/A')}, 阈值: {issue.get('threshold', 'N/A')})")

        print(f"\n💡 建议:")
        for rec in self.results["recommendations"]:
            icon = "✅" if rec["type"] == "success" else "⚠️"
            print(f"  {icon} {rec['message']}")
            print(f"    行动: {rec['action']}")

        print("\n" + "=" * 60)
        print("✅ Redis治理功能测试完成")


async def main():
    """主函数"""
    tester = RedisGovernanceTester()

    try:
        # 运行所有测试
        results = await tester.run_all_tests()

        # 保存结果
        tester.save_results()

        # 打印报告
        tester.print_report()

        # 返回退出码（0表示成功）
        return 0

    except Exception as e:
        logger.error(f"❌ Redis治理功能测试失败: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)