#!/usr/bin/env python3
"""
测试解析函数
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

from tmp.run_full_chain_stress_test_with_monitoring import (
    StressTestConfig, TestScenario, FullChainStressTester
)

# 创建配置
config = StressTestConfig(
    total_messages=5,
    concurrent_users=1,
    batch_size=5,
    scenario=TestScenario.CONSTANT_LOAD,
    duration_seconds=30,
    monitor_interval=0.5,
    enable_system_monitoring=False,
    enable_redis_monitoring=False,
    enable_postgres_monitoring=False,
    report_dir=PROJECT_ROOT / "tmp/stress_test_reports",
    detailed_report=True
)

print("创建FullChainStressTester实例...")
tester = FullChainStressTester(config)

print(f"raw_test_path: {tester.raw_test_path}")
print(f"文件存在: {tester.raw_test_path.exists()}")

# 测试解析
try:
    samples = tester._parse_test_cases(5)
    print(f"成功解析 {len(samples)} 条样本")
    for i, sample in enumerate(samples[:3]):
        print(f"样本 {i+1}: {sample}")
except Exception as e:
    print(f"解析失败: {e}")
    import traceback
    traceback.print_exc()