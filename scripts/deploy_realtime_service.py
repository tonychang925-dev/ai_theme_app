#!/usr/bin/env python3
"""
Redis Stream 实时推送服务部署脚本

验证Redis连接、服务配置，并提供部署指南。
"""
import asyncio
import os
import sys
import logging
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_redis_connection():
    """检查Redis连接"""
    try:
        from redis.asyncio import Redis
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        logger.info(f"尝试连接到Redis: {redis_url}")

        redis_client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=5)

        # 测试连接
        pong = await redis_client.ping()
        if pong:
            logger.info("✅ Redis连接成功")

            # 获取Redis信息
            info = await redis_client.info()
            logger.info(f"Redis版本: {info.get('redis_version', '未知')}")
            logger.info(f"已用内存: {info.get('used_memory_human', '未知')}")

            await redis_client.close()
            return True
        else:
            logger.error("❌ Redis ping失败")
            return False

    except ImportError as e:
        logger.error(f"❌ 缺少Redis依赖: {e}")
        logger.info("请安装依赖: pip install redis")
        return False
    except Exception as e:
        logger.error(f"❌ Redis连接失败: {e}")
        return False


async def check_service_imports():
    """检查服务导入"""
    imports_to_test = [
        ("database_service.streams.realtime_push_service", "RealtimePushService"),
        ("database_service.streams.realtime_push_service", "ConnectionManager"),
        ("frontend_bff.realtime_service", "realtime_service"),
        ("frontend_bff.realtime_service", "FrontendRealtimeService"),
    ]

    all_passed = True
    for module_name, item_name in imports_to_test:
        try:
            exec(f"from {module_name} import {item_name}")
            logger.info(f"✅ 导入成功: {module_name}.{item_name}")
        except ImportError as e:
            logger.error(f"❌ 导入失败: {module_name}.{item_name} - {e}")
            all_passed = False
        except Exception as e:
            logger.error(f"❌ 导入错误: {module_name}.{item_name} - {e}")
            all_passed = False

    return all_passed


def check_environment_variables():
    """检查环境变量"""
    required_vars = ["REDIS_URL"]
    optional_vars = ["REALTIME_SERVICE_ENABLED", "REALTIME_SERVICE_LOG_LEVEL"]

    logger.info("检查环境变量...")

    all_present = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            logger.info(f"✅ {var}={value}")
        else:
            logger.warning(f"⚠️  环境变量缺失: {var}")
            logger.info(f"  默认值将使用: redis://localhost:6379/0")
            all_present = False

    for var in optional_vars:
        value = os.getenv(var)
        if value:
            logger.info(f"✅ {var}={value}")
        else:
            logger.info(f"📝 {var} 未设置，将使用默认值")

    return all_present


def check_app_integration():
    """检查app.py集成"""
    app_path = "frontend_bff/app.py"

    try:
        with open(app_path, "r", encoding="utf-8") as f:
            content = f.read()

        endpoints_to_check = [
            ("@app.websocket", "/ws/realtime"),
            ("@app.get", "/api/realtime/stats"),
            ("@app.get", "/api/realtime/streams"),
            ("realtime_service", "import"),
            ("lifespan", "realtime_service"),
        ]

        all_found = True
        for pattern, description in endpoints_to_check:
            if pattern in content:
                logger.info(f"✅ 在app.py中找到: {description} ({pattern})")
            else:
                logger.warning(f"⚠️  在app.py中未找到: {description} ({pattern})")
                all_found = False

        return all_found

    except FileNotFoundError:
        logger.error(f"❌ 文件不存在: {app_path}")
        return False
    except Exception as e:
        logger.error(f"❌ 检查app.py集成时出错: {e}")
        return False


def generate_deployment_guide():
    """生成部署指南"""
    logger.info("\n" + "="*60)
    logger.info("部署指南")
    logger.info("="*60)

    guide = """
1. 环境要求
   - Python 3.8+
   - Redis 6.0+
   - 依赖包:
     - redis>=4.5.0
     - fastapi>=0.104.0
     - websockets>=12.0

2. 安装依赖
   pip install redis fastapi websockets

3. 启动Redis
   docker run -d -p 6379:6379 redis:latest
   或
   brew services start redis (macOS)

4. 启动Frontend BFF服务
   cd frontend_bff
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload

5. 验证服务
   - WebSocket端点: ws://localhost:8000/ws/realtime
   - 统计接口: http://localhost:8000/api/realtime/stats
   - Stream列表: http://localhost:8000/api/realtime/streams

6. 客户端连接示例
   ```javascript
   const ws = new WebSocket('ws://localhost:8000/ws/realtime');
   ws.onopen = () => {
     ws.send(JSON.stringify({command: 'subscribe', stream: 'stream:event:feed'}));
   };
   ws.onmessage = (event) => {
     console.log('收到消息:', JSON.parse(event.data));
   };
   ```

7. 监控指标
   - 连接数: /api/realtime/stats
   - Redis内存使用: redis-cli info memory
   - Stream长度: redis-cli xlen stream:event:feed

8. 故障排除
   - 检查Redis连接: REDIS_URL环境变量
   - 检查日志: frontend_bff服务日志
   - 验证端口: 确保8000端口未被占用
"""

    print(guide)


async def test_service_initialization():
    """测试服务初始化"""
    try:
        from frontend_bff.realtime_service import realtime_service

        logger.info("测试实时推送服务初始化...")

        # 初始化服务
        await realtime_service.initialize()

        # 检查服务状态
        if realtime_service.is_available():
            logger.info("✅ 实时推送服务可用")
            stats = realtime_service.get_stats()
            logger.info(f"服务统计: {stats}")
        else:
            logger.warning("⚠️  实时推送服务不可用")
            stats = realtime_service.get_stats()
            logger.info(f"服务状态: {stats}")

        # 关闭服务
        await realtime_service.shutdown()
        logger.info("✅ 服务关闭成功")

        return True

    except Exception as e:
        logger.error(f"❌ 服务初始化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主部署验证函数"""
    logger.info("="*60)
    logger.info("Redis Stream 实时推送服务部署验证")
    logger.info("="*60)

    tests = [
        ("环境变量检查", lambda: check_environment_variables()),
        ("Redis连接测试", check_redis_connection),
        ("服务导入检查", check_service_imports),
        ("app.py集成检查", lambda: check_app_integration()),
        ("服务初始化测试", test_service_initialization),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n📋 运行测试: {test_name}")
        try:
            if asyncio.iscoroutinefunction(test_func):
                success = await test_func()
            else:
                success = test_func()
            results.append((test_name, success))
            if success:
                logger.info(f"✅ {test_name} - 通过")
            else:
                logger.warning(f"⚠️  {test_name} - 失败")
        except Exception as e:
            logger.error(f"❌ {test_name} - 异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # 总结
    logger.info("\n" + "="*60)
    logger.info("部署验证结果总结")
    logger.info("="*60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\n总计: {passed}/{total} 个测试通过")

    if passed == total:
        logger.info("🎉 所有部署检查通过！实时推送服务已准备好部署。")
        generate_deployment_guide()
        return 0
    else:
        logger.warning("⚠️  部分部署检查失败，请根据上述日志修复问题。")
        generate_deployment_guide()
        return 1


if __name__ == "__main__":
    # 切换到项目根目录
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 运行部署验证
    exit_code = asyncio.run(main())
    sys.exit(exit_code)