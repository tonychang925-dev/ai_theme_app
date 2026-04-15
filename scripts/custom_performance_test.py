#!/usr/bin/env python3
"""
自定义Python性能测试脚本
用于测试AI模型推理性能
"""

import time
import sys
import numpy as np
from typing import Dict, List

class PerformanceTest:
    """性能测试类"""

    def __init__(self, iterations: int = 1000):
        self.iterations = iterations
        self.results: Dict[str, float] = {}

    def test_matrix_multiplication(self) -> float:
        """测试矩阵乘法性能"""
        start = time.time()
        for _ in range(self.iterations // 10):
            a = np.random.rand(100, 100)
            b = np.random.rand(100, 100)
            np.dot(a, b)
        elapsed = time.time() - start
        self.results['matrix_multiplication'] = elapsed
        return elapsed

    def test_list_comprehension(self) -> float:
        """测试列表推导式性能"""
        start = time.time()
        for _ in range(self.iterations):
            squares = [i**2 for i in range(1000)]
        elapsed = time.time() - start
        self.results['list_comprehension'] = elapsed
        return elapsed

    def test_dict_operations(self) -> float:
        """测试字典操作性能"""
        start = time.time()
        for _ in range(self.iterations):
            d = {i: i**2 for i in range(1000)}
            _ = {k: v * 2 for k, v in d.items()}
        elapsed = time.time() - start
        self.results['dict_operations'] = elapsed
        return elapsed

    def run_all_tests(self) -> Dict[str, float]:
        """运行所有测试"""
        print(f"开始性能测试，迭代次数: {self.iterations}")
        print("-" * 50)

        self.test_matrix_multiplication()
        self.test_list_comprehension()
        self.test_dict_operations()

        print("测试结果:")
        for test_name, duration in self.results.items():
            print(f"  {test_name}: {duration:.4f} 秒")

        return self.results

def main():
    """主函数"""
    if len(sys.argv) > 1:
        iterations = int(sys.argv[1])
    else:
        iterations = 1000

    tester = PerformanceTest(iterations)
    results = tester.run_all_tests()

    # 保存结果到文件
    with open('performance_results.txt', 'w') as f:
        f.write("性能测试结果\n")
        f.write("=" * 50 + "\n")
        for test_name, duration in results.items():
            f.write(f"{test_name}: {duration:.4f} 秒\n")

    print(f"\n结果已保存到 performance_results.txt")

if __name__ == "__main__":
    main()