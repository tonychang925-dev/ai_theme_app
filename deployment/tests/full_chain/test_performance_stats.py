#!/usr/bin/env python3
"""
测试性能统计功能
"""

import json
import time
import statistics

# 模拟性能数据
performance_metrics = {
    "write_times": [0.05, 0.08, 0.12, 0.07, 0.09],  # 数据库写入时间 (秒)
    "redis_publish_times": [0.01, 0.02, 0.015, 0.018, 0.012],  # Redis发布时间 (秒)
    "processing_times": [2.5, 3.1, 2.8, 3.5, 2.9],  # 总处理时间 (秒)
    "stage_latencies": {
        "news_to_event": [0.8, 1.2, 0.9, 1.1, 1.0],
        "event_to_classified": [1.5, 1.8, 1.6, 2.0, 1.7],
        "classified_to_theme": [0.5, 0.6, 0.55, 0.7, 0.6],
        "theme_to_decision": [0.3, 0.4, 0.35, 0.45, 0.4]
    },
    "throughput": 25.5,  # 条/秒
    "success_count": 48,
    "error_count": 2
}

# 性能达标标准
performance_standards = {
    "db_write_latency": 0.1,  # 100ms
    "redis_publish_latency": 0.05,  # 50ms
    "news_to_event_latency": 2.0,  # 2秒
    "event_to_classified_latency": 3.0,  # 3秒
    "classified_to_theme_latency": 2.0,  # 2秒
    "theme_to_decision_latency": 1.0,  # 1秒
    "total_processing_latency": 8.0,  # 8秒
    "throughput_min": 10.0,  # 10条/秒
    "success_rate": 90.0,  # 90%
    "conversion_rate": 70.0  # 70%
}

def verify_performance_standards(metrics, standards):
    """验证性能数据是否达标"""
    verification = {
        "standards": standards.copy(),
        "actual_values": {},
        "passed": {},
        "overall_passed": True,
        "recommendations": []
    }

    # 检查数据库写入延迟
    if metrics["write_times"]:
        avg_db_write = statistics.mean(metrics["write_times"])
        verification["actual_values"]["db_write_latency"] = avg_db_write
        verification["passed"]["db_write_latency"] = avg_db_write <= standards["db_write_latency"]
        if not verification["passed"]["db_write_latency"]:
            verification["overall_passed"] = False
            verification["recommendations"].append(f"数据库写入延迟过高: {avg_db_write*1000:.1f}ms > {standards['db_write_latency']*1000:.0f}ms")

    # 检查Redis发布延迟
    if metrics["redis_publish_times"]:
        avg_redis_publish = statistics.mean(metrics["redis_publish_times"])
        verification["actual_values"]["redis_publish_latency"] = avg_redis_publish
        verification["passed"]["redis_publish_latency"] = avg_redis_publish <= standards["redis_publish_latency"]
        if not verification["passed"]["redis_publish_latency"]:
            verification["overall_passed"] = False
            verification["recommendations"].append(f"Redis发布延迟过高: {avg_redis_publish*1000:.1f}ms > {standards['redis_publish_latency']*1000:.0f}ms")

    # 检查各阶段延迟
    for stage in ["news_to_event", "event_to_classified", "classified_to_theme", "theme_to_decision"]:
        if metrics["stage_latencies"][stage]:
            avg_latency = statistics.mean(metrics["stage_latencies"][stage])
            verification["actual_values"][f"{stage}_latency"] = avg_latency
            standard_key = f"{stage}_latency"
            if standard_key in standards:
                verification["passed"][standard_key] = avg_latency <= standards[standard_key]
                if not verification["passed"][standard_key]:
                    verification["overall_passed"] = False
                    verification["recommendations"].append(f"{stage}延迟过高: {avg_latency:.2f}秒 > {standards[standard_key]:.1f}秒")

    # 检查总处理延迟
    if metrics["processing_times"]:
        avg_total = statistics.mean(metrics["processing_times"])
        verification["actual_values"]["total_processing_latency"] = avg_total
        verification["passed"]["total_processing_latency"] = avg_total <= standards["total_processing_latency"]
        if not verification["passed"]["total_processing_latency"]:
            verification["overall_passed"] = False
            verification["recommendations"].append(f"总处理延迟过高: {avg_total:.2f}秒 > {standards['total_processing_latency']:.1f}秒")

    # 检查吞吐量
    verification["actual_values"]["throughput"] = metrics["throughput"]
    verification["passed"]["throughput"] = metrics["throughput"] >= standards["throughput_min"]
    if not verification["passed"]["throughput"]:
        verification["overall_passed"] = False
        verification["recommendations"].append(f"吞吐量过低: {metrics['throughput']:.2f}条/秒 < {standards['throughput_min']:.0f}条/秒")

    # 检查成功率
    total_ops = metrics["success_count"] + metrics["error_count"]
    if total_ops > 0:
        success_rate = (metrics["success_count"] / total_ops) * 100
        verification["actual_values"]["success_rate"] = success_rate
        verification["passed"]["success_rate"] = success_rate >= standards["success_rate"]
        if not verification["passed"]["success_rate"]:
            verification["overall_passed"] = False
            verification["recommendations"].append(f"成功率过低: {success_rate:.1f}% < {standards['success_rate']:.0f}%")

    return verification

