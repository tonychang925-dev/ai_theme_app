# ai_theme_app/run_dual_scheduler.py
#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.scheduler.task_manager import TaskManager

async def main():
    """运行双源差异化调度器"""
    print("🏃 启动双源差异化调度器")
    print("   财联社: 每15分钟")
    print("   央视新闻: 每60分钟")
    print("   测试模式: 运行2个周期")
    
    manager = TaskManager()
    
    # 使用差异化调度
    await manager.start_differential_scheduling(max_cycles=2)

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