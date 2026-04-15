#!/usr/bin/env python3
"""
实时推送服务验证脚本

验证RealtimePushService和WebSocket集成的基本功能。
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_service_initialization():
    """测试服务初始化"""
    try:
        from realtime_service import realtime_service

        logger.info("测试服务初始化...")

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


async def test_imports():
    """测试所有必要的导入"""
    imports_to_test = [
        ("frontend_bff.realtime_service", "realtime_service"),
        ("database_service.streams.realtime_push_service", "RealtimePushService"),
        ("fastapi", "FastAPI"),
        ("fastapi", "WebSocket"),
        ("redis.asyncio", "Redis"),
    ]

    all_passed = True
    for module_name, item_name in imports_to_test:
        try:
            if item_name:
                exec(f"from {module_name} import {item_name}")
                logger.info(f"✅ 导入成功: {module_name}.{item_name}")
            else:
                exec(f"import {module_name}")
                logger.info(f"✅ 导入成功: {module_name}")
        except ImportError as e:
            logger.error(f"❌ 导入失败: {module_name}.{item_name} - {e}")
            all_passed = False
        except Exception as e:
            logger.error(f"❌ 导入错误: {module_name}.{item_name} - {e}")
            all_passed = False

    return all_passed


async def test_app_integration():
    """测试app.py中的集成"""
    try:
        # 检查app.py中的WebSocket端点定义
        with open("app.py", "r", encoding="utf-8") as f:
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

    except Exception as e:
        logger.error(f"❌ app.py集成测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    logger.info("=" * 60)
    logger.info("实时推送服务验证测试")
    logger.info("=" * 60)

    tests = [
        ("导入测试", test_imports),
        ("app.py集成测试", test_app_integration),
        ("服务初始化测试", test_service_initialization),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n📋 运行测试: {test_name}")
        try:
            success = await test_func()
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
    logger.info("\n" + "=" * 60)
    logger.info("测试结果总结")
    logger.info("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\n总计: {passed}/{total} 个测试通过")

    if passed == total:
        logger.info("🎉 所有测试通过！实时推送服务已准备好集成。")
        return 0
    else:
        logger.warning("⚠️  部分测试失败，需要进一步检查。")
        return 1


if __name__ == "__main__":
    # 切换到脚本所在目录
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 运行测试
    exit_code = asyncio.run(main())
    sys.exit(exit_code)