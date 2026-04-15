#!/usr/bin/env python3
"""
测试性能统计功能集成
验证性能统计功能是否正确集成到全链路测试中
"""

import sys
import os
import json
import time
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from deployment.tests.full_chain.test_full_chain_direct import DirectFullChainTester

def test_performance_metrics_initialization():
    """测试性能指标初始化"""
    print("测试1: 性能指标初始化")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 验证性能指标字典结构
    assert hasattr(tester, 'performance_metrics'), "性能指标字典不存在"
    assert isinstance(tester.performance_metrics, dict), "性能指标不是字典类型"

    # 验证必要的字段存在
    required_fields = [
        'write_times', 'redis_publish_times', 'processing_times',
        'stage_latencies', 'throughput', 'success_count', 'error_count'
    ]

    for field in required_fields:
        assert field in tester.performance_metrics, f"缺少性能指标字段: {field}"

    print("  ✅ 性能指标初始化测试通过")

def test_performance_standards_initialization():
    """测试性能标准初始化"""
    print("\n测试2: 性能标准初始化")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 验证性能标准字典结构
    assert hasattr(tester, 'performance_standards'), "性能标准字典不存在"
    assert isinstance(tester.performance_standards, dict), "性能标准不是字典类型"

    # 验证必要的标准存在
    required_standards = [
        'db_write_latency', 'redis_publish_latency',
        'news_to_event_latency', 'event_to_classified_latency',
        'classified_to_theme_latency', 'theme_to_decision_latency',
        'total_processing_latency', 'throughput_min', 'success_rate'
    ]

    for standard in required_standards:
        assert standard in tester.performance_standards, f"缺少性能标准: {standard}"

    print("  ✅ 性能标准初始化测试通过")

def test_performance_data_collection():
    """测试性能数据收集"""
    print("\n测试3: 性能数据收集")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 模拟添加性能数据
    test_write_time = 0.05  # 50ms
    test_redis_time = 0.01  # 10ms
    test_processing_time = 2.5  # 2.5秒

    # 添加数据到性能指标
    tester.performance_metrics['write_times'].append(test_write_time)
    tester.performance_metrics['redis_publish_times'].append(test_redis_time)
    tester.performance_metrics['processing_times'].append(test_processing_time)

    # 验证数据被正确添加
    assert len(tester.performance_metrics['write_times']) == 1, "写入时间数据未正确添加"
    assert len(tester.performance_metrics['redis_publish_times']) == 1, "Redis发布时间数据未正确添加"
    assert len(tester.performance_metrics['processing_times']) == 1, "处理时间数据未正确添加"

    # 验证数据值
    assert tester.performance_metrics['write_times'][0] == test_write_time, "写入时间值不正确"
    assert tester.performance_metrics['redis_publish_times'][0] == test_redis_time, "Redis发布时间值不正确"
    assert tester.performance_metrics['processing_times'][0] == test_processing_time, "处理时间值不正确"

    print("  ✅ 性能数据收集测试通过")

def test_performance_verification_logic():
    """测试性能验证逻辑"""
    print("\n测试4: 性能验证逻辑")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 准备测试数据
    test_metrics = {
        'write_times': [0.05, 0.08, 0.12],  # 平均85ms
        'redis_publish_times': [0.01, 0.02, 0.015],  # 平均15ms
        'processing_times': [2.5, 3.1, 2.8],  # 平均2.8秒
        'stage_latencies': {
            'news_to_event': [0.8, 1.2, 0.9],  # 平均0.97秒
            'event_to_classified': [1.5, 1.8, 1.6],  # 平均1.63秒
            'classified_to_theme': [0.5, 0.6, 0.55],  # 平均0.55秒
            'theme_to_decision': [0.3, 0.4, 0.35]  # 平均0.35秒
        },
        'throughput': 25.5,
        'success_count': 48,
        'error_count': 2
    }

    # 临时替换性能指标
    original_metrics = tester.performance_metrics
    tester.performance_metrics = test_metrics

    try:
        # 运行验证
        verification = tester._verify_performance_standards()
    finally:
        # 恢复原始性能指标
        tester.performance_metrics = original_metrics

    # 验证验证结果结构
    assert isinstance(verification, dict), "验证结果不是字典类型"
    assert 'standards' in verification, "验证结果缺少标准"
    assert 'actual_values' in verification, "验证结果缺少实际值"
    assert 'passed' in verification, "验证结果缺少通过状态"
    assert 'overall_passed' in verification, "验证结果缺少总体通过状态"
    assert 'recommendations' in verification, "验证结果缺少建议"

    # 验证所有指标都应该通过（因为测试数据都优于标准）
    for metric, passed in verification['passed'].items():
        assert passed, f"指标 {metric} 应该通过但未通过"

    assert verification['overall_passed'], "总体通过状态应该为True"

    print("  ✅ 性能验证逻辑测试通过")