def print_performance_summary(metrics):
    """打印性能数据摘要"""
    print("\n" + "=" * 60)
    print("性能数据摘要:")
    print("=" * 60)

    if metrics["write_times"]:
        avg_db_write = statistics.mean(metrics["write_times"]) * 1000
        print(f"数据库写入延迟: {avg_db_write:.1f}ms (平均)")

    if metrics["redis_publish_times"]:
        avg_redis_publish = statistics.mean(metrics["redis_publish_times"]) * 1000
        print(f"Redis发布延迟: {avg_redis_publish:.1f}ms (平均)")

    for stage, latencies in metrics["stage_latencies"].items():
        if latencies:
            avg_latency = statistics.mean(latencies)
            print(f"{stage}延迟: {avg_latency:.2f}秒 (平均)")

    if metrics["processing_times"]:
        avg_total = statistics.mean(metrics["processing_times"])
        print(f"总处理延迟: {avg_total:.2f}秒 (平均)")

    print(f"吞吐量: {metrics['throughput']:.2f}条/秒")

    total_ops = metrics["success_count"] + metrics["error_count"]
    if total_ops > 0:
        success_rate = (metrics["success_count"] / total_ops) * 100
        print(f"成功率: {success_rate:.1f}% ({metrics['success_count']}/{total_ops})")

    print("=" * 60)

def print_verification_results(verification):
    """打印验证结果"""
    print("\n" + "=" * 60)
    print("性能达标验证结果:")
    print("=" * 60)

    passed_count = sum(1 for v in verification["passed"].values() if v)
    total_count = len(verification["passed"])
    print(f"通过率: {passed_count}/{total_count} ({passed_count/total_count*100:.1f}%)")

    for metric, passed in verification["passed"].items():
        actual = verification["actual_values"].get(metric, "N/A")
        standard = verification["standards"].get(metric, "N/A")
        status = "✅ 通过" if passed else "❌ 失败"

        if isinstance(actual, float):
            if "latency" in metric:
                actual_str = f"{actual*1000:.1f}ms" if actual < 1 else f"{actual:.2f}秒"
                standard_str = f"{standard*1000:.0f}ms" if standard < 1 else f"{standard:.1f}秒"
            elif "rate" in metric:
                actual_str = f"{actual:.1f}%"
                standard_str = f"{standard:.0f}%"
            elif "throughput" in metric:
                actual_str = f"{actual:.2f}条/秒"
                if isinstance(standard, (int, float)):
                    standard_str = f"{standard:.0f}条/秒"
                else:
                    standard_str = str(standard)
            else:
                actual_str = f"{actual:.3f}"
                standard_str = f"{standard:.3f}"
        else:
            actual_str = str(actual)
            standard_str = str(standard)

        print(f"  {metric}: {actual_str} (标准: {standard_str}) - {status}")

    if verification["recommendations"]:
        print("\n优化建议:")
        for rec in verification["recommendations"]:
            print(f"  - {rec}")

    print(f"\n总体结果: {'✅ 所有性能指标达标' if verification['overall_passed'] else '❌ 部分性能指标未达标'}")

def main():
    """主函数"""
    print("AI主题分析应用 - 性能统计测试")
    print("=" * 60)

    # 打印性能摘要
    print_performance_summary(performance_metrics)

    # 验证性能是否达标
    verification = verify_performance_standards(performance_metrics, performance_standards)

    # 打印验证结果
    print_verification_results(verification)

    # 保存详细报告
    report = {
        "test_name": "performance_stats_test",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "performance_metrics": performance_metrics,
        "performance_standards": performance_standards,
        "verification": verification
    }

    report_file = "performance_stats_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n详细报告已保存: {report_file}")

if __name__ == "__main__":
    main()