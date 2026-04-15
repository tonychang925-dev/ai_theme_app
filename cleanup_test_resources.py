#!/usr/bin/env python3
"""
测试资源清理脚本
用于手动清理测试结束后残留的Redis Stream和消费者组
避免测试资源占用生产环境Redis内存
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def main():
    """主清理函数"""
    print("🧹 Redis测试资源清理工具")
    print("=" * 60)
    print("功能:")
    print("  1. 清理所有测试Stream（根据模式匹配）")
    print("  2. 清理所有测试消费者组（根据模式匹配）")
    print("  3. 避免测试资源泄漏到生产环境")
    print("=" * 60)

    try:
        # 导入清理工具
        try:
            from database_service.streams.utils.test_cleanup_tool import (
                TestCleanupTool,
                cleanup_test_environment,
                get_test_resources_report
            )
            print("✅ 清理工具导入成功")
        except ImportError as e:
            print(f"❌ 导入清理工具失败: {e}")
            print("\n💡 请确保项目路径正确，或者手动清理:")
            print("  redis-cli keys 'stream:*test*' | xargs redis-cli del")
            print("  redis-cli keys 'stream:*temp*' | xargs redis-cli del")
            return 1

        # 获取测试资源报告
        print("\n📋 获取当前测试资源报告...")
        report = await get_test_resources_report()

        if "error" in report:
            print(f"❌ 获取报告失败: {report['error']}")
        else:
            test_streams = report['summary']['test_streams_count']
            test_groups = report['summary']['test_groups_count']
            estimated_memory = report['summary']['estimated_memory_bytes']

            print(f"📊 当前测试资源状态:")
            print(f"  测试Stream数: {test_streams}")
            print(f"  测试消费者组数: {test_groups}")
            print(f"  估计占用内存: {estimated_memory / (1024 * 1024):.2f} MB")

            if test_streams == 0 and test_groups == 0:
                print("✅ 没有发现需要清理的测试资源")
                return 0

        # 确认清理
        print("\n⚠️  确认清理操作")
        print("此操作将删除所有测试Stream和消费者组，无法撤销！")

        if len(sys.argv) > 1 and sys.argv[1] == "--force":
            print("使用 --force 参数，跳过确认")
            confirm = "y"
        else:
            confirm = input("是否继续? (y/N): ").strip().lower()

        if confirm != 'y':
            print("❌ 清理操作已取消")
            return 0

        # 执行清理
        print("\n🚀 开始清理测试资源...")
        cleanup_result = await cleanup_test_environment(dry_run=False)

        if "error" in cleanup_result:
            print(f"❌ 清理失败: {cleanup_result['error']}")
            return 1

        # 显示清理结果
        streams_found = cleanup_result.get('streams_found', 0)
        streams_cleaned = cleanup_result.get('streams_cleaned', 0)
        groups_found = cleanup_result.get('groups_found', 0)
        groups_cleaned = cleanup_result.get('groups_cleaned', 0)
        memory_freed = cleanup_result.get('memory_freed_bytes', 0)

        print("\n✅ 清理完成!")
        print(f"📊 清理统计:")
        print(f"  Stream: 找到 {streams_found} 个, 清理 {streams_cleaned} 个")
        print(f"  消费者组: 找到 {groups_found} 个, 清理 {groups_cleaned} 个")
        print(f"  释放内存: {memory_freed / (1024 * 1024):.2f} MB")

        if streams_cleaned > 0 or groups_cleaned > 0:
            print(f"\n💡 成功避免了测试资源泄漏!")
        else:
            print(f"\n💡 没有需要清理的资源")

        # 可选：再次验证
        print("\n🔍 验证清理结果...")
        verify_report = await get_test_resources_report()

        if "error" not in verify_report:
            remaining_streams = verify_report['summary']['test_streams_count']
            remaining_groups = verify_report['summary']['test_groups_count']

            if remaining_streams == 0 and remaining_groups == 0:
                print("✅ 验证通过：所有测试资源已清理干净")
            else:
                print(f"⚠️  仍有残留资源: {remaining_streams} 个Stream, {remaining_groups} 个消费者组")

        return 0

    except KeyboardInterrupt:
        print("\n\n❌ 清理操作被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 清理过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)