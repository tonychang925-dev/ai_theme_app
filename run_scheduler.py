#!/usr/bin/env python3
"""
新闻抓取调度器 - 主运行脚本
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.scheduler.task_manager import TaskManager

async def main():
    """
    主运行函数
    
    运行模式说明:
    1. 测试模式: interval=1, max_cycles=2 (每1分钟运行，共2次)
    2. 开发模式: interval=5, max_cycles=10 (每5分钟运行，最多10次)
    3. 生产模式: interval=15, max_cycles=None (每15分钟运行，无限循环)
    """
    # 选择运行模式
    mode = "test"  # 改为 "dev" 或 "prod" 切换模式
    
    if mode == "test":
        interval = 1    # 1分钟间隔（快速测试）
        max_cycles = 2  # 只运行2次
    elif mode == "dev":
        interval = 5    # 5分钟间隔
        max_cycles = 10 # 运行10次
    else:  # prod
        interval = 15   # 15分钟间隔
        max_cycles = None  # 无限循环
    
    print(f"🏃 启动调度器 [{mode}模式]")
    print(f"   抓取间隔: {interval} 分钟")
    print(f"   最大周期: {'无限' if max_cycles is None else max_cycles}")
    
    manager = TaskManager()
    
    if max_cycles is None:
        # 生产模式：无限循环
        await manager.start(interval_minutes=interval)
    else:
        # 测试/开发模式：有限次数
        await manager.start(interval_minutes=interval, max_cycles=max_cycles)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户中断，程序退出")
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)