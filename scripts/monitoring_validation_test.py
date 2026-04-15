#!/usr/bin/env python3
"""
监控体系验证测试脚本
验证alert_service.py的告警触发机制和监控指标准确性
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_service.streams.utils.alert_service import (
    AlertSeverity, AlertType, Alert, AlertContext,
    ConsoleAlertService, AlertManager, get_default_alert_manager,
    init_alert_manager
)

# 模拟StreamDefinition类
class MockStreamDefinition:
    """模拟StreamDefinition用于测试"""
    def __init__(self, alert_on_backlog=True, backlog_threshold=100,
                 alert_on_stuck=True, stuck_threshold_ms=60000):
        self.alert_on_backlog = alert_on_backlog
        self.backlog_threshold = backlog_threshold
        self.alert_on_stuck = alert_on_stuck
        self.stuck_threshold_ms = stuck_threshold_ms


class MonitoringValidationTest:
    """监控验证测试类"""

    def __init__(self):
        self.test_results = []
        self.alert_manager = None
        self.console_service = None

    async def setup(self):
        """设置测试环境"""
        print("🔧 设置监控验证测试环境...")

        # 创建控制台告警服务
        self.console_service = ConsoleAlertService(name="test_console", enabled=True)

        # 初始化告警管理器
        init_alert_manager([self.console_service])
        self.alert_manager = get_default_alert_manager()

        print("✅ 测试环境设置完成")

    async def test_alert_severity_levels(self):
        """测试告警级别"""
        print("\n📊 测试告警级别...")

        test_cases = [
            (AlertSeverity.INFO, "信息级别告警"),
            (AlertSeverity.WARNING, "警告级别告警"),
            (AlertSeverity.ERROR, "错误级别告警"),
            (AlertSeverity.CRITICAL, "严重级别告警"),
        ]

        for severity, description in test_cases:
            alert = Alert(
                type=AlertType.GENERAL,
                severity=severity,
                message=f"测试{description}",
                context=AlertContext(
                    stream_name="test_stream",
                    metric_value=100,
                    threshold=50
                )
            )

            results = await self.alert_manager.send_alert(alert)
            success = any(r.get("success", False) for r in results)

            self.test_results.append({
                "test": f"告警级别测试 - {severity.value}",
                "success": success,
                "description": description
            })

            print(f"  {'✅' if success else '❌'} {severity.value}: {description}")

        return all(r["success"] for r in self.test_results[-len(test_cases):])

    async def test_alert_types(self):
        """测试告警类型"""
        print("\n📊 测试告警类型...")

        test_cases = [
            (AlertType.BACKLOG, "积压告警", 150, 100),
            (AlertType.STUCK_MESSAGE, "卡住消息告警", 120000, 60000),
            (AlertType.LOW_SUCCESS_RATE, "低成功率告警", 0.85, 0.9),
            (AlertType.AGING_STREAM, "Stream老化告警", 35, 30),
            (AlertType.LARGE_STREAM, "大型Stream告警", 6000, 5000),
            (AlertType.INACTIVE_GROUP, "非活跃消费者组告警", 8, 7),
            (AlertType.HIGH_PENDING, "高pending消息告警", 150, 100),
            (AlertType.ERROR_RATE, "高错误率告警", 0.15, 0.1),
        ]

        for alert_type, description, metric_value, threshold in test_cases:
            # 使用服务的方法生成告警
            if alert_type == AlertType.BACKLOG:
                stream_config = MockStreamDefinition(backlog_threshold=threshold)
                alert = self.console_service.check_backlog_alert(
                    "test_stream", stream_config, metric_value
                )
            elif alert_type == AlertType.STUCK_MESSAGE:
                stream_config = MockStreamDefinition(stuck_threshold_ms=threshold)
                alert = self.console_service.check_stuck_message_alert(
                    "test_stream", stream_config, metric_value
                )
            elif alert_type == AlertType.LOW_SUCCESS_RATE:
                alert = self.console_service.check_success_rate_alert(
                    "test_operation", metric_value, threshold
                )
            elif alert_type == AlertType.AGING_STREAM:
                alert = self.console_service.check_aging_stream_alert(
                    "test_stream", metric_value, threshold
                )
            elif alert_type == AlertType.LARGE_STREAM:
                alert = self.console_service.check_large_stream_alert(
                    "test_stream", metric_value, threshold
                )
            elif alert_type == AlertType.INACTIVE_GROUP:
                alert = self.console_service.check_inactive_group_alert(
                    "test_stream", "test_group", metric_value
                )
            elif alert_type == AlertType.HIGH_PENDING:
                alert = self.console_service.check_high_pending_alert(
                    "test_stream", "test_group", metric_value, threshold
                )
            else:
                # 通用告警
                alert = Alert(
                    type=alert_type,
                    severity=AlertSeverity.WARNING,
                    message=f"测试{description}",
                    context=AlertContext(
                        stream_name="test_stream",
                        metric_value=metric_value,
                        threshold=threshold
                    )
                )

            if alert:
                results = await self.alert_manager.send_alert(alert)
                success = any(r.get("success", False) for r in results)
            else:
                success = False

            self.test_results.append({
                "test": f"告警类型测试 - {alert_type.value}",
                "success": success,
                "description": f"{description} (值: {metric_value}, 阈值: {threshold})"
            })

            print(f"  {'✅' if success else '❌'} {alert_type.value}: {description}")

        return all(r["success"] for r in self.test_results[-len(test_cases):])

    async def test_threshold_accuracy(self):
        """测试阈值准确性"""
        print("\n📊 测试阈值准确性...")

        # 测试积压告警阈值
        backlog_test_cases = [
            (90, 100, False, "低于阈值不应触发"),
            (100, 100, False, "等于阈值不应触发"),
            (101, 100, True, "超过阈值应触发"),
            (200, 100, True, "大幅超过阈值应触发"),
        ]

        for backlog_count, threshold, should_trigger, description in backlog_test_cases:
            stream_config = MockStreamDefinition(backlog_threshold=threshold)
            alert = self.console_service.check_backlog_alert(
                "test_stream", stream_config, backlog_count
            )

            triggered = alert is not None
            success = triggered == should_trigger

            self.test_results.append({
                "test": f"阈值准确性测试 - 积压告警",
                "success": success,
                "description": f"积压数: {backlog_count}, 阈值: {threshold}, {description}"
            })

            print(f"  {'✅' if success else '❌'} 积压{backlog_count}/{threshold}: {description}")

        # 测试成功率告警阈值
        success_rate_cases = [
            (0.91, 0.9, False, "高于阈值不应触发"),
            (0.90, 0.9, False, "等于阈值不应触发"),
            (0.89, 0.9, True, "低于阈值应触发"),
            (0.70, 0.9, True, "大幅低于阈值应触发"),
        ]

        for success_rate, threshold, should_trigger, description in success_rate_cases:
            alert = self.console_service.check_success_rate_alert(
                "test_operation", success_rate, threshold
            )

            triggered = alert is not None
            success = triggered == should_trigger

            self.test_results.append({
                "test": f"阈值准确性测试 - 成功率告警",
                "success": success,
                "description": f"成功率: {success_rate}, 阈值: {threshold}, {description}"
            })

            print(f"  {'✅' if success else '❌'} 成功率{success_rate}/{threshold}: {description}")

        return all(r["success"] for r in self.test_results[-len(backlog_test_cases) - len(success_rate_cases):])

    async def test_severity_calculation(self):
        """测试告警级别计算"""
        print("\n📊 测试告警级别计算...")

        # 测试积压告警级别
        backlog_cases = [
            (101, 100, AlertSeverity.WARNING, "轻微超过阈值应为WARNING"),
            (250, 100, AlertSeverity.ERROR, "大幅超过阈值应为ERROR"),
        ]

        for backlog_count, threshold, expected_severity, description in backlog_cases:
            stream_config = MockStreamDefinition(backlog_threshold=threshold)
            alert = self.console_service.check_backlog_alert(
                "test_stream", stream_config, backlog_count
            )

            if alert:
                success = alert.severity == expected_severity
                severity_str = alert.severity.value
            else:
                success = False
                severity_str = "无告警"

            self.test_results.append({
                "test": f"告警级别计算测试 - 积压告警",
                "success": success,
                "description": f"积压{backlog_count}/{threshold}: {description} (实际: {severity_str})"
            })

            print(f"  {'✅' if success else '❌'} 积压{backlog_count}/{threshold}: {description}")

        # 测试卡住消息告警级别
        stuck_cases = [
            (61000, 60000, AlertSeverity.WARNING, "轻微超过阈值应为WARNING"),
            (130000, 60000, AlertSeverity.ERROR, "大幅超过阈值应为ERROR"),
        ]

        for age_ms, threshold, expected_severity, description in stuck_cases:
            stream_config = MockStreamDefinition(stuck_threshold_ms=threshold)
            alert = self.console_service.check_stuck_message_alert(
                "test_stream", stream_config, age_ms
            )

            if alert:
                success = alert.severity == expected_severity
                severity_str = alert.severity.value
            else:
                success = False
                severity_str = "无告警"

            self.test_results.append({
                "test": f"告警级别计算测试 - 卡住消息告警",
                "success": success,
                "description": f"年龄{age_ms}ms/{threshold}ms: {description} (实际: {severity_str})"
            })

            print(f"  {'✅' if success else '❌'} 年龄{age_ms}ms/{threshold}ms: {description}")

        return all(r["success"] for r in self.test_results[-len(backlog_cases) - len(stuck_cases):])

    async def test_alert_manager_stats(self):
        """测试告警管理器统计"""
        print("\n📊 测试告警管理器统计...")

        # 发送一些测试告警
        test_alerts = [
            Alert(
                type=AlertType.BACKLOG,
                severity=AlertSeverity.WARNING,
                message="测试统计告警1",
                context=AlertContext(stream_name="test_stream1")
            ),
            Alert(
                type=AlertType.ERROR_RATE,
                severity=AlertSeverity.ERROR,
                message="测试统计告警2",
                context=AlertContext(stream_name="test_stream2")
            ),
            Alert(
                type=AlertType.GENERAL,
                severity=AlertSeverity.INFO,
                message="测试统计告警3",
                context=AlertContext(stream_name="test_stream3")
            ),
        ]

        for alert in test_alerts:
            await self.alert_manager.send_alert(alert)

        # 获取统计信息
        manager_stats = self.alert_manager.get_stats()
        service_stats = self.console_service.get_stats()

        # 验证统计
        checks = [
            (manager_stats["total_alerts_sent"] >= 3, f"总告警数: {manager_stats['total_alerts_sent']}"),
            (manager_stats["last_alert_time"] is not None, "最后告警时间不为空"),
            (service_stats["total_alerts"] >= 3, f"服务告警数: {service_stats['total_alerts']}"),
            ("backlog" in service_stats["alerts_by_type"], "积压告警类型统计"),
            ("warning" in service_stats["alerts_by_severity"], "警告级别统计"),
            ("error" in service_stats["alerts_by_severity"], "错误级别统计"),
        ]

        for check_passed, description in checks:
            self.test_results.append({
                "test": "告警管理器统计测试",
                "success": check_passed,
                "description": description
            })

            print(f"  {'✅' if check_passed else '❌'} {description}")

        return all(check_passed for check_passed, _ in checks)

    async def test_alert_context_integrity(self):
        """测试告警上下文完整性"""
        print("\n📊 测试告警上下文完整性...")

        alert = Alert(
            type=AlertType.BACKLOG,
            severity=AlertSeverity.WARNING,
            message="测试上下文完整性",
            context=AlertContext(
                stream_name="test_stream",
                metric_value=150,
                threshold=100,
                additional_info={"test_key": "test_value"}
            )
        )

        # 转换为字典并验证
        alert_dict = alert.to_dict()

        checks = [
            (alert_dict["type"] == "backlog", f"类型: {alert_dict['type']}"),
            (alert_dict["severity"] == "warning", f"级别: {alert_dict['severity']}"),
            (alert_dict["context"]["stream_name"] == "test_stream", f"Stream: {alert_dict['context']['stream_name']}"),
            (alert_dict["context"]["metric_value"] == 150, f"指标值: {alert_dict['context']['metric_value']}"),
            (alert_dict["context"]["threshold"] == 100, f"阈值: {alert_dict['context']['threshold']}"),
            (alert_dict["context"]["additional_info"]["test_key"] == "test_value", "附加信息"),
        ]

        for check_passed, description in checks:
            self.test_results.append({
                "test": "告警上下文完整性测试",
                "success": check_passed,
                "description": description
            })

            print(f"  {'✅' if check_passed else '❌'} {description}")

        return all(check_passed for check_passed, _ in checks)

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("📋 监控验证测试摘要")
        print("="*60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests

        print(f"总测试数: {total_tests}")
        print(f"通过测试: {passed_tests}")
        print(f"失败测试: {failed_tests}")
        print(f"通过率: {(passed_tests/total_tests*100):.1f}%")

        if failed_tests > 0:
            print("\n❌ 失败测试详情:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['description']}")

        print("\n" + "="*60)

        return passed_tests == total_tests

    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始监控体系验证测试")
        print("="*60)

        await self.setup()

        test_methods = [
            ("告警级别测试", self.test_alert_severity_levels),
            ("告警类型测试", self.test_alert_types),
            ("阈值准确性测试", self.test_threshold_accuracy),
            ("告警级别计算测试", self.test_severity_calculation),
            ("告警管理器统计测试", self.test_alert_manager_stats),
            ("告警上下文完整性测试", self.test_alert_context_integrity),
        ]

        all_passed = True
        for test_name, test_method in test_methods:
            print(f"\n🧪 {test_name}")
            print("-"*40)

            try:
                passed = await test_method()
                if passed:
                    print(f"✅ {test_name} 通过")
                else:
                    print(f"❌ {test_name} 失败")
                    all_passed = False
            except Exception as e:
                print(f"❌ {test_name} 异常: {e}")
                all_passed = False

        # 打印摘要
        final_passed = self.print_summary()

        return all_passed and final_passed


async def main():
    """主函数"""
    test = MonitoringValidationTest()

    try:
        success = await test.run_all_tests()

        if success:
            print("\n🎉 监控体系验证测试全部通过！")
            print("✅ 告警触发机制验证完成")
            print("✅ 监控指标准确性验证完成")
            print("✅ 告警级别计算验证完成")
            print("✅ 统计功能验证完成")
            return 0
        else:
            print("\n❌ 监控体系验证测试失败")
            return 1

    except Exception as e:
        print(f"\n❌ 测试执行异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)