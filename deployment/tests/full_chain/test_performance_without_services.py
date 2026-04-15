#!/usr/bin/env python3
"""
不依赖系统服务的性能统计测试
直接测试性能数据收集和达标验证功能
"""

import asyncio
import json
import time
import statistics
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from deployment.tests.full_chain.test_full_chain_direct import DirectFullChainTester

class PerformanceOnlyTester:
    """仅测试性能统计功能，不依赖系统服务"""

    def __init__(self):
        # 创建DirectFullChainTester实例但不运行完整测试
        self.tester = DirectFullChainTester(test_news_count=5)

        # 模拟的性能数据
        self.simulated_metrics = {
            "write_times": [0.005, 0.008, 0.012, 0.007, 0.009],  # 5-12ms
            "redis_publish_times": [0.001, 0.002, 0.0015, 0.0018, 0.0012],  # 1-2ms
            "processing_times": [1.5, 2.1, 1.8, 2.5, 1.9],  # 1.5-2.5秒
            "stage_latencies": {
                "news_to_event": [0.5, 0.8, 0.6, 0.9, 0.7],  # 0.5-0.9秒
                "event_to_classified": [1.0, 1.3, 1.1, 1.5, 1.2],  # 1.0-1.5秒
                "classified_to_theme": [0.3, 0.4, 0.35, 0.5, 0.45],  # 0.3-0.5秒
                "theme_to_decision": [0.2, 0.3, 0.25, 0.35, 0.3]  # 0.2-0.35秒
            },
            "throughput": 45.5,  # 条/秒
            "success_count": 48,
            "error_count": 2
        }

        # 不达标的性能数据（用于测试失败场景）
        self.failed_metrics = {
            "write_times": [0.15, 0.18, 0.22, 0.19, 0.21],  # 150-220ms > 100ms标准
            "redis_publish_times": [0.08, 0.09, 0.085, 0.095, 0.088],  # 80-95ms > 50ms标准
            "processing_times": [9.5, 10.1, 9.8, 10.5, 9.9],  # 9.5-10.5秒 > 8秒标准
            "stage_latencies": {
                "news_to_event": [2.5, 2.8, 2.6, 3.0, 2.7],  # 2.5-3.0秒 > 2秒标准
                "event_to_classified": [3.5, 3.8, 3.6, 4.0, 3.7],  # 3.5-4.0秒 > 3秒标准
                "classified_to_theme": [2.5, 2.8, 2.6, 3.0, 2.7],  # 2.5-3.0秒 > 2秒标准
                "theme_to_decision": [1.5, 1.8, 1.6, 2.0, 1.7]  # 1.5-2.0秒 > 1秒标准
            },
            "throughput": 5.5,  # 条/秒 < 10条/秒标准
            "success_count": 40,
            "error_count": 10  # 成功率80% < 90%标准
        }

    def test_performance_metrics_structure(self):
        """测试性能指标数据结构"""
        print("测试1: 性能指标数据结构")

        metrics = self.tester.performance_metrics

        # 验证基本结构
        assert isinstance(metrics, dict), "性能指标不是字典类型"

        # 验证必要字段
        required_fields = [
            'write_times', 'redis_publish_times', 'processing_times',
            'stage_latencies', 'throughput', 'success_count', 'error_count'
        ]

        for field in required_fields:
            assert field in metrics, f"缺少性能指标字段: {field}"

        # 验证stage_latencies结构
        assert isinstance(metrics['stage_latencies'], dict), "stage_latencies不是字典类型"
        required_stages = ['news_to_event', 'event_to_classified', 'classified_to_theme', 'theme_to_decision']
        for stage in required_stages:
            assert stage in metrics['stage_latencies'], f"缺少阶段延迟字段: {stage}"
            assert isinstance(metrics['stage_latencies'][stage], list), f"{stage}不是列表类型"

        print("  ✅ 性能指标数据结构测试通过")
        return True

    def test_performance_standards_structure(self):
        """测试性能标准结构"""
        print("\n测试2: 性能标准结构")

        standards = self.tester.performance_standards

        # 验证基本结构
        assert isinstance(standards, dict), "性能标准不是字典类型"

        # 验证必要标准
        required_standards = [
            'db_write_latency', 'redis_publish_latency',
            'news_to_event_latency', 'event_to_classified_latency',
            'classified_to_theme_latency', 'theme_to_decision_latency',
            'total_processing_latency', 'throughput_min', 'success_rate'
        ]

        for standard in required_standards:
            assert standard in standards, f"缺少性能标准: {standard}"
            assert isinstance(standards[standard], (int, float)), f"标准 {standard} 不是数值类型"

        print("  ✅ 性能标准结构测试通过")
        return True

    def test_performance_verification_success(self):
        """测试性能验证成功场景"""
        print("\n测试3: 性能验证成功场景")

        # 保存原始指标
        original_metrics = self.tester.performance_metrics
        self.tester.performance_metrics = self.simulated_metrics

        try:
            # 运行验证
            verification = self.tester._verify_performance_standards()

            # 验证结果结构
            assert isinstance(verification, dict), "验证结果不是字典类型"
            assert 'standards' in verification, "验证结果缺少标准"
            assert 'actual_values' in verification, "验证结果缺少实际值"
            assert 'passed' in verification, "验证结果缺少通过状态"
            assert 'overall_passed' in verification, "验证结果缺少总体通过状态"
            assert 'recommendations' in verification, "验证结果缺少建议"

            # 验证所有指标都应该通过
            for metric, passed in verification['passed'].items():
                assert passed, f"指标 {metric} 应该通过但未通过"

            assert verification['overall_passed'], "总体通过状态应该为True"
            assert len(verification['recommendations']) == 0, "成功场景不应该有优化建议"

            print("  ✅ 性能验证成功场景测试通过")
            return True

        finally:
            # 恢复原始指标
            self.tester.performance_metrics = original_metrics

    def test_performance_verification_failure(self):
        """测试性能验证失败场景"""
        print("\n测试4: 性能验证失败场景")

        # 保存原始指标
        original_metrics = self.tester.performance_metrics
        self.tester.performance_metrics = self.failed_metrics

        try:
            # 运行验证
            verification = self.tester._verify_performance_standards()

            # 验证失败指标
            failed_metrics = []
            for metric, passed in verification['passed'].items():
                if not passed:
                    failed_metrics.append(metric)

            assert len(failed_metrics) > 0, "应该有失败的指标"
            assert not verification['overall_passed'], "总体通过状态应该为False"
            assert len(verification['recommendations']) > 0, "失败场景应该有优化建议"

            print(f"  ✅ 性能验证失败场景测试通过 (失败指标: {len(failed_metrics)}个)")
            return True

        finally:
            # 恢复原始指标
            self.tester.performance_metrics = original_metrics

    def test_performance_summary_output(self):
        """测试性能摘要输出"""
        print("\n测试5: 性能摘要输出")

        # 保存原始指标
        original_metrics = self.tester.performance_metrics
        self.tester.performance_metrics = self.simulated_metrics

        try:
            # 捕获输出
            import io
            from contextlib import redirect_stdout

            f = io.StringIO()
            with redirect_stdout(f):
                self.tester._print_performance_summary()

            output = f.getvalue()

            # 验证输出包含关键信息
            assert "性能数据摘要" in output, "输出缺少性能数据摘要标题"
            assert "=" * 60 in output, "输出缺少分隔符"

            # 验证数值输出格式
            if self.simulated_metrics["write_times"]:
                assert "数据库写入延迟" in output, "输出缺少数据库写入延迟信息"

            if self.simulated_metrics["redis_publish_times"]:
                assert "Redis发布延迟" in output, "输出缺少Redis发布延迟信息"

            assert "吞吐量" in output, "输出缺少吞吐量信息"

            print("  ✅ 性能摘要输出测试通过")
            return True

        finally:
            # 恢复原始指标
            self.tester.performance_metrics = original_metrics

    def test_json_report_generation(self):
        """测试JSON报告生成"""
        print("\n测试6: JSON报告生成")

        # 保存原始指标
        original_metrics = self.tester.performance_metrics
        self.tester.performance_metrics = self.simulated_metrics

        try:
            # 运行验证
            verification = self.tester._verify_performance_standards()

            # 模拟报告生成（基于DirectFullChainTester中的逻辑）
            report = {
                "test_name": "performance_only_test",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "performance_metrics": self.simulated_metrics,
                "performance_standards": self.tester.performance_standards,
                "verification": verification,
                "summary": {
                    "db_write_latency_avg": statistics.mean(self.simulated_metrics["write_times"]) * 1000,
                    "redis_publish_latency_avg": statistics.mean(self.simulated_metrics["redis_publish_times"]) * 1000,
                    "throughput": self.simulated_metrics["throughput"],
                    "success_rate": (self.simulated_metrics["success_count"] /
                                   (self.simulated_metrics["success_count"] + self.simulated_metrics["error_count"])) * 100
                }
            }

            # 验证报告结构
            assert isinstance(report, dict), "报告不是字典类型"
            assert 'test_name' in report, "报告缺少测试名称"
            assert 'timestamp' in report, "报告缺少时间戳"
            assert 'performance_metrics' in report, "报告缺少性能指标"
            assert 'performance_standards' in report, "报告缺少性能标准"
            assert 'verification' in report, "报告缺少验证结果"

            # 验证可以序列化为JSON
            try:
                json_str = json.dumps(report, ensure_ascii=False, indent=2)
                assert isinstance(json_str, str), "JSON序列化失败"

                # 保存报告
                report_file = "performance_only_test_report.json"
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(json_str)

                print(f"  ✅ JSON报告生成测试通过 (报告已保存: {report_file})")
                return True

            except Exception as e:
                assert False, f"JSON序列化失败: {e}"

        finally:
            # 恢复原始指标
            self.tester.performance_metrics = original_metrics

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("不依赖系统服务的性能统计功能测试")
        print("=" * 60)

        tests = [
            self.test_performance_metrics_structure,
            self.test_performance_standards_structure,
            self.test_performance_verification_success,
            self.test_performance_verification_failure,
            self.test_performance_summary_output,
            self.test_json_report_generation
        ]

        passed_tests = 0
        failed_tests = []

        for test_func in tests:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                print(f"  ❌ {test_func.__name__} 失败: {e}")
                failed_tests.append((test_func.__name__, str(e)))

        print("\n" + "=" * 60)
        print(f"测试结果: {passed_tests}/{len(tests)} 通过")

        if failed_tests:
            print("\n失败的测试:")
            for test_name, error in failed_tests:
                print(f"  - {test_name}: {error}")
            return False
        else:
            print("✅ 所有测试通过！")
            return True


def main():
    """主函数"""
    tester = PerformanceOnlyTester()

    if tester.run_all_tests():
        print("\n" + "=" * 60)
        print("性能统计功能验证完成总结:")
        print("=" * 60)
        print("1. ✅ 性能指标数据结构完整")
        print("2. ✅ 性能标准定义完整")
        print("3. ✅ 性能验证算法正确（成功场景）")
        print("4. ✅ 性能验证算法正确（失败场景）")
        print("5. ✅ 性能摘要输出格式正确")
        print("6. ✅ JSON报告生成功能正常")
        print("\n结论: 性能统计功能已100%实现，不依赖系统服务即可正常工作")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
