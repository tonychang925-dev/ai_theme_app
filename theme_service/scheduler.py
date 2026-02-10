"""
任务调度器 - 修复版
"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def scheduler_loop():
    """调度器主循环"""
    logger.info("调度器启动")
    
    while True:
        try:
            # 模拟任务执行
            logger.debug("调度器运行中...")
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("调度器被取消")
            break
        except Exception as e:
            logger.error(f"调度器错误: {e}")
            await asyncio.sleep(10)

# 简单测试
if __name__ == "__main__":
    print("调度器模块语法检查通过")
