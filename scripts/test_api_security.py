#!/usr/bin/env python3
"""
API安全功能测试脚本
测试基础认证、输入验证、安全头设置等功能
"""

import asyncio
import json
import logging
import sys
from datetime import datetime

# 添加项目路径
sys.path.append('.')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class APISecurityTester:
    """API安全功能测试"""

    def __init__(self):
        self.test_results = []
        self.base_url = "http://localhost:8000"  # 假设BFF运行在8000端口

        # 测试配置
        self.test_config = {
            "security_headers_tests": [
                {"header": "X-Content-Type-Options", "expected": "nosniff"},
                {"header": "X-Frame-Options", "expected": "DENY"},
                {"header": "X-XSS-Protection", "expected": "1; mode=block"},
            ],
            "input_validation_tests": [
                {"type": "sql_injection", "value": "' OR '1'='1"},
                {"type": "xss", "value": "<script>alert('xss')</script>"},
                {"type": "path_traversal", "value": "../../etc/passwd"},
            ],
            "rate_limit_tests": [
                {"requests": 110, "expected_status": 429},  # 超过100次限制
            ]
        }

        logger.info(f"🔒 初始化API安全测试")
        logger.info(f"   基础URL: {self.base_url}")
        logger.info(f"   测试类型: {len(self.test_config)}种")

    async def test_security_headers(self):
        """测试安全头"""
        logger.info("🧪 测试安全头...")

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # 发送测试请求
                response = await client.get(f"{self.base_url}/health")

                # 检查安全头
                headers_found = []
                headers_missing = []

                for test in self.test_config["security_headers_tests"]:
                    header_name = test["header"]
                    expected_value = test["expected"]

                    actual_value = response.headers.get(header_name)

                    if actual_value:
                        if actual_value == expected_value:
                            headers_found.append(header_name)
                            logger.info(f"✅ 安全头正确: {header_name}={actual_value}")
                        else:
                            logger.warning(f"⚠️  安全头值不匹配: {header_name}={actual_value} (期望: {expected_value})")
                    else:
                        headers_missing.append(header_name)
                        logger.warning(f"⚠️  安全头缺失: {header_name}")

                # 记录结果
                result = {
                    "test": "security_headers",
                    "timestamp": datetime.now().isoformat(),
                    "total_headers": len(self.test_config["security_headers_tests"]),
                    "headers_found": len(headers_found),
                    "headers_missing": headers_missing,
                    "success": len(headers_missing) == 0
                }

                self.test_results.append(result)
                return result

        except Exception as e:
            logger.error(f"❌ 安全头测试失败: {e}")
            return {"test": "security_headers", "error": str(e), "success": False}

    async def test_input_validation(self):
        """测试输入验证"""
        logger.info("🧪 测试输入验证...")

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                test_results = []

                for test in self.test_config["input_validation_tests"]:
                    test_type = test["type"]
                    malicious_value = test["value"]

                    # 测试查询参数
                    try:
                        response = await client.get(
                            f"{self.base_url}/test",
                            params={"input": malicious_value}
                        )

                        status = response.status_code

                        if status == 400:
                            logger.info(f"✅ 输入验证成功阻止 {test_type}: {malicious_value[:30]}")
                            test_results.append({
                                "type": test_type,
                                "value": malicious_value,
                                "status": status,
                                "blocked": True
                            })
                        else:
                            logger.warning(f"⚠️  输入验证未阻止 {test_type}: status={status}")
                            test_results.append({
                                "type": test_type,
                                "value": malicious_value,
                                "status": status,
                                "blocked": False
                            })

                    except Exception as e:
                        logger.error(f"❌ 输入验证测试异常 {test_type}: {e}")
                        test_results.append({
                            "type": test_type,
                            "value": malicious_value,
                            "error": str(e),
                            "blocked": False
                        })

                # 记录结果
                blocked_count = sum(1 for r in test_results if r.get("blocked", False))
                total_tests = len(test_results)

                result = {
                    "test": "input_validation",
                    "timestamp": datetime.now().isoformat(),
                    "total_tests": total_tests,
                    "blocked_count": blocked_count,
                    "blocked_rate": blocked_count / total_tests if total_tests > 0 else 0,
                    "details": test_results,
                    "success": blocked_count == total_tests
                }

                self.test_results.append(result)
                return result

        except Exception as e:
            logger.error(f"❌ 输入验证测试失败: {e}")
            return {"test": "input_validation", "error": str(e), "success": False}

    async def test_rate_limiting(self):
        """测试速率限制"""
        logger.info("🧪 测试速率限制...")

        try:
            import httpx
            import asyncio

            async with httpx.AsyncClient() as client:
                test_results = []

                for test in self.test_config["rate_limit_tests"]:
                    request_count = test["requests"]
                    expected_status = test["expected_status"]

                    successful_requests = 0
                    rate_limited_requests = 0

                    # 快速发送多个请求
                    tasks = []
                    for i in range(request_count):
                        task = client.get(f"{self.base_url}/health")
                        tasks.append(task)

                    # 并行执行
                    responses = await asyncio.gather(*tasks, return_exceptions=True)

                    for response in responses:
                        if isinstance(response, Exception):
                            logger.warning(f"请求异常: {response}")
                            continue

                        if response.status_code == 200:
                            successful_requests += 1
                        elif response.status_code == expected_status:
                            rate_limited_requests += 1

                    logger.info(f"📊 速率限制测试: {successful_requests}成功, {rate_limited_requests}被限制")

                    test_results.append({
                        "request_count": request_count,
                        "successful": successful_requests,
                        "rate_limited": rate_limited_requests,
                        "expected_status": expected_status,
                        "has_rate_limit": rate_limited_requests > 0
                    })

                # 记录结果
                has_rate_limit = any(r["has_rate_limit"] for r in test_results)

                result = {
                    "test": "rate_limiting",
                    "timestamp": datetime.now().isoformat(),
                    "total_tests": len(test_results),
                    "has_rate_limit": has_rate_limit,
                    "details": test_results,
                    "success": has_rate_limit
                }

                self.test_results.append(result)
                return result

        except Exception as e:
            logger.error(f"❌ 速率限制测试失败: {e}")
            return {"test": "rate_limiting", "error": str(e), "success": False}

    async def test_authentication(self):
        """测试认证功能"""
        logger.info("🧪 测试认证功能...")

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # 测试无认证的请求
                response = await client.get(f"{self.base_url}/api/protected")
                no_auth_status = response.status_code

                logger.info(f"无认证请求状态: {no_auth_status}")

                # 测试有认证的请求（如果有API密钥）
                api_key = "test_key_123"  # 测试用密钥
                headers = {"X-API-Key": api_key}

                response_with_auth = await client.get(
                    f"{self.base_url}/api/protected",
                    headers=headers
                )
                auth_status = response_with_auth.status_code

                logger.info(f"有认证请求状态: {auth_status}")

                # 分析结果
                result = {
                    "test": "authentication",
                    "timestamp": datetime.now().isoformat(),
                    "no_auth_status": no_auth_status,
                    "auth_status": auth_status,
                    "requires_auth": no_auth_status == 401 or no_auth_status == 403,
                    "auth_works": auth_status != 401 and auth_status != 403,
                    "success": (no_auth_status == 401 or no_auth_status == 403) and (auth_status != 401 and auth_status != 403)
                }

                self.test_results.append(result)
                return result

        except Exception as e:
            logger.error(f"❌ 认证测试失败: {e}")
            return {"test": "authentication", "error": str(e), "success": False}

    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始API安全综合测试")
        logger.info("=" * 60)

        tests = [
            self.test_security_headers,
            self.test_input_validation,
            self.test_rate_limiting,
            self.test_authentication
        ]

        for test_func in tests:
            try:
                await test_func()
                await asyncio.sleep(1)  # 短暂暂停
            except Exception as e:
                logger.error(f"❌ 测试执行失败: {e}")

        # 生成报告
        report = await self._generate_report()

        logger.info("✅ API安全测试全部完成")
        return report

    async def _generate_report(self):
        """生成测试报告"""
        logger.info("📄 生成测试报告...")

        # 分析结果
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.get("success", False))
        success_rate = successful_tests / total_tests if total_tests > 0 else 0

        # 找出问题
        issues = []
        recommendations = []

        for result in self.test_results:
            test_name = result.get("test", "unknown")
            if not result.get("success", False):
                issues.append({
                    "test": test_name,
                    "error": result.get("error", "未知错误"),
                    "details": result
                })

        # 生成建议
        if success_rate < 1.0:
            recommendations.append({
                "type": "warning",
                "title": "安全测试未完全通过",
                "content": f"成功率: {success_rate:.1%} ({successful_tests}/{total_tests})",
                "action": "检查失败测试的详细日志"
            })

        # 检查具体问题
        for issue in issues:
            test_name = issue["test"]

            if test_name == "security_headers":
                recommendations.append({
                    "type": "security",
                    "title": "安全头配置问题",
                    "content": "部分安全头缺失或配置不正确",
                    "action": "检查安全中间件配置"
                })
            elif test_name == "input_validation":
                recommendations.append({
                    "type": "security",
                    "title": "输入验证问题",
                    "content": "未能有效阻止恶意输入",
                    "action": "加强输入验证规则"
                })
            elif test_name == "rate_limiting":
                recommendations.append({
                    "type": "performance",
                    "title": "速率限制问题",
                    "content": "未能有效限制请求频率",
                    "action": "检查速率限制中间件配置"
                })
            elif test_name == "authentication":
                recommendations.append({
                    "type": "security",
                    "title": "认证问题",
                    "content": "认证机制存在问题",
                    "action": "检查认证中间件配置"
                })

        report = {
            "metadata": {
                "report_name": "API安全测试报告",
                "generated_at": datetime.now().isoformat(),
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "success_rate": success_rate
            },
            "summary": {
                "overall_status": "PASS" if success_rate == 1.0 else "FAIL",
                "security_level": self._calculate_security_level(success_rate),
                "recommended_actions": len(recommendations)
            },
            "test_results": self.test_results,
            "issues": issues,
            "recommendations": recommendations
        }

        # 保存报告
        report_file = f"api_security_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"📄 报告已保存: {report_file}")
        except Exception as e:
            logger.error(f"保存报告失败: {e}")

        return report

    def _calculate_security_level(self, success_rate: float) -> str:
        """计算安全等级"""
        if success_rate >= 0.9:
            return "HIGH"
        elif success_rate >= 0.7:
            return "MEDIUM"
        elif success_rate >= 0.5:
            return "LOW"
        else:
            return "CRITICAL"

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 70)
        print("🔒 API安全测试摘要")
        print("=" * 70)

        if not self.test_results:
            print("❌ 无测试结果")
            return

        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.get("success", False))
        success_rate = successful_tests / total_tests if total_tests > 0 else 0

        print(f"📊 测试统计:")
        print(f"   总测试数: {total_tests}")
        print(f"   成功测试: {successful_tests}")
        print(f"   成功率: {success_rate:.1%}")

        print(f"\n🧪 详细结果:")
        for result in self.test_results:
            test_name = result.get("test", "unknown")
            success = result.get("success", False)
            status = "✅" if success else "❌"

            print(f"   {status} {test_name}: {'通过' if success else '失败'}")

            if not success:
                error = result.get("error", "未知错误")
                print(f"      错误: {error[:50]}...")

        print(f"\n🏆 安全等级: {self._calculate_security_level(success_rate)}")

        if success_rate < 1.0:
            print(f"\n⚠️  发现 {total_tests - successful_tests} 个问题:")
            for result in self.test_results:
                if not result.get("success", False):
                    test_name = result.get("test", "unknown")
                    print(f"   - {test_name} 测试失败")

        print("=" * 70)


async def main():
    """主函数"""
    print("🔒 API安全功能测试")
    print("=" * 60)
    print("目标: 测试API安全中间件的各项功能")
    print("测试项目: 安全头、输入验证、速率限制、认证")
    print("基础URL: http://localhost:8000")
    print()

    try:
        # 创建测试实例
        tester = APISecurityTester()

        # 运行测试
        report = await tester.run_all_tests()

        # 打印摘要
        tester.print_summary()

        print("\n💡 建议:")
        print("1. 根据测试结果修复发现的安全问题")
        print("2. 定期运行安全测试确保防护有效")
        print("3. 在生产环境中启用所有安全中间件")
        print("4. 监控安全日志，及时发现攻击尝试")

        return report

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


if __name__ == "__main__":
    # 运行测试
    report = asyncio.run(main())

    # 退出码
    if "error" in report:
        sys.exit(1)
    else:
        sys.exit(0)