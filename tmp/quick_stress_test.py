#!/usr/bin/env python3
"""
快速压力测试 - 在theme_matcher_env环境下验证全链路压力测试框架
"""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))

from tmp.run_full_chain_stress_test_with_monitoring import (
    StressTestConfig, TestScenario, FullChainStressTester
)

async def main():
    """运行快速压力测试"""
    print("🚀 在theme_matcher_env环境下启动快速压力测试")

    # 检查环境变量
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("警告: DEEPSEEK_API_KEY 环境变量未设置")
        env_file = PROJECT_ROOT / ".env.theme"
        if env_file.exists():
            content = env_file.read_text()
            for line in content.splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip()
                    print(f"已从.env.theme文件读取DEEPSEEK_API_KEY")
                    # 确保使用正确的数据库
                    os.environ["POSTGRES_DATABASE"] = "stock_data"
                    break

    # 配置快速测试
    config = StressTestConfig(
        total_messages=5,           # 少量消息快速验证
        concurrent_users=2,         # 低并发
        batch_size=5,
        scenario=TestScenario.CONSTANT_LOAD,
        duration_seconds=30,        # 30秒超时
        monitor_interval=0.5,       # 快速监控
        enable_system_monitoring=False,
        enable_redis_monitoring=False,
        enable_postgres_monitoring=False,
        report_dir=PROJECT_ROOT / "tmp/stress_test_reports",
        detailed_report=True
    )

    print(f"测试配置:")
    print(f"  消息数: {config.total_messages}")
    print(f"  并发用户: {config.concurrent_users}")
    print(f"  测试场景: {config.scenario.value}")

    # 创建测试器
    tester = FullChainStressTester(config)

    try:
        # 运行测试
        report = await tester.run_stress_test()

        if report:
            print(f"\n✅ 压力测试完成!")
            # 使用正确的报告结构
            stats = report.get('performance_statistics', {})
            success_rate = stats.get('overall_success_rate', 0)
            throughput = stats.get('throughput', 0)
            print(f"  成功率: {success_rate:.2%}")
            print(f"  吞吐量: {throughput:.2f} 消息/秒")
            # 检查是否有延迟指标
            latency = stats.get('avg_latency', 'N/A')
            if latency == 'N/A':
                # 尝试从news_raw_publish_latency获取平均延迟
                if 'news_raw_publish_latency' in stats:
                    latency = stats['news_raw_publish_latency'].get('mean', 'N/A')
            print(f"  平均延迟: {latency} 秒")

            # 保存报告
            import json
            from datetime import datetime
            report_file = PROJECT_ROOT / f"tmp/quick_stress_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  报告已保存: {report_file}")
        else:
            print("\n❌ 压力测试失败: 未生成报告")

    except Exception as e:
        print(f"\n❌ 压力测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)