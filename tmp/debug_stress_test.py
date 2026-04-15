#!/usr/bin/env python3
"""
调试压力测试框架
"""

import asyncio
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

from tmp.run_full_chain_stress_test_with_monitoring import (
    StressTestConfig, TestScenario, FullChainStressTester
)

async def debug_init():
    """调试初始化"""
    print("测试FullChainStressTester初始化...")

    config = StressTestConfig(
        total_messages=2,
        concurrent_users=1,
        batch_size=2,
        scenario=TestScenario.CONSTANT_LOAD,
        duration_seconds=10,
        monitor_interval=0.5,
        enable_system_monitoring=False,
        enable_redis_monitoring=False,
        enable_postgres_monitoring=False,
        report_dir=PROJECT_ROOT / "tmp/stress_test_reports",
        detailed_report=True
    )

    print("创建FullChainStressTester实例...")
    tester = FullChainStressTester(config)

    print("尝试运行压力测试...")
    try:
        report = await tester.run_stress_test()
        print(f"压力测试成功，报告: {report}")
    except Exception as e:
        print(f"压力测试失败: {e}")
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(debug_init())
    sys.exit(0 if success else 1)