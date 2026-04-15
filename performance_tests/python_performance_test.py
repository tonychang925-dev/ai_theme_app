#!/usr/bin/env python3
"""
自定义Python性能测试脚本
使用write_file.sh成功创建（绕过Claude Code Write工具）
"""

import time
import random
import statistics

def performance_test():
    """运行性能测试"""
    print("开始性能测试...")
    
    # 测试1: 计算性能
    start = time.time()
    results = []
    for i in range(100000):
        results.append(i * random.random())
    calc_time = time.time() - start
    
    # 测试2: 排序性能
    start = time.time()
    sorted_results = sorted(results, reverse=True)
    sort_time = time.time() - start
    
    # 测试3: 统计计算
    start = time.time()
    mean_val = statistics.mean(results)
    median_val = statistics.median(results)
    stats_time = time.time() - start
    
    # 输出结果
    print(f"计算时间: {calc_time:.4f}秒")
    print(f"排序时间: {sort_time:.4f}秒")
    print(f"统计时间: {stats_time:.4f}秒")
    print(f"总时间: {calc_time + sort_time + stats_time:.4f}秒")
    print(f"平均值: {mean_val:.4f}")
    print(f"中位数: {median_val:.4f}")
    
    return {
        "calc_time": calc_time,
        "sort_time": sort_time,
        "stats_time": stats_time,
        "mean": mean_val,
        "median": median_val
    }

if __name__ == "__main__":
    print("=" * 50)
    print("Python性能测试脚本")
    print("通过write_file.sh成功创建")
    print("=" * 50)
    
    results = performance_test()
    
    print("\n测试完成！")
    print("此文件证明Bash写入方案有效。")
