#!/usr/bin/env python3
"""
Redis治理功能测试
验证Redis Stream治理功能，包括内存监控、消费者组管理、消息清理和性能优化
"""

import asyncio
import json
import sys
import logging
from datetime import datetime
from typing import Dict, Any, List

# 添加项目路径
sys.path.insert(0, '/Users/admin/desktop/ai_theme_app')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RedisGovernanceTest:
    """Redis治理功能测试类"""

    def __init__(self):
        self.test_results = []
        self.redis_client = None

    async def setup(self):
        """测试设置"""
        print("🔧 设置Redis治理测试环境...")

        try:
            import redis.asyncio as redis
            self.redis_client = await redis.from_url("redis://localhost:6379/0", decode_responses=True)

            # 测试连接
            await self.redis_client.ping()
            print("✅ Redis连接成功")
            return True

        except Exception as e:
            print(f"❌ Redis连接失败: {e}")
            return False

    async def test_memory_monitoring(self):
        """测试内存监控功能"""
        print("\n🧪 测试Redis内存监控...")

        try:
            # 获取Redis内存信息
            memory_info = await self.redis_client.info('memory')

            # 解析内存信息
            used_memory = int(memory_info.get('used_memory', 0))
            used_memory_human = memory_info.get('used_memory_human', '0B')
            maxmemory = int(memory_info.get('maxmemory', 0))

            # 计算内存使用率
            memory_usage_percent = (used_memory / maxmemory * 100) if maxmemory > 0 else 0

            print(f"  内存使用: {used_memory_human} ({memory_usage_percent:.1f}%)")

            # 检查内存使用是否过高
            if memory_usage_percent > 80:
                print(f"  ⚠️  警告: 内存使用率超过80% ({memory_usage_percent:.1f}%)")
                self.record_test_result("内存监控", True, f"内存使用率: {memory_usage_percent:.1f}% (警告)")
            else:
                print(f"  ✅ 内存使用正常: {memory_usage_percent:.1f}%")
                self.record_test_result("内存监控", True, f"内存使用率: {memory_usage_percent:.1f}%")

        except Exception as e:
            self.record_test_result("内存监控", False, f"内存监控失败: {e}")
            print(f"  ❌ 内存监控失败: {e}")

    async def test_stream_analysis(self):
        """测试Stream分析功能"""
        print("\n🧪 测试Stream分析...")

        try:
            # 获取所有Stream
            streams = await self.redis_client.keys("stream:*")
            stream_count = len(streams)

            print(f"  找到 {stream_count} 个Streams")

            # 分析每个Stream
            stream_details = []
            for stream in streams:
                stream_name = stream if isinstance(stream, str) else stream.decode('utf-8')

                try:
                    # 获取Stream信息
                    stream_info = await self.redis_client.xinfo_stream(stream_name)
                    length = stream_info.get('length', 0)

                    # 获取消费者组信息
                    groups_info = await self.redis_client.xinfo_groups(stream_name)
                    group_count = len(groups_info)

                    # 分析pending消息
                    total_pending = 0
                    for group_info in groups_info:
                        total_pending += group_info.get('pending', 0)

                    stream_details.append({
                        "stream": stream_name,
                        "length": length,
                        "groups": group_count,
                        "pending": total_pending
                    })

                except Exception as e:
                    print(f"    分析Stream失败 {stream_name}: {e}")

            # 统计信息
            total_messages = sum(s["length"] for s in stream_details)
            total_groups = sum(s["groups"] for s in stream_details)
            total_pending = sum(s["pending"] for s in stream_details)

            print(f"  总消息数: {total_messages}")
            print(f"  总消费者组数: {total_groups}")
            print(f"  总pending消息: {total_pending}")

            # 检查高pending消息
            high_pending_streams = [s for s in stream_details if s["pending"] > 100]
            if high_pending_streams:
                print(f"  ⚠️  警告: 发现高pending消息的Streams:")
                for stream in high_pending_streams:
                    print(f"    - {stream['stream']}: {stream['pending']}条pending")
                self.record_test_result("Stream分析", True, f"发现{len(high_pending_streams)}个高pending Stream")
            else:
                print(f"  ✅ 所有Stream pending消息正常")
                self.record_test_result("Stream分析", True, f"Stream分析完成: {stream_count}个Streams")

        except Exception as e:
            self.record_test_result("Stream分析", False, f"Stream分析失败: {e}")
            print(f"  ❌ Stream分析失败: {e}")

    async def test_consumer_group_management(self):
        """测试消费者组管理功能"""
        print("\n🧪 测试消费者组管理...")

        try:
            from scripts.redis_consumer_group_cleanup import EnhancedConsumerGroupCleanup

            # 创建清理器（干跑模式）
            config = {
                "dry_run": True,
                "max_group_age_hours": 24,
                "min_idle_time_minutes": 120,
                "max_pending_messages": 0,
                "report_file": "test_consumer_group_cleanup_report.json",
                "protected_groups": [
                    "news_storage_handlers",
                    "theme_processors_v1",
                    "major_workers",
                    "theme_workers",
                    "data_updaters",
                    "monitoring",
                    "news_business_processors"
                ]
            }

            cleanup = EnhancedConsumerGroupCleanup(self.redis_client, config)
            report = await cleanup.run_cleanup()

            # 分析报告
            stats = report.get("statistics", {})
            total_groups = stats.get("total_groups", 0)
            groups_cleaned = stats.get("groups_cleaned", 0)
            groups_protected = stats.get("groups_protected", 0)

            print(f"  总消费者组数: {total_groups}")
            print(f"  可清理组数: {groups_cleaned}")
            print(f"  保护组数: {groups_protected}")

            # 检查非活跃组
            if groups_cleaned > 0:
                print(f"  ⚠️  发现 {groups_cleaned} 个可清理的非活跃组")
                self.record_test_result("消费者组管理", True, f"发现{groups_cleaned}个可清理的非活跃组")
            else:
                print(f"  ✅ 没有发现可清理的非活跃组")
                self.record_test_result("消费者组管理", True, "消费者组管理正常")

        except ImportError:
            self.record_test_result("消费者组管理", False, "清理脚本导入失败")
            print(f"  ❌ 清理脚本导入失败")
        except Exception as e:
            self.record_test_result("消费者组管理", False, f"消费者组管理失败: {e}")
            print(f"  ❌ 消费者组管理失败: {e}")

    async def test_performance_monitoring(self):
        """测试性能监控功能"""
        print("\n🧪 测试Redis性能监控...")

        try:
            # 获取Redis性能信息
            stats_info = await self.redis_client.info('stats')
            cpu_info = await self.redis_client.info('cpu')

            # 解析关键性能指标
            total_connections = int(stats_info.get('total_connections_received', 0))
            total_commands = int(stats_info.get('total_commands_processed', 0))
            used_cpu_sys = float(cpu_info.get('used_cpu_sys', 0))
            used_cpu_user = float(cpu_info.get('used_cpu_user', 0))

            print(f"  总连接数: {total_connections}")
            print(f"  总命令数: {total_commands}")
            print(f"  CPU使用: 系统{used_cpu_sys:.1f}s, 用户{used_cpu_user:.1f}s")

            # 检查连接数是否过高
            if total_connections > 1000:
                print(f"  ⚠️  警告: 连接数较高 ({total_connections})")
                self.record_test_result("性能监控", True, f"连接数: {total_connections} (警告)")
            else:
                print(f"  ✅ 连接数正常")
                self.record_test_result("性能监控", True, "性能监控正常")

        except Exception as e:
            self.record_test_result("性能监控", False, f"性能监控失败: {e}")
            print(f"  ❌ 性能监控失败: {e}")

    async def test_high_pending_issue(self):
        """测试高pending消息问题处理"""
        print("\n🧪 测试高pending消息问题...")

        try:
            # 检查stream:events:normal/news_business_processors的高pending问题
            stream = "stream:events:normal"
            group = "news_business_processors"

            try:
                # 获取消费者组信息
                groups_info = await self.redis_client.xinfo_groups(stream)
                target_group = None

                for group_info in groups_info:
                    if group_info["name"] == group:
                        target_group = group_info
                        break

                if target_group:
                    pending_count = target_group.get("pending", 0)
                    consumers = target_group.get("consumers", 0)

                    print(f"  消费者组: {stream}/{group}")
                    print(f"  Pending消息: {pending_count}条")
                    print(f"  活跃消费者: {consumers}个")

                    if pending_count > 100:
                        print(f"  ⚠️  严重: 发现高pending消息 ({pending_count}条)")

                        # 分析可能的原因
                        if consumers == 0:
                            print(f"    原因: 没有活跃消费者")
                            recommendation = "增加消费者数量或重启消费者"
                        elif pending_count > 1000:
                            print(f"    原因: 消息积压严重")
                            recommendation = "优化消费者处理性能或增加消费者数量"
                        else:
                            print(f"    原因: 消费者处理速度不足")
                            recommendation = "优化消费者处理逻辑或增加消费者数量"

                        self.record_test_result("高pending问题", True,
                                              f"发现{pending_count}条pending消息 - {recommendation}")
                    else:
                        print(f"  ✅ Pending消息正常")
                        self.record_test_result("高pending问题", True, "Pending消息正常")
                else:
                    print(f"  ℹ️  消费者组不存在: {stream}/{group}")
                    self.record_test_result("高pending问题", True, "消费者组不存在")

            except Exception as e:
                if "NOGROUP" in str(e):
                    print(f"  ℹ️  消费者组不存在: {stream}/{group}")
                    self.record_test_result("高pending问题", True, "消费者组不存在")
                else:
                    raise e

        except Exception as e:
            self.record_test_result("高pending问题", False, f"高pending问题检查失败: {e}")
            print(f"  ❌ 高pending问题检查失败: {e}")

    def record_test_result(self, test_name: str, passed: bool, details: str):
        """记录测试结果"""
        self.test_results.append({
            "test_name": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("📋 Redis治理功能测试摘要")
        print("="*60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["passed"])
        failed_tests = total_tests - passed_tests

        print(f"总测试数: {total_tests}")
        print(f"通过测试: {passed_tests}")
        print(f"失败测试: {failed_tests}")
        print(f"通过率: {passed_tests/total_tests:.1%}" if total_tests > 0 else "通过率: N/A")

        if failed_tests > 0:
            print("\n❌ 失败测试:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  - {result['test_name']}: {result['details']}")

        print("\n✅ 通过测试:")
        for result in self.test_results:
            if result["passed"]:
                print(f"  - {result['test_name']}: {result['details']}")

        print("="*60)

        # 生成建议
        print("\n💡 治理建议:")

        # 检查高pending问题
        high_pending_result = next((r for r in self.test_results if r["test_name"] == "高pending问题"), None)
        if high_pending_result and "发现" in high_pending_result["details"]:
            print("1. 立即处理高pending消息问题")
            print("   - 增加news_business_processors消费者数量")
            print("   - 优化AI模型处理性能")
            print("   - 考虑批量处理消息")

        # 检查内存使用
        memory_result = next((r for r in self.test_results if r["test_name"] == "内存监控"), None)
        if memory_result and "警告" in memory_result["details"]:
            print("2. 监控Redis内存使用")
            print("   - 设置内存使用告警阈值")
            print("   - 定期清理过期数据")
            print("   - 考虑Redis集群部署")

        # 检查非活跃组
        group_result = next((r for r in self.test_results if r["test_name"] == "消费者组管理"), None)
        if group_result and "发现" in group_result["details"]:
            print("3. 清理非活跃消费者组")
            print("   - 运行清理脚本 (dry_run=False)")
            print("   - 建立定期清理机制")
            print("   - 规范测试组创建和清理")

        print("="*60)

        # 返回总体结果
        return passed_tests == total_tests

    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始Redis治理功能测试")
        print("="*60)

        try:
            # 设置测试环境
            setup_success = await self.setup()
            if not setup_success:
                print("❌ 测试环境设置失败")
                return False

            # 运行测试
            await self.test_memory_monitoring()
            await self.test_stream_analysis()
            await self.test_consumer_group_management()
            await self.test_performance_monitoring()
            await self.test_high_pending_issue()

            # 打印摘要
            all_passed = self.print_summary()

            # 保存测试结果
            with open("redis_governance_test_results.json", "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "success": all_passed,
                    "results": self.test_results,
                    "summary": {
                        "total": len(self.test_results),
                        "passed": sum(1 for r in self.test_results if r["passed"]),
                        "failed": sum(1 for r in self.test_results if not r["passed"])
                    }
                }, f, ensure_ascii=False, indent=2)

            print(f"\n📥 测试结果已保存到: redis_governance_test_results.json")

            if all_passed:
                print("🎉 Redis治理功能测试完成")
                return True
            else:
                print("⚠️  部分测试失败，请检查Redis治理功能")
                return False

        except Exception as e:
            print(f"❌ 测试执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 清理资源
            if self.redis_client:
                await self.redis_client.close()


async def main():
    """主函数"""
    tester = RedisGovernanceTest()
    success = await tester.run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)