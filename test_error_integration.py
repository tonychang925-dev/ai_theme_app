#!/usr/bin/env python3
"""
后端错误处理集成测试
验证错误分类、编码和恢复机制的集成工作
"""

import asyncio
import json
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, List

# 添加项目路径
sys.path.insert(0, '/Users/admin/desktop/ai_theme_app')

from database_service.utils.error_codes import (
    ErrorCode, AppError, ErrorResponse, create_error,
    create_redis_connection_error, create_ai_service_error,
    create_validation_error, create_api_error
)

from database_service.streams.utils.error_handler import (
    StreamErrorHandler, ErrorCategory, create_error_handler,
    with_error_handler
)


class ErrorIntegrationTest:
    """错误处理集成测试类"""

    def __init__(self):
        self.test_results = []
        self.error_handler = None

    async def setup(self):
        """测试设置"""
        print("🔧 设置测试环境...")

        # 创建错误处理器（无Redis连接用于测试）
        self.error_handler = await create_error_handler()

        print("✅ 测试环境设置完成")

    async def test_error_code_system(self):
        """测试错误编码系统"""
        print("\n🧪 测试错误编码系统...")

        tests = [
            {
                "name": "Redis连接错误",
                "error": create_redis_connection_error(Exception("Connection refused")),
                "expected_code": ErrorCode.REDIS_CONNECTION_FAILED,
                "expected_severity": "ERROR"
            },
            {
                "name": "AI服务错误",
                "error": create_ai_service_error(Exception("AI服务超时")),
                "expected_code": ErrorCode.AI_SERVICE_UNAVAILABLE,
                "expected_severity": "ERROR"
            },
            {
                "name": "验证错误",
                "error": create_validation_error("email", "无效的邮箱格式"),
                "expected_code": ErrorCode.VALIDATION_INPUT_INVALID,
                "expected_severity": "ERROR"
            },
            {
                "name": "API速率限制错误",
                "error": create_api_error(
                    ErrorCode.API_RATE_LIMIT_EXCEEDED,
                    "请求频率超过限制",
                    {"limit": 100, "current": 150}
                ),
                "expected_code": ErrorCode.API_RATE_LIMIT_EXCEEDED,
                "expected_severity": "WARN"
            }
        ]

        for test in tests:
            try:
                error = test["error"]

                # 验证错误码
                assert error.error_code == test["expected_code"], \
                    f"错误码不匹配: {error.error_code} != {test['expected_code']}"

                # 验证严重程度
                assert error.severity.value == test["expected_severity"], \
                    f"严重程度不匹配: {error.severity.value} != {test['expected_severity']}"

                # 验证错误信息
                assert error.message is not None and len(error.message) > 0, \
                    "错误消息为空"

                # 验证字典转换
                error_dict = error.to_dict()
                assert "error_code" in error_dict, "字典缺少error_code"
                assert "message" in error_dict, "字典缺少message"
                assert "timestamp" in error_dict, "字典缺少timestamp"

                # 验证JSON转换
                error_json = error.to_json()
                parsed = json.loads(error_json)
                assert parsed["error_code"] == test["expected_code"], \
                    "JSON解析错误"

                self.record_test_result(test["name"], True, "通过")
                print(f"  ✅ {test['name']}")

            except AssertionError as e:
                self.record_test_result(test["name"], False, str(e))
                print(f"  ❌ {test['name']}: {e}")
            except Exception as e:
                self.record_test_result(test["name"], False, f"未预期错误: {e}")
                print(f"  ❌ {test['name']}: 未预期错误: {e}")

    async def test_error_handler_integration(self):
        """测试错误处理器集成"""
        print("\n🧪 测试错误处理器集成...")

        # 模拟各种错误场景
        test_scenarios = [
            {
                "name": "Redis连接错误处理",
                "error": Exception("Connection refused"),
                "context": {"operation": "redis_connect", "stream": "stream:test"},
                "expected_category": ErrorCategory.REDIS_CONNECTION.value
            },
            {
                "name": "Stream不存在错误处理",
                "error": Exception("no such key 'stream:not:exists'"),
                "context": {"operation": "stream_read", "stream": "stream:not:exists"},
                "expected_category": ErrorCategory.STREAM_NOT_FOUND.value
            },
            {
                "name": "消息格式错误处理",
                "error": json.JSONDecodeError("Expecting value", "invalid json", 0),
                "context": {"operation": "message_parse", "stream": "stream:test", "message_id": "test_id"},
                "expected_category": ErrorCategory.MESSAGE_FORMAT.value
            },
            {
                "name": "消费者组错误处理",
                "error": Exception("BUSYGROUP Consumer Group name already exists"),
                "context": {"operation": "group_create", "stream": "stream:test", "group": "test_group"},
                "expected_category": ErrorCategory.CONSUMER_GROUP.value
            }
        ]

        for scenario in test_scenarios:
            try:
                # 使用错误处理器处理错误
                result = await self.error_handler.handle_error(
                    scenario["error"], scenario["context"]
                )

                # 验证错误分类
                assert result["category"] == scenario["expected_category"], \
                    f"错误分类不匹配: {result['category']} != {scenario['expected_category']}"

                # 验证错误记录包含必要字段
                required_fields = ["timestamp", "category", "error_type", "error_message", "context"]
                for field in required_fields:
                    assert field in result, f"缺少必要字段: {field}"

                self.record_test_result(scenario["name"], True, "通过")
                print(f"  ✅ {scenario['name']}")

            except AssertionError as e:
                self.record_test_result(scenario["name"], False, str(e))
                print(f"  ❌ {scenario['name']}: {e}")
            except Exception as e:
                self.record_test_result(scenario["name"], False, f"未预期错误: {e}")
                print(f"  ❌ {scenario['name']}: 未预期错误: {e}")

    async def test_error_response_integration(self):
        """测试错误响应集成"""
        print("\n🧪 测试错误响应集成...")

        try:
            # 创建应用错误
            app_error = create_redis_connection_error(
                Exception("Connection refused")
            )

            # 创建错误响应
            response = ErrorResponse(app_error, request_id="test_req_123")

            # 验证响应结构
            response_dict = response.to_dict()

            assert response_dict["success"] == False, "响应success应为False"
            assert "error" in response_dict, "响应缺少error字段"
            assert "timestamp" in response_dict, "响应缺少timestamp字段"
            assert response_dict["request_id"] == "test_req_123", "请求ID不匹配"

            # 验证错误信息
            error_info = response_dict["error"]
            assert error_info["error_code"] == ErrorCode.REDIS_CONNECTION_FAILED
            assert error_info["message"] is not None
            assert error_info["severity"] == "ERROR"
            assert "suggested_action" in error_info
            assert "recovery_strategy" in error_info

            # 验证JSON序列化
            response_json = response.to_json()
            parsed = json.loads(response_json)
            assert parsed["success"] == False
            assert parsed["error"]["error_code"] == ErrorCode.REDIS_CONNECTION_FAILED

            self.record_test_result("错误响应集成", True, "通过")
            print(f"  ✅ 错误响应集成")

        except AssertionError as e:
            self.record_test_result("错误响应集成", False, str(e))
            print(f"  ❌ 错误响应集成: {e}")
        except Exception as e:
            self.record_test_result("错误响应集成", False, f"未预期错误: {e}")
            print(f"  ❌ 错误响应集成: 未预期错误: {e}")

    async def test_error_handler_decorator(self):
        """测试错误处理装饰器"""
        print("\n🧪 测试错误处理装饰器...")

        try:
            # 创建测试函数
            @with_error_handler(self.error_handler, {"test": "decorator"})
            async def test_function(should_fail: bool):
                if should_fail:
                    raise Exception("测试错误")
                return "成功"

            # 测试正常情况
            result = await test_function(False)
            assert result == "成功", "正常执行应返回成功"

            # 测试错误情况
            try:
                await test_function(True)
                # 如果错误被恢复，不会抛出异常
                self.record_test_result("错误处理装饰器", True, "通过（错误被处理）")
                print(f"  ✅ 错误处理装饰器（错误被处理）")
            except Exception as e:
                # 错误未被恢复，重新抛出
                assert str(e) == "测试错误", f"错误消息不匹配: {e}"
                self.record_test_result("错误处理装饰器", True, "通过（错误重新抛出）")
                print(f"  ✅ 错误处理装饰器（错误重新抛出）")

        except AssertionError as e:
            self.record_test_result("错误处理装饰器", False, str(e))
            print(f"  ❌ 错误处理装饰器: {e}")
        except Exception as e:
            self.record_test_result("错误处理装饰器", False, f"未预期错误: {e}")
            print(f"  ❌ 错误处理装饰器: 未预期错误: {e}")

    async def test_error_statistics(self):
        """测试错误统计"""
        print("\n🧪 测试错误统计...")

        try:
            # 创建新的错误处理器来隔离统计
            stats_handler = await create_error_handler()

            # 生成一些测试错误
            test_errors = [
                (Exception("统计测试错误1"), {"operation": "stats_test1"}),
                (Exception("统计测试错误2"), {"operation": "stats_test2"}),
                (Exception("统计测试错误3"), {"operation": "stats_test3"})
            ]

            for error, context in test_errors:
                await stats_handler.handle_error(error, context)

            # 获取统计信息
            stats = stats_handler.get_stats()

            # 验证统计信息
            assert stats["total_errors"] == 3, f"总错误数不正确: {stats['total_errors']}"
            assert "recovery_rate" in stats, "缺少恢复率"
            assert "category_percentages" in stats, "缺少分类百分比"

            # 打印统计信息
            print(f"  总错误数: {stats['total_errors']}")
            print(f"  恢复率: {stats['recovery_rate']:.1%}")
            print(f"  错误分类: {stats['by_category']}")

            self.record_test_result("错误统计", True, "通过")
            print(f"  ✅ 错误统计")

        except AssertionError as e:
            self.record_test_result("错误统计", False, str(e))
            print(f"  ❌ 错误统计: {e}")
        except Exception as e:
            self.record_test_result("错误统计", False, f"未预期错误: {e}")
            print(f"  ❌ 错误统计: 未预期错误: {e}")

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
        print("📋 错误处理集成测试摘要")
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
                print(f"  - {result['test_name']}")

        print("="*60)

        # 返回总体结果
        return passed_tests == total_tests

    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始后端错误处理集成测试")
        print("="*60)

        try:
            await self.setup()
            await self.test_error_code_system()
            await self.test_error_handler_integration()
            await self.test_error_response_integration()
            await self.test_error_handler_decorator()
            await self.test_error_statistics()

            all_passed = self.print_summary()

            if all_passed:
                print("🎉 所有测试通过！")
                return True
            else:
                print("⚠️  部分测试失败，请检查错误处理系统")
                return False

        except Exception as e:
            print(f"❌ 测试执行失败: {e}")
            traceback.print_exc()
            return False


async def main():
    """主函数"""
    tester = ErrorIntegrationTest()
    success = await tester.run_all_tests()

    # 导出测试结果
    with open("error_integration_test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "results": tester.test_results,
            "summary": {
                "total": len(tester.test_results),
                "passed": sum(1 for r in tester.test_results if r["passed"]),
                "failed": sum(1 for r in tester.test_results if not r["passed"])
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"\n📥 测试结果已保存到: error_integration_test_results.json")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)