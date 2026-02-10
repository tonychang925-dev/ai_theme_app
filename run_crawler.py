import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.scheduler.task_manager import TaskManager

async def main():
    manager = TaskManager()
    await manager.start(interval_minutes=15)  # 生产环境建议15分钟

if __name__ == "__main__":
    asyncio.run(main())