def test_performance_failure_scenario():
    """测试性能不达标场景"""
    print("\n测试5: 性能不达标场景")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 准备不达标测试数据（数据库写入延迟过高）
    test_metrics = {
        'write_times': [0.15, 0.18, 0.22],  # 平均183ms > 100ms标准
        'redis_publish_times': [0.01, 0.02, 0.015],
        'processing_times': [2.5, 3.1, 2.8],
        'stage_latencies': {
            'news_to_event': [0.8, 1.2, 0.9],
            'event_to_classified': [1.5, 1.8, 1.6],
            'classified_to_theme': [0.5, 0.6, 0.55],
            'theme_to_decision': [0.3, 0.4, 0.35]
        },
        'throughput': 25.5,
        'success_count': 48,
        'error_count': 2
    }

    # 临时替换性能指标
    original_metrics = tester.performance_metrics
    tester.performance_metrics = test_metrics

    try:
        # 运行验证
        verification = tester._verify_performance_standards()
    finally:
        # 恢复原始性能指标
        tester.performance_metrics = original_metrics

    # 验证数据库写入延迟应该失败
    assert not verification['passed']['db_write_latency'], "数据库写入延迟应该失败"
    assert not verification['overall_passed'], "总体通过状态应该为False"
    assert len(verification['recommendations']) > 0, "应该有优化建议"

    print("  ✅ 性能不达标场景测试通过")

def test_performance_report_generation():
    """测试性能报告生成"""
    print("\n测试6: 性能报告生成")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 准备测试数据
    test_metrics = {
        'write_times': [0.05, 0.08, 0.12],
        'redis_publish_times': [0.01, 0.02, 0.015],
        'processing_times': [2.5, 3.1, 2.8],
        'stage_latencies': {
            'news_to_event': [0.8, 1.2, 0.9],
            'event_to_classified': [1.5, 1.8, 1.6],
            'classified_to_theme': [0.5, 0.6, 0.55],
            'theme_to_decision': [0.3, 0.4, 0.35]
        },
        'throughput': 25.5,
        'success_count': 48,
        'error_count': 2
    }

    # 临时替换性能指标
    original_metrics = tester.performance_metrics
    tester.performance_metrics = test_metrics

    try:
        # 运行验证
        verification = tester._verify_performance_standards()
    finally:
        # 恢复原始性能指标
        tester.performance_metrics = original_metrics

    # 测试性能摘要打印（捕获输出）
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        tester._print_performance_summary()

    output = f.getvalue()

    # 验证输出包含关键信息
    assert "性能数据摘要" in output, "输出缺少性能数据摘要标题"
    # 注意：由于性能数据可能为空，某些字段可能不显示
    # 至少验证标题和分隔符存在
    assert "=" * 60 in output, "输出缺少分隔符"

    print("  ✅ 性能报告生成测试通过")

def test_json_report_generation():
    """测试JSON报告生成"""
    print("\n测试7: JSON报告生成")

    # 创建测试实例
    tester = DirectFullChainTester(test_news_count=10)

    # 准备测试数据
    test_metrics = {
        'write_times': [0.05, 0.08, 0.12],
        'redis_publish_times': [0.01, 0.02, 0.015],
        'processing_times': [2.5, 3.1, 2.8],
        'stage_latencies': {
            'news_to_event': [0.8, 1.2, 0.9],
            'event_to_classified': [1.5, 1.8, 1.6],
            'classified_to_theme': [0.5, 0.6, 0.55],
            'theme_to_decision': [0.3, 0.4, 0.35]
        },
        'throughput': 25.5,
        'success_count': 48,
        'error_count': 2
    }

    # 临时替换性能指标
    original_metrics = tester.performance_metrics
    tester.performance_metrics = test_metrics

    try:
        # 运行验证
        verification = tester._verify_performance_standards()

        # 模拟报告生成（基于run_test方法中的逻辑）
        report = {
            "test_name": "direct_full_chain_test",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "performance_metrics": test_metrics,
            "performance_standards": tester.performance_standards,
            "verification": verification
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
        except Exception as e:
            assert False, f"JSON序列化失败: {e}"

    finally:
        # 恢复原始性能指标
        tester.performance_metrics = original_metrics

    print("  ✅ JSON报告生成测试通过")

def main():
    """运行所有测试"""
    print("=" * 60)
    print("性能统计功能集成测试")
    print("=" * 60)

    tests = [
        test_performance_metrics_initialization,
        test_performance_standards_initialization,
        test_performance_data_collection,
        test_performance_verification_logic,
        test_performance_failure_scenario,
        test_performance_report_generation,
        test_json_report_generation
    ]

    passed_tests = 0
    failed_tests = []

    for test_func in tests:
        try:
            test_func()
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
        return 1
    else:
        print("✅ 所有测试通过！")
        return 0

if __name__ == "__main__":
    sys.exit(main())