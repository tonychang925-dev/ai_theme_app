#!/usr/bin/env python3
"""
数据库服务启动脚本
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database_service.gateway import DatabaseGateway
from database_service.config import get_config, init_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    logger.info("🚀 启动数据库服务...")
    
    # 加载配置
    config_path = Path("config/config.yaml")
    if config_path.exists():
        from database_service.config import DatabaseConfig
        config = DatabaseConfig.from_yaml(str(config_path))
        init_config(config)
        logger.info(f"从配置文件加载: {config_path}")
    else:
        config = get_config()
        logger.info("从环境变量加载配置")
    
    logger.info(f"数据库类型: {config.db_type.value}")
    logger.info(f"Redis启用: {config.redis.enabled}")
    
    # 初始化网关
    gateway = None
    try:
        gateway = await DatabaseGateway.initialize(config)
        
        # 健康检查
        healthy = await gateway.health_check()
        if not healthy:
            logger.error("❌ 数据库健康检查失败")
            sys.exit(1)
        
        logger.info("✅ 数据库服务启动成功")
        logger.info("📊 按 Ctrl+C 停止服务")
        
        # 保持运行
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        sys.exit(1)
    finally:
        if gateway:
            await gateway.close()
        logger.info("数据库服务已停止")


def signal_handler(signum, frame):
    """信号处理"""
    logger.info(f"收到信号 {signum}, 准备退出...")
    sys.exit(0)


if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 运行主函数
    asyncio.run(main())